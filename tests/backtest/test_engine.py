from __future__ import annotations

import pandas as pd

from backend.backtest.engine import BacktestEngine
from backend.backtest.exchange import BacktestExchange
from backend.config import RiskConfig
from backend.strategies.technical import RSIStrategy


def _trending_ohlcv(n: int = 100) -> pd.DataFrame:
    """Generate trending data: down then up to trigger RSI signals."""
    closes = []
    for i in range(n):
        if i < 40:
            closes.append(65000.0 - i * 200)
        elif i < 70:
            closes.append(closes[-1] + 300)
        else:
            closes.append(closes[-1] - 100)

    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC"),
        "open": closes,
        "high": [c + 50 for c in closes],
        "low": [c - 50 for c in closes],
        "close": closes,
        "volume": [100.0] * n,
    })


def _flat_ohlcv(n: int = 60) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC"),
        "open": [65000.0] * n,
        "high": [65050.0] * n,
        "low": [64950.0] * n,
        "close": [65000.0] * n,
        "volume": [100.0] * n,
    })


class TestBacktestEngine:
    async def test_runs_to_completion(self):
        ohlcv = _flat_ohlcv(n=60)
        exchange = BacktestExchange(ohlcv, initial_balance_usdt=10000.0)
        strategy = RSIStrategy()

        engine = BacktestEngine(
            exchange=exchange,
            strategies=[strategy],
            symbol="BTC/USDT",
        )
        result = await engine.run()

        assert result.initial_balance == 10000.0
        assert result.final_balance > 0
        assert len(result.equity_curve) > 0
        assert len(result.timestamps) == len(result.equity_curve)

    async def test_trending_data_produces_trades(self):
        ohlcv = _trending_ohlcv(n=100)
        exchange = BacktestExchange(
            ohlcv, initial_balance_usdt=10000.0,
        )
        strategy = RSIStrategy()

        engine = BacktestEngine(
            exchange=exchange,
            strategies=[strategy],
            symbol="BTC/USDT",
        )
        result = await engine.run()

        assert len(result.trades) > 0

    async def test_equity_curve_length_matches_candles(self):
        n = 50
        ohlcv = _flat_ohlcv(n=n)
        exchange = BacktestExchange(ohlcv)
        strategy = RSIStrategy()

        engine = BacktestEngine(
            exchange=exchange,
            strategies=[strategy],
            symbol="BTC/USDT",
        )
        result = await engine.run()

        assert len(result.equity_curve) == n + 1

    async def test_risk_config_respected(self):
        ohlcv = _trending_ohlcv(n=100)
        exchange = BacktestExchange(
            ohlcv, initial_balance_usdt=10000.0,
        )
        risk = RiskConfig(
            max_position_pct=0.05,
            max_single_order_usdt=500.0,
        )
        engine = BacktestEngine(
            exchange=exchange,
            strategies=[RSIStrategy()],
            symbol="BTC/USDT",
            risk_config=risk,
        )
        result = await engine.run()

        for bt in result.trades:
            if bt.trade.side == "BUY":
                cost = bt.trade.amount * bt.trade.price
                assert cost <= 500.0 + 1.0
