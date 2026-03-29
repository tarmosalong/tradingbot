"""Multi-LLM veto system: requires quorum agreement before approving a trade."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from backend.ai.base_provider import LLMProvider
from backend.core.exceptions import AIError
from backend.core.logger import get_logger

logger = get_logger("veto_system")

VETO_SYSTEM_PROMPT = (
    """You are a crypto market analyst. """
    """Evaluate the trading signal described below.

Return ONLY valid JSON in this exact format:
{
  "score": -1.0 to 1.0,
  "direction": "BUY" | "SELL" | "NEUTRAL",
  "reasoning": "brief 1-2 sentence explanation"
}

score scale: -1.0 = strongly bearish, 0.0 = neutral, 1.0 = strongly bullish.
direction: your recommended action based on the data.
Be decisive — avoid scores near 0 unless the data is truly ambiguous."""
)


@dataclass
class ProviderVote:
    provider_name: str
    score: float
    direction: str
    reasoning: str
    error: str | None = None


@dataclass
class VetoResult:
    approved: bool
    avg_score: float
    direction: str
    votes: list[ProviderVote] = field(default_factory=list)
    reasoning: str = ""
    providers_responded: int = 0
    providers_agreed: int = 0


class VetoSystem:
    """Queries multiple LLM providers in parallel and requires quorum agreement."""

    def __init__(
        self,
        providers: list[LLMProvider],
        min_agree: int = 2,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._providers = providers
        self._min_agree = min(min_agree, len(providers))
        self._timeout = timeout_seconds

    async def evaluate(
        self,
        signal_description: str,
        expected_direction: str,
    ) -> VetoResult:
        """Ask all providers to evaluate, return veto result."""
        tasks = [
            self._query_provider(p, signal_description)
            for p in self._providers
        ]

        try:
            votes = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self._timeout,
            )
        except TimeoutError:
            logger.warning("Veto system timed out")
            return VetoResult(
                approved=False,
                avg_score=0.0,
                direction="NEUTRAL",
                reasoning="Veto timed out — defaulting to reject",
            )

        result = VetoResult(
            approved=False,
            avg_score=0.0,
            direction="NEUTRAL",
        )

        for vote in votes:
            if isinstance(vote, BaseException):
                result.votes.append(ProviderVote(
                    provider_name="unknown",
                    score=0.0,
                    direction="NEUTRAL",
                    reasoning="",
                    error=str(vote),
                ))
            else:
                result.votes.append(vote)

        valid_votes = [v for v in result.votes if v.error is None]
        result.providers_responded = len(valid_votes)

        if not valid_votes:
            result.reasoning = "No providers responded — defaulting to reject"
            return result

        scores = [v.score for v in valid_votes]
        result.avg_score = sum(scores) / len(scores)

        agreeing = sum(
            1 for v in valid_votes
            if v.direction == expected_direction
        )
        result.providers_agreed = agreeing

        result.approved = agreeing >= self._min_agree

        if result.approved:
            result.direction = expected_direction
            result.reasoning = (
                f"{agreeing}/{len(valid_votes)} providers agree on "
                f"{expected_direction} (avg score: {result.avg_score:.2f})"
            )
        else:
            result.direction = "NEUTRAL"
            result.reasoning = (
                f"Only {agreeing}/{len(valid_votes)} providers agree on "
                f"{expected_direction} (need {self._min_agree}) — vetoed"
            )

        logger.info(
            "Veto evaluation",
            approved=result.approved,
            direction=expected_direction,
            agreed=agreeing,
            responded=len(valid_votes),
            avg_score=f"{result.avg_score:.2f}",
        )

        return result

    async def _query_provider(
        self,
        provider: LLMProvider,
        signal_description: str,
    ) -> ProviderVote:
        try:
            resp = await provider.analyze(
                system_prompt=VETO_SYSTEM_PROMPT,
                user_prompt=signal_description,
                max_tokens=512,
            )
            return ProviderVote(
                provider_name=provider.name,
                score=float(resp.get("score", 0.0)),
                direction=resp.get("direction", "NEUTRAL"),
                reasoning=resp.get("reasoning", ""),
            )
        except (AIError, Exception) as e:
            logger.warning(
                "Provider failed in veto",
                provider=provider.name,
                error=str(e),
            )
            return ProviderVote(
                provider_name=provider.name,
                score=0.0,
                direction="NEUTRAL",
                reasoning="",
                error=str(e),
            )
