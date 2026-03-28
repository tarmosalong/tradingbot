from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import ccxt.async_support as ccxt_async
import pandas as pd

from backend.config import Settings
from backend.core.exceptions import (
    ExchangeError,
    InsufficientFundsError,
    OrderError,
    RateLimitError,
)
from backend.core.logger import get_logger
from backend.exchange.base import ExchangeBase
from backend.models import Order, OrderSide, OrderStatus, OrderType, Ticker

logger = get_logger("binance")


class BinanceClient(ExchangeBase):
    """CCXT async wrapper for Binance."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._exchange = ccxt_async.binance({
            "apiKey": settings.binance_api_key,
            "secret": settings.binance_api_secret,
            "enableRateLimit": True,
            "rateLimit": settings.exchange.rate_limit_ms,
            "options": {"defaultType": "spot"},
        })
        if settings.exchange.sandbox:
            self._exchange.set_sandbox_mode(True)
        self._semaphore = asyncio.Semaphore(5)

    async def _call(self, coro):
        """Execute an exchange call with rate-limit protection."""
        async with self._semaphore:
            try:
                return await coro
            except ccxt_async.InsufficientFunds as e:
                raise InsufficientFundsError(str(e)) from e
            except ccxt_async.RateLimitExceeded as e:
                raise RateLimitError(str(e)) from e
            except ccxt_async.OrderNotFound as e:
                raise OrderError(str(e)) from e
            except ccxt_async.BaseError as e:
                raise ExchangeError(str(e)) from e

    async def get_balance(self) -> dict[str, float]:
        result = await self._call(self._exchange.fetch_balance())
        free: dict = result.get("free", {})
        return {k: v for k, v in free.items() if v and v > 0}

    async def get_ticker(self, symbol: str) -> Ticker:
        data = await self._call(self._exchange.fetch_ticker(symbol))
        return Ticker(
            symbol=symbol,
            bid=float(data.get("bid", 0)),
            ask=float(data.get("ask", 0)),
            last=float(data.get("last", 0)),
            timestamp=datetime.now(UTC),
        )

    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> pd.DataFrame:
        raw = await self._call(
            self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        )
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
    ) -> Order:
        logger.info(
            "Creating order",
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=amount,
            price=price,
        )
        if order_type.upper() == "MARKET":
            raw = await self._call(
                self._exchange.create_order(symbol, "market", side.lower(), amount)
            )
        else:
            if price is None:
                raise OrderError("Limit order requires a price")
            raw = await self._call(
                self._exchange.create_order(symbol, "limit", side.lower(), amount, price)
            )

        return self._parse_order(raw)

    async def cancel_order(self, order_id: str, symbol: str) -> None:
        logger.info("Cancelling order", order_id=order_id, symbol=symbol)
        await self._call(self._exchange.cancel_order(order_id, symbol))

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        raw_list = await self._call(self._exchange.fetch_open_orders(symbol))
        return [self._parse_order(o) for o in raw_list]

    async def close(self) -> None:
        await self._exchange.close()
        logger.info("Binance client closed")

    @staticmethod
    def _parse_order(raw: dict) -> Order:
        side_str = raw.get("side", "buy").upper()
        type_str = raw.get("type", "market").upper()
        status_str = raw.get("status", "open").upper()

        side_map = {"BUY": OrderSide.BUY, "SELL": OrderSide.SELL}
        type_map = {"MARKET": OrderType.MARKET, "LIMIT": OrderType.LIMIT}
        status_map = {
            "OPEN": OrderStatus.OPEN,
            "CLOSED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
        }

        return Order(
            id=str(raw.get("id", "")),
            symbol=raw.get("symbol", ""),
            side=side_map.get(side_str, OrderSide.BUY),
            order_type=type_map.get(type_str, OrderType.MARKET),
            amount=float(raw.get("amount", 0)),
            price=raw.get("price"),
            status=status_map.get(status_str, OrderStatus.OPEN),
            filled_amount=float(raw.get("filled", 0)),
            filled_price=raw.get("average"),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
