from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from backend.config import (
    ExchangeConfig,
    RiskConfig,
    Settings,
    TradingConfig,
)
from backend.core.exceptions import ConfigError
from backend.core.safety import LiveTradingGuard


def _paper_settings() -> Settings:
    return Settings(
        trading=TradingConfig(mode="paper"),
    )


def _live_settings(
    api_key: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    api_secret: str = "secretsecretsecretsecret",
    risk: RiskConfig | None = None,
) -> Settings:
    return Settings(
        trading=TradingConfig(mode="live", pairs=["BTC/USDT"]),
        exchange=ExchangeConfig(name="binance"),
        risk=risk or RiskConfig(),
        binance_api_key=api_key,
        binance_api_secret=api_secret,
    )


class TestLiveTradingGuardPaper:
    def test_paper_mode_verifies_immediately(self):
        guard = LiveTradingGuard(_paper_settings())
        guard.verify_live_trading()
        assert guard.is_verified
        assert not guard.is_live

    def test_paper_assert_can_trade_passes_after_verify(self):
        guard = LiveTradingGuard(_paper_settings())
        guard.verify_live_trading()
        guard.assert_can_trade()

    def test_unverified_assert_raises(self):
        guard = LiveTradingGuard(_paper_settings())
        with pytest.raises(ConfigError, match="not verified"):
            guard.assert_can_trade()


class TestLiveTradingGuardLive:
    @patch.dict(os.environ, {"CONFIRM_LIVE_TRADING": "YES_I_UNDERSTAND_THE_RISKS"})
    def test_live_verifies_with_all_checks(self):
        guard = LiveTradingGuard(_live_settings())
        guard.verify_live_trading()
        assert guard.is_verified
        assert guard.is_live

    def test_live_fails_without_confirm_env(self):
        guard = LiveTradingGuard(_live_settings())
        with pytest.raises(ConfigError, match="CONFIRM_LIVE_TRADING"):
            guard.verify_live_trading()

    @patch.dict(os.environ, {"CONFIRM_LIVE_TRADING": "YES_I_UNDERSTAND_THE_RISKS"})
    def test_live_fails_without_api_key(self):
        guard = LiveTradingGuard(_live_settings(api_key=""))
        with pytest.raises(ConfigError, match="API_KEY"):
            guard.verify_live_trading()

    @patch.dict(os.environ, {"CONFIRM_LIVE_TRADING": "YES_I_UNDERSTAND_THE_RISKS"})
    def test_live_fails_with_short_api_key(self):
        guard = LiveTradingGuard(_live_settings(api_key="short"))
        with pytest.raises(ConfigError, match="invalid"):
            guard.verify_live_trading()

    @patch.dict(os.environ, {"CONFIRM_LIVE_TRADING": "YES_I_UNDERSTAND_THE_RISKS"})
    def test_live_fails_without_api_secret(self):
        guard = LiveTradingGuard(_live_settings(api_secret=""))
        with pytest.raises(ConfigError, match="API_SECRET"):
            guard.verify_live_trading()

    @patch.dict(os.environ, {"CONFIRM_LIVE_TRADING": "YES_I_UNDERSTAND_THE_RISKS"})
    def test_live_fails_with_high_position_pct(self):
        risk = RiskConfig(max_position_pct=0.50)
        guard = LiveTradingGuard(_live_settings(risk=risk))
        with pytest.raises(ConfigError, match="max_position_pct"):
            guard.verify_live_trading()

    @patch.dict(os.environ, {"CONFIRM_LIVE_TRADING": "YES_I_UNDERSTAND_THE_RISKS"})
    def test_live_fails_with_high_order_limit(self):
        risk = RiskConfig(max_single_order_usdt=10000)
        guard = LiveTradingGuard(_live_settings(risk=risk))
        with pytest.raises(ConfigError, match="max_single_order_usdt"):
            guard.verify_live_trading()

    @patch.dict(os.environ, {"CONFIRM_LIVE_TRADING": "YES_I_UNDERSTAND_THE_RISKS"})
    def test_live_fails_with_zero_stop_loss(self):
        risk = RiskConfig(stop_loss_pct=0)
        guard = LiveTradingGuard(_live_settings(risk=risk))
        with pytest.raises(ConfigError, match="stop_loss_pct"):
            guard.verify_live_trading()
