from __future__ import annotations

from backend.api.websocket import ConnectionManager


class TestConnectionManager:
    async def test_broadcast_to_no_connections(self):
        mgr = ConnectionManager()
        await mgr.broadcast({"type": "update", "data": {}})

        assert mgr.active_count == 0

    def test_active_count_starts_at_zero(self):
        mgr = ConnectionManager()
        assert mgr.active_count == 0
