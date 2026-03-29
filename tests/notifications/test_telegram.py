from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from backend.config import TelegramConfig
from backend.models import OrderSide, Signal, Trade
from backend.notifications.telegram import TelegramNotifier


def _config(enabled: bool = True) -> TelegramConfig:
    return TelegramConfig(
        enabled=enabled,
        bot_token="123:ABC",
        chat_id="999",
    )


def _trade() -> Trade:
    return Trade(
        id="t1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        amount=0.005,
        price=65000.0,
        executed_at=datetime.now(UTC),
    )


def _signal() -> Signal:
    return Signal(
        symbol="BTC/USDT",
        direction="BUY",
        confidence=0.72,
        strategy_name="aggregator",
        reason="RSI oversold | MACD bullish crossover",
    )


class TestTelegramNotifierDisabled:
    def test_not_enabled_when_disabled(self):
        n = TelegramNotifier(_config(enabled=False))
        assert not n.enabled

    def test_not_enabled_without_token(self):
        cfg = TelegramConfig(enabled=True, bot_token="", chat_id="999")
        n = TelegramNotifier(cfg)
        assert not n.enabled

    @pytest.mark.asyncio
    async def test_send_trade_noop_when_disabled(self):
        n = TelegramNotifier(_config(enabled=False))
        await n.send_trade(_trade(), _signal())

    @pytest.mark.asyncio
    async def test_send_alert_noop_when_disabled(self):
        n = TelegramNotifier(_config(enabled=False))
        await n.send_alert("test", "WARNING")


class TestTelegramNotifierSend:
    @pytest.mark.asyncio
    async def test_send_trade_calls_api(self):
        notifier = TelegramNotifier(_config())
        mock_resp = AsyncMock()
        mock_resp.status = 200

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.post.return_value = mock_ctx
        notifier._session = mock_session

        await notifier.send_trade(_trade(), _signal())

        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert "123:ABC" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["chat_id"] == "999"
        assert "BUY" in payload["text"]
        assert "BTC/USDT" in payload["text"]
        assert "65,000.00" in payload["text"]

    @pytest.mark.asyncio
    async def test_send_alert_formats_level(self):
        notifier = TelegramNotifier(_config())
        mock_resp = AsyncMock()
        mock_resp.status = 200

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.post.return_value = mock_ctx
        notifier._session = mock_session

        await notifier.send_alert("Drawdown exceeded 15%", "CRITICAL")

        payload = mock_session.post.call_args[1]["json"]
        assert "CRITICAL" in payload["text"]
        assert "Drawdown exceeded 15%" in payload["text"]

    @pytest.mark.asyncio
    async def test_send_daily_summary(self):
        notifier = TelegramNotifier(_config())
        mock_resp = AsyncMock()
        mock_resp.status = 200

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.post.return_value = mock_ctx
        notifier._session = mock_session

        await notifier.send_daily_summary({
            "daily_pnl": 150.50,
            "trades_today": 5,
            "win_rate": 0.6,
            "portfolio_value": 10500.0,
        })

        payload = mock_session.post.call_args[1]["json"]
        assert "+150.50" in payload["text"]
        assert "$10,500.00" in payload["text"]

    @pytest.mark.asyncio
    async def test_send_returns_false_on_api_error(self):
        notifier = TelegramNotifier(_config())
        mock_resp = AsyncMock()
        mock_resp.status = 403
        mock_resp.text = AsyncMock(return_value="Forbidden")

        mock_session = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.post.return_value = mock_ctx
        notifier._session = mock_session

        result = await notifier._send("test")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_returns_false_without_session(self):
        notifier = TelegramNotifier(_config())
        result = await notifier._send("test")
        assert result is False

    @pytest.mark.asyncio
    async def test_start_creates_session(self):
        notifier = TelegramNotifier(_config())
        with patch("backend.notifications.telegram.aiohttp.ClientSession") as mock_cls:
            await notifier.start()
            mock_cls.assert_called_once()
            assert notifier._session is not None

    @pytest.mark.asyncio
    async def test_close_cleans_session(self):
        notifier = TelegramNotifier(_config())
        mock_session = AsyncMock()
        notifier._session = mock_session

        await notifier.close()
        mock_session.close.assert_awaited_once()
        assert notifier._session is None
