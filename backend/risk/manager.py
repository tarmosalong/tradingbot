from __future__ import annotations

from datetime import UTC, datetime

from backend.config import RiskConfig
from backend.core.logger import get_logger
from backend.database import Database
from backend.models import Signal

logger = get_logger("risk_manager")


class RiskManager:
    """Validates trades against risk limits before execution."""

    def __init__(self, config: RiskConfig, database: Database) -> None:
        self._cfg = config
        self._db = database
        self._initial_portfolio_value: float | None = None
        self._daily_start_value: float | None = None
        self._daily_start_date: datetime | None = None

    def set_initial_portfolio_value(self, value: float) -> None:
        self._initial_portfolio_value = value
        if self._daily_start_value is None:
            self._daily_start_value = value
            self._daily_start_date = datetime.now(UTC)

    async def check_signal(
        self,
        signal: Signal,
        portfolio_value: float,
        balance: dict[str, float],
        current_price: float,
    ) -> RiskDecision:
        """Validate a signal against all risk rules.

        Returns a RiskDecision with approved/rejected status and
        the allowed position size.
        """
        self._maybe_reset_daily(portfolio_value)

        if self._initial_portfolio_value:
            drawdown = self._calculate_drawdown(portfolio_value)
            if drawdown >= self._cfg.max_drawdown_pct:
                return RiskDecision(
                    approved=False,
                    reason=(
                        f"Max drawdown {drawdown:.1%} exceeds"
                        f" limit {self._cfg.max_drawdown_pct:.1%}"
                    ),
                )

        if self._daily_start_value:
            daily_loss = self._calculate_daily_loss(portfolio_value)
            if daily_loss >= self._cfg.daily_loss_limit_pct:
                return RiskDecision(
                    approved=False,
                    reason=(
                        f"Daily loss {daily_loss:.1%} exceeds"
                        f" limit {self._cfg.daily_loss_limit_pct:.1%}"
                    ),
                )

        base, quote = signal.symbol.split("/")

        if signal.direction == "BUY":
            available = balance.get(quote, 0.0)
            max_by_pct = portfolio_value * self._cfg.max_position_pct
            max_by_cap = self._cfg.max_single_order_usdt
            budget = min(available, max_by_pct, max_by_cap)

            if budget < 1.0:
                return RiskDecision(
                    approved=False,
                    reason=f"Budget too small: {budget:.2f} {quote}",
                )

            amount = budget / current_price
            return RiskDecision(
                approved=True,
                amount=amount,
                reason=f"BUY {amount:.6f} {base} (budget {budget:.2f} {quote})",
            )

        if signal.direction == "SELL":
            available = balance.get(base, 0.0)
            if available <= 0:
                return RiskDecision(
                    approved=False,
                    reason=f"No {base} position to sell",
                )

            return RiskDecision(
                approved=True,
                amount=available,
                reason=f"SELL {available:.6f} {base}",
            )

        return RiskDecision(approved=False, reason="HOLD signal, no action")

    def calculate_stop_loss(self, entry_price: float, side: str) -> float:
        """Calculate stop-loss price for a new position."""
        if side == "BUY":
            return entry_price * (1 - self._cfg.stop_loss_pct)
        return entry_price * (1 + self._cfg.stop_loss_pct)

    def calculate_trailing_stop(
        self, current_price: float, best_price: float, side: str
    ) -> float:
        """Calculate trailing stop price based on the best price seen."""
        if side == "BUY":
            return best_price * (1 - self._cfg.trailing_stop_pct)
        return best_price * (1 + self._cfg.trailing_stop_pct)

    def should_trigger_stop(
        self, current_price: float, stop_price: float, side: str
    ) -> bool:
        """Check if the stop price has been hit."""
        if side == "BUY":
            return current_price <= stop_price
        return current_price >= stop_price

    def _calculate_drawdown(self, current_value: float) -> float:
        if not self._initial_portfolio_value or self._initial_portfolio_value <= 0:
            return 0.0
        loss = self._initial_portfolio_value - current_value
        return max(0.0, loss / self._initial_portfolio_value)

    def _calculate_daily_loss(self, current_value: float) -> float:
        if not self._daily_start_value or self._daily_start_value <= 0:
            return 0.0
        loss = self._daily_start_value - current_value
        return max(0.0, loss / self._daily_start_value)

    def check_portfolio_health(
        self, portfolio_value: float,
    ) -> RiskDecision:
        """Check drawdown and daily loss limits without a specific signal."""
        self._maybe_reset_daily(portfolio_value)

        if self._initial_portfolio_value:
            drawdown = self._calculate_drawdown(portfolio_value)
            if drawdown >= self._cfg.max_drawdown_pct:
                return RiskDecision(
                    approved=False,
                    reason=(
                        f"Max drawdown {drawdown:.1%} exceeds"
                        f" limit {self._cfg.max_drawdown_pct:.1%}"
                    ),
                )

        if self._daily_start_value:
            daily_loss = self._calculate_daily_loss(portfolio_value)
            if daily_loss >= self._cfg.daily_loss_limit_pct:
                return RiskDecision(
                    approved=False,
                    reason=(
                        f"Daily loss {daily_loss:.1%} exceeds"
                        f" limit {self._cfg.daily_loss_limit_pct:.1%}"
                    ),
                )

        return RiskDecision(approved=True, reason="Portfolio health OK")

    def _maybe_reset_daily(self, current_value: float) -> None:
        """Reset daily tracking at the start of a new UTC day."""
        now = datetime.now(UTC)
        if self._daily_start_date is None or now.date() > self._daily_start_date.date():
            self._daily_start_value = current_value
            self._daily_start_date = now


class RiskDecision:
    """Result of a risk check."""

    def __init__(
        self,
        approved: bool,
        amount: float = 0.0,
        reason: str = "",
    ) -> None:
        self.approved = approved
        self.amount = amount
        self.reason = reason

    def __repr__(self) -> str:
        status = "APPROVED" if self.approved else "REJECTED"
        return f"RiskDecision({status}, amount={self.amount:.6f}, reason={self.reason!r})"
