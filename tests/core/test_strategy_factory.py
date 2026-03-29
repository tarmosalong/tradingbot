from __future__ import annotations

from backend.config import load_settings
from backend.core.strategy_factory import build_strategies


def test_build_strategies_returns_instances_for_enabled() -> None:
    settings = load_settings()
    strategies = build_strategies(settings)
    names = {type(s).__name__ for s in strategies}
    assert len(strategies) >= 1
    assert any("RSI" in n or "MACD" in n or "Bollinger" in n for n in names)
