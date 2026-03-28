from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.deps import get_database
from backend.config import load_settings

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


class BacktestRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    start: str = "2025-01-01"
    end: str = "2025-12-31"
    balance: float = 10000.0
    strategies: list[str] = ["rsi", "macd", "bollinger"]


@router.post("/backtest")
async def run_backtest(req: BacktestRequest):
    from backend.backtest.data_loader import load_from_binance
    from backend.backtest.engine import BacktestEngine
    from backend.backtest.exchange import BacktestExchange
    from backend.backtest.report import generate_report
    from backend.strategies import STRATEGY_REGISTRY

    settings = load_settings()

    start_dt = datetime.strptime(req.start, "%Y-%m-%d").replace(
        tzinfo=UTC,
    )
    end_dt = datetime.strptime(req.end, "%Y-%m-%d").replace(
        tzinfo=UTC,
    )

    ohlcv = await load_from_binance(
        req.symbol, req.timeframe, start_dt, end_dt,
    )
    if ohlcv.empty:
        return {"error": "No data loaded for the given period"}

    exchange = BacktestExchange(
        ohlcv=ohlcv,
        initial_balance_usdt=req.balance,
        symbol=req.symbol,
    )

    config_map = {
        "rsi": settings.strategies.rsi,
        "macd": settings.strategies.macd,
        "bollinger": settings.strategies.bollinger,
    }
    strats = []
    for name in req.strategies:
        cls = STRATEGY_REGISTRY.get(name)
        if cls:
            cfg = config_map.get(name)
            strats.append(cls(cfg) if cfg else cls())

    if not strats:
        return {"error": "No valid strategies provided"}

    engine = BacktestEngine(
        exchange=exchange,
        strategies=strats,
        symbol=req.symbol,
        risk_config=settings.risk,
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

    return {
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
