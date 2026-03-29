from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.bot_runner import bot_runner
from backend.api.deps import get_database
from backend.config import load_settings
from backend.config_io import patch_paper_dashboard_settings

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/config")
async def get_config():
    settings = load_settings()
    return {
        "mode": settings.trading.mode,
        "pairs": settings.trading.pairs,
        "timeframe": settings.trading.timeframe,
        "poll_interval": settings.trading.poll_interval_seconds,
        "strategies": settings.strategies.enabled,
        "paper_trading": {
            "initial_balance_usdt": settings.paper_trading.initial_balance_usdt,
        },
        "risk": {
            "max_position_pct": settings.risk.max_position_pct,
            "stop_loss_pct": settings.risk.stop_loss_pct,
            "trailing_stop_pct": settings.risk.trailing_stop_pct,
            "max_drawdown_pct": settings.risk.max_drawdown_pct,
            "daily_loss_limit_pct": settings.risk.daily_loss_limit_pct,
            "max_single_order_usdt": settings.risk.max_single_order_usdt,
        },
    }


@router.get("/trades")
async def get_trades(symbol: str | None = None, limit: int = 50):
    db = get_database()
    trades = await db.get_trades(symbol=symbol, limit=limit)
    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side.value,
            "amount": t.amount,
            "price": t.price,
            "fee": t.fee,
            "pnl": t.pnl,
            "executed_at": t.executed_at.isoformat(),
        }
        for t in trades
    ]


@router.get("/orders")
async def get_orders(symbol: str | None = None):
    db = get_database()
    orders = await db.get_open_orders(symbol=symbol)
    return [
        {
            "id": o.id,
            "symbol": o.symbol,
            "side": o.side.value,
            "order_type": o.order_type.value,
            "amount": o.amount,
            "price": o.price,
            "status": o.status.value,
            "filled_amount": o.filled_amount,
            "filled_price": o.filled_price,
            "created_at": o.created_at.isoformat(),
        }
        for o in orders
    ]


@router.get("/portfolio")
async def get_portfolio(limit: int = 100):
    db = get_database()
    history = await db.get_portfolio_history(limit=limit)
    return history


class RSIParams(BaseModel):
    period: int = 14
    oversold: int = 30
    overbought: int = 70


class MACDParams(BaseModel):
    fast: int = 12
    slow: int = 26
    signal: int = 9


class BollingerParams(BaseModel):
    period: int = 20
    std_dev: float = 2.0


class RiskParams(BaseModel):
    max_position_pct: float = 0.10
    stop_loss_pct: float = 0.03
    trailing_stop_pct: float = 0.02
    max_single_order_usdt: float = 1000.0


class AIFilterParams(BaseModel):
    enabled: bool = False
    strength: float = 0.5
    crash_lookback: int = 10
    crash_threshold_pct: float = -5.0
    volatility_multiplier: float = 2.0
    volume_spike_multiplier: float = 2.5
    recovery_boost: float = 1.3


class EngineParams(BaseModel):
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005
    min_confidence: float = 0.0
    cooldown_candles: int = 0
    use_dynamic_sizing: bool = False
    enable_regime_filter: bool = False
    adx_trending_threshold: float = 25.0
    take_profit_pct: float = 0.0
    take_profit_ratio: float = 0.5


class WalkForwardParams(BaseModel):
    enabled: bool = False
    n_folds: int = 3
    train_pct: float = 0.7
    step_type: str = "rolling"


class BacktestRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    start: str = "2025-01-01"
    end: str = "2025-12-31"
    balance: float = 10000.0
    strategies: list[str] = ["rsi", "macd", "bollinger"]
    rsi: RSIParams = RSIParams()
    macd: MACDParams = MACDParams()
    bollinger: BollingerParams = BollingerParams()
    risk: RiskParams = RiskParams()
    ai_filter: AIFilterParams = AIFilterParams()
    engine: EngineParams = EngineParams()
    walk_forward: WalkForwardParams = WalkForwardParams()


