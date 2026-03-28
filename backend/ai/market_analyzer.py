from __future__ import annotations

import pandas as pd

from backend.ai.claude_client import ClaudeClient
from backend.ai.prompts import (
    MARKET_ANALYSIS_SYSTEM,
    TRADE_FILTER_SYSTEM,
    build_market_analysis_prompt,
    build_trade_filter_prompt,
)
from backend.core.logger import get_logger
from backend.models import Signal

logger = get_logger("market_analyzer")


class MarketAnalyzer:
    """Uses Claude to analyze market conditions and filter trade signals."""

    def __init__(self, client: ClaudeClient) -> None:
        self._client = client

    async def analyze_market(
        self,
        symbol: str,
        ohlcv: pd.DataFrame,
        indicators: dict[str, float],
    ) -> dict:
        """Get Claude's assessment of current market conditions."""
        current_price = float(ohlcv["close"].iloc[-1])
        ohlcv_summary = self._summarize_ohlcv(ohlcv)

        prompt = build_market_analysis_prompt(
            symbol=symbol,
            ohlcv_summary=ohlcv_summary,
            indicators=indicators,
            current_price=current_price,
        )

        result = await self._client.analyze_market(
            system_prompt=MARKET_ANALYSIS_SYSTEM,
            user_prompt=prompt,
            cache_key=f"market:{symbol}",
        )

        logger.info(
            "Market analysis complete",
            symbol=symbol,
            condition=result.get("condition"),
            strength=result.get("strength"),
        )
        return result

    async def filter_trade(
        self,
        signal: Signal,
        market_condition: str,
        balance: dict[str, float],
        risk_params: str,
    ) -> dict:
        """Ask Claude to approve or reject a proposed trade."""
        prompt = build_trade_filter_prompt(
            symbol=signal.symbol,
            direction=signal.direction,
            confidence=signal.confidence,
            reason=signal.reason,
            market_condition=market_condition,
            balance=balance,
            risk_params=risk_params,
        )

        result = await self._client.filter_trade(
            system_prompt=TRADE_FILTER_SYSTEM,
            user_prompt=prompt,
        )

        logger.info(
            "Trade filter result",
            symbol=signal.symbol,
            direction=signal.direction,
            decision=result.get("decision"),
            ai_confidence=result.get("confidence"),
        )
        return result

    @staticmethod
    def _summarize_ohlcv(ohlcv: pd.DataFrame, last_n: int = 10) -> str:
        """Create a text summary of recent price action."""
        recent = ohlcv.tail(last_n)
        lines = []
        for _, row in recent.iterrows():
            lines.append(
                f"O:{row['open']:.2f} H:{row['high']:.2f} "
                f"L:{row['low']:.2f} C:{row['close']:.2f} V:{row['volume']:.0f}"
            )
        return "\n".join(lines)
