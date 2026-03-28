from __future__ import annotations

from unittest.mock import AsyncMock

import pandas as pd

from backend.ai.sentiment_analyzer import SentimentAnalyzer
from backend.strategies.sentiment import SentimentStrategy


def _sample_ohlcv() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=50, freq="h"),
        "open": [65000.0] * 50,
        "high": [65200.0] * 50,
        "low": [64800.0] * 50,
        "close": [65100.0] * 50,
        "volume": [100.0] * 50,
    })


class TestSentimentStrategy:
    async def test_bullish_sentiment_returns_buy(self):
        mock_claude = AsyncMock()
        mock_analyzer = SentimentAnalyzer(mock_claude)
        mock_analyzer.analyze = AsyncMock(return_value={
            "sentiment": 0.6,
            "confidence": 0.8,
            "summary": "Positive outlook",
            "key_topics": ["bullish"],
        })
        strategy = SentimentStrategy(mock_analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv())

        assert signal.direction == "BUY"
        assert signal.confidence > 0

    async def test_bearish_sentiment_returns_sell(self):
        mock_claude = AsyncMock()
        mock_analyzer = SentimentAnalyzer(mock_claude)
        mock_analyzer.analyze = AsyncMock(return_value={
            "sentiment": -0.5,
            "confidence": 0.7,
            "summary": "Negative news",
            "key_topics": ["bearish"],
        })
        strategy = SentimentStrategy(mock_analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv())

        assert signal.direction == "SELL"

    async def test_neutral_sentiment_returns_hold(self):
        mock_claude = AsyncMock()
        mock_analyzer = SentimentAnalyzer(mock_claude)
        mock_analyzer.analyze = AsyncMock(return_value={
            "sentiment": 0.1,
            "confidence": 0.5,
            "summary": "Mixed signals",
            "key_topics": [],
        })
        strategy = SentimentStrategy(mock_analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv())

        assert signal.direction == "HOLD"

    async def test_low_confidence_returns_hold(self):
        mock_claude = AsyncMock()
        mock_analyzer = SentimentAnalyzer(mock_claude)
        mock_analyzer.analyze = AsyncMock(return_value={
            "sentiment": 0.8,
            "confidence": 0.1,
            "summary": "Uncertain",
            "key_topics": [],
        })
        strategy = SentimentStrategy(mock_analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv())

        assert signal.direction == "HOLD"

    async def test_includes_sentiment_indicators(self):
        mock_claude = AsyncMock()
        mock_analyzer = SentimentAnalyzer(mock_claude)
        mock_analyzer.analyze = AsyncMock(return_value={
            "sentiment": 0.5,
            "confidence": 0.6,
            "summary": "Positive",
            "key_topics": [],
        })
        strategy = SentimentStrategy(mock_analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv())

        assert "sentiment" in signal.indicators
        assert "sentiment_confidence" in signal.indicators
