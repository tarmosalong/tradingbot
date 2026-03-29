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
        cfg = config_map.get(name)
        strategies.append(cls(cfg) if cfg else cls())
    return strategies
