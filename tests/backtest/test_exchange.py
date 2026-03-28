from __future__ import annotations

import pandas as pd
import pytest

from backend.backtest.exchange import BacktestExchange
from backend.core.exceptions import InsufficientFundsError


def _sample_ohlcv(n: int = 60) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC"),
        "open": [65000.0 + i * 10 for i in range(n)],
        "high": [65200.0 + i * 10 for i in range(n)],
        "low": [64800.0 + i * 10 for i in range(n)],
        "close": [65100.0 + i * 10 for i in range(n)],
        "volume": [100.0] * n,
    })


class TestBacktestExchange:
    def test_initial_state(self):
        ex = BacktestExchange(_sample_ohlcv(), initial_balance_usdt=10000.0)

        assert ex.current_index == 0
        assert ex.total_candles == 60
        assert not ex.is_finished

    def test_advance_moves_index(self):
        ex = BacktestExchange(_sample_ohlcv(n=5))

        assert ex.advance()
        assert ex.current_index == 1
        assert ex.advance()
        assert ex.current_index == 2

    def test_advance_returns_false_at_end(self):
        ex = BacktestExchange(_sample_ohlcv(n=3))

        assert ex.advance()
        assert ex.advance()
        assert not ex.advance()
        assert ex.is_finished

    async def test_get_balance(self):
        ex = BacktestExchange(_sample_ohlcv(), initial_balance_usdt=5000.0)
        balance = await ex.get_balance()

        assert balance["USDT"] == 5000.0

    async def test_get_ticker_uses_current_candle(self):
        ex = BacktestExchange(_sample_ohlcv())
        ticker = await ex.get_ticker("BTC/USDT")

        assert ticker.last == 65100.0

        ex.advance()
        ticker2 = await ex.get_ticker("BTC/USDT")
        assert ticker2.last == 65110.0

    async def test_get_ohlcv_returns_history_up_to_current(self):
        ex = BacktestExchange(_sample_ohlcv(n=10))
        for _ in range(4):
            ex.advance()

        ohlcv = await ex.get_ohlcv("BTC/USDT", limit=100)
        assert len(ohlcv) == 5

    async def test_buy_order_updates_balances(self):
        ex = BacktestExchange(
            _sample_ohlcv(), initial_balance_usdt=100000.0,
        )
        order = await ex.create_order(
            "BTC/USDT", "BUY", "MARKET", 0.1,
        )

        assert order.filled_amount == 0.1
        balance = await ex.get_balance()
        assert balance["BTC"] == pytest.approx(0.1)
        assert balance["USDT"] < 100000.0

    async def test_sell_order_updates_balances(self):
        ex = BacktestExchange(
            _sample_ohlcv(), initial_balance_usdt=100000.0,
        )
        await ex.create_order("BTC/USDT", "BUY", "MARKET", 0.1)
        await ex.create_order("BTC/USDT", "SELL", "MARKET", 0.1)

        balance = await ex.get_balance()
        assert balance.get("BTC", 0.0) == pytest.approx(0.0, abs=1e-10)

    async def test_insufficient_funds_buy(self):
        ex = BacktestExchange(_sample_ohlcv(), initial_balance_usdt=1.0)

        with pytest.raises(InsufficientFundsError):
            await ex.create_order("BTC/USDT", "BUY", "MARKET", 1.0)

    async def test_insufficient_funds_sell(self):
        ex = BacktestExchange(_sample_ohlcv())

        with pytest.raises(InsufficientFundsError):
            await ex.create_order("BTC/USDT", "SELL", "MARKET", 1.0)

    async def test_portfolio_value(self):
        ex = BacktestExchange(
            _sample_ohlcv(), initial_balance_usdt=10000.0,
        )
        value = await ex.get_portfolio_value()
        assert value == 10000.0

    async def test_empty_ohlcv_raises(self):
        with pytest.raises(ValueError, match="not be empty"):
            BacktestExchange(pd.DataFrame())
