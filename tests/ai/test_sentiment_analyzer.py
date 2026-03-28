from __future__ import annotations

from unittest.mock import AsyncMock

from backend.ai.sentiment_analyzer import NewsFetcher, SentimentAnalyzer
from backend.core.exceptions import AIError


class TestSentimentAnalyzer:
    async def test_bullish_sentiment(self):
        mock_claude = AsyncMock()
        mock_claude.analyze_sentiment.return_value = {
            "sentiment": 0.7,
            "confidence": 0.8,
            "summary": "Positive institutional adoption news",
            "key_topics": ["ETF", "adoption"],
        }
        mock_news = AsyncMock(spec=NewsFetcher)
        mock_news.fetch_headlines.return_value = [
            "Bitcoin ETF sees record inflows",
            "Major bank launches crypto trading",
        ]

        analyzer = SentimentAnalyzer(mock_claude, mock_news)
        result = await analyzer.analyze("BTC/USDT")

        assert result["sentiment"] == 0.7
        assert result["confidence"] == 0.8
        assert len(result["key_topics"]) == 2

    async def test_bearish_sentiment(self):
        mock_claude = AsyncMock()
        mock_claude.analyze_sentiment.return_value = {
            "sentiment": -0.6,
            "confidence": 0.7,
            "summary": "Regulatory crackdown fears",
            "key_topics": ["regulation", "ban"],
        }
        mock_news = AsyncMock(spec=NewsFetcher)
        mock_news.fetch_headlines.return_value = [
            "SEC announces new crypto regulations",
        ]

        analyzer = SentimentAnalyzer(mock_claude, mock_news)
        result = await analyzer.analyze("BTC/USDT")

        assert result["sentiment"] == -0.6

    async def test_no_headlines_returns_neutral(self):
        mock_claude = AsyncMock()
        mock_news = AsyncMock(spec=NewsFetcher)
        mock_news.fetch_headlines.return_value = []

        analyzer = SentimentAnalyzer(mock_claude, mock_news)
        result = await analyzer.analyze("BTC/USDT")

        assert result["sentiment"] == 0.0
        assert result["confidence"] == 0.0
        mock_claude.analyze_sentiment.assert_not_called()

    async def test_ai_error_returns_neutral(self):
        mock_claude = AsyncMock()
        mock_claude.analyze_sentiment.side_effect = AIError("API down")
        mock_news = AsyncMock(spec=NewsFetcher)
        mock_news.fetch_headlines.return_value = ["Some headline"]

        analyzer = SentimentAnalyzer(mock_claude, mock_news)
        result = await analyzer.analyze("BTC/USDT")

        assert result["sentiment"] == 0.0

    async def test_clamps_sentiment_range(self):
        mock_claude = AsyncMock()
        mock_claude.analyze_sentiment.return_value = {
            "sentiment": 2.5,
            "confidence": 1.5,
            "summary": "Extreme",
            "key_topics": [],
        }
        mock_news = AsyncMock(spec=NewsFetcher)
        mock_news.fetch_headlines.return_value = ["Headline"]

        analyzer = SentimentAnalyzer(mock_claude, mock_news)
        result = await analyzer.analyze("BTC/USDT")

        assert result["sentiment"] == 1.0
        assert result["confidence"] == 1.0
