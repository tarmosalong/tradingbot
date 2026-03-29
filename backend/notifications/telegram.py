"""Telegram notification service using the Bot API via aiohttp."""
from __future__ import annotations

from datetime import UTC, datetime

import aiohttp

from backend.config import TelegramConfig
from backend.core.logger import get_logger
from backend.models import Signal, Trade

logger = get_logger("telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Sends formatted trading alerts to a Telegram chat."""

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None

    @property
    def enabled(self) -> bool:
        return (
            self._config.enabled
            and bool(self._config.bot_token)
            and bool(self._config.chat_id)
        )

    async def start(self) -> None:
        if self.enabled:
            self._session = aiohttp.ClientSession()
            logger.info("Telegram notifier started")

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def send_trade(self, trade: Trade, signal: Signal) -> None:
        if not self.enabled:
            return

        side_emoji = "\U0001f7e2" if trade.side.value == "BUY" else "\U0001f534"
        msg = (
            f"{side_emoji} *{trade.side.value}* {trade.symbol}\n"
            f"Price: `{trade.price:,.2f}`\n"
            f"Amount: `{trade.amount:.6f}`\n"
            f"Value: `${trade.price * trade.amount:,.2f}`\n"
            f"Confidence: `{signal.confidence:.0%}`\n"
            f"Strategy: _{signal.strategy_name}_\n"
            f"Reason: _{signal.reason[:120]}_"
        )
        await self._send(msg)

    async def send_daily_summary(self, stats: dict) -> None:
        if not self.enabled:
            return

        pnl = stats.get("daily_pnl", 0.0)
        pnl_sign = "+" if pnl >= 0 else ""
        trades_today = stats.get("trades_today", 0)
        win_rate = stats.get("win_rate", 0.0)
        portfolio = stats.get("portfolio_value", 0.0)

        msg = (
            "\U0001f4ca *Daily Summary*\n"
            f"P&L: `{pnl_sign}{pnl:,.2f} USDT`\n"
            f"Trades: `{trades_today}`\n"
            f"Win rate: `{win_rate:.0%}`\n"
            f"Portfolio: `${portfolio:,.2f}`\n"
            f"_{datetime.now(UTC).strftime('%Y-%m-%d')}_"
        )
        await self._send(msg)

    async def send_alert(self, message: str, level: str = "WARNING") -> None:
        if not self.enabled:
            return

        prefix = {
            "INFO": "\u2139\ufe0f",
            "WARNING": "\u26a0\ufe0f",
            "ERROR": "\u274c",
            "CRITICAL": "\U0001f6a8",
        }.get(level, "\u2139\ufe0f")

        msg = f"{prefix} *{level}*\n{message}"
        await self._send(msg)

    async def _send(self, text: str) -> bool:
        if not self._session:
            return False

        url = TELEGRAM_API.format(token=self._config.bot_token)
        payload = {
            "chat_id": self._config.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            async with self._session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(
                        "Telegram send failed",
                        status=resp.status,
                        body=body[:200],
                    )
                    return False
                return True
        except Exception:
            logger.exception("Telegram send error")
            return False
