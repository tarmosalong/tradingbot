from __future__ import annotations

import uuid

import pandas as pd

from backend.core.exceptions import InsufficientFundsError, OrderError
from backend.core.logger import get_logger
from backend.exchange.base import ExchangeBase
from backend.models import Order, OrderSide, OrderStatus, OrderType, Ticker

logger = get_logger("backtest_exchange")


class BacktestExchange(ExchangeBase):
    """Simulated exchange that replays pre-loaded historical OHLCV data.

    Call `advance()` to move the clock forward one candle at a time.
    All price lookups use the current candle's data.
    """

    def __init__(
        self,
        ohlcv: pd.DataFrame,
        initial_balance_usdt: float = 10_000.0,
        symbol: str = "BTC/USDT",
    ) -> None:
        if ohlcv.empty:
            raise ValueError("OHLCV data must not be empty")

        self._ohlcv = ohlcv.reset_index(drop=True)
        self._symbol = symbol
        self._index = 0
        self._balances: dict[str, float] = {"USDT": initial_balance_usdt}
        self._orders: dict[str, Order] = {}

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def total_candles(self) -> int:
        return len(self._ohlcv)

    @property
    def is_finished(self) -> bool:
        return self._index >= len(self._ohlcv) - 1

    def advance(self) -> bool:
        """Move to the next candle. Returns False if at the end."""
        if self.is_finished:
            return False
        self._index += 1
        return True

    def _current_row(self) -> pd.Series:
        return self._ohlcv.iloc[self._index]

    async def get_balance(self) -> dict[str, float]:
        return {k: v for k, v in self._balances.items() if v > 0}

    async def get_ticker(self, symbol: str) -> Ticker:
        row = self._current_row()
        close = float(row["close"])
        return Ticker(
            symbol=symbol,
            bid=close,
            ask=close,
            last=close,
            timestamp=pd.Timestamp(row["timestamp"]).to_pydatetime(),
        )

    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> pd.DataFrame:
        end = self._index + 1
        start = max(0, end - limit)
        return self._ohlcv.iloc[start:end].copy()

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
    ) -> Order:
        row = self._current_row()
        fill_price = price if price and order_type.upper() == "LIMIT" else float(row["close"])

        base, quote = symbol.split("/")
        cost = amount * fill_price

        if side.upper() == "BUY":
            available = self._balances.get(quote, 0.0)
            if available < cost:
                raise InsufficientFundsError(
                    f"Need {cost:.2f} {quote}, have {available:.2f}"
                )
            self._balances[quote] = available - cost
            self._balances[base] = self._balances.get(base, 0.0) + amount
        elif side.upper() == "SELL":
            available = self._balances.get(base, 0.0)
            if available < amount:
                raise InsufficientFundsError(
                    f"Need {amount} {base}, have {available}"
                )
            self._balances[base] = available - amount
            self._balances[quote] = self._balances.get(quote, 0.0) + cost
        else:
            raise OrderError(f"Unknown side: {side}")

        ts = pd.Timestamp(row["timestamp"]).to_pydatetime()
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
            created_at=ts,
            updated_at=ts,
        )
        self._orders[order.id] = order
        return order

    async def cancel_order(self, order_id: str, symbol: str) -> None:
        order = self._orders.get(order_id)
        if not order:
            raise OrderError(f"Order {order_id} not found")
        order.status = OrderStatus.CANCELLED

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        orders = [o for o in self._orders.values() if o.status == OrderStatus.OPEN]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    async def close(self) -> None:
        pass

    async def get_portfolio_value(self, quote: str = "USDT") -> float:
        """Calculate total portfolio value in the quote currency."""
        total = self._balances.get(quote, 0.0)
        row = self._current_row()
        close = float(row["close"])
        for currency, amount in self._balances.items():
            if currency != quote and amount > 0:
                total += amount * close
        return total
