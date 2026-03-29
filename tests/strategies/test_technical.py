from __future__ import annotations

import numpy as np
import pandas as pd

from backend.config import BollingerConfig, MACDConfig, RSIConfig
from backend.strategies.technical import (
    BollingerStrategy,
    MACDStrategy,
    RSIStrategy,
)


def _make_ohlcv(closes: list[float], n: int = 50) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from a list of close prices."""
    if len(closes) < n:
        pad = [closes[0]] * (n - len(closes))
        closes = pad + closes
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(closes), freq="h"),
        "open": closes,
        "high": [c + 10 for c in closes],
        "low": [c - 10 for c in closes],
        "close": closes,
        "volume": [100.0] * len(closes),
    })


def _trending_down(start: float = 70000, drop: float = 15000, n: int = 60) -> list[float]:
    """Generate a strong downtrend to push RSI into oversold territory."""
    return [start - (drop * i / n) for i in range(n)]


def _trending_up(start: float = 55000, rise: float = 15000, n: int = 60) -> list[float]:
    """Generate a strong uptrend to push RSI into overbought territory."""
    return [start + (rise * i / n) for i in range(n)]


def _macd_bullish_crossover() -> list[float]:
    """Flat → slow decline → big recovery candle at end: hist flips neg→pos."""
    prices = [65000.0 + (i % 3) * 5 for i in range(50)]
    prices += [65000.0 - (i + 1) * 100 for i in range(48)]
    prices.append(prices[-1] + 3000)
    return prices


def _macd_bearish_crossover() -> list[float]:
    """Flat → slow rise → big drop candle at end: hist flips pos→neg."""
    prices = [65000.0 + (i % 3) * 5 for i in range(50)]
    prices += [65000.0 + (i + 1) * 100 for i in range(48)]
    prices.append(prices[-1] - 3000)
    return prices


class TestRSIStrategy:
    async def test_oversold_returns_buy(self):
        closes = _trending_down()
        ohlcv = _make_ohlcv(closes, n=len(closes))
        strategy = RSIStrategy(RSIConfig(period=14, oversold=30, overbought=70))

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "BUY"
        assert signal.confidence >= 0.5
        assert "rsi" in signal.indicators
        assert signal.indicators["rsi"] < 30

    async def test_overbought_returns_sell(self):
        closes = _trending_up()
        ohlcv = _make_ohlcv(closes, n=len(closes))
        strategy = RSIStrategy(RSIConfig(period=14, oversold=30, overbought=70))

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "SELL"
        assert signal.confidence >= 0.5
        assert signal.indicators["rsi"] > 70

    async def test_neutral_returns_hold(self):
        closes = [65000 + (i % 5) * 10 for i in range(60)]
        ohlcv = _make_ohlcv(closes, n=len(closes))
        strategy = RSIStrategy()

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "HOLD"

    async def test_hold_has_graduated_confidence(self):
        closes = [65000 + (i % 5) * 10 for i in range(60)]
        ohlcv = _make_ohlcv(closes, n=len(closes))
        strategy = RSIStrategy()

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "HOLD"
        assert 0 <= signal.confidence <= 0.45
        assert "pts from" in signal.reason

    async def test_insufficient_data_returns_hold(self):
        ohlcv = _make_ohlcv([65000.0] * 5, n=5)
        strategy = RSIStrategy()

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "HOLD"
        assert "Insufficient" in signal.reason


class TestMACDStrategy:
    async def test_bullish_crossover_returns_buy(self):
        closes = _macd_bullish_crossover()
        ohlcv = _make_ohlcv(closes, n=len(closes))
        strategy = MACDStrategy(MACDConfig(fast=12, slow=26, signal=9))

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "BUY"
        assert signal.confidence >= 0.5
        assert "macd" in signal.indicators

    async def test_bearish_crossover_returns_sell(self):
        closes = _macd_bearish_crossover()
        ohlcv = _make_ohlcv(closes, n=len(closes))
        strategy = MACDStrategy(MACDConfig(fast=12, slow=26, signal=9))

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "SELL"
        assert signal.confidence >= 0.5

    async def test_no_crossover_returns_hold(self):
        closes = [65000.0 + i * 50 for i in range(60)]
        ohlcv = _make_ohlcv(closes, n=len(closes))
        strategy = MACDStrategy()

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "HOLD"
        assert 0 <= signal.confidence <= 0.45

    async def test_insufficient_data_returns_hold(self):
        ohlcv = _make_ohlcv([65000.0] * 10, n=10)
        strategy = MACDStrategy()

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "HOLD"


class TestBollingerStrategy:
    async def test_below_lower_band_returns_buy(self):
        closes = [65000.0] * 50 + [60000.0, 58000.0, 56000.0]
        ohlcv = _make_ohlcv(closes, n=len(closes))
        strategy = BollingerStrategy(BollingerConfig(period=20, std_dev=2.0))

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "BUY"
        assert signal.confidence >= 0.5
        assert "bb_lower" in signal.indicators

    async def test_above_upper_band_returns_sell(self):
        closes = [65000.0] * 50 + [70000.0, 72000.0, 74000.0]
        ohlcv = _make_ohlcv(closes, n=len(closes))
        strategy = BollingerStrategy(BollingerConfig(period=20, std_dev=2.0))

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "SELL"
        assert signal.confidence >= 0.5

    async def test_within_bands_returns_hold(self):
        closes = [65000.0 + np.sin(i / 3) * 50 for i in range(60)]
        ohlcv = _make_ohlcv(closes, n=len(closes))
        strategy = BollingerStrategy()

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "HOLD"
        assert 0 <= signal.confidence <= 0.45

    async def test_insufficient_data_returns_hold(self):
        ohlcv = _make_ohlcv([65000.0] * 10, n=10)
        strategy = BollingerStrategy()

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        assert signal.direction == "HOLD"

    async def test_signal_includes_all_band_indicators(self):
        closes = [65000.0] * 50 + [60000.0, 58000.0, 56000.0]
        ohlcv = _make_ohlcv(closes, n=len(closes))
        strategy = BollingerStrategy()

        signal = await strategy.analyze("BTC/USDT", ohlcv)

        for key in ("bb_lower", "bb_mid", "bb_upper", "bb_width", "close"):
            assert key in signal.indicators
