"""Tests for RegimeDetector: ADX classification, hysteresis, weight maps."""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from backend.config import RegimeConfig
from backend.core.regime import (
    REGIME_RANGING,
    REGIME_TRENDING,
    REGIME_VOLATILE,
    RegimeDetector,
)


def _make_ohlcv(n: int = 100, *, trend: bool = False, volatile: bool = False) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    base = 100.0
    prices = [base]
    for _ in range(n - 1):
        if trend:
            drift = 0.5
        elif volatile:
            drift = 0.0
        else:
            drift = 0.0
        noise_scale = 5.0 if volatile else 0.5
        change = drift + np.random.randn() * noise_scale
        prices.append(max(prices[-1] + change, 1.0))

    closes = np.array(prices)
    highs = closes * (1 + np.random.uniform(0.001, 0.02, n))
    lows = closes * (1 - np.random.uniform(0.001, 0.02, n))
    opens = closes + np.random.randn(n) * 0.3
    volume = np.random.uniform(100, 1000, n)
    timestamps = pd.date_range("2025-01-01", periods=n, freq="1h")

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volume,
    })


class TestRegimeClassification:
    def test_disabled_returns_ranging(self):
        cfg = RegimeConfig(enabled=False)
        detector = RegimeDetector(cfg)
        ohlcv = _make_ohlcv(100, trend=True)
        result = detector.detect(ohlcv)
        assert result == REGIME_RANGING

    def test_insufficient_data_returns_default(self):
        cfg = RegimeConfig(enabled=True, adx_period=14)
        detector = RegimeDetector(cfg)
        ohlcv = _make_ohlcv(10)
        result = detector.detect(ohlcv)
        assert result == REGIME_RANGING

    def test_none_ohlcv_returns_current(self):
        cfg = RegimeConfig(enabled=True)
        detector = RegimeDetector(cfg)
        result = detector.detect(None)
        assert result == REGIME_RANGING

    def test_trending_classification(self):
        cfg = RegimeConfig(
            enabled=True,
            trending_threshold=20.0,
            hysteresis_buffer=2.0,
        )
        detector = RegimeDetector(cfg)

        with patch.object(detector, "_compute_adx", return_value=35.0):
            with patch.object(detector, "_compute_atr_percentile", return_value=50.0):
                result = detector.detect(_make_ohlcv(50))
                assert result == REGIME_TRENDING

    def test_ranging_classification(self):
        cfg = RegimeConfig(
            enabled=True,
            trending_threshold=25.0,
            hysteresis_buffer=5.0,
        )
        detector = RegimeDetector(cfg)

        with patch.object(detector, "_compute_adx", return_value=15.0):
            with patch.object(detector, "_compute_atr_percentile", return_value=50.0):
                result = detector.detect(_make_ohlcv(50))
                assert result == REGIME_RANGING

    def test_volatile_classification_overrides_trending(self):
        cfg = RegimeConfig(
            enabled=True,
            trending_threshold=20.0,
            hysteresis_buffer=2.0,
            volatile_atr_percentile=80.0,
        )
        detector = RegimeDetector(cfg)

        with patch.object(detector, "_compute_adx", return_value=40.0):
            with patch.object(detector, "_compute_atr_percentile", return_value=90.0):
                result = detector.detect(_make_ohlcv(50))
                assert result == REGIME_VOLATILE


class TestHysteresis:
    def test_enter_trending_requires_upper_band(self):
        """ADX must exceed threshold + buffer to enter trending from ranging."""
        cfg = RegimeConfig(
            enabled=True,
            trending_threshold=25.0,
            hysteresis_buffer=5.0,
        )
        detector = RegimeDetector(cfg)
        ohlcv = _make_ohlcv(50)

        with patch.object(detector, "_compute_atr_percentile", return_value=50.0):
            with patch.object(detector, "_compute_adx", return_value=28.0):
                result = detector.detect(ohlcv)
                assert result == REGIME_RANGING, (
                    "ADX 28 < 30 (threshold+buffer), should stay ranging"
                )

            with patch.object(detector, "_compute_adx", return_value=31.0):
                result = detector.detect(ohlcv)
                assert result == REGIME_TRENDING, "ADX 31 > 30, should enter trending"

    def test_exit_trending_requires_lower_band(self):
        """ADX must drop below threshold - buffer to exit back to ranging."""
        cfg = RegimeConfig(
            enabled=True,
            trending_threshold=25.0,
            hysteresis_buffer=5.0,
        )
        detector = RegimeDetector(cfg)
        ohlcv = _make_ohlcv(50)

        with patch.object(detector, "_compute_atr_percentile", return_value=50.0):
            with patch.object(detector, "_compute_adx", return_value=35.0):
                detector.detect(ohlcv)
                assert detector.current_regime == REGIME_TRENDING

            with patch.object(detector, "_compute_adx", return_value=22.0):
                detector.detect(ohlcv)
                assert detector.current_regime == REGIME_TRENDING, (
                    "ADX 22 > 20 (threshold-buffer), should stay trending"
                )

            with patch.object(detector, "_compute_adx", return_value=18.0):
                detector.detect(ohlcv)
                assert detector.current_regime == REGIME_RANGING, (
                    "ADX 18 < 20, should exit trending"
                )

    def test_no_whipsaw_at_boundary(self):
        """ADX oscillating near threshold should not cause rapid flipping."""
        cfg = RegimeConfig(
            enabled=True,
            trending_threshold=25.0,
            hysteresis_buffer=5.0,
        )
        detector = RegimeDetector(cfg)
        ohlcv = _make_ohlcv(50)

        adx_sequence = [26, 24, 26, 28, 24, 26]
        with patch.object(detector, "_compute_atr_percentile", return_value=50.0):
            for adx_val in adx_sequence:
                with patch.object(detector, "_compute_adx", return_value=float(adx_val)):
                    detector.detect(ohlcv)

        assert detector.transitions == 0, (
            "Should have zero transitions with ADX bouncing inside band"
        )
        assert detector.current_regime == REGIME_RANGING

    def test_transition_counter(self):
        cfg = RegimeConfig(
            enabled=True,
            trending_threshold=25.0,
            hysteresis_buffer=5.0,
        )
        detector = RegimeDetector(cfg)
        ohlcv = _make_ohlcv(50)

        with patch.object(detector, "_compute_atr_percentile", return_value=50.0):
            with patch.object(detector, "_compute_adx", return_value=35.0):
                detector.detect(ohlcv)
            assert detector.transitions == 1

            with patch.object(detector, "_compute_adx", return_value=15.0):
                detector.detect(ohlcv)
            assert detector.transitions == 2


