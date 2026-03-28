from __future__ import annotations

from backend.config import Settings
from backend.exchange.base import ExchangeBase
from backend.exchange.binance_client import BinanceClient
from backend.exchange.paper_exchange import PaperExchange


def create_exchange(settings: Settings) -> ExchangeBase:
    """Factory: returns PaperExchange or BinanceClient based on config."""
    if settings.trading.mode == "paper":
        return PaperExchange(settings)
    return BinanceClient(settings)
