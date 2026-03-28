from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.ai.claude_client import ClaudeClient
from backend.core.exceptions import AIError

SAMPLE_ANALYSIS = {
    "condition": "trending_up",
    "strength": 0.8,
    "summary": "Bullish",
    "key_levels": {"support": 60000, "resistance": 70000},
}

SAMPLE_RANGING = {
    "condition": "ranging",
    "strength": 0.3,
    "summary": "Sideways",
    "key_levels": {"support": 60000, "resistance": 65000},
}

SAMPLE_VOLATILE = {
    "condition": "volatile",
    "strength": 0.6,
    "summary": "High vol",
    "key_levels": {"support": 58000, "resistance": 68000},
}

SAMPLE_APPROVE = {
    "decision": "approve",
    "confidence": 0.9,
    "reason": "Good setup",
    "adjusted_size_pct": 0.8,
}


def _mock_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.content = [block]
    response.usage = MagicMock(
        input_tokens=input_tokens, output_tokens=output_tokens,
    )
    return response


def _mock_thinking_response(text: str):
    thinking = MagicMock()
    thinking.type = "thinking"
    thinking.thinking = "internal reasoning..."

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    response = MagicMock()
    response.content = [thinking, text_block]
    response.usage = MagicMock(input_tokens=200, output_tokens=100)
    return response


class TestClaudeClient:
    @patch("backend.ai.claude_client.anthropic.AsyncAnthropic")
    async def test_analyze_market_returns_parsed_json(self, mock_cls):
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_response(
            json.dumps(SAMPLE_ANALYSIS)
        )

        client = ClaudeClient(api_key="test-key")
        result = await client.analyze_market("system", "user prompt")

        assert result["condition"] == "trending_up"
        assert result["strength"] == 0.8
        assert client.call_count == 1

    @patch("backend.ai.claude_client.anthropic.AsyncAnthropic")
    async def test_handles_markdown_code_fences(self, mock_cls):
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        fenced = f"```json\n{json.dumps(SAMPLE_RANGING)}\n```"
        mock_client.messages.create.return_value = _mock_response(fenced)

        client = ClaudeClient(api_key="test-key")
        result = await client.analyze_market("system", "user prompt")

        assert result["condition"] == "ranging"

    @patch("backend.ai.claude_client.anthropic.AsyncAnthropic")
    async def test_handles_thinking_blocks(self, mock_cls):
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_thinking_response(
            json.dumps(SAMPLE_VOLATILE)
        )

        client = ClaudeClient(api_key="test-key")
        result = await client.analyze_market("system", "user prompt")

        assert result["condition"] == "volatile"

    @patch("backend.ai.claude_client.anthropic.AsyncAnthropic")
    async def test_invalid_json_raises_ai_error(self, mock_cls):
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_response(
            "This is not JSON at all"
        )

        client = ClaudeClient(api_key="test-key")
        with pytest.raises(AIError, match="Failed to parse"):
            await client.analyze_market("system", "user prompt")

    @patch("backend.ai.claude_client.anthropic.AsyncAnthropic")
    async def test_cache_hit_avoids_api_call(self, mock_cls):
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        cached_data = {
            "condition": "trending_up", "strength": 0.7,
            "summary": "Up", "key_levels": {},
        }
        mock_client.messages.create.return_value = _mock_response(
            json.dumps(cached_data)
        )

        client = ClaudeClient(api_key="test-key")
        result1 = await client.analyze_market(
            "system", "prompt", cache_key="test-cache",
        )
        result2 = await client.analyze_market(
            "system", "prompt", cache_key="test-cache",
        )

        assert result1 == result2
        assert client.call_count == 1

    @patch("backend.ai.claude_client.anthropic.AsyncAnthropic")
    async def test_filter_trade_no_cache(self, mock_cls):
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_response(
            json.dumps(SAMPLE_APPROVE)
        )

        client = ClaudeClient(api_key="test-key")
        result = await client.filter_trade("system", "prompt")

        assert result["decision"] == "approve"
        assert result["adjusted_size_pct"] == 0.8

    @patch("backend.ai.claude_client.anthropic.AsyncAnthropic")
    async def test_tracks_token_usage(self, mock_cls):
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        data = {"condition": "ranging", "strength": 0.5, "summary": "Flat", "key_levels": {}}
        mock_client.messages.create.return_value = _mock_response(
            json.dumps(data), input_tokens=200, output_tokens=80,
        )

        client = ClaudeClient(api_key="test-key")
        await client.analyze_market("system", "prompt")

        assert client.total_tokens == 280
