from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pandas as pd

from backend.config import Settings
from backend.core.exceptions import InsufficientFundsError, OrderError
from backend.core.logger import get_logger
from backend.exchange.base import ExchangeBase
from backend.exchange.binance_client import BinanceClient
from backend.models import Order, OrderSide, OrderStatus, OrderType, Ticker

logger = get_logger("paper_exchange")


class PaperExchange(ExchangeBase):
    """Simulated exchange using real market prices from Binance public endpoints."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._balances: dict[str, float] = {
            "USDT": settings.paper_trading.initial_balance_usdt,
        }
        self._orders: dict[str, Order] = {}
        self._price_feed = BinanceClient(
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

    async def get_balance(self) -> dict[str, float]:
        return {k: v for k, v in self._balances.items() if v > 0}

    async def get_ticker(self, symbol: str) -> Ticker:
        return await self._price_feed.get_ticker(symbol)

    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> pd.DataFrame:
        return await self._price_feed.get_ohlcv(symbol, timeframe, limit)

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
    ) -> Order:
        ticker = await self.get_ticker(symbol)
        fill_price = price if price and order_type.upper() == "LIMIT" else ticker.last

        base, quote = symbol.split("/")
        cost = amount * fill_price

        if side.upper() == "BUY":
            available = self._balances.get(quote, 0.0)
            if available < cost:
                raise InsufficientFundsError(
                    f"Need {cost:.2f} {quote} but only have {available:.2f}"
                )
            self._balances[quote] = available - cost
            self._balances[base] = self._balances.get(base, 0.0) + amount
        elif side.upper() == "SELL":
            available = self._balances.get(base, 0.0)
            if available < amount:
                raise InsufficientFundsError(
                    f"Need {amount} {base} but only have {available}"
                )
            self._balances[base] = available - amount
            self._balances[quote] = self._balances.get(quote, 0.0) + cost
        else:
            raise OrderError(f"Unknown side: {side}")

        now = datetime.now(UTC)
        order = Order(
            id=str(uuid.uuid4()),
            symbol=symbol,
            side=OrderSide(side.upper()),
            order_type=OrderType(order_type.upper()),
            amount=amount,
            price=fill_price,
            status=OrderStatus.FILLED,
            filled_amount=amount,
            filled_price=fill_price,
            created_at=now,
            updated_at=now,
        )
        self._orders[order.id] = order

        logger.info(
            "Paper order filled",
            order_id=order.id,
            symbol=symbol,
            side=side,
            amount=amount,
            price=fill_price,
        )
        return order

    async def cancel_order(self, order_id: str, symbol: str) -> None:
        order = self._orders.get(order_id)
        if not order:
            raise OrderError(f"Order {order_id} not found")
        if order.status != OrderStatus.OPEN:
            raise OrderError(f"Cannot cancel order in status {order.status}")
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.now(UTC)

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        orders = [o for o in self._orders.values() if o.status == OrderStatus.OPEN]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    async def close(self) -> None:
        await self._price_feed.close()
        logger.info("Paper exchange closed")
