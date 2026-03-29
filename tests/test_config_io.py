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


def test_patch_rsi_params(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    write_raw_config({}, path=p)
    patch_paper_dashboard_settings(
        rsi_params={"period": 21, "oversold": 25, "overbought": 75},
        path=p,
    )
    data = load_raw_config(p)
    assert data["strategies"]["rsi"]["period"] == 21
    assert data["strategies"]["rsi"]["oversold"] == 25
    assert data["strategies"]["rsi"]["overbought"] == 75


def test_patch_macd_params(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    write_raw_config({}, path=p)
    patch_paper_dashboard_settings(
        macd_params={"fast": 8, "slow": 21, "signal": 5},
        path=p,
    )
    data = load_raw_config(p)
    assert data["strategies"]["macd"]["fast"] == 8
    assert data["strategies"]["macd"]["slow"] == 21
    assert data["strategies"]["macd"]["signal"] == 5


def test_patch_bollinger_params(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    write_raw_config({}, path=p)
    patch_paper_dashboard_settings(
        bollinger_params={"period": 30, "std_dev": 2.5},
        path=p,
    )
    data = load_raw_config(p)
    assert data["strategies"]["bollinger"]["period"] == 30
    assert data["strategies"]["bollinger"]["std_dev"] == 2.5


def test_patch_risk_params(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    write_raw_config({}, path=p)
    patch_paper_dashboard_settings(
        risk_params={
            "max_position_pct": 0.15,
            "stop_loss_pct": 0.05,
            "trailing_stop_pct": 0.03,
            "max_single_order_usdt": 2000,
        },
        path=p,
    )
    data = load_raw_config(p)
    assert data["risk"]["max_position_pct"] == 0.15
    assert data["risk"]["stop_loss_pct"] == 0.05
    assert data["risk"]["trailing_stop_pct"] == 0.03
    assert data["risk"]["max_single_order_usdt"] == 2000


def test_patch_rejects_out_of_range_rsi(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    write_raw_config({}, path=p)
    with pytest.raises(ValueError, match="period"):
        patch_paper_dashboard_settings(
            rsi_params={"period": 100},
            path=p,
        )


def test_patch_rejects_out_of_range_risk(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    write_raw_config({}, path=p)
    with pytest.raises(ValueError, match="stop_loss_pct"):
        patch_paper_dashboard_settings(
            risk_params={"stop_loss_pct": 0.50},
            path=p,
        )
