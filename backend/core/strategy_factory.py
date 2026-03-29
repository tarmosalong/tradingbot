"""Build strategy instances from Settings (shared by CLI and API bot runner)."""
from __future__ import annotations

from backend.config import Settings
from backend.core.logger import get_logger
from backend.strategies import STRATEGY_REGISTRY
from backend.strategies.base import StrategyBase

logger = get_logger("strategy_factory")


def build_strategies(settings: Settings) -> list[StrategyBase]:
    """Instantiate enabled strategies from the registry."""
    strategies: list[StrategyBase] = []
    for name in settings.strategies.enabled:
        cls = STRATEGY_REGISTRY.get(name)
        if cls is None:
            logger.warning("Unknown strategy, skipping", name=name)
            continue

        config_map = {
            "rsi": settings.strategies.rsi,
            "macd": settings.strategies.macd,
            "bollinger": settings.strategies.bollinger,
        }

        if name == "ai_filter":
            instance = _build_ai_filter(settings)
            if instance:
                strategies.append(instance)
            continue

        if name == "sentiment":
            instance = _build_sentiment(settings)
            if instance:
                strategies.append(instance)
            continue

        cfg = config_map.get(name)
        strategies.append(cls(cfg) if cfg else cls())
    return strategies


def _build_ai_filter(settings: Settings) -> StrategyBase | None:
    if not settings.anthropic_api_key:
        logger.warning("ai_filter enabled but ANTHROPIC_API_KEY not set — skipping")
        return None
    try:
        from backend.ai.claude_client import ClaudeClient
        from backend.ai.market_analyzer import MarketAnalyzer
        from backend.strategies.ai_strategy import AIFilterStrategy

        client = ClaudeClient(api_key=settings.anthropic_api_key, config=settings.ai)
        analyzer = MarketAnalyzer(client)

        veto = None
        if settings.ai.veto_enabled and settings.openai_api_key:
            from backend.ai.openai_client import OpenAIClient as OpenAIProvider
            from backend.ai.veto_system import VetoSystem

            provider = OpenAIProvider(
                api_key=settings.openai_api_key,
                model=settings.ai.openai_model,
            )
            veto = VetoSystem(
                providers=[provider],
                min_agree=settings.ai.veto_min_agree,
            )

        return AIFilterStrategy(analyzer, veto_system=veto)
    except Exception:
        logger.exception("Failed to build ai_filter strategy")
        return None


def _build_sentiment(settings: Settings) -> StrategyBase | None:
    if not settings.anthropic_api_key:
        logger.warning("sentiment enabled but ANTHROPIC_API_KEY not set — skipping")
        return None
    try:
        from backend.ai.claude_client import ClaudeClient
        from backend.ai.sentiment_analyzer import SentimentAnalyzer
        from backend.strategies.sentiment import SentimentStrategy

        client = ClaudeClient(api_key=settings.anthropic_api_key, config=settings.ai)
        analyzer = SentimentAnalyzer(client)
        return SentimentStrategy(analyzer)
    except Exception:
        logger.exception("Failed to build sentiment strategy")
        return None
