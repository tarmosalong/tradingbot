"""Sentiment-based strategy: uses news sentiment from Claude to generate signals."""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from backend.ai.sentiment_analyzer import SentimentAnalyzer
from backend.core.logger import get_logger
from backend.models import Signal
from backend.strategies.base import StrategyBase

logger = get_logger("sentiment_strategy")

BULLISH_THRESHOLD = 0.3
BEARISH_THRESHOLD = -0.3


class SentimentStrategy(StrategyBase):
    """Generates signals based on news sentiment analysis."""

    name = "sentiment"

    def __init__(self, analyzer: SentimentAnalyzer) -> None:
        self._analyzer = analyzer

    async def analyze(self, symbol: str, ohlcv: pd.DataFrame) -> Signal:
        result = await self._analyzer.analyze(symbol)

        sentiment = result["sentiment"]
        confidence = result["confidence"]
        summary = result["summary"]

        indicators = {
            "sentiment": sentiment,
            "sentiment_confidence": confidence,
        }

        if sentiment >= BULLISH_THRESHOLD and confidence > 0.3:
            return Signal(
                symbol=symbol,
                direction="BUY",
                confidence=min(abs(sentiment) * confidence, 1.0),
                strategy_name=self.name,
                reason=f"Bullish sentiment ({sentiment:.2f}): {summary}",
                indicators=indicators,
                timestamp=datetime.now(UTC),
            )

        if sentiment <= BEARISH_THRESHOLD and confidence > 0.3:
            return Signal(
                symbol=symbol,
                direction="SELL",
                confidence=min(abs(sentiment) * confidence, 1.0),
                strategy_name=self.name,
                reason=f"Bearish sentiment ({sentiment:.2f}): {summary}",
                indicators=indicators,
                timestamp=datetime.now(UTC),
            )

        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            strategy_name=self.name,
            reason=f"Neutral sentiment ({sentiment:.2f}): {summary}",
            indicators=indicators,
            timestamp=datetime.now(UTC),
        )
