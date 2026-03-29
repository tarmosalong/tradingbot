"""OpenAI GPT wrapper implementing the LLMProvider interface."""
from __future__ import annotations

import asyncio
import json

import openai

from backend.ai.base_provider import LLMProvider
from backend.core.exceptions import AIError
from backend.core.logger import get_logger

logger = get_logger("openai_client")


class OpenAIClient(LLMProvider):
    """Async wrapper for the OpenAI API with rate limiting."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        max_calls_per_minute: int = 10,
    ) -> None:
        self._model = model
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._semaphore = asyncio.Semaphore(max_calls_per_minute)
        self._call_count = 0
        self._total_tokens = 0

    @property
    def name(self) -> str:
        return "openai"

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> dict:
        async with self._semaphore:
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    temperature=0.3,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
            except openai.APIError as e:
                logger.error("OpenAI API error", error=str(e))
                raise AIError(f"OpenAI API call failed: {e}") from e

        self._call_count += 1
        usage = response.usage
        if usage:
            self._total_tokens += usage.total_tokens

        logger.info(
            "OpenAI API call",
            model=self._model,
            call_count=self._call_count,
            tokens=usage.total_tokens if usage else 0,
        )

        raw_text = response.choices[0].message.content or ""
        return self._parse_json(raw_text)

    @staticmethod
    def _parse_json(text: str) -> dict:
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
                "Failed to parse OpenAI JSON response",
                raw_text=text[:500],
                error=str(e),
            )
            raise AIError(
                f"Failed to parse OpenAI response as JSON: {e}"
            ) from e

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def total_tokens(self) -> int:
        return self._total_tokens
