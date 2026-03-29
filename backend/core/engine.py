from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from backend.config import Settings
from backend.core.exceptions import ExchangeError, StrategyError
from backend.core.logger import get_logger
from backend.database import Database
from backend.exchange.base import ExchangeBase
from backend.models import OrderSide, Signal, Trade
from backend.strategies.base import StrategyBase

if TYPE_CHECKING:
    from backend.notifications.telegram import TelegramNotifier

logger = get_logger("engine")


class TradingEngine:
    """Orchestrates the trading loop: fetch data, run strategies, execute orders."""

    def __init__(
        self,
        settings: Settings,
        exchange: ExchangeBase,
        database: Database,
        strategies: list[StrategyBase],
        notifier: TelegramNotifier | None = None,
    ) -> None:
        self._settings = settings
        self._exchange = exchange
        self._db = database
        self._strategies = strategies
        self._notifier = notifier
        self._running = False
        self._positions: dict[str, float] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Start the trading loop."""
        self._running = True
        logger.info(
            "Engine started",
            mode=self._settings.trading.mode,
            pairs=self._settings.trading.pairs,
            strategies=[s.name for s in self._strategies],
        )

        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                logger.info("Engine cancelled, shutting down")
                break
            except Exception:
                logger.exception("Unexpected error in trading loop")
                await self._notify_alert(
                    "Unexpected error in trading loop — check logs",
                    "ERROR",
                )

            await asyncio.sleep(
                self._settings.trading.poll_interval_seconds
            )

        self._running = False
        logger.info("Engine stopped")

    async def stop(self) -> None:
        """Signal the engine to stop after the current tick."""
        self._running = False
        logger.info("Engine stop requested")

    async def _tick(self) -> None:
        """Single iteration: fetch data, analyze, optionally trade."""
        for symbol in self._settings.trading.pairs:
            try:
                ohlcv = await self._exchange.get_ohlcv(
                    symbol,
                    self._settings.trading.timeframe,
                    limit=100,
                )
            except ExchangeError:
                logger.exception("Failed to fetch OHLCV", symbol=symbol)
                continue

            signals = await self._collect_signals(symbol, ohlcv)
            if not signals:
                continue

            combined = self._aggregate_signals(signals)
            logger.info(
                "Aggregated signal",
                symbol=symbol,
                direction=combined.direction,
                confidence=combined.confidence,
                reason=combined.reason,
            )

            if combined.direction == "HOLD":
                continue

            await self._execute_signal(combined)
            await self._snapshot_portfolio()

    async def _collect_signals(self, symbol, ohlcv) -> list[Signal]:
        """Run all strategies and collect their signals."""
        signals: list[Signal] = []
        for strategy in self._strategies:
            try:
                signal = await strategy.analyze(symbol, ohlcv)
                logger.debug(
                    "Strategy signal",
                    strategy=strategy.name,
                    symbol=symbol,
                    direction=signal.direction,
                    confidence=signal.confidence,
                )
                signals.append(signal)
            except StrategyError:
                logger.exception(
                    "Strategy failed",
                    strategy=strategy.name,
                    symbol=symbol,
                )
        return signals

    @staticmethod
    def _aggregate_signals(signals: list[Signal]) -> Signal:
        """Combine multiple strategy signals into one decision.

        Weighted average of confidence scores. Direction is decided by
        majority vote among non-HOLD signals; ties result in HOLD.
        """
        non_hold = [s for s in signals if s.direction != "HOLD"]
        if not non_hold:
            return Signal(
                symbol=signals[0].symbol,
                direction="HOLD",
                confidence=0.0,
                strategy_name="aggregator",
                reason="All strategies returned HOLD",
            )

        buy_weight = sum(
            s.confidence for s in non_hold if s.direction == "BUY"
        )
        sell_weight = sum(
            s.confidence for s in non_hold if s.direction == "SELL"
        )

        if buy_weight > sell_weight:
            direction = "BUY"
            total_weight = buy_weight
        elif sell_weight > buy_weight:
            direction = "SELL"
            total_weight = sell_weight
        else:
            return Signal(
                symbol=signals[0].symbol,
                direction="HOLD",
                confidence=0.0,
                strategy_name="aggregator",
                reason="BUY/SELL signals tied",
            )

        count = sum(
            1 for s in non_hold if s.direction == direction
        )
        avg_confidence = total_weight / count

        reasons = [
            f"{s.strategy_name}: {s.reason}"
            for s in non_hold
            if s.direction == direction
        ]

        return Signal(
            symbol=signals[0].symbol,
            direction=direction,
            confidence=avg_confidence,
            strategy_name="aggregator",
            reason=" | ".join(reasons),
        )

    async def _execute_signal(self, signal: Signal) -> None:
        """Execute a trading signal via the exchange."""
        balance = await self._exchange.get_balance()
        ticker = await self._exchange.get_ticker(signal.symbol)
        base, quote = signal.symbol.split("/")

        max_order = self._settings.risk.max_single_order_usdt
        position_pct = self._settings.risk.max_position_pct

        if signal.direction == "BUY":
            available = balance.get(quote, 0.0)
            budget = min(available * position_pct, max_order)
            if budget < 1.0:
                logger.warning(
                    "Insufficient budget for BUY",
                    symbol=signal.symbol,
                    available=available,
                )
                return
            amount = budget / ticker.last
        elif signal.direction == "SELL":
            available = balance.get(base, 0.0)
            if available <= 0:
                logger.warning(
                    "No position to SELL",
                    symbol=signal.symbol,
                )
                return
            amount = available
        else:
            return

        try:
            order = await self._exchange.create_order(
                symbol=signal.symbol,
                side=signal.direction,
                order_type="MARKET",
                amount=amount,
            )
            logger.info(
                "Order executed",
                order_id=order.id,
                symbol=order.symbol,
                side=order.side,
                amount=order.filled_amount,
                price=order.filled_price,
            )

            trade = Trade(
                id=str(uuid.uuid4()),
                symbol=order.symbol,
                side=OrderSide(signal.direction),
                amount=order.filled_amount,
                price=order.filled_price or ticker.last,
                signal=signal,
            )
            await self._db.insert_trade(trade)
            await self._db.insert_order(order)
            await self._notify_trade(trade, signal)

        except ExchangeError:
            logger.exception(
                "Order execution failed",
                symbol=signal.symbol,
                direction=signal.direction,
            )

    async def _snapshot_portfolio(self) -> None:
        """Save a portfolio balance snapshot to the database."""
        try:
            balance = await self._exchange.get_balance()
            total = 0.0
            for currency, amount in balance.items():
                if currency == "USDT":
                    total += amount
                else:
                    try:
                        ticker = await self._exchange.get_ticker(
                            f"{currency}/USDT"
                        )
                        total += amount * ticker.last
                    except ExchangeError:
                        pass
            await self._db.save_portfolio_snapshot(total, balance)
        except ExchangeError:
            logger.exception("Failed to snapshot portfolio")

    async def _notify_trade(self, trade: Trade, signal: Signal) -> None:
        if self._notifier:
            try:
                await self._notifier.send_trade(trade, signal)
            except Exception:
                logger.debug("Telegram trade notification failed")

    async def _notify_alert(self, message: str, level: str) -> None:
        if self._notifier:
            try:
                await self._notifier.send_alert(message, level)
            except Exception:
                logger.debug("Telegram alert notification failed")
