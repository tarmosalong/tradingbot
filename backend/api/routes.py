from __future__ import annotations

from fastapi import APIRouter

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
