from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from backend.config import Settings, load_settings
from backend.exchange.base import ExchangeBase
from backend.models import Order, OrderSide, OrderStatus, OrderType, Ticker


@pytest.fixture
def settings() -> Settings:
    return load_settings()


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Realistic BTC/USDT 1h OHLCV data (20 candles)."""
    base_ts = datetime(2026, 3, 1, tzinfo=UTC)
    rows = []
    price = 65000.0
    for i in range(20):
        o = price + (i % 3 - 1) * 100
        h = o + 200
        low = o - 150
        c = o + (i % 5 - 2) * 50
        vol = 100.0 + i * 10
        ts = base_ts.replace(hour=i % 24)
        rows.append([ts, o, h, low, c, vol])
        price = c
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])


@pytest.fixture
def mock_exchange() -> ExchangeBase:
    """AsyncMock implementing ExchangeBase interface."""
    exchange = AsyncMock(spec=ExchangeBase)
    exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.1}
    exchange.get_ticker.return_value = Ticker(
        symbol="BTC/USDT", bid=65000.0, ask=65010.0, last=65005.0
    )
    exchange.create_order.return_value = Order(
        id="mock-order-1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        amount=0.01,
        price=65005.0,
        status=OrderStatus.FILLED,
        filled_amount=0.01,
        filled_price=65005.0,
    )
    exchange.get_open_orders.return_value = []
    return exchange
