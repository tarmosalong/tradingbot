from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from backend.models import Order, Ticker


class ExchangeBase(ABC):
    """Abstract interface every exchange client must implement."""

    @abstractmethod
    async def get_balance(self) -> dict[str, float]:
        """Return available balances keyed by currency (e.g. {"USDT": 9500.0, "BTC": 0.1})."""
        ...

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """Return current bid/ask/last for a symbol."""
        ...

    @abstractmethod
    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> pd.DataFrame:
        """Return OHLCV DataFrame with columns: timestamp, open, high, low, close, volume."""
        ...

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
    ) -> Order:
        """Place an order and return the Order object."""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> None:
        """Cancel an open order."""
        ...

    @abstractmethod
    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        """Return all open orders, optionally filtered by symbol."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up connections and resources."""
        ...
