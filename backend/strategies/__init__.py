from __future__ import annotations

from backend.strategies.base import StrategyBase
from backend.strategies.technical import BollingerStrategy, MACDStrategy, RSIStrategy

STRATEGY_REGISTRY: dict[str, type[StrategyBase]] = {
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "bollinger": BollingerStrategy,
}
