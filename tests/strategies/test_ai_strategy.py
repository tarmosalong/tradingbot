from __future__ import annotations

from unittest.mock import AsyncMock

import pandas as pd

from backend.ai.market_analyzer import MarketAnalyzer
from backend.core.exceptions import AIError
from backend.strategies.ai_strategy import AIFilterStrategy


def _sample_ohlcv(n: int = 50) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="h"),
        "open": [65000.0] * n,
        "high": [65200.0] * n,
        "low": [64800.0] * n,
        "close": [65100.0] * n,
        "volume": [100.0] * n,
    })


class TestAIFilterStrategy:
    async def test_trending_up_returns_buy(self):
        mock_client = AsyncMock()
        mock_client.analyze_market.return_value = {
            "condition": "trending_up",
            "strength": 0.8,
            "summary": "Strong bullish momentum",
        }
        analyzer = MarketAnalyzer(mock_client)
        strategy = AIFilterStrategy(analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv())

        assert signal.direction == "BUY"
        assert signal.confidence == 0.8
        assert "AI:" in signal.reason

    async def test_trending_down_returns_sell(self):
        mock_client = AsyncMock()
        mock_client.analyze_market.return_value = {
            "condition": "trending_down",
            "strength": 0.7,
            "summary": "Bearish pressure",
        }
        analyzer = MarketAnalyzer(mock_client)
        strategy = AIFilterStrategy(analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv())

        assert signal.direction == "SELL"
        assert signal.confidence == 0.7

    async def test_ranging_returns_hold(self):
        mock_client = AsyncMock()
        mock_client.analyze_market.return_value = {
            "condition": "ranging",
            "strength": 0.3,
            "summary": "Sideways market",
        }
        analyzer = MarketAnalyzer(mock_client)
        strategy = AIFilterStrategy(analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv())

        assert signal.direction == "HOLD"

    async def test_low_strength_trending_returns_hold(self):
        mock_client = AsyncMock()
        mock_client.analyze_market.return_value = {
            "condition": "trending_up",
            "strength": 0.3,
            "summary": "Weak uptrend",
        }
        analyzer = MarketAnalyzer(mock_client)
        strategy = AIFilterStrategy(analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv())

        assert signal.direction == "HOLD"

    async def test_ai_error_returns_hold(self):
        mock_client = AsyncMock()
        mock_client.analyze_market.side_effect = AIError("API down")
        analyzer = MarketAnalyzer(mock_client)
        strategy = AIFilterStrategy(analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv())

        assert signal.direction == "HOLD"
        assert "failed" in signal.reason.lower()

    async def test_insufficient_data_returns_hold(self):
        mock_client = AsyncMock()
        analyzer = MarketAnalyzer(mock_client)
        strategy = AIFilterStrategy(analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv(n=10))

        assert signal.direction == "HOLD"
        mock_client.analyze_market.assert_not_called()

    async def test_clamps_strength_to_valid_range(self):
        mock_client = AsyncMock()
        mock_client.analyze_market.return_value = {
            "condition": "trending_up",
            "strength": 1.5,
            "summary": "Very bullish",
        }
        analyzer = MarketAnalyzer(mock_client)
        strategy = AIFilterStrategy(analyzer)

        signal = await strategy.analyze("BTC/USDT", _sample_ohlcv())

        assert signal.confidence == 1.0
