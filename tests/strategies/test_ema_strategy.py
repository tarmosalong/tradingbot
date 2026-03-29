"""Tests for EMAStrategy (trend-following EMA crossover)."""
from __future__ import annotations

import pandas as pd
import pytest

from backend.config import EMAConfig
from backend.strategies.technical import EMAStrategy


def _make_ohlcv(closes: list[float], n: int = 50) -> pd.DataFrame:
    if len(closes) < n:
        pad = [closes[0]] * (n - len(closes))
        closes = pad + closes
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(closes), freq="h"),
        "open": closes,
        "high": [c + 5 for c in closes],
        "low": [c - 5 for c in closes],
        "close": closes,
        "volume": [100.0] * len(closes),
    })


def _bullish_crossover_data() -> list[float]:
    """Long decline then sharp 5-candle recovery: fast crosses above slow."""
    decline = [200.0 - i * 1.0 for i in range(50)]
    recovery = [decline[-1] + i * 6.0 for i in range(5)]
    return decline + recovery


def _bearish_crossover_data() -> list[float]:
    """Long rise then sharp 5-candle drop: fast crosses below slow."""
    rise = [100.0 + i * 1.0 for i in range(50)]
    drop = [rise[-1] - i * 6.0 for i in range(5)]
    return rise + drop


class TestEMABullishCrossover:
    @pytest.mark.asyncio
    async def test_buy_on_bullish_cross(self):
        ohlcv = _make_ohlcv(_bullish_crossover_data())
        s = EMAStrategy()
        signal = await s.analyze("BTC/USDT", ohlcv)
        assert signal.direction == "BUY"
        assert signal.confidence >= 0.5
        assert "bullish crossover" in signal.reason

    @pytest.mark.asyncio
    async def test_buy_confidence_scales_with_gap(self):
        strong = _bullish_crossover_data()
        strong[-1] += 20.0
        strong[-2] += 10.0
        ohlcv = _make_ohlcv(strong)
        s = EMAStrategy()
        signal = await s.analyze("BTC/USDT", ohlcv)
        assert signal.direction == "BUY"
        assert signal.confidence > 0.55


class TestEMABearishCrossover:
    @pytest.mark.asyncio
    async def test_sell_on_bearish_cross(self):
        ohlcv = _make_ohlcv(_bearish_crossover_data())
        s = EMAStrategy()
        signal = await s.analyze("BTC/USDT", ohlcv)
        assert signal.direction == "SELL"
        assert signal.confidence >= 0.5
        assert "bearish crossover" in signal.reason


class TestEMAHold:
    @pytest.mark.asyncio
    async def test_hold_when_no_crossover(self):
        flat = [100.0 + i * 0.01 for i in range(60)]
        ohlcv = _make_ohlcv(flat)
        s = EMAStrategy()
        signal = await s.analyze("BTC/USDT", ohlcv)
        assert signal.direction == "HOLD"

    @pytest.mark.asyncio
    async def test_hold_on_insufficient_data(self):
        ohlcv = _make_ohlcv([100.0] * 5, n=5)
        s = EMAStrategy()
        signal = await s.analyze("BTC/USDT", ohlcv)
        assert signal.direction == "HOLD"
        assert "Insufficient" in signal.reason


class TestEMAConfig:
    @pytest.mark.asyncio
    async def test_custom_periods(self):
        cfg = EMAConfig(fast_period=5, slow_period=15)
        s = EMAStrategy(cfg)
        ohlcv = _make_ohlcv(_bullish_crossover_data())
        signal = await s.analyze("BTC/USDT", ohlcv)
        assert signal.strategy_name == "ema"
        assert signal.direction in ("BUY", "HOLD", "SELL")

    @pytest.mark.asyncio
    async def test_indicators_present(self):
        ohlcv = _make_ohlcv(_bullish_crossover_data())
        s = EMAStrategy()
        signal = await s.analyze("BTC/USDT", ohlcv)
        assert "ema_fast" in signal.indicators
        assert "ema_slow" in signal.indicators
        assert "ema_gap" in signal.indicators
        assert "ema_gap_atr" in signal.indicators

    @pytest.mark.asyncio
    async def test_name(self):
        s = EMAStrategy()
        assert s.name == "ema"
