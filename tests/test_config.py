from __future__ import annotations

from pathlib import Path

from backend.config import load_settings


class TestLoadSettings:
    def test_loads_default_config_yaml(self):
        settings = load_settings()

        assert settings.trading.mode == "paper"
        assert "BTC/USDT" in settings.trading.pairs
        assert settings.trading.timeframe == "1h"

    def test_default_paper_balance(self):
        settings = load_settings()

        assert settings.paper_trading.initial_balance_usdt == 10_000.0

    def test_strategy_defaults(self):
        settings = load_settings()

        assert settings.strategies.rsi.period == 14
        assert settings.strategies.rsi.oversold == 30
        assert settings.strategies.macd.fast == 12
        assert settings.strategies.bollinger.std_dev == 2.0

    def test_risk_defaults(self):
        settings = load_settings()

        assert settings.risk.max_position_pct == 0.10
        assert settings.risk.stop_loss_pct == 0.03
        assert settings.risk.max_single_order_usdt == 1000.0

    def test_ai_config(self):
        settings = load_settings()

        assert settings.ai.model == "claude-opus-4-6"
        assert settings.ai.max_calls_per_minute == 10

    def test_missing_config_file_uses_defaults(self, tmp_path: Path):
        settings = load_settings(config_path=tmp_path / "nonexistent.yaml")

        assert settings.trading.mode == "paper"
        assert settings.strategies.rsi.period == 14

    def test_env_override_trading_mode(self, monkeypatch: object):
        monkeypatch.setenv("TRADING_MODE", "live")

        settings = load_settings()

        assert settings.trading.mode == "live"
