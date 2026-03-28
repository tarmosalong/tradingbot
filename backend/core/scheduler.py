from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from backend.core.logger import get_logger

logger = get_logger("scheduler")


class PeriodicTask:
    """Runs an async callable on a fixed interval."""

    def __init__(
        self,
        name: str,
        func: Callable[[], Awaitable[None]],
        interval_seconds: float,
    ) -> None:
        self.name = name
        self._func = func
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None

    async def _loop(self) -> None:
        while True:
            try:
                await self._func()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    "Periodic task error", task=self.name
                )
            await asyncio.sleep(self._interval)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._loop(), name=f"periodic-{self.name}"
            )
            logger.info(
                "Periodic task started",
                task=self.name,
                interval=self._interval,
            )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Periodic task stopped", task=self.name)


class Scheduler:
    """Manages a collection of periodic tasks."""

    def __init__(self) -> None:
        self._tasks: list[PeriodicTask] = []

    def add(
        self,
        name: str,
        func: Callable[[], Awaitable[None]],
        interval_seconds: float,
    ) -> None:
        self._tasks.append(
            PeriodicTask(name, func, interval_seconds)
        )

    def start_all(self) -> None:
        for task in self._tasks:
            task.start()

    async def stop_all(self) -> None:
        await asyncio.gather(*(t.stop() for t in self._tasks))
