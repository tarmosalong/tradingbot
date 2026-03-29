from __future__ import annotations

import pytest

from backend.ai.base_provider import LLMProvider
from backend.ai.veto_system import VetoSystem
from backend.core.exceptions import AIError


class MockProvider(LLMProvider):
    """Test provider that returns a canned response."""

    def __init__(
        self,
        provider_name: str,
        score: float,
        direction: str,
        should_fail: bool = False,
    ) -> None:
        self._name = provider_name
        self._score = score
        self._direction = direction
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return self._name

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> dict:
        if self._should_fail:
            raise AIError("Provider unavailable")
        return {
            "score": self._score,
            "direction": self._direction,
            "reasoning": f"{self._name} analysis",
        }


class TestVetoQuorum:
    @pytest.mark.asyncio
    async def test_all_agree_approves(self):
        providers = [
            MockProvider("p1", 0.8, "BUY"),
            MockProvider("p2", 0.7, "BUY"),
            MockProvider("p3", 0.6, "BUY"),
        ]
        veto = VetoSystem(providers, min_agree=2)
        result = await veto.evaluate("test signal", "BUY")

        assert result.approved is True
        assert result.direction == "BUY"
        assert result.providers_agreed == 3
        assert result.providers_responded == 3

    @pytest.mark.asyncio
    async def test_majority_agree_approves(self):
        providers = [
            MockProvider("claude", 0.8, "BUY"),
            MockProvider("gpt", 0.6, "BUY"),
            MockProvider("gemini", -0.3, "SELL"),
        ]
        veto = VetoSystem(providers, min_agree=2)
        result = await veto.evaluate("test signal", "BUY")

        assert result.approved is True
        assert result.providers_agreed == 2

    @pytest.mark.asyncio
    async def test_no_quorum_rejects(self):
        providers = [
            MockProvider("claude", 0.8, "BUY"),
            MockProvider("gpt", -0.5, "SELL"),
            MockProvider("gemini", -0.3, "SELL"),
        ]
        veto = VetoSystem(providers, min_agree=2)
        result = await veto.evaluate("test signal", "BUY")

        assert result.approved is False
        assert result.providers_agreed == 1
        assert "vetoed" in result.reasoning

    @pytest.mark.asyncio
    async def test_sell_direction_quorum(self):
        providers = [
            MockProvider("p1", -0.8, "SELL"),
            MockProvider("p2", -0.6, "SELL"),
        ]
        veto = VetoSystem(providers, min_agree=2)
        result = await veto.evaluate("test signal", "SELL")

        assert result.approved is True
        assert result.direction == "SELL"


class TestVetoErrorHandling:
    @pytest.mark.asyncio
    async def test_one_provider_fails_still_works(self):
        providers = [
            MockProvider("claude", 0.8, "BUY"),
            MockProvider("gpt", 0.7, "BUY"),
            MockProvider("broken", 0.0, "BUY", should_fail=True),
        ]
        veto = VetoSystem(providers, min_agree=2)
        result = await veto.evaluate("test signal", "BUY")

        assert result.approved is True
        assert result.providers_responded == 2
        error_votes = [v for v in result.votes if v.error]
        assert len(error_votes) == 1

    @pytest.mark.asyncio
    async def test_all_providers_fail_rejects(self):
        providers = [
            MockProvider("p1", 0.0, "BUY", should_fail=True),
            MockProvider("p2", 0.0, "BUY", should_fail=True),
        ]
        veto = VetoSystem(providers, min_agree=2)
        result = await veto.evaluate("test signal", "BUY")

        assert result.approved is False
        assert result.providers_responded == 0


class TestVetoScoring:
    @pytest.mark.asyncio
    async def test_avg_score_calculated(self):
        providers = [
            MockProvider("p1", 0.8, "BUY"),
            MockProvider("p2", 0.4, "BUY"),
        ]
        veto = VetoSystem(providers, min_agree=2)
        result = await veto.evaluate("test signal", "BUY")

        assert abs(result.avg_score - 0.6) < 0.001

    @pytest.mark.asyncio
    async def test_votes_contain_provider_names(self):
        providers = [
            MockProvider("claude", 0.8, "BUY"),
            MockProvider("gpt", 0.6, "BUY"),
        ]
        veto = VetoSystem(providers, min_agree=2)
        result = await veto.evaluate("test signal", "BUY")

        names = {v.provider_name for v in result.votes}
        assert "claude" in names
        assert "gpt" in names

    @pytest.mark.asyncio
    async def test_min_agree_capped_to_provider_count(self):
        providers = [
            MockProvider("p1", 0.8, "BUY"),
        ]
        veto = VetoSystem(providers, min_agree=5)
        result = await veto.evaluate("test signal", "BUY")

        assert result.approved is True
