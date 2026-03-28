"""Technical analysis strategies: RSI, MACD, Bollinger Bands.

Each receives OHLCV data and returns a Signal. Actual indicator computation
will be wired up in Phase 3 using pandas-ta. This file provides the class
skeletons and basic logic so the import chain works from Phase 1 onward.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from backend.config import BollingerConfig, MACDConfig, RSIConfig
from backend.models import Signal
from backend.strategies.base import StrategyBase


class RSIStrategy(StrategyBase):
    name = "rsi"

    def __init__(self, config: RSIConfig | None = None) -> None:
        self._cfg = config or RSIConfig()

    async def analyze(self, symbol: str, ohlcv: pd.DataFrame) -> Signal:
        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            strategy_name=self.name,
            reason="not implemented yet",
            timestamp=datetime.now(UTC),
        )


class MACDStrategy(StrategyBase):
    name = "macd"

    def __init__(self, config: MACDConfig | None = None) -> None:
        self._cfg = config or MACDConfig()

    async def analyze(self, symbol: str, ohlcv: pd.DataFrame) -> Signal:
        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            strategy_name=self.name,
            reason="not implemented yet",
            timestamp=datetime.now(UTC),
        )


class BollingerStrategy(StrategyBase):
    name = "bollinger"

    def __init__(self, config: BollingerConfig | None = None) -> None:
        self._cfg = config or BollingerConfig()

    async def analyze(self, symbol: str, ohlcv: pd.DataFrame) -> Signal:
        return Signal(
            symbol=symbol,
            direction="HOLD",
            confidence=0.0,
            strategy_name=self.name,
            reason="not implemented yet",
            timestamp=datetime.now(UTC),
        )
