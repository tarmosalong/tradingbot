from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from backend.models import Signal


class StrategyBase(ABC):
    """Base class for all trading strategies."""

    name: str = "base"

    @abstractmethod
    async def analyze(self, symbol: str, ohlcv: pd.DataFrame) -> Signal:
        """Analyze OHLCV data and return a trading signal."""
        ...
