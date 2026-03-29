"""Technical analysis strategies: RSI, MACD, Bollinger Bands.

Each receives OHLCV data, computes indicators via pandas-ta, and
returns a Signal with direction, confidence, and supporting data.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pandas_ta as ta

from backend.config import BollingerConfig, MACDConfig, RSIConfig
from backend.models import Signal
from backend.strategies.base import StrategyBase

MIN_ROWS = 30


class RSIStrategy(StrategyBase):
    """Relative Strength Index: oversold → BUY, overbought → SELL."""

    name = "rsi"

    def __init__(self, config: RSIConfig | None = None) -> None:
        self._cfg = config or RSIConfig()

    async def analyze(self, symbol: str, ohlcv: pd.DataFrame) -> Signal:
        if len(ohlcv) < MIN_ROWS:
            return self._hold(symbol, "Insufficient data for RSI")

        rsi_series = ta.rsi(ohlcv["close"], length=self._cfg.period)
        if rsi_series is None or rsi_series.empty:
            return self._hold(symbol, "RSI computation failed")

        rsi_val = float(rsi_series.iloc[-1])

        if pd.isna(rsi_val):
            return self._hold(symbol, "RSI value is NaN")

        indicators = {"rsi": rsi_val}

        if rsi_val <= self._cfg.oversold:
            distance = (self._cfg.oversold - rsi_val) / self._cfg.oversold
            confidence = min(0.5 + distance, 1.0)
            return Signal(
                symbol=symbol,
                direction="BUY",
                confidence=confidence,
                strategy_name=self.name,
                reason=f"RSI {rsi_val:.1f} below oversold {self._cfg.oversold}",
                indicators=indicators,
                timestamp=datetime.now(UTC),
            )

        if rsi_val >= self._cfg.overbought:
            distance = (rsi_val - self._cfg.overbought) / (100 - self._cfg.overbought)
            confidence = min(0.5 + distance, 1.0)
            return Signal(
                symbol=symbol,
                direction="SELL",
                confidence=confidence,
                strategy_name=self.name,
                reason=f"RSI {rsi_val:.1f} above overbought {self._cfg.overbought}",
                indicators=indicators,
                timestamp=datetime.now(UTC),
            )

        mid = (self._cfg.oversold + self._cfg.overbought) / 2
        dist_buy = rsi_val - self._cfg.oversold
        dist_sell = self._cfg.overbought - rsi_val
        nearest_dist = min(dist_buy, dist_sell)
        half_range = mid - self._cfg.oversold
        warmth = max(0.0, (half_range - nearest_dist) / half_range) * 0.45

        if dist_buy < dist_sell:
            reason = f"RSI {rsi_val:.1f} in neutral zone, {dist_buy:.0f} pts from buy"
        else:
            reason = f"RSI {rsi_val:.1f} in neutral zone, {dist_sell:.0f} pts from sell"

        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=round(warmth, 3),
            strategy_name=self.name,
            reason=reason,
            indicators=indicators,
            timestamp=datetime.now(UTC),
        )

    def _hold(self, symbol: str, reason: str) -> Signal:
        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
            timestamp=datetime.now(UTC),
        )


class MACDStrategy(StrategyBase):
    """MACD crossover: MACD crosses above signal → BUY, below → SELL."""

    name = "macd"

    def __init__(self, config: MACDConfig | None = None) -> None:
        self._cfg = config or MACDConfig()

    async def analyze(self, symbol: str, ohlcv: pd.DataFrame) -> Signal:
        if len(ohlcv) < MIN_ROWS:
            return self._hold(symbol, "Insufficient data for MACD")

        macd_df = ta.macd(
            ohlcv["close"],
            fast=self._cfg.fast,
            slow=self._cfg.slow,
            signal=self._cfg.signal,
        )
        if macd_df is None or macd_df.empty:
            return self._hold(symbol, "MACD computation failed")

        col_macd = next((c for c in macd_df.columns if c.startswith("MACD_")), None)
        col_signal = next((c for c in macd_df.columns if c.startswith("MACDs_")), None)
        col_hist = next((c for c in macd_df.columns if c.startswith("MACDh_")), None)

        if not col_macd or not col_signal or not col_hist:
            return self._hold(symbol, "MACD columns not found")

        macd_val = float(macd_df[col_macd].iloc[-1])
        signal_val = float(macd_df[col_signal].iloc[-1])
        hist_val = float(macd_df[col_hist].iloc[-1])
        prev_hist = float(macd_df[col_hist].iloc[-2])

        if pd.isna(macd_val) or pd.isna(signal_val):
            return self._hold(symbol, "MACD values are NaN")

        indicators = {
            "macd": macd_val,
            "macd_signal": signal_val,
            "macd_histogram": hist_val,
        }

        if prev_hist < 0 and hist_val > 0:
            confidence = min(0.5 + abs(hist_val) * 10, 1.0)
            return Signal(
                symbol=symbol,
                direction="BUY",
                confidence=confidence,
                strategy_name=self.name,
                reason=f"MACD bullish crossover, histogram {hist_val:.4f}",
                indicators=indicators,
                timestamp=datetime.now(UTC),
            )

        if prev_hist > 0 and hist_val < 0:
            confidence = min(0.5 + abs(hist_val) * 10, 1.0)
            return Signal(
                symbol=symbol,
                direction="SELL",
                confidence=confidence,
                strategy_name=self.name,
                reason=f"MACD bearish crossover, histogram {hist_val:.4f}",
                indicators=indicators,
                timestamp=datetime.now(UTC),
            )

        abs_hist = abs(hist_val)
        closing = abs_hist < abs(prev_hist)
        scale = max(abs(prev_hist), 1e-9)
        warmth = max(0.0, (1.0 - abs_hist / scale)) * 0.4 if closing else 0.0
        warmth = min(warmth, 0.45)

        side = "buy" if hist_val < 0 else "sell"
        trend = "converging" if closing else "diverging"

        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=round(warmth, 3),
            strategy_name=self.name,
            reason=f"MACD {trend} toward {side}, histogram {hist_val:.4f}",
            indicators=indicators,
            timestamp=datetime.now(UTC),
        )

    def _hold(self, symbol: str, reason: str) -> Signal:
        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
            timestamp=datetime.now(UTC),
        )


class BollingerStrategy(StrategyBase):
    """Bollinger Bands: price below lower band → BUY, above upper → SELL."""

    name = "bollinger"

    def __init__(self, config: BollingerConfig | None = None) -> None:
        self._cfg = config or BollingerConfig()

    async def analyze(self, symbol: str, ohlcv: pd.DataFrame) -> Signal:
        if len(ohlcv) < MIN_ROWS:
            return self._hold(symbol, "Insufficient data for Bollinger")

        bb = ta.bbands(
            ohlcv["close"],
            length=self._cfg.period,
            std=self._cfg.std_dev,
        )
        if bb is None or bb.empty:
            return self._hold(symbol, "Bollinger computation failed")

        col_lower = next((c for c in bb.columns if c.startswith("BBL_")), None)
        col_mid = next((c for c in bb.columns if c.startswith("BBM_")), None)
        col_upper = next((c for c in bb.columns if c.startswith("BBU_")), None)

        if not col_lower or not col_mid or not col_upper:
            return self._hold(symbol, "Bollinger columns not found")

        close = float(ohlcv["close"].iloc[-1])
        lower = float(bb[col_lower].iloc[-1])
        mid = float(bb[col_mid].iloc[-1])
        upper = float(bb[col_upper].iloc[-1])

        if pd.isna(lower) or pd.isna(upper):
            return self._hold(symbol, "Bollinger values are NaN")

        band_width = upper - lower
        indicators = {
            "bb_lower": lower,
            "bb_mid": mid,
            "bb_upper": upper,
            "bb_width": band_width,
            "close": close,
        }

        if close < lower:
            penetration = (lower - close) / band_width if band_width > 0 else 0
            confidence = min(0.5 + penetration * 2, 1.0)
            return Signal(
                symbol=symbol,
                direction="BUY",
                confidence=confidence,
                strategy_name=self.name,
                reason=f"Price {close:.2f} below lower band {lower:.2f}",
                indicators=indicators,
                timestamp=datetime.now(UTC),
            )

        if close > upper:
            penetration = (close - upper) / band_width if band_width > 0 else 0
            confidence = min(0.5 + penetration * 2, 1.0)
            return Signal(
                symbol=symbol,
                direction="SELL",
                confidence=confidence,
                strategy_name=self.name,
                reason=f"Price {close:.2f} above upper band {upper:.2f}",
                indicators=indicators,
                timestamp=datetime.now(UTC),
            )

        half_width = band_width / 2 if band_width > 0 else 1
        dist_lower = close - lower
        dist_upper = upper - close
        nearest_dist = min(dist_lower, dist_upper)
        warmth = max(0.0, (half_width - nearest_dist) / half_width) * 0.45

        if dist_lower < dist_upper:
            reason = f"Price {close:.2f} within bands, ${dist_lower:.0f} from lower"
        else:
            reason = f"Price {close:.2f} within bands, ${dist_upper:.0f} from upper"

        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=round(warmth, 3),
            strategy_name=self.name,
            reason=reason,
            indicators=indicators,
            timestamp=datetime.now(UTC),
        )

    def _hold(self, symbol: str, reason: str) -> Signal:
        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
            timestamp=datetime.now(UTC),
        )
