from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

import backend.api.deps as deps_module
from backend.api.app import create_app
from backend.database import Database
from backend.models import Order, OrderSide, OrderStatus, OrderType, Trade


@pytest.fixture
async def db(tmp_path):
    database = Database(db_path=tmp_path / "test_api.db")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app()

    original_db = deps_module._db
    deps_module._db = db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    deps_module._db = original_db


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        response = await client.get("/api/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestConfigEndpoint:
    async def test_config_returns_settings(self, client):
        response = await client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "pairs" in data
        assert "risk" in data
        assert "paper_trading" in data
        assert "initial_balance_usdt" in data["paper_trading"]


class TestTradesEndpoint:
    async def test_get_trades_empty(self, client):
        response = await client.get("/api/trades")

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_trades_with_data(self, client, db):
        trade = Trade(
            id=str(uuid.uuid4()),
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            amount=0.01,
            price=65000.0,
            executed_at=datetime.now(UTC),
        )
        await db.insert_trade(trade)

        response = await client.get("/api/trades")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "BTC/USDT"
        assert data[0]["side"] == "BUY"

    async def test_get_trades_filter_by_symbol(self, client, db):
        for sym in ("BTC/USDT", "ETH/USDT"):
            trade = Trade(
                id=str(uuid.uuid4()),
                symbol=sym,
                side=OrderSide.BUY,
                amount=0.01,
                price=65000.0,
                executed_at=datetime.now(UTC),
            )
            await db.insert_trade(trade)

        response = await client.get("/api/trades?symbol=BTC/USDT")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "BTC/USDT"


class TestOrdersEndpoint:
    async def test_get_orders_empty(self, client):
        response = await client.get("/api/orders")

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_open_orders(self, client, db):
        order = Order(
            id="order-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=0.01,
            price=64000.0,
            status=OrderStatus.OPEN,
        )
        await db.insert_order(order)

        response = await client.get("/api/orders")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "OPEN"


class TestPortfolioEndpoint:
    async def test_get_portfolio_empty(self, client):
        response = await client.get("/api/portfolio")

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_portfolio_history(self, client, db):
        await db.save_portfolio_snapshot(
            10000.0, {"USDT": 10000.0}
        )

        response = await client.get("/api/portfolio")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["total_value_usdt"] == 10000.0
