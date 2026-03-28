from __future__ import annotations

import pytest

from backend.database import Database
from backend.models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Signal,
    Trade,
)


@pytest.fixture
async def db(tmp_path):
    database = Database(db_path=tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


class TestDatabase:
    async def test_insert_and_get_trade(self, db: Database):
        trade = Trade(
            id="t-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            amount=0.01,
            price=65000.0,
            fee=6.5,
        )

        await db.insert_trade(trade)
        trades = await db.get_trades()

        assert len(trades) == 1
        assert trades[0].id == "t-1"
        assert trades[0].price == 65000.0

    async def test_insert_trade_with_signal(self, db: Database):
        signal = Signal(
            symbol="BTC/USDT",
            direction="BUY",
            confidence=0.8,
            strategy_name="rsi",
            reason="Oversold",
        )
        trade = Trade(
            id="t-2",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            amount=0.01,
            price=65000.0,
            signal=signal,
        )

        await db.insert_trade(trade)
        trades = await db.get_trades()

        assert len(trades) == 1

    async def test_get_trades_filtered_by_symbol(self, db: Database):
        trade_btc = Trade(
            id="t-btc", symbol="BTC/USDT", side=OrderSide.BUY,
            amount=0.01, price=65000.0,
        )
        trade_eth = Trade(
            id="t-eth", symbol="ETH/USDT", side=OrderSide.BUY,
            amount=1.0, price=3500.0,
        )

        await db.insert_trade(trade_btc)
        await db.insert_trade(trade_eth)

        btc_trades = await db.get_trades(symbol="BTC/USDT")
        assert len(btc_trades) == 1
        assert btc_trades[0].symbol == "BTC/USDT"

    async def test_insert_and_get_order(self, db: Database):
        order = Order(
            id="o-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.01,
            price=None,
            status=OrderStatus.OPEN,
        )

        await db.insert_order(order)
        open_orders = await db.get_open_orders()

        assert len(open_orders) == 1
        assert open_orders[0].id == "o-1"

    async def test_get_open_orders_excludes_filled(self, db: Database):
        open_order = Order(
            id="o-open", symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.LIMIT, amount=0.01, price=60000.0, status=OrderStatus.OPEN,
        )
        filled_order = Order(
            id="o-filled", symbol="BTC/USDT", side=OrderSide.SELL,
            order_type=OrderType.MARKET, amount=0.01, price=65000.0, status=OrderStatus.FILLED,
        )

        await db.insert_order(open_order)
        await db.insert_order(filled_order)

        open_orders = await db.get_open_orders()
        assert len(open_orders) == 1
        assert open_orders[0].id == "o-open"

    async def test_portfolio_snapshot(self, db: Database):
        await db.save_portfolio_snapshot(10500.0, {"USDT": 9000.0, "BTC": 0.023})

        history = await db.get_portfolio_history()
        assert len(history) == 1
        assert history[0]["total_value_usdt"] == 10500.0
        assert history[0]["balances"]["BTC"] == 0.023
