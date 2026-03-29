"""AI-powered strategy: uses Claude as a trade signal filter.

Wraps the MarketAnalyzer to fit the StrategyBase interface. Collects
indicator data from the OHLCV, asks Claude for market analysis, and
returns a signal based on Claude's assessment. Optionally validates
signals through a multi-LLM veto system.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pandas as pd
import pandas_ta as ta

from backend.ai.market_analyzer import MarketAnalyzer
from backend.core.exceptions import AIError
from backend.core.logger import get_logger
from backend.models import Signal
from backend.strategies.base import StrategyBase

if TYPE_CHECKING:
    from backend.ai.veto_system import VetoSystem

logger = get_logger("ai_strategy")


class AIFilterStrategy(StrategyBase):
    """Asks Claude to assess market conditions and provide a trading signal."""

    name = "ai_filter"

    def __init__(
        self,
        analyzer: MarketAnalyzer,
        veto_system: VetoSystem | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._veto = veto_system

    async def analyze(self, symbol: str, ohlcv: pd.DataFrame) -> Signal:
        if len(ohlcv) < 30:
            return self._hold(symbol, "Insufficient data for AI analysis")

        indicators = self._compute_indicators(ohlcv)

        try:
            analysis = await self._analyzer.analyze_market(
                symbol=symbol,
                ohlcv=ohlcv,
                indicators=indicators,
            )
        except AIError:
            logger.exception("AI analysis failed", symbol=symbol)
            return self._hold(symbol, "AI analysis failed")

        condition = analysis.get("condition", "ranging")
        strength = float(analysis.get("strength", 0.0))
        summary = analysis.get("summary", "")

        strength = max(0.0, min(1.0, strength))

        if condition == "trending_up" and strength > 0.5:
            direction = "BUY"
        elif condition == "trending_down" and strength > 0.5:
            direction = "SELL"
        else:
            return self._hold(
                symbol,
                f"AI: {condition} (strength {strength:.2f}) - {summary}",
            )

        if self._veto:
            veto_result = await self._run_veto(
                symbol, direction, strength, summary, indicators,
            )
            if not veto_result:
                return self._hold(
                    symbol,
                    f"AI: {direction} vetoed by multi-LLM consensus",
                )

        return Signal(
            symbol=symbol,
            direction=direction,
            confidence=strength,
            strategy_name=self.name,
            reason=f"AI: {summary}",
            indicators=indicators,
            timestamp=datetime.now(UTC),
        )

    async def _run_veto(
        self,
        symbol: str,
        direction: str,
        strength: float,
        summary: str,
        indicators: dict[str, float],
    ) -> bool:
        """Run multi-LLM veto. Returns True if approved, False if vetoed."""
        indicator_str = ", ".join(
            f"{k}: {v:.4f}" for k, v in indicators.items()
        )
        description = (
            f"Symbol: {symbol}\n"
            f"Proposed direction: {direction}\n"
            f"Confidence: {strength:.2f}\n"
            f"AI summary: {summary}\n"
            f"Indicators: {indicator_str}"
        )
        try:
            result = await self._veto.evaluate(description, direction)
            logger.info(
                "Veto result",
                symbol=symbol,
                direction=direction,
                approved=result.approved,
                agreed=result.providers_agreed,
                responded=result.providers_responded,
            )
            return result.approved
        except Exception:
            logger.exception("Veto system error, allowing signal")
            return True

    @staticmethod
    def _compute_indicators(ohlcv: pd.DataFrame) -> dict[str, float]:
        """Compute key indicators to send to Claude for context."""
        indicators: dict[str, float] = {}

        rsi = ta.rsi(ohlcv["close"], length=14)
        if rsi is not None and not rsi.empty:
            val = rsi.iloc[-1]
            if not pd.isna(val):
                indicators["rsi"] = float(val)

        macd_df = ta.macd(ohlcv["close"], fast=12, slow=26, signal=9)
        if macd_df is not None:
            for col in macd_df.columns:
                if col.startswith("MACDh_"):
                    val = macd_df[col].iloc[-1]
                    if not pd.isna(val):
                        indicators["macd_histogram"] = float(val)

        bb = ta.bbands(ohlcv["close"], length=20, std=2.0)
        if bb is not None:
            for col in bb.columns:
                if col.startswith("BBU_"):
                    val = bb[col].iloc[-1]
                    if not pd.isna(val):
                        indicators["bb_upper"] = float(val)
                elif col.startswith("BBL_"):
                    val = bb[col].iloc[-1]
                    if not pd.isna(val):
                        indicators["bb_lower"] = float(val)

        return indicators

    def _hold(self, symbol: str, reason: str) -> Signal:
        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            strategy_name=self.name,
            reason=reason,
            timestamp=datetime.now(UTC),
        )
