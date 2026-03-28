from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import anthropic

from backend.config import AIConfig
from backend.core.exceptions import AIError
from backend.core.logger import get_logger

logger = get_logger("claude")


class ClaudeClient:
    """Async wrapper for the Anthropic Claude API with rate limiting and caching."""

    def __init__(self, api_key: str, config: AIConfig | None = None) -> None:
        self._config = config or AIConfig()
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._semaphore = asyncio.Semaphore(self._config.max_calls_per_minute)
        self._cache: dict[str, tuple[float, Any]] = {}
        self._call_count = 0
        self._total_tokens = 0

    async def analyze_market(
        self,
        system_prompt: str,
        user_prompt: str,
        cache_key: str | None = None,
    ) -> dict:
        """Call Claude for market analysis. Returns parsed JSON dict."""
        return await self._call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=self._config.max_tokens_analysis,
            cache_key=cache_key,
            cache_ttl=self._config.analysis_cache_ttl_seconds,
        )

    async def filter_trade(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        """Call Claude to approve/reject a trade. No caching (time-sensitive)."""
        return await self._call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=self._config.max_tokens_analysis,
            cache_key=None,
            cache_ttl=0,
        )

    async def analyze_sentiment(
        self,
        system_prompt: str,
        user_prompt: str,
        cache_key: str | None = None,
    ) -> dict:
        """Call Claude for sentiment analysis. Returns parsed JSON dict."""
        return await self._call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=self._config.max_tokens_sentiment,
            cache_key=cache_key,
            cache_ttl=self._config.sentiment_cache_ttl_seconds,
        )

    async def _call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        cache_key: str | None,
        cache_ttl: int,
    ) -> dict:
        if cache_key:
            cached = self._get_cached(cache_key, cache_ttl)
            if cached is not None:
                logger.debug("Cache hit", cache_key=cache_key)
                return cached

        async with self._semaphore:
            try:
                response = await self._client.messages.create(
                    model=self._config.model,
                    max_tokens=max_tokens,
                    thinking={"type": "adaptive"},
                    temperature=1,
                    messages=[
                        {"role": "user", "content": user_prompt},
                    ],
                    system=system_prompt,
                )
            except anthropic.APIError as e:
                logger.error("Claude API error", error=str(e))
                raise AIError(f"Claude API call failed: {e}") from e

        self._call_count += 1
        input_tokens = getattr(response.usage, "input_tokens", 0)
        output_tokens = getattr(response.usage, "output_tokens", 0)
        self._total_tokens += input_tokens + output_tokens

        logger.info(
            "Claude API call",
            call_count=self._call_count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=self._total_tokens,
        )

        raw_text = self._extract_text(response)
        result = self._parse_json(raw_text)

        if cache_key:
            self._cache[cache_key] = (time.monotonic(), result)

        return result

    @staticmethod
    def _extract_text(response) -> str:
        """Extract text content from Claude response, skipping thinking blocks."""
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse JSON from Claude response, handling markdown code fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse Claude JSON response",
                raw_text=text[:500],
                error=str(e),
            )
            raise AIError(f"Failed to parse Claude response as JSON: {e}") from e

    def _get_cached(self, key: str, ttl: int) -> Any | None:
        if key not in self._cache:
            return None
        cached_time, value = self._cache[key]
        if time.monotonic() - cached_time > ttl:
            del self._cache[key]
            return None
        return value

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def total_tokens(self) -> int:
        return self._total_tokens
