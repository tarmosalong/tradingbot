from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backend.core.logger import get_logger
from backend.models import Signal

logger = get_logger("ai_filter")


@dataclass(frozen=True)
class AIFilterConfig:
    enabled: bool = False
    strength: float = 0.5
    crash_lookback: int = 10
    crash_threshold_pct: float = -5.0
    volatility_lookback: int = 20
    volatility_multiplier: float = 2.0
    volume_spike_multiplier: float = 2.5
    recovery_boost: float = 1.3
    min_confidence_threshold: float = 0.3


@dataclass
class AIFilterStats:
    signals_reviewed: int = 0
    signals_blocked: int = 0
    signals_reduced: int = 0
    signals_boosted: int = 0
    crash_detections: int = 0
    volatility_detections: int = 0
    volume_spike_detections: int = 0
    recovery_detections: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "signals_reviewed": self.signals_reviewed,
            "signals_blocked": self.signals_blocked,
            "signals_reduced": self.signals_reduced,
            "signals_boosted": self.signals_boosted,
            "crash_detections": self.crash_detections,
            "volatility_detections": self.volatility_detections,
            "volume_spike_detections": self.volume_spike_detections,
            "recovery_detections": self.recovery_detections,
        }


class AISimulationFilter:
    """Simulates AI trade filtering without calling an LLM.

    Detects crash conditions (rapid drops, high volatility, volume spikes)
    and adjusts signal confidence accordingly. Uses a ``strength`` parameter
    (0.0–1.0) to control how aggressively signals are filtered.
    """

    def __init__(self, config: AIFilterConfig | None = None) -> None:
        self._config = config or AIFilterConfig()
        self.stats = AIFilterStats()

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def evaluate(self, signal: Signal, ohlcv: pd.DataFrame) -> Signal:
        if not self._config.enabled or signal.direction == "HOLD":
            return signal

        self.stats.signals_reviewed += 1

        crash_score = self._detect_crash(ohlcv)
        vol_score = self._detect_high_volatility(ohlcv)
        spike_score = self._detect_volume_spike(ohlcv)
        recovery = self._detect_recovery(ohlcv)

        risk_score = max(crash_score, vol_score, spike_score)
        penalty = risk_score * self._config.strength

        if signal.direction == "BUY":
            if recovery > 0 and risk_score < 0.3:
                boost = 1.0 + (self._config.recovery_boost - 1.0) * self._config.strength
                new_confidence = min(signal.confidence * boost, 1.0)
                self.stats.signals_boosted += 1
                return Signal(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    confidence=new_confidence,
                    strategy_name=signal.strategy_name,
                    reason=(
                        f"{signal.reason} [AI: recovery detected, "
                        f"conf boosted {signal.confidence:.2f}\u2192{new_confidence:.2f}]"
                    ),
                    indicators=signal.indicators,
                    timestamp=signal.timestamp,
                )

            if penalty > 0:
                new_confidence = signal.confidence * (1.0 - penalty)
                if new_confidence < self._config.min_confidence_threshold:
                    self.stats.signals_blocked += 1
                    reasons = self._build_block_reasons(
                        crash_score, vol_score, spike_score,
                    )
                    return Signal(
                        symbol=signal.symbol,
                        direction="HOLD",
                        confidence=0.0,
                        strategy_name=signal.strategy_name,
                        reason=f"AI filter blocked BUY: {reasons}",
                        indicators=signal.indicators,
                        timestamp=signal.timestamp,
                    )

                self.stats.signals_reduced += 1
                reasons = self._build_reduce_reasons(
                    crash_score, vol_score, spike_score,
                )
                return Signal(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    confidence=new_confidence,
                    strategy_name=signal.strategy_name,
                    reason=(
                        f"{signal.reason} [AI: {reasons}, "
                        f"conf {signal.confidence:.2f}\u2192{new_confidence:.2f}]"
                    ),
                    indicators=signal.indicators,
                    timestamp=signal.timestamp,
                )

        if signal.direction == "SELL" and crash_score > 0.5:
            boost = 1.0 + penalty * 0.5
            new_confidence = min(signal.confidence * boost, 1.0)
            if new_confidence != signal.confidence:
                self.stats.signals_boosted += 1
                return Signal(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    confidence=new_confidence,
                    strategy_name=signal.strategy_name,
                    reason=(
                        f"{signal.reason} [AI: crash detected, "
                        f"SELL conf boosted {signal.confidence:.2f}\u2192{new_confidence:.2f}]"
                    ),
                    indicators=signal.indicators,
                    timestamp=signal.timestamp,
                )

        return signal

    def _detect_crash(self, ohlcv: pd.DataFrame) -> float:
        lookback = self._config.crash_lookback
        if len(ohlcv) < lookback + 1:
            return 0.0

        recent = ohlcv.tail(lookback)
        close_start = float(recent.iloc[0]["close"])
        close_end = float(recent.iloc[-1]["close"])

        if close_start <= 0:
            return 0.0

        change_pct = ((close_end - close_start) / close_start) * 100
        threshold = self._config.crash_threshold_pct

        if change_pct >= threshold:
            return 0.0

        self.stats.crash_detections += 1
        severity = min(abs(change_pct / threshold), 3.0) / 3.0
        return severity

    def _detect_high_volatility(self, ohlcv: pd.DataFrame) -> float:
        lookback = self._config.volatility_lookback
        if len(ohlcv) < lookback + 10:
            return 0.0

        closes = ohlcv["close"].astype(float)
        returns = closes.pct_change().dropna()

        recent_vol = float(returns.tail(lookback).std())
        long_vol = float(returns.std())

        if long_vol <= 0:
            return 0.0

        ratio = recent_vol / long_vol
        threshold = self._config.volatility_multiplier

        if ratio < threshold:
            return 0.0

        self.stats.volatility_detections += 1
        severity = min((ratio - threshold) / threshold, 1.0)
        return 0.3 + severity * 0.7

    def _detect_volume_spike(self, ohlcv: pd.DataFrame) -> float:
        if len(ohlcv) < 21:
            return 0.0

        volumes = ohlcv["volume"].astype(float)
        avg_volume = float(volumes.iloc[-21:-1].mean())
        current_volume = float(volumes.iloc[-1])

        if avg_volume <= 0:
            return 0.0

        ratio = current_volume / avg_volume
        threshold = self._config.volume_spike_multiplier

        if ratio < threshold:
            return 0.0

        closes = ohlcv["close"].astype(float)
        price_down = closes.iloc[-1] < closes.iloc[-2]

        if not price_down:
            return 0.0

        self.stats.volume_spike_detections += 1
        severity = min((ratio - threshold) / threshold, 1.0)
        return 0.3 + severity * 0.7

    def _detect_recovery(self, ohlcv: pd.DataFrame) -> float:
        lookback = self._config.crash_lookback
        if len(ohlcv) < lookback * 2:
            return 0.0

        older = ohlcv.iloc[-(lookback * 2):-lookback]
        recent = ohlcv.tail(lookback)

        older_start = float(older.iloc[0]["close"])
        older_end = float(older.iloc[-1]["close"])
        recent_start = float(recent.iloc[0]["close"])
        recent_end = float(recent.iloc[-1]["close"])

        if older_start <= 0 or recent_start <= 0:
            return 0.0

        older_change = (older_end - older_start) / older_start
        recent_change = (recent_end - recent_start) / recent_start

        if older_change < -0.03 and recent_change > 0.01:
            self.stats.recovery_detections += 1
            return min(recent_change / 0.05, 1.0)

        return 0.0

    def _build_block_reasons(
        self, crash: float, vol: float, spike: float,
    ) -> str:
        parts: list[str] = []
        if crash > 0:
            parts.append(f"crash={crash:.0%}")
        if vol > 0:
            parts.append(f"volatility={vol:.0%}")
        if spike > 0:
            parts.append(f"volume_spike={spike:.0%}")
        return ", ".join(parts) or "elevated risk"

    def _build_reduce_reasons(
        self, crash: float, vol: float, spike: float,
    ) -> str:
        parts: list[str] = []
        if crash > 0:
            parts.append("crash risk")
        if vol > 0:
            parts.append("high volatility")
        if spike > 0:
            parts.append("volume spike")
        return " + ".join(parts) or "risk detected"
