"""Read/write config.yaml for dashboard-driven paper trading settings."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from backend.config import _project_root
from backend.strategies import STRATEGY_REGISTRY

ALLOWED_STRATEGIES = frozenset(STRATEGY_REGISTRY.keys())


def config_yaml_path() -> Path:
    return _project_root() / "config.yaml"


def load_raw_config(path: Path | None = None) -> dict[str, Any]:
    p = path or config_yaml_path()
    if not p.exists():
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


def write_raw_config(data: dict[str, Any], path: Path | None = None) -> None:
    p = path or config_yaml_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".yaml.tmp")
    with open(tmp, "w") as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    os.replace(tmp, p)


def patch_paper_dashboard_settings(
    *,
    initial_balance_usdt: float | None = None,
    pairs: list[str] | None = None,
    timeframe: str | None = None,
    poll_interval_seconds: int | None = None,
    strategies_enabled: list[str] | None = None,
    path: Path | None = None,
) -> None:
    """Merge allowed keys into config.yaml. Does not change trading.mode."""
    if all(
        x is None
        for x in (
            initial_balance_usdt,
            pairs,
            timeframe,
            poll_interval_seconds,
            strategies_enabled,
        )
    ):
        return

    data = load_raw_config(path)

    if initial_balance_usdt is not None:
        if initial_balance_usdt < 100 or initial_balance_usdt > 1_000_000_000:
            raise ValueError("initial_balance_usdt out of allowed range")
        data.setdefault("paper_trading", {})
        data["paper_trading"]["initial_balance_usdt"] = float(initial_balance_usdt)

    if pairs is not None:
        cleaned = [p.strip() for p in pairs if p and p.strip()]
        if not cleaned:
            raise ValueError("pairs must not be empty")
        data.setdefault("trading", {})
        data["trading"]["pairs"] = cleaned

    if timeframe is not None:
        if timeframe not in ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"):
            raise ValueError("unsupported timeframe")
        data.setdefault("trading", {})
        data["trading"]["timeframe"] = timeframe

    if poll_interval_seconds is not None:
        if poll_interval_seconds < 10 or poll_interval_seconds > 86_400:
            raise ValueError("poll_interval_seconds out of range")
        data.setdefault("trading", {})
        data["trading"]["poll_interval_seconds"] = int(poll_interval_seconds)

    if strategies_enabled is not None:
        filtered = [s for s in strategies_enabled if s in ALLOWED_STRATEGIES]
        if not filtered:
            raise ValueError("at least one valid strategy required")
        data.setdefault("strategies", {})
        data["strategies"]["enabled"] = filtered

    write_raw_config(data, path)
