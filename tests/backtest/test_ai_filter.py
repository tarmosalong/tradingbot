from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from backend.backtest.ai_filter import AIFilterConfig, AISimulationFilter
from backend.models import Signal


def _make_signal(direction: str = "BUY", confidence: float = 0.6) -> Signal:
    return Signal(
        symbol="BTC/USDT",
        direction=direction,
        confidence=confidence,
        strategy_name="test",
        reason="test signal",
    )


def _flat_ohlcv(n: int = 50, base_price: float = 100.0) -> pd.DataFrame:
    rows = []
    for i in range(n):
        ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
        rows.append({
            "timestamp": ts,
            "open": base_price,
            "high": base_price * 1.005,
            "low": base_price * 0.995,
            "close": base_price,
            "volume": 1000.0,
        })
    return pd.DataFrame(rows)


def _crash_ohlcv(n: int = 50, drop_pct: float = 0.10) -> pd.DataFrame:
    """Create OHLCV with a crash in the last 10 candles."""
    rows = []
    base = 100.0
    for i in range(n):
        ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
        if i >= n - 10:
            progress = (i - (n - 10)) / 10
            price = base * (1.0 - drop_pct * progress)
        else:
            price = base
        rows.append({
            "timestamp": ts,
            "open": price * 1.002,
            "high": price * 1.005,
            "low": price * 0.995,
            "close": price,
            "volume": 1000.0 if i < n - 10 else 3000.0,
        })
    return pd.DataFrame(rows)


def _recovery_ohlcv(n: int = 60) -> pd.DataFrame:
    """Older window crashes (-8%), recent window recovers (+4%)."""
    rows = []
    base = 100.0
    lookback = 10

    for i in range(n):
        ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
        if i < n - lookback * 2:
            price = base
        elif i < n - lookback:
            progress = (i - (n - lookback * 2)) / lookback
            price = base * (1.0 - 0.08 * progress)
        else:
            progress = (i - (n - lookback)) / lookback
            price = base * 0.92 * (1.0 + 0.06 * progress)
        rows.append({
            "timestamp": ts,
            "open": price * 1.001,
            "high": price * 1.003,
            "low": price * 0.997,
            "close": price,
            "volume": 1000.0,
        })
    return pd.DataFrame(rows)


class TestAIFilterDisabled:
    def test_disabled_returns_unchanged(self):
        f = AISimulationFilter(AIFilterConfig(enabled=False))
        sig = _make_signal("BUY", 0.7)
        ohlcv = _flat_ohlcv()
        result = f.evaluate(sig, ohlcv)
        assert result.direction == "BUY"
        assert result.confidence == 0.7

    def test_hold_passes_through(self):
        f = AISimulationFilter(AIFilterConfig(enabled=True))
        sig = _make_signal("HOLD", 0.0)
        result = f.evaluate(sig, _flat_ohlcv())
        assert result.direction == "HOLD"
        assert f.stats.signals_reviewed == 0


class TestCrashDetection:
    def test_buy_blocked_during_crash(self):
        f = AISimulationFilter(AIFilterConfig(
            enabled=True, strength=0.9, crash_threshold_pct=-5.0,
        ))
        sig = _make_signal("BUY", 0.5)
        ohlcv = _crash_ohlcv(50, drop_pct=0.10)
        result = f.evaluate(sig, ohlcv)
        assert result.direction == "HOLD"
        assert f.stats.signals_blocked == 1
        assert f.stats.crash_detections >= 1

    def test_buy_reduced_during_mild_crash(self):
        f = AISimulationFilter(AIFilterConfig(
            enabled=True, strength=0.3, crash_threshold_pct=-5.0,
        ))
        sig = _make_signal("BUY", 0.8)
        ohlcv = _crash_ohlcv(50, drop_pct=0.06)
        result = f.evaluate(sig, ohlcv)
        assert result.direction == "BUY"
        assert result.confidence < 0.8
        assert f.stats.signals_reduced == 1

    def test_sell_boosted_during_crash(self):
        f = AISimulationFilter(AIFilterConfig(
            enabled=True, strength=0.8, crash_threshold_pct=-5.0,
        ))
        sig = _make_signal("SELL", 0.5)
        ohlcv = _crash_ohlcv(50, drop_pct=0.10)
        result = f.evaluate(sig, ohlcv)
        assert result.direction == "SELL"
        assert result.confidence >= 0.5

    def test_no_effect_on_flat_market(self):
        f = AISimulationFilter(AIFilterConfig(enabled=True, strength=1.0))
        sig = _make_signal("BUY", 0.7)
        result = f.evaluate(sig, _flat_ohlcv())
        assert result.direction == "BUY"
        assert result.confidence == 0.7
        assert f.stats.crash_detections == 0


class TestRecoveryDetection:
    def test_buy_boosted_on_recovery(self):
        f = AISimulationFilter(AIFilterConfig(
            enabled=True, strength=0.8, recovery_boost=1.5,
        ))
        sig = _make_signal("BUY", 0.5)
        ohlcv = _recovery_ohlcv(60)
        result = f.evaluate(sig, ohlcv)
        assert result.direction == "BUY"
        assert result.confidence > 0.5
        assert f.stats.signals_boosted == 1
        assert f.stats.recovery_detections >= 1


class TestStrengthParameter:
    def test_zero_strength_no_effect(self):
        f = AISimulationFilter(AIFilterConfig(
            enabled=True, strength=0.0,
        ))
        sig = _make_signal("BUY", 0.6)
        ohlcv = _crash_ohlcv(50, drop_pct=0.10)
        result = f.evaluate(sig, ohlcv)
        assert result.direction == "BUY"
        assert result.confidence == 0.6

    def test_full_strength_maximum_effect(self):
        f = AISimulationFilter(AIFilterConfig(
            enabled=True, strength=1.0, crash_threshold_pct=-5.0,
        ))
        sig = _make_signal("BUY", 0.5)
        ohlcv = _crash_ohlcv(50, drop_pct=0.10)
        result = f.evaluate(sig, ohlcv)
        assert result.direction == "HOLD"
        assert result.confidence == 0.0


class TestStats:
    def test_stats_accumulate(self):
        f = AISimulationFilter(AIFilterConfig(
            enabled=True, strength=0.9, crash_threshold_pct=-5.0,
        ))
        ohlcv = _crash_ohlcv(50, drop_pct=0.10)

        f.evaluate(_make_signal("BUY", 0.5), ohlcv)
        f.evaluate(_make_signal("BUY", 0.5), ohlcv)
        f.evaluate(_make_signal("SELL", 0.5), ohlcv)

        assert f.stats.signals_reviewed == 3
        assert f.stats.signals_blocked == 2

    def test_to_dict(self):
        f = AISimulationFilter(AIFilterConfig(enabled=True))
        d = f.stats.to_dict()
        assert "signals_reviewed" in d
        assert "signals_blocked" in d
        assert "crash_detections" in d
        assert all(isinstance(v, int) for v in d.values())
