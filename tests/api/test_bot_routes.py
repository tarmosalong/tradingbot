from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import backend.api.deps as deps_module
import backend.api.routes as routes_module
from backend.api.app import create_app
from backend.database import Database


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(db_path=tmp_path / "test_api.db")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def client(db: Database) -> AsyncClient:
    app = create_app()

    original_db = deps_module._db
    deps_module._db = db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    deps_module._db = original_db


@pytest.fixture
def reset_bot_runner() -> None:
    r = routes_module.bot_runner
    r._state = "stopped"  # noqa: SLF001
    r._task = None  # noqa: SLF001
    r._engine = None  # noqa: SLF001
    r._last_error = None  # noqa: SLF001


class TestBotStatus:
    async def test_status_shape(self, client: AsyncClient, reset_bot_runner: None) -> None:
        response = await client.get("/api/bot/status")
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "stopped"
        assert "mode" in data
        assert "control_enabled" in data
        assert data["last_error"] is None


class TestBotPatchSettings:
    async def test_patch_409_when_running(
        self,
        client: AsyncClient,
        reset_bot_runner: None,
    ) -> None:
        routes_module.bot_runner._state = "running"  # noqa: SLF001
        try:
            response = await client.patch(
                "/api/bot/settings",
                json={"initial_balance_usdt": 10_000.0},
            )
            assert response.status_code == 409
        finally:
            routes_module.bot_runner._state = "stopped"  # noqa: SLF001

    async def test_patch_400_invalid(self, client: AsyncClient, reset_bot_runner: None) -> None:
        response = await client.patch(
            "/api/bot/settings",
            json={"initial_balance_usdt": 10.0},
        )
        assert response.status_code == 400

    async def test_patch_writes_sandbox_yaml(
        self,
        client: AsyncClient,
        db: Database,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        reset_bot_runner: None,
    ) -> None:
        repo_root = Path(__file__).resolve().parent.parent.parent
        shutil.copy(repo_root / "config.yaml", tmp_path / "config.yaml")

        monkeypatch.setattr(
            "backend.config_io.config_yaml_path",
            lambda: tmp_path / "config.yaml",
        )

        import backend.config as config_module

        def load_tmp() -> object:
            return config_module.load_settings(tmp_path / "config.yaml")

        monkeypatch.setattr("backend.api.routes.load_settings", load_tmp)

        response = await client.patch(
            "/api/bot/settings",
            json={
                "initial_balance_usdt": 12_345.0,
                "pairs": ["BTC/USDT"],
                "timeframe": "1h",
                "poll_interval_seconds": 120,
                "strategies": ["rsi", "macd"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["paper_trading"]["initial_balance_usdt"] == 12_345.0
        assert body["pairs"] == ["BTC/USDT"]
        assert body["poll_interval"] == 120
        assert set(body["strategies"]) >= {"rsi", "macd"}


class TestBotStartControl:
    async def test_start_403_when_disabled(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        reset_bot_runner: None,
    ) -> None:
        monkeypatch.setenv("BOT_CONTROL_ENABLED", "false")
        response = await client.post("/api/bot/start")
        assert response.status_code == 403
