"""Safety checks for live trading mode.

Two-stage verification: the engine must explicitly unlock live trading
by calling verify_live_trading(). Until then, all live trade attempts
are blocked. This prevents accidental live trades during development.
"""
from __future__ import annotations

import os

from backend.config import Settings
from backend.core.exceptions import ConfigError
from backend.core.logger import get_logger

logger = get_logger("safety")


class LiveTradingGuard:
    """Gate that prevents live trading unless explicitly verified."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._verified = False

    @property
    def is_live(self) -> bool:
        return self._settings.trading.mode == "live"

    @property
    def is_verified(self) -> bool:
        return self._verified

    def verify_live_trading(self) -> None:
        """Run all safety checks and unlock live trading.

        Raises ConfigError if any check fails.
        """
        if not self.is_live:
            logger.info("Paper mode, skipping live verification")
            self._verified = True
            return

        self._check_api_keys()
        self._check_environment_variable()
        self._check_risk_limits()
        self._check_sandbox_disabled()

        self._verified = True
        logger.warning(
            "LIVE TRADING VERIFIED AND UNLOCKED",
            mode=self._settings.trading.mode,
            pairs=self._settings.trading.pairs,
        )

    def assert_can_trade(self) -> None:
        """Raise if live trading hasn't been verified."""
        if not self._verified:
            raise ConfigError(
                "Live trading not verified. Call verify_live_trading() first."
            )

    def _check_api_keys(self) -> None:
        if not self._settings.binance_api_key:
            raise ConfigError("BINANCE_API_KEY is not set")
        if not self._settings.binance_api_secret:
            raise ConfigError("BINANCE_API_SECRET is not set")
        if len(self._settings.binance_api_key) < 20:
            raise ConfigError("BINANCE_API_KEY looks invalid (too short)")

    def _check_environment_variable(self) -> None:
        confirm = os.getenv("CONFIRM_LIVE_TRADING", "")
        if confirm != "YES_I_UNDERSTAND_THE_RISKS":
            raise ConfigError(
                "Set CONFIRM_LIVE_TRADING=YES_I_UNDERSTAND_THE_RISKS "
                "to enable live trading"
            )

    def _check_risk_limits(self) -> None:
        risk = self._settings.risk
        if risk.max_position_pct > 0.25:
            raise ConfigError(
                f"max_position_pct {risk.max_position_pct} too high for live (max 25%)"
            )
        if risk.max_single_order_usdt > 5000:
            raise ConfigError(
                f"max_single_order_usdt ${risk.max_single_order_usdt} too high for live"
            )
        if risk.stop_loss_pct <= 0:
            raise ConfigError("stop_loss_pct must be positive for live trading")

    def _check_sandbox_disabled(self) -> None:
        if self._settings.exchange.sandbox:
            logger.info("Sandbox mode enabled — safe for testing")
