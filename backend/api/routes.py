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
            "initial_balance_usdt": (
                settings.paper_trading.initial_balance_usdt
            ),
        },
        "risk": {
            "max_position_pct": settings.risk.max_position_pct,
            "stop_loss_pct": settings.risk.stop_loss_pct,
            "trailing_stop_pct": settings.risk.trailing_stop_pct,
            "max_drawdown_pct": settings.risk.max_drawdown_pct,
            "daily_loss_limit_pct": settings.risk.daily_loss_limit_pct,
            "max_single_order_usdt": settings.risk.max_single_order_usdt,
            "min_confidence": settings.risk.min_confidence,
            "max_concurrent_positions": settings.risk.max_concurrent_positions,
            "max_data_age_seconds": settings.risk.max_data_age_seconds,
            "max_price_deviation_pct": settings.risk.max_price_deviation_pct,
            "circuit_breaker_threshold": settings.risk.circuit_breaker_threshold,
            "atr_stop_multiplier": settings.risk.atr_stop_multiplier,
            "atr_tp_multiplier": settings.risk.atr_tp_multiplier,
            "atr_trailing_multiplier": settings.risk.atr_trailing_multiplier,
            "volume_min_multiplier": settings.risk.volume_min_multiplier,
            "ema_trend_period": settings.risk.ema_trend_period,
            "ema_trend_enabled": settings.risk.ema_trend_enabled,
            "risk_per_trade_pct": settings.risk.risk_per_trade_pct,
            "partial_tp_ratio": settings.risk.partial_tp_ratio,
        },
        "strategy_weights": settings.strategies.weights,
        "strategy_params": {
            "rsi": {
                "period": settings.strategies.rsi.period,
                "oversold": settings.strategies.rsi.oversold,
                "overbought": settings.strategies.rsi.overbought,
            },
            "macd": {
                "fast": settings.strategies.macd.fast,
                "slow": settings.strategies.macd.slow,
                "signal": settings.strategies.macd.signal,
            },
            "bollinger": {
                "period": settings.strategies.bollinger.period,
                "std_dev": settings.strategies.bollinger.std_dev,
            },
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


@router.get("/signals")
async def get_signals(
    symbol: str | None = None,
    strategy: str | None = None,
    limit: int = 50,
):
    db = get_database()
    return await db.get_signals(symbol=symbol, strategy=strategy, limit=limit)


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


class EMAParams(BaseModel):
    fast_period: int = 9
    slow_period: int = 21


class RiskParams(BaseModel):
    max_position_pct: float = 0.10
    stop_loss_pct: float = 0.03
    trailing_stop_pct: float = 0.02
    max_single_order_usdt: float = 1000.0
    max_drawdown_pct: float = 0.15
    daily_loss_limit_pct: float = 0.05
    min_confidence: float = 0.4
    atr_stop_multiplier: float = 2.0
    atr_tp_multiplier: float = 3.0
    atr_trailing_multiplier: float = 1.5
    volume_min_multiplier: float = 1.2
    ema_trend_period: int = 50
    ema_trend_enabled: bool = True
    risk_per_trade_pct: float = 0.01
    partial_tp_ratio: float = 0.5


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


class RegimeParams(BaseModel):
    enabled: bool = False
    adx_period: int = 14
    trending_threshold: float = 25.0
    hysteresis_buffer: float = 5.0
    volatile_atr_percentile: float = 80.0
    atr_lookback: int = 100
    trending_ema_weight: float = 1.5
    trending_mr_weight: float = 0.2
    ranging_ema_weight: float = 0.2
    ranging_mr_weight: float = 1.2


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
    strategy_weights: dict[str, float] = {}
    rsi: RSIParams = RSIParams()
    macd: MACDParams = MACDParams()
    bollinger: BollingerParams = BollingerParams()
    ema: EMAParams = EMAParams()
    risk: RiskParams = RiskParams()
    ai_filter: AIFilterParams = AIFilterParams()
    engine: EngineParams = EngineParams()
    walk_forward: WalkForwardParams = WalkForwardParams()
    regime: RegimeParams = RegimeParams()
    min_agreement: int = 1
    hold_opposition: float = 0.0


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

    from backend.config import EMAConfig

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
        "ema": EMAConfig(
            fast_period=req.ema.fast_period,
            slow_period=req.ema.slow_period,
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
        max_drawdown_pct=req.risk.max_drawdown_pct,
        daily_loss_limit_pct=req.risk.daily_loss_limit_pct,
        min_confidence=req.risk.min_confidence,
        atr_stop_multiplier=req.risk.atr_stop_multiplier,
        atr_tp_multiplier=req.risk.atr_tp_multiplier,
        atr_trailing_multiplier=req.risk.atr_trailing_multiplier,
        volume_min_multiplier=req.risk.volume_min_multiplier,
        ema_trend_period=req.risk.ema_trend_period,
        ema_trend_enabled=req.risk.ema_trend_enabled,
        risk_per_trade_pct=req.risk.risk_per_trade_pct,
        partial_tp_ratio=req.risk.partial_tp_ratio,
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
    from backend.config import RegimeConfig

    engine_cfg = EngineConfig(
        min_confidence=req.engine.min_confidence,
        cooldown_candles=req.engine.cooldown_candles,
        use_dynamic_sizing=req.engine.use_dynamic_sizing,
        enable_regime_filter=req.engine.enable_regime_filter,
        adx_trending_threshold=req.engine.adx_trending_threshold,
        take_profit_pct=req.engine.take_profit_pct,
        take_profit_ratio=req.engine.take_profit_ratio,
    )

    regime_cfg = RegimeConfig(
        enabled=req.regime.enabled,
        adx_period=req.regime.adx_period,
        trending_threshold=req.regime.trending_threshold,
        hysteresis_buffer=req.regime.hysteresis_buffer,
        volatile_atr_percentile=req.regime.volatile_atr_percentile,
        atr_lookback=req.regime.atr_lookback,
        trending_weights={
            "ema": req.regime.trending_ema_weight,
            "rsi": req.regime.trending_mr_weight,
            "macd": req.regime.trending_mr_weight,
            "bollinger": req.regime.trending_mr_weight,
        },
        ranging_weights={
            "ema": req.regime.ranging_ema_weight,
            "rsi": req.regime.ranging_mr_weight,
            "macd": req.regime.ranging_mr_weight,
            "bollinger": req.regime.ranging_mr_weight,
        },
    )

    engine = BacktestEngine(
        exchange=exchange,
        strategies=strats,
        symbol=req.symbol,
        risk_config=risk_config,
        ai_filter_config=ai_config,
        engine_config=engine_cfg,
        strategy_weights=req.strategy_weights or None,
        min_agreement=req.min_agreement,
        hold_opposition=req.hold_opposition,
        regime_config=regime_cfg,
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
            strategy_weights=req.strategy_weights or None,
            min_agreement=req.min_agreement,
            hold_opposition=req.hold_opposition,
            regime_config=regime_cfg,
        )
        response["walk_forward"] = wf_result.to_dict()

    return response


@router.get("/ohlcv")
async def get_ohlcv(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    limit: int = 100,
):
    """Return OHLCV candle data directly from Binance."""
    from backend.config import Settings
    from backend.exchange.binance_client import BinanceClient

    settings = load_settings()
    client = BinanceClient(
        Settings(
            trading=settings.trading,
            exchange=settings.exchange,
            paper_trading=settings.paper_trading,
            strategies=settings.strategies,
            ai=settings.ai,
            risk=settings.risk,
            binance_api_key="",
            binance_api_secret="",
            anthropic_api_key="",
            log_level=settings.log_level,
        )
    )
    try:
        df = await client.get_ohlcv(symbol, timeframe, limit)
    finally:
        await client.close()

    return [
        {
            "time": int(row["timestamp"].timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for _, row in df.iterrows()
    ]


class RSIPatch(BaseModel):
    period: int | None = None
    oversold: int | None = None
    overbought: int | None = None


class MACDPatch(BaseModel):
    fast: int | None = None
    slow: int | None = None
    signal: int | None = None


class BollingerPatch(BaseModel):
    period: int | None = None
    std_dev: float | None = None


class RiskPatch(BaseModel):
    max_position_pct: float | None = None
    stop_loss_pct: float | None = None
    trailing_stop_pct: float | None = None
    max_drawdown_pct: float | None = None
    daily_loss_limit_pct: float | None = None
    max_single_order_usdt: float | None = None
    min_confidence: float | None = None
    max_concurrent_positions: int | None = None
    max_data_age_seconds: int | None = None
    max_price_deviation_pct: float | None = None
    circuit_breaker_threshold: int | None = None
    atr_stop_multiplier: float | None = None
    atr_tp_multiplier: float | None = None
    atr_trailing_multiplier: float | None = None
    volume_min_multiplier: float | None = None
    ema_trend_period: int | None = None
    ema_trend_enabled: bool | None = None
    risk_per_trade_pct: float | None = None
    partial_tp_ratio: float | None = None


class PaperBotSettingsPatch(BaseModel):
    initial_balance_usdt: float | None = None
    pairs: list[str] | None = None
    timeframe: str | None = None
    poll_interval_seconds: int | None = None
    strategies: list[str] | None = None
    rsi: RSIPatch | None = None
    macd: MACDPatch | None = None
    bollinger: BollingerPatch | None = None
    risk: RiskPatch | None = None
    strategy_weights: dict[str, float] | None = None


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


@router.get("/bot/positions")
async def bot_positions():
    positions = await bot_runner.get_positions()

    if not positions:
        positions = await _positions_from_db()

    settings = load_settings()
    risk = settings.risk
    return {
        "positions": positions,
        "risk_config": {
            "stop_loss_pct": risk.stop_loss_pct,
            "trailing_stop_pct": risk.trailing_stop_pct,
        },
        "exit_rules": [
            {
                "name": "ATR stop-loss",
                "description": (
                    f"ATR \u00d7 {risk.atr_stop_multiplier:.1f} below entry"
                    f" (fallback: {risk.stop_loss_pct*100:.1f}% fixed)"
                ),
                "active": True,
            },
            {
                "name": "ATR trailing stop",
                "description": (
                    f"ATR \u00d7 {risk.atr_trailing_multiplier:.1f} below peak"
                    f" (fallback: {risk.trailing_stop_pct*100:.1f}% fixed)"
                ),
                "active": True,
            },
            {
                "name": "Take-profit",
                "description": (
                    f"ATR \u00d7 {risk.atr_tp_multiplier:.1f} above entry"
                    f" ({risk.partial_tp_ratio:.0%} partial, rest trails)"
                ),
                "active": risk.atr_tp_multiplier > 0,
            },
            {
                "name": "Strategy signal",
                "description": (
                    "Sell when RSI \u2265 70 (overbought),"
                    " bearish MACD crossover, or price"
                    " above upper Bollinger band"
                ),
                "active": True,
            },
        ],
    }


async def _positions_from_db() -> list[dict]:
    """Reconstruct positions from trade history (survives restarts)."""
    db = get_database()
    if db is None:
        return []

    settings = load_settings()
    sl_pct = settings.risk.stop_loss_pct
    ts_pct = settings.risk.trailing_stop_pct

    raw = await db.get_net_positions()
    result = []
    for p in raw:
        from backend.core.engine import OpenPosition

        pos = OpenPosition(
            symbol=p["symbol"],
            amount=p["amount"],
            entry_price=p["entry_price"],
            peak_price=p["peak_price"],
            opened_at=datetime.fromisoformat(p["opened_at"]),
        )
        pos.set_risk(sl_pct, ts_pct)

        try:
            from backend.exchange.binance_client import BinanceClient

            settings_for_price = load_settings()
            client = BinanceClient(settings_for_price)
            ticker = await client.get_ticker(p["symbol"])
            current_price = ticker.last
            await client.close()
        except Exception:
            current_price = p["entry_price"]

        if current_price > pos.peak_price:
            pos.peak_price = current_price

        result.append(pos.to_dict(current_price))
    return result


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
            rsi_params=(
                body.rsi.model_dump(exclude_none=True) if body.rsi else None
            ),
            macd_params=(
                body.macd.model_dump(exclude_none=True)
                if body.macd
                else None
            ),
            bollinger_params=(
                body.bollinger.model_dump(exclude_none=True)
                if body.bollinger
                else None
            ),
            risk_params=(
                body.risk.model_dump(exclude_none=True)
                if body.risk
                else None
            ),
            strategy_weights=body.strategy_weights,
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


# ---- Parameter Optimizer ----


class OptimizeRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    start: str = "2025-01-01"
    end: str = "2025-06-30"
    balance: float = 10000.0
    strategies: list[str] = ["rsi", "macd", "bollinger"]
    n_trials: int = 50
    scoring: str = "sharpe"
    tune_groups: list[str] = [
        "strategy", "risk", "atr", "guards", "engine",
    ]
    validate_best: bool = True
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005


@router.post("/optimize")
async def run_optimize(req: OptimizeRequest):
    from backend.backtest.data_loader import load_from_binance
    from backend.backtest.optimizer import run_optimization

    if not req.start or not req.end:
        return {"error": "Start and end dates are required"}

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

    try:
        result = await run_optimization(
            ohlcv=ohlcv,
            symbol=req.symbol,
            balance=req.balance,
            strategy_names=req.strategies,
            tune_groups=req.tune_groups,
            n_trials=req.n_trials,
            scoring=req.scoring,
            fee_rate=req.fee_rate,
            slippage_rate=req.slippage_rate,
            validate_best=req.validate_best,
        )
        return result.to_dict()
    except ValueError as e:
        return {"error": str(e)}
