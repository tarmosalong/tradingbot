from __future__ import annotations

from backend.strategies.ai_strategy import AIFilterStrategy
from backend.strategies.base import StrategyBase
from backend.strategies.sentiment import SentimentStrategy
from backend.strategies.technical import (
    BollingerStrategy,
    EMAStrategy,
    MACDStrategy,
    RSIStrategy,
)

STRATEGY_REGISTRY: dict[str, type[StrategyBase]] = {
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "bollinger": BollingerStrategy,
    "ema": EMAStrategy,
    "ai_filter": AIFilterStrategy,
    "sentiment": SentimentStrategy,
}