@router.post("/backtest")
async def run_backtest(req: BacktestRequest):
    from backend.backtest.data_loader import load_from_binance
    from backend.backtest.engine import BacktestEngine
    from backend.backtest.exchange import BacktestExchange
    from backend.backtest.report import generate_report
    from backend.config import (
        BollingerConfig,
        MACDConfig,
        RiskConfig,
        RSIConfig,
    )
    from backend.strategies import STRATEGY_REGISTRY

    if not req.start or not req.end:
        return {"error": "Start and end dates are required (YYYY-MM-DD)"}

    try:
        start_dt = datetime.strptime(req.start, "%Y-%m-%d").replace(
            tzinfo=UTC,
        )
        end_dt = datetime.strptime(req.end, "%Y-%m-%d").replace(
            tzinfo=UTC,
        )
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}

    ohlcv = await load_from_binance(
        req.symbol, req.timeframe, start_dt, end_dt,
    )
    if ohlcv.empty:
        return {"error": "No data loaded for the given period"}

    exchange = BacktestExchange(
        ohlcv=ohlcv,
        initial_balance_usdt=req.balance,
        symbol=req.symbol,
        fee_rate=req.engine.fee_rate,
        slippage_rate=req.engine.slippage_rate,
    )

    config_map: dict = {
        "rsi": RSIConfig(
            period=req.rsi.period,
            oversold=req.rsi.oversold,
            overbought=req.rsi.overbought,
        ),
        "macd": MACDConfig(
            fast=req.macd.fast,
            slow=req.macd.slow,
            signal=req.macd.signal,
        ),
        "bollinger": BollingerConfig(
            period=req.bollinger.period,
            std_dev=req.bollinger.std_dev,
        ),
    }
    strats = []
    for name in req.strategies:
        cls = STRATEGY_REGISTRY.get(name)
        if cls:
            cfg = config_map.get(name)
            strats.append(cls(cfg) if cfg else cls())

    if not strats:
        return {"error": "No valid strategies provided"}

    risk_config = RiskConfig(
        max_position_pct=req.risk.max_position_pct,
        stop_loss_pct=req.risk.stop_loss_pct,
        trailing_stop_pct=req.risk.trailing_stop_pct,
        max_single_order_usdt=req.risk.max_single_order_usdt,
    )

    from backend.backtest.ai_filter import AIFilterConfig

    ai_config = AIFilterConfig(
        enabled=req.ai_filter.enabled,
        strength=req.ai_filter.strength,
        crash_lookback=req.ai_filter.crash_lookback,
        crash_threshold_pct=req.ai_filter.crash_threshold_pct,
        volatility_multiplier=req.ai_filter.volatility_multiplier,
        volume_spike_multiplier=req.ai_filter.volume_spike_multiplier,
        recovery_boost=req.ai_filter.recovery_boost,
    )

    from backend.backtest.engine import EngineConfig

    engine_cfg = EngineConfig(
        min_confidence=req.engine.min_confidence,
        cooldown_candles=req.engine.cooldown_candles,
        use_dynamic_sizing=req.engine.use_dynamic_sizing,
        enable_regime_filter=req.engine.enable_regime_filter,
        adx_trending_threshold=req.engine.adx_trending_threshold,
        take_profit_pct=req.engine.take_profit_pct,
        take_profit_ratio=req.engine.take_profit_ratio,
    )

    engine = BacktestEngine(
        exchange=exchange,
        strategies=strats,
        symbol=req.symbol,
        risk_config=risk_config,
        ai_filter_config=ai_config,
        engine_config=engine_cfg,
    )

    result = await engine.run()
    report = generate_report(result)

    ohlcv_data = [
        {
            "time": int(row["timestamp"].timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for _, row in ohlcv.iterrows()
    ]

    response: dict = {
        "report": report.to_dict(),
        "equity_curve": result.equity_curve,
        "timestamps": result.timestamps,
        "ohlcv": ohlcv_data,
        "trades": [
            {
                "symbol": bt.trade.symbol,
                "side": bt.trade.side.value if hasattr(bt.trade.side, "value") else bt.trade.side,
                "amount": bt.trade.amount,
                "price": bt.trade.price,
                "executed_at": bt.trade.executed_at.isoformat() if bt.trade.executed_at else "",
                "portfolio_value": bt.portfolio_value,
            }
            for bt in result.trades
        ],
    }

    if req.walk_forward.enabled:
        from backend.backtest.walk_forward import (
            WalkForwardConfig,
            run_walk_forward,
        )

        wf_config = WalkForwardConfig(
            n_folds=req.walk_forward.n_folds,
            train_pct=req.walk_forward.train_pct,
            step_type=req.walk_forward.step_type,
        )
        wf_result = await run_walk_forward(
            ohlcv=ohlcv,
            symbol=req.symbol,
            balance=req.balance,
            strategies=strats,
            risk_config=risk_config,
            ai_filter_config=ai_config,
            engine_config=engine_cfg,
            wf_config=wf_config,
            fee_rate=req.engine.fee_rate,
            slippage_rate=req.engine.slippage_rate,
        )
        response["walk_forward"] = wf_result.to_dict()

    return response


class PaperBotSettingsPatch(BaseModel):
    initial_balance_usdt: float | None = None
    pairs: list[str] | None = None
    timeframe: str | None = None
    poll_interval_seconds: int | None = None
    strategies: list[str] | None = None


@router.get("/bot/status")
async def bot_status():
    return bot_runner.status_dict()


@router.post("/bot/start")
async def bot_start():
    if not bot_runner.status_dict()["control_enabled"]:
        raise HTTPException(status_code=403, detail="Bot control disabled")
    try:
        await bot_runner.start()
    except RuntimeError as e:
        msg = str(e)
        code = 409 if "already" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg) from e
    return {"ok": True, **bot_runner.status_dict()}


@router.post("/bot/stop")
async def bot_stop():
    await bot_runner.stop()
    return {"ok": True, **bot_runner.status_dict()}


@router.patch("/bot/settings")
async def bot_patch_settings(body: PaperBotSettingsPatch):
    if bot_runner.state != "stopped":
        raise HTTPException(
            status_code=409,
            detail="Stop the bot before changing settings",
        )
    try:
        patch_paper_dashboard_settings(
            initial_balance_usdt=body.initial_balance_usdt,
            pairs=body.pairs,
            timeframe=body.timeframe,
            poll_interval_seconds=body.poll_interval_seconds,
            strategies_enabled=body.strategies,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    settings = load_settings()
    return {
        "ok": True,
        "mode": settings.trading.mode,
        "pairs": settings.trading.pairs,
        "timeframe": settings.trading.timeframe,
        "poll_interval": settings.trading.poll_interval_seconds,
        "strategies": settings.strategies.enabled,
        "paper_trading": {
            "initial_balance_usdt": settings.paper_trading.initial_balance_usdt,
        },
    }
