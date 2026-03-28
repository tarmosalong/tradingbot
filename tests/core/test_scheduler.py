from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from backend.core.scheduler import PeriodicTask, Scheduler


class TestPeriodicTask:
    async def test_runs_function_on_interval(self):
        call_count = 0

        async def counter():
            nonlocal call_count
            call_count += 1

        task = PeriodicTask("test", counter, interval_seconds=0.05)
        task.start()
        await asyncio.sleep(0.18)
        await task.stop()

        assert call_count >= 2

    async def test_stop_cancels_task(self):
        func = AsyncMock()
        task = PeriodicTask("test", func, interval_seconds=0.1)
        task.start()
        await asyncio.sleep(0.05)
        await task.stop()

        assert task._task.done()

    async def test_error_does_not_stop_loop(self):
        call_count = 0

        async def failing():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("boom")

        task = PeriodicTask("test", failing, interval_seconds=0.05)
        task.start()
        await asyncio.sleep(0.18)
        await task.stop()

        assert call_count >= 2


class TestScheduler:
    async def test_start_and_stop_all(self):
        func_a = AsyncMock()
        func_b = AsyncMock()

        scheduler = Scheduler()
        scheduler.add("a", func_a, interval_seconds=0.05)
        scheduler.add("b", func_b, interval_seconds=0.05)

        scheduler.start_all()
        await asyncio.sleep(0.12)
        await scheduler.stop_all()

        assert func_a.call_count >= 1
        assert func_b.call_count >= 1