class TestWeightMaps:
    def test_disabled_returns_base_weights(self):
        cfg = RegimeConfig(enabled=False)
        detector = RegimeDetector(cfg)
        base = {"rsi": 1.0, "ema": 1.0}
        result = detector.get_weights(base)
        assert result == base

    def test_disabled_returns_empty_for_none(self):
        cfg = RegimeConfig(enabled=False)
        detector = RegimeDetector(cfg)
        result = detector.get_weights(None)
        assert result == {}

    def test_trending_weights(self):
        cfg = RegimeConfig(enabled=True)
        detector = RegimeDetector(cfg)
        detector._current_regime = REGIME_TRENDING

        weights = detector.get_weights()
        assert weights["ema"] == 1.5
        assert weights["rsi"] == 0.2
        assert weights["bollinger"] == 0.2

    def test_ranging_weights(self):
        cfg = RegimeConfig(enabled=True)
        detector = RegimeDetector(cfg)
        detector._current_regime = REGIME_RANGING

        weights = detector.get_weights()
        assert weights["ema"] == 0.2
        assert weights["rsi"] == 1.2
        assert weights["bollinger"] == 1.2

    def test_volatile_weights(self):
        cfg = RegimeConfig(enabled=True)
        detector = RegimeDetector(cfg)
        detector._current_regime = REGIME_VOLATILE

        weights = detector.get_weights()
        assert weights["ema"] == 0.5
        assert weights["rsi"] == 0.5

    def test_weights_multiply_base(self):
        cfg = RegimeConfig(enabled=True)
        detector = RegimeDetector(cfg)
        detector._current_regime = REGIME_TRENDING

        base = {"rsi": 2.0, "ema": 3.0}
        weights = detector.get_weights(base)
        assert weights["ema"] == pytest.approx(3.0 * 1.5)
        assert weights["rsi"] == pytest.approx(2.0 * 0.2)

    def test_weights_merge_all_keys(self):
        """Keys from both base_weights and regime multipliers should appear."""
        cfg = RegimeConfig(enabled=True)
        detector = RegimeDetector(cfg)
        detector._current_regime = REGIME_TRENDING

        base = {"custom_strat": 2.0}
        weights = detector.get_weights(base)
        assert "custom_strat" in weights
        assert weights["custom_strat"] == 2.0  # base * default multiplier (1.0)
        assert "ema" in weights  # from regime multipliers


class TestReset:
    def test_reset_clears_state(self):
        cfg = RegimeConfig(enabled=True)
        detector = RegimeDetector(cfg)
        detector._current_regime = REGIME_TRENDING
        detector._transitions = 5

        detector.reset()
        assert detector.current_regime == REGIME_RANGING
        assert detector.transitions == 0


class TestADXComputation:
    def test_compute_adx_returns_float(self):
        cfg = RegimeConfig(enabled=True, adx_period=14)
        detector = RegimeDetector(cfg)
        ohlcv = _make_ohlcv(100)
        result = detector._compute_adx(ohlcv)
        assert result is None or isinstance(result, float)

    def test_compute_adx_with_real_data(self):
        cfg = RegimeConfig(enabled=True, adx_period=14)
        detector = RegimeDetector(cfg)
        ohlcv = _make_ohlcv(100, trend=True)
        result = detector._compute_adx(ohlcv)
        assert result is not None
        assert 0 <= result <= 100


class TestATRPercentile:
    def test_percentile_in_range(self):
        cfg = RegimeConfig(enabled=True)
        detector = RegimeDetector(cfg)
        ohlcv = _make_ohlcv(100)
        pct = detector._compute_atr_percentile(ohlcv)
        assert 0 <= pct <= 100

    def test_volatile_data_high_percentile(self):
        """Volatile data at the end should have higher ATR percentile."""
        cfg = RegimeConfig(enabled=True, atr_lookback=50)
        detector = RegimeDetector(cfg)

        np.random.seed(99)
        n = 100
        closes = np.cumsum(np.random.randn(n) * 0.5) + 100
        closes[-20:] += np.random.randn(20) * 10  # spike volatility at end
        closes = np.maximum(closes, 1.0)
        highs = closes + np.abs(np.random.randn(n)) * 2
        lows = closes - np.abs(np.random.randn(n)) * 2
        lows = np.maximum(lows, 0.5)

        ohlcv = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=n, freq="1h"),
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.random.uniform(100, 1000, n),
        })

        pct = detector._compute_atr_percentile(ohlcv)
        assert pct >= 60, f"Expected high ATR percentile for volatile tail, got {pct}"

    def test_short_data_returns_default(self):
        cfg = RegimeConfig(enabled=True)
        detector = RegimeDetector(cfg)
        ohlcv = _make_ohlcv(2)
        pct = detector._compute_atr_percentile(ohlcv)
        assert pct == 50.0
