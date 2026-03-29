from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.config_io import load_raw_config, patch_paper_dashboard_settings, write_raw_config


def test_patch_no_op_when_all_none(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("trading:\n  mode: paper\n")
    patch_paper_dashboard_settings(path=p)
    assert p.read_text() == "trading:\n  mode: paper\n"


def test_patch_balance_and_pairs(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    write_raw_config({"trading": {"mode": "paper", "pairs": ["BTC/USDT"]}}, path=p)
    patch_paper_dashboard_settings(
        initial_balance_usdt=5000.0,
        pairs=["ETH/USDT", "SOL/USDT"],
        path=p,
    )
    data = load_raw_config(p)
    assert data["paper_trading"]["initial_balance_usdt"] == 5000.0
    assert data["trading"]["pairs"] == ["ETH/USDT", "SOL/USDT"]
    assert data["trading"]["mode"] == "paper"


def test_patch_rejects_invalid_balance(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    write_raw_config({"trading": {"mode": "paper"}}, path=p)
    with pytest.raises(ValueError, match="initial_balance"):
        patch_paper_dashboard_settings(initial_balance_usdt=50.0, path=p)


def test_patch_rejects_empty_pairs(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    write_raw_config({}, path=p)
    with pytest.raises(ValueError, match="pairs"):
        patch_paper_dashboard_settings(pairs=[], path=p)


def test_patch_strategies_keeps_non_registry_names(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    write_raw_config({"strategies": {"enabled": ["rsi"]}}, path=p)
    patch_paper_dashboard_settings(
        strategies_enabled=["ai_filter", "rsi", "macd", "sentiment"],
        path=p,
    )
    data = yaml.safe_load(p.read_text())
    assert data["strategies"]["enabled"] == [
        "ai_filter",
        "rsi",
        "macd",
        "sentiment",
    ]


def test_patch_rejects_no_registered_technical_strategy(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    write_raw_config({}, path=p)
    with pytest.raises(ValueError, match="registered technical"):
        patch_paper_dashboard_settings(strategies_enabled=["ai_filter", "sentiment"], path=p)
