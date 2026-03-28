from __future__ import annotations

from unittest.mock import AsyncMock

import pandas as pd

from backend.ai.market_analyzer import MarketAnalyzer
from backend.models import Signal


def _sample_ohlcv() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=50, freq="h"),
        "open": [65000.0] * 50,
        "high": [65200.0] * 50,
        "low": [64800.0] * 50,
        "close": [65100.0] * 50,
        "volume": [100.0] * 50,
    })


class TestMarketAnalyzer:
    async def test_analyze_market_calls_client(self):
        mock_client = AsyncMock()
        mock_client.analyze_market.return_value = {
            "condition": "trending_up",
            "strength": 0.8,
            "summary": "Bullish momentum",
            "key_levels": {"support": 63000, "resistance": 67000},
        }

        analyzer = MarketAnalyzer(mock_client)
        result = await analyzer.analyze_market(
            "BTC/USDT", _sample_ohlcv(), {"rsi": 45.0},
        )

        assert result["condition"] == "trending_up"
        mock_client.analyze_market.assert_called_once()

    async def test_filter_trade_approve(self):
        mock_client = AsyncMock()
        mock_client.filter_trade.return_value = {
            "decision": "approve",
            "confidence": 0.85,
            "reason": "Strong signal with low risk",
            "adjusted_size_pct": 1.0,
        }

        analyzer = MarketAnalyzer(mock_client)
        signal = Signal(
            symbol="BTC/USDT",
            direction="BUY",
            confidence=0.8,
            strategy_name="rsi",
            reason="Oversold",
        )
        result = await analyzer.filter_trade(
            signal=signal,
            market_condition="trending_up",
            balance={"USDT": 10000.0},
            risk_params="max 10% per trade",
        )

        assert result["decision"] == "approve"

    async def test_filter_trade_reject(self):
        mock_client = AsyncMock()
        mock_client.filter_trade.return_value = {
            "decision": "reject",
            "confidence": 0.0,
            "reason": "Market too volatile",
            "adjusted_size_pct": 0.0,
        }

        analyzer = MarketAnalyzer(mock_client)
        signal = Signal(
            symbol="BTC/USDT",
            direction="BUY",
            confidence=0.6,
            strategy_name="macd",
            reason="Crossover",
        )
        result = await analyzer.filter_trade(
            signal=signal,
            market_condition="volatile",
            balance={"USDT": 5000.0},
            risk_params="max 10% per trade",
        )

        assert result["decision"] == "reject"
        assert result["adjusted_size_pct"] == 0.0

    async def test_summarize_ohlcv(self):
        ohlcv = _sample_ohlcv()
        summary = MarketAnalyzer._summarize_ohlcv(ohlcv, last_n=3)

        assert "65000.00" in summary
        assert summary.count("\n") == 2
