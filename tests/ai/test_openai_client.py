from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.ai.openai_client import OpenAIClient
from backend.core.exceptions import AIError


def _mock_response(content: dict, total_tokens: int = 100):
    usage = MagicMock()
    usage.total_tokens = total_tokens
    choice = MagicMock()
    choice.message.content = json.dumps(content)
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


class TestOpenAIClient:
    @pytest.mark.asyncio
    async def test_analyze_returns_parsed_json(self):
        expected = {"score": 0.7, "direction": "BUY", "reasoning": "bullish"}
        mock_resp = _mock_response(expected)

        client = OpenAIClient(api_key="test-key", model="gpt-4o")
        client._client = MagicMock()
        client._client.chat.completions.create = AsyncMock(return_value=mock_resp)

        result = await client.analyze("system", "user")
        assert result == expected
        assert client.call_count == 1
        assert client.total_tokens == 100

    @pytest.mark.asyncio
    async def test_analyze_strips_code_fences(self):
        content = '```json\n{"score": 0.5}\n```'
        choice = MagicMock()
        choice.message.content = content
        usage = MagicMock()
        usage.total_tokens = 50
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage

        client = OpenAIClient(api_key="test-key")
        client._client = MagicMock()
        client._client.chat.completions.create = AsyncMock(return_value=resp)

        result = await client.analyze("sys", "usr")
        assert result["score"] == 0.5

    @pytest.mark.asyncio
    async def test_analyze_raises_on_invalid_json(self):
        choice = MagicMock()
        choice.message.content = "not json"
        usage = MagicMock()
        usage.total_tokens = 10
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage

        client = OpenAIClient(api_key="test-key")
        client._client = MagicMock()
        client._client.chat.completions.create = AsyncMock(return_value=resp)

        with pytest.raises(AIError, match="Failed to parse"):
            await client.analyze("sys", "usr")

    def test_name_property(self):
        client = OpenAIClient(api_key="test-key")
        assert client.name == "openai"

    def test_implements_llm_provider(self):
        from backend.ai.base_provider import LLMProvider

        client = OpenAIClient(api_key="test-key")
        assert isinstance(client, LLMProvider)
