"""Market regime detection with ADX + ATR and hysteresis."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.config import RegimeConfig
from backend.core.logger import get_logger

logger = get_logger("regime")

REGIME_TRENDING = "trending"
REGIME_RANGING = "ranging"
REGIME_VOLATILE = "volatile"


class RegimeDetector:
    """Stateful regime detector with hysteresis to prevent whipsaw flipping.

    Uses ADX for trend strength and ATR percentile for volatility.
    Hysteresis means a higher threshold is needed to *enter* trending than
    to *exit* back to ranging, avoiding rapid oscillation near the boundary.
    """

    def __init__(self, config: RegimeConfig | None = None) -> None:
        self._cfg = config or RegimeConfig()
        self._current_regime: str = REGIME_RANGING
        self._prev_regime: str = REGIME_RANGING
        self._transitions: int = 0

    @property
    def current_regime(self) -> str:
        return self._current_regime

    @property
    def transitions(self) -> int:
        return self._transitions

    def detect(self, ohlcv: pd.DataFrame) -> str:
        """Classify current market regime from OHLCV data.

        Returns one of 'trending', 'ranging', or 'volatile'.
        """
        if not self._cfg.enabled:
            return self._current_regime

        if ohlcv is None or len(ohlcv) < self._cfg.adx_period + 1:
            return self._current_regime

        adx_val = self._compute_adx(ohlcv)
        if adx_val is None:
            return self._current_regime

        atr_pct = self._compute_atr_percentile(ohlcv)

        new_regime = self._classify(adx_val, atr_pct)
        if new_regime != self._current_regime:
            self._prev_regime = self._current_regime
            self._current_regime = new_regime
            self._transitions += 1
            logger.debug(
                "Regime transition",
                prev=self._prev_regime,
                new=self._current_regime,
                adx=round(adx_val, 2),
                atr_percentile=round(atr_pct, 1),
                transitions=self._transitions,
            )

        return self._current_regime

    def get_weights(
        self, base_weights: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Return strategy weights adjusted for the current regime.

        If regime detection is disabled, returns base_weights unchanged.
        Otherwise, multiplies base weights by the regime-specific multipliers.
        """
        if not self._cfg.enabled:
            return base_weights or {}

        regime_map = {
            REGIME_TRENDING: self._cfg.trending_weights,
            REGIME_RANGING: self._cfg.ranging_weights,
            REGIME_VOLATILE: self._cfg.volatile_weights,
        }
        multipliers = regime_map.get(self._current_regime, {})

        if not base_weights:
            return dict(multipliers)

        merged: dict[str, float] = {}
        all_keys = set(base_weights) | set(multipliers)
        for key in all_keys:
            base = base_weights.get(key, 1.0)
            mult = multipliers.get(key, 1.0)
            merged[key] = base * mult
        return merged

    def _classify(self, adx_val: float, atr_percentile: float) -> str:
        """Classify regime using ADX + ATR percentile with hysteresis."""
        threshold = self._cfg.trending_threshold
        buffer = self._cfg.hysteresis_buffer

        if atr_percentile >= self._cfg.volatile_atr_percentile:
            return REGIME_VOLATILE

        if self._current_regime == REGIME_TRENDING:
            if adx_val < threshold - buffer:
                return REGIME_RANGING
            return REGIME_TRENDING
        else:
            if adx_val > threshold + buffer:
                return REGIME_TRENDING
            return REGIME_RANGING

    def _compute_adx(self, ohlcv: pd.DataFrame) -> float | None:
        """Compute ADX using pandas-ta."""
        try:
            import pandas_ta as ta

            adx_df = ta.adx(
                ohlcv["high"], ohlcv["low"], ohlcv["close"],
                length=self._cfg.adx_period,
            )
            if adx_df is None or adx_df.empty:
                return None

            col = next(
                (c for c in adx_df.columns if c.startswith("ADX_")), None,
            )
            if not col:
                return None

            val = adx_df[col].iloc[-1]
            if pd.isna(val):
                return None
            return float(val)
        except Exception:
            logger.debug("ADX computation failed")
            return None

    def _compute_atr_percentile(self, ohlcv: pd.DataFrame) -> float:
        """Compute current ATR as a percentile of its rolling history."""
        try:
            high = ohlcv["high"]
            low = ohlcv["low"]
            close = ohlcv["close"]

            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)

            atr_period = min(14, len(tr) - 1)
            if atr_period < 2:
                return 50.0

            atr_series = tr.rolling(window=atr_period).mean().dropna()
            if len(atr_series) < 2:
                return 50.0

            lookback = min(self._cfg.atr_lookback, len(atr_series))
            window = atr_series.iloc[-lookback:]
            current_atr = float(atr_series.iloc[-1])

            rank = float(np.sum(window <= current_atr))
            percentile = (rank / len(window)) * 100.0
            return percentile
        except Exception:
            logger.debug("ATR percentile computation failed")
            return 50.0

    def reset(self) -> None:
        """Reset regime state (useful between backtest runs)."""
        self._current_regime = REGIME_RANGING
        self._prev_regime = REGIME_RANGING
        self._transitions = 0
