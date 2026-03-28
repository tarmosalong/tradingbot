from __future__ import annotations

import aiohttp

from backend.ai.claude_client import ClaudeClient
from backend.ai.prompts import SENTIMENT_ANALYSIS_SYSTEM, build_sentiment_prompt
from backend.core.exceptions import AIError
from backend.core.logger import get_logger

logger = get_logger("sentiment")

CRYPTOPANIC_API = "https://cryptopanic.com/api/free/v1/posts/"
SYMBOL_MAP = {
    "BTC": "BTC",
    "ETH": "ETH",
    "SOL": "SOL",
    "XRP": "XRP",
}


class NewsFetcher:
    """Fetches crypto news headlines from CryptoPanic free API or RSS."""

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key

    async def fetch_headlines(
        self, symbol: str, limit: int = 15
    ) -> list[str]:
        """Fetch recent news headlines for a crypto symbol."""
        base_currency = symbol.split("/")[0]
        currency_filter = SYMBOL_MAP.get(base_currency, base_currency)

        params: dict[str, str | int] = {
            "currencies": currency_filter,
            "kind": "news",
            "limit": limit,
        }
        if self._api_key:
            params["auth_token"] = self._api_key

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    CRYPTOPANIC_API, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "CryptoPanic API error",
                            status=resp.status,
                            symbol=symbol,
                        )
                        return []
                    data = await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            logger.exception("Failed to fetch news", symbol=symbol)
            return []

        results = data.get("results", [])
        return [item.get("title", "") for item in results if item.get("title")]


class SentimentAnalyzer:
    """Uses news headlines + Claude to produce a sentiment score."""

    def __init__(
        self,
        claude_client: ClaudeClient,
        news_fetcher: NewsFetcher | None = None,
    ) -> None:
        self._claude = claude_client
        self._news = news_fetcher or NewsFetcher()

    async def analyze(self, symbol: str) -> dict:
        """Fetch news and get Claude's sentiment assessment.

        Returns dict with keys: sentiment (-1..1), confidence (0..1),
        summary (str), key_topics (list[str]).
        Falls back to neutral on any error.
        """
        headlines = await self._news.fetch_headlines(symbol)

        if not headlines:
            logger.info("No headlines found", symbol=symbol)
            return self._neutral(symbol)

        prompt = build_sentiment_prompt(symbol, headlines)

        try:
            result = await self._claude.analyze_sentiment(
                system_prompt=SENTIMENT_ANALYSIS_SYSTEM,
                user_prompt=prompt,
                cache_key=f"sentiment:{symbol}",
            )
        except AIError:
            logger.exception("Sentiment analysis failed", symbol=symbol)
            return self._neutral(symbol)

        sentiment = float(result.get("sentiment", 0.0))
        sentiment = max(-1.0, min(1.0, sentiment))

        confidence = float(result.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        logger.info(
            "Sentiment analysis complete",
            symbol=symbol,
            sentiment=sentiment,
            confidence=confidence,
            headline_count=len(headlines),
        )

        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "summary": result.get("summary", ""),
            "key_topics": result.get("key_topics", []),
        }

    @staticmethod
    def _neutral(symbol: str) -> dict:
        return {
            "sentiment": 0.0,
            "confidence": 0.0,
            "summary": f"No data available for {symbol}",
            "key_topics": [],
        }
