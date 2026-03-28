from __future__ import annotations

from backend.config import Settings
from backend.exchange.base import ExchangeBase
from backend.exchange.binance_client import BinanceClient
from backend.exchange.paper_exchange import PaperExchange


def create_exchange(settings: Settings) -> ExchangeBase:
    """Factory: returns PaperExchange, BinanceClient, or raises for backtest mode."""
    if settings.trading.mode == "paper":
        return PaperExchange(settings)
    if settings.trading.mode == "backtest":
        raise ValueError(
            "BacktestExchange must be created directly with OHLCV data, "
            "not through the factory. Use backend.backtest.exchange.BacktestExchange."
        )
    return BinanceClient(settings)
