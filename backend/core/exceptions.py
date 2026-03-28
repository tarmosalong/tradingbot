from __future__ import annotations


class TradingBotError(Exception):
    """Base exception for all trading bot errors."""


class ConfigError(TradingBotError):
    """Invalid or missing configuration."""


class ExchangeError(TradingBotError):
    """Exchange communication or API error."""


class InsufficientFundsError(ExchangeError):
    """Not enough balance to execute the order."""


class OrderError(ExchangeError):
    """Order creation, cancellation, or fill error."""


class RateLimitError(ExchangeError):
    """Exchange or API rate limit exceeded."""


class StrategyError(TradingBotError):
    """Strategy analysis or signal generation error."""


class AIError(TradingBotError):
    """Claude API communication or response parsing error."""


class RiskError(TradingBotError):
    """Risk limit violated (drawdown, position size, daily loss)."""
