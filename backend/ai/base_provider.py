"""Abstract base for LLM providers used in the veto system."""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Common interface for AI model providers (Claude, GPT, etc.)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this provider (e.g. 'claude', 'openai')."""
        ...

    @abstractmethod
    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> dict:
        """Send a prompt and return the parsed JSON response."""
        ...
