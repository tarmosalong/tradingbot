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
    rsi_params: dict[str, Any] | None = None,
    macd_params: dict[str, Any] | None = None,
    bollinger_params: dict[str, Any] | None = None,
    risk_params: dict[str, Any] | None = None,
    path: Path | None = None,
) -> None:
    """Merge allowed keys into config.yaml. Does not change trading.mode."""
    data = load_raw_config(path)

    if initial_balance_usdt is not None:
        if initial_balance_usdt < 100 or initial_balance_usdt > 1_000_000_000:
            raise ValueError("initial_balance_usdt out of allowed range")
        data.setdefault("paper_trading", {})
        data["paper_trading"]["initial_balance_usdt"] = float(
            initial_balance_usdt,
        )

    if pairs is not None:
        cleaned = [p.strip() for p in pairs if p and p.strip()]
        if not cleaned:
            raise ValueError("pairs must not be empty")
        data.setdefault("trading", {})
        data["trading"]["pairs"] = cleaned

    if timeframe is not None:
        valid_tf = (
            "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d",
        )
        if timeframe not in valid_tf:
            raise ValueError("unsupported timeframe")
        data.setdefault("trading", {})
        data["trading"]["timeframe"] = timeframe

    if poll_interval_seconds is not None:
        if poll_interval_seconds < 10 or poll_interval_seconds > 86_400:
            raise ValueError("poll_interval_seconds out of range")
        data.setdefault("trading", {})
        data["trading"]["poll_interval_seconds"] = int(
            poll_interval_seconds,
        )

    if strategies_enabled is not None:
        if not strategies_enabled:
            raise ValueError("strategies list must not be empty")
        if not any(s in ALLOWED_STRATEGIES for s in strategies_enabled):
            raise ValueError(
                "at least one registered technical strategy required",
            )
        data.setdefault("strategies", {})
        data["strategies"]["enabled"] = list(strategies_enabled)

    if rsi_params is not None:
        data.setdefault("strategies", {}).setdefault("rsi", {})
        _merge_bounded(data["strategies"]["rsi"], rsi_params, {
            "period": (2, 50),
            "oversold": (5, 45),
            "overbought": (55, 95),
        })

    if macd_params is not None:
        data.setdefault("strategies", {}).setdefault("macd", {})
        _merge_bounded(data["strategies"]["macd"], macd_params, {
            "fast": (2, 50),
            "slow": (10, 100),
            "signal": (2, 50),
        })

    if bollinger_params is not None:
        data.setdefault("strategies", {}).setdefault("bollinger", {})
        _merge_bounded(data["strategies"]["bollinger"], bollinger_params, {
            "period": (5, 50),
            "std_dev": (0.5, 4.0),
        })

    if risk_params is not None:
        data.setdefault("risk", {})
        _merge_bounded(data["risk"], risk_params, {
            "max_position_pct": (0.01, 1.0),
            "stop_loss_pct": (0.0, 0.20),
            "trailing_stop_pct": (0.0, 0.20),
            "max_drawdown_pct": (0.01, 0.50),
            "daily_loss_limit_pct": (0.01, 0.50),
            "max_single_order_usdt": (10, 100_000),
            "min_confidence": (0.0, 1.0),
            "max_concurrent_positions": (1, 20),
            "max_data_age_seconds": (60, 86_400),
            "max_price_deviation_pct": (0.01, 0.50),
            "circuit_breaker_threshold": (1, 50),
        })

    write_raw_config(data, path)


def _merge_bounded(
    target: dict[str, Any],
    source: dict[str, Any],
    bounds: dict[str, tuple[float, float]],
) -> None:
    for key, (lo, hi) in bounds.items():
        if key in source and source[key] is not None:
            val = float(source[key])
            if val < lo or val > hi:
                raise ValueError(
                    f"{key}={val} out of range [{lo}, {hi}]",
                )
            target[key] = int(val) if isinstance(lo, int) else val
