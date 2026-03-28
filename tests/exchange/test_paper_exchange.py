from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.config import Settings, load_settings
from backend.core.exceptions import InsufficientFundsError
from backend.exchange.paper_exchange import PaperExchange
from backend.models import OrderSide, OrderStatus, Ticker


@pytest.fixture
def paper_settings() -> Settings:
    return load_settings()


@pytest.fixture
def paper_exchange(paper_settings: Settings) -> PaperExchange:
    return PaperExchange(paper_settings)


class TestPaperExchange:
    async def test_initial_balance(self, paper_exchange: PaperExchange):
        balance = await paper_exchange.get_balance()

        assert balance["USDT"] == 10_000.0

    @patch("backend.exchange.paper_exchange.BinanceClient.get_ticker")
    async def test_buy_order_deducts_quote(
        self, mock_ticker: AsyncMock, paper_exchange: PaperExchange
    ):
        mock_ticker.return_value = Ticker(symbol="BTC/USDT", bid=50000.0, ask=50010.0, last=50000.0)

        order = await paper_exchange.create_order("BTC/USDT", "BUY", "MARKET", 0.1)

        assert order.status == OrderStatus.FILLED
        assert order.side == OrderSide.BUY
        assert order.filled_amount == 0.1

        balance = await paper_exchange.get_balance()
        assert balance["USDT"] == pytest.approx(5000.0)
        assert balance["BTC"] == pytest.approx(0.1)

    @patch("backend.exchange.paper_exchange.BinanceClient.get_ticker")
    async def test_sell_order_adds_quote(
        self, mock_ticker: AsyncMock, paper_exchange: PaperExchange
    ):
        mock_ticker.return_value = Ticker(symbol="BTC/USDT", bid=50000.0, ask=50010.0, last=50000.0)

        await paper_exchange.create_order("BTC/USDT", "BUY", "MARKET", 0.1)
        order = await paper_exchange.create_order("BTC/USDT", "SELL", "MARKET", 0.1)

        assert order.status == OrderStatus.FILLED
        balance = await paper_exchange.get_balance()
        assert balance["USDT"] == pytest.approx(10_000.0)

    @patch("backend.exchange.paper_exchange.BinanceClient.get_ticker")
    async def test_insufficient_funds_buy(
        self, mock_ticker: AsyncMock, paper_exchange: PaperExchange
    ):
        mock_ticker.return_value = Ticker(symbol="BTC/USDT", bid=50000.0, ask=50010.0, last=50000.0)

        with pytest.raises(InsufficientFundsError):
            await paper_exchange.create_order("BTC/USDT", "BUY", "MARKET", 1.0)

    @patch("backend.exchange.paper_exchange.BinanceClient.get_ticker")
    async def test_insufficient_funds_sell(
        self, mock_ticker: AsyncMock, paper_exchange: PaperExchange
    ):
        mock_ticker.return_value = Ticker(symbol="BTC/USDT", bid=50000.0, ask=50010.0, last=50000.0)

        with pytest.raises(InsufficientFundsError):
            await paper_exchange.create_order("BTC/USDT", "SELL", "MARKET", 0.1)

    async def test_open_orders_empty_initially(self, paper_exchange: PaperExchange):
        orders = await paper_exchange.get_open_orders()

        assert orders == []
