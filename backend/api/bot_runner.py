"""In-process paper trading loop for the API server (dashboard Start/Stop)."""
from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Literal

from backend.api.deps import get_database
from backend.config import load_settings
from backend.core.engine import TradingEngine
from backend.core.logger import get_logger
from backend.core.strategy_factory import build_strategies
from backend.exchange import create_exchange

if TYPE_CHECKING:
    from backend.notifications.telegram import TelegramNotifier

logger = get_logger("bot_runner")

BotState = Literal["stopped", "starting", "running", "stopping"]


def _bot_control_enabled() -> bool:
    return os.getenv("BOT_CONTROL_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
    )


class BotRunner:
    """Runs TradingEngine inside the uvicorn process (paper mode only)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state: BotState = "stopped"
        self._task: asyncio.Task[None] | None = None
        self._engine: TradingEngine | None = None
        self._last_error: str | None = None

    @property
    def state(self) -> BotState:
        return self._state

    def status_dict(self) -> dict:
        s = load_settings()
        return {
            "state": self._state,
            "mode": s.trading.mode,
            "control_enabled": _bot_control_enabled(),
            "last_error": self._last_error,
        }

    async def start(self) -> None:
        if not _bot_control_enabled():
            raise RuntimeError("Bot control disabled (set BOT_CONTROL_ENABLED=true)")
        async with self._lock:
            self._last_error = None
            if self._state in ("starting", "running"):
                raise RuntimeError("Bot already running or starting")
            if self._task and not self._task.done():
                raise RuntimeError("Bot task still active")
            settings = load_settings()
            if settings.trading.mode != "paper":
                raise RuntimeError(
                    "Dashboard can only start the bot in paper mode "
                    "(set trading.mode: paper in config.yaml)",
                )
            self._state = "starting"
            self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        notifier: TelegramNotifier | None = None
        exchange = None
        try:
            settings = load_settings()
            db = get_database()
            if db is None:
                raise RuntimeError("Database not initialized")

            exchange = create_exchange(settings)
            strategies = build_strategies(settings)

            if settings.telegram.enabled:
                from backend.notifications.telegram import TelegramNotifier

                notifier = TelegramNotifier(settings.telegram)
                await notifier.start()

            engine = TradingEngine(
                settings=settings,
                exchange=exchange,
                database=db,
                strategies=strategies,
                notifier=notifier,
            )
            self._engine = engine
            self._state = "running"
            logger.info("Dashboard bot loop started", paper=True)
            await engine.start()
        except asyncio.CancelledError:
            logger.info("Dashboard bot task cancelled")
            raise
        except Exception as e:
            self._last_error = str(e)
            logger.exception("Dashboard bot crashed", error=str(e))
        finally:
            self._state = "stopped"
            self._engine = None
            self._task = None
            if exchange is not None:
                try:
                    await exchange.close()
                except Exception:
                    logger.exception("Exchange close error")
            if notifier is not None:
                try:
                    await notifier.close()
                except Exception:
                    logger.exception("Notifier close error")
            logger.info("Dashboard bot loop ended")

    async def stop(self) -> None:
        async with self._lock:
            eng = self._engine
            task = self._task
            if eng is None and (task is None or task.done()):
                self._state = "stopped"
                return
            self._state = "stopping"
        if eng is not None:
            await eng.stop()
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=120.0)
            except TimeoutError:
                logger.warning("Bot task did not finish in time, cancelling")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        async with self._lock:
            self._state = "stopped"

    async def get_positions(self) -> list[dict]:
        if self._engine is not None:
            return await self._engine.get_positions_with_prices()
        return []

    async def shutdown(self) -> None:
        await self.stop()


bot_runner = BotRunner()
