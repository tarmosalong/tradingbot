from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
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


@dataclass
class OpenPosition:
    symbol: str
    amount: float
    entry_price: float
    peak_price: float
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def stop_loss_pct(self) -> float:
        """Filled in by engine from config."""
        return self._sl_pct

    @property
    def trailing_stop_pct(self) -> float:
        return self._ts_pct

    def set_risk(self, sl_pct: float, ts_pct: float) -> None:
        self._sl_pct = sl_pct
        self._ts_pct = ts_pct

    @property
    def stop_loss_price(self) -> float:
        return self.entry_price * (1 - self._sl_pct)

    @property
    def trailing_stop_price(self) -> float:
        return self.peak_price * (1 - self._ts_pct)

    def to_dict(self, current_price: float) -> dict:
        pnl = (current_price - self.entry_price) * self.amount
        pnl_pct = ((current_price / self.entry_price) - 1) * 100 if self.entry_price else 0
        return {
            "symbol": self.symbol,
            "amount": self.amount,
            "entry_price": self.entry_price,
            "current_price": current_price,
            "peak_price": self.peak_price,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "stop_loss_price": round(self.stop_loss_price, 2),
            "trailing_stop_price": round(self.trailing_stop_price, 2),
            "opened_at": self.opened_at.isoformat(),
            "exit_conditions": [
                (
                    f"Stop-loss at ${self.stop_loss_price:,.2f}"
                    f" ({self._sl_pct*100:.1f}% below entry)"
                ),
                (
                    f"Trailing stop at ${self.trailing_stop_price:,.2f}"
                    f" ({self._ts_pct*100:.1f}% below peak"
                    f" ${self.peak_price:,.2f})"
                ),
                (
                    "Strategy SELL signal (RSI ≥ 70 or MACD bearish"
                    " crossover or price above Bollinger upper band)"
                ),
            ],
        }


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
        self._positions: dict[str, OpenPosition] = {}
        self._last_trade_time: dict[str, datetime] = {}

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

    def get_open_positions(self) -> dict[str, OpenPosition]:
        return dict(self._positions)

    async def get_positions_with_prices(self) -> list[dict]:
        result = []
        for symbol, pos in self._positions.items():
            try:
                ticker = await self._exchange.get_ticker(symbol)
                result.append(pos.to_dict(ticker.last))
            except ExchangeError:
                result.append(pos.to_dict(pos.entry_price))
        return result

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

            exited = await self._check_position_exit(symbol)
            if exited:
                await self._snapshot_portfolio()
                continue

            signals = await self._collect_signals(symbol, ohlcv)
            if not signals:
                continue

            await self._persist_signals(signals)

            combined = self._aggregate_signals(signals)
            logger.info(
                "Aggregated signal",
                symbol=symbol,
                direction=combined.direction,
                confidence=combined.confidence,
                reason=combined.reason,
            )

            await self._persist_signals([combined])
            await self._broadcast_signal(combined)

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

    async def _persist_signals(self, signals: list[Signal]) -> None:
        for sig in signals:
            try:
                await self._db.insert_signal(sig)
            except Exception:
                logger.debug("Failed to persist signal", strategy=sig.strategy_name)

    async def _broadcast_signal(self, signal: Signal) -> None:
        try:
            from backend.api.websocket import manager

            await manager.broadcast({
                "type": "signal",
                "symbol": signal.symbol,
                "direction": signal.direction,
                "confidence": signal.confidence,
                "strategy_name": signal.strategy_name,
                "reason": signal.reason,
                "indicators": signal.indicators,
                "timestamp": signal.timestamp.isoformat(),
            })
        except Exception:
            logger.debug("Signal broadcast failed")

    async def _check_position_exit(self, symbol: str) -> bool:
        """Check if an open position should be closed by stop-loss or trailing stop."""
        pos = self._positions.get(symbol)
        if not pos:
            return False

        try:
            ticker = await self._exchange.get_ticker(symbol)
        except ExchangeError:
            return False

        price = ticker.last
        if price > pos.peak_price:
            pos.peak_price = price

        risk = self._settings.risk
        sl_price = pos.entry_price * (1 - risk.stop_loss_pct)
        ts_price = pos.peak_price * (1 - risk.trailing_stop_pct)

        exit_reason = None

        if risk.stop_loss_pct > 0 and price <= sl_price:
            exit_reason = (
                f"Stop-loss triggered at ${price:,.2f}"
                f" (entry ${pos.entry_price:,.2f},"
                f" limit ${sl_price:,.2f})"
            )
        elif (
            risk.trailing_stop_pct > 0
            and price <= ts_price
            and ts_price > sl_price
        ):
            exit_reason = (
                f"Trailing stop triggered at ${price:,.2f}"
                f" (peak ${pos.peak_price:,.2f},"
                f" limit ${ts_price:,.2f})"
            )

        if not exit_reason:
            return False

        logger.info("Position exit", symbol=symbol, reason=exit_reason)

        signal = Signal(
            symbol=symbol,
            direction="SELL",
            confidence=1.0,
            strategy_name="risk_exit",
            reason=exit_reason,
            timestamp=datetime.now(UTC),
        )
        await self._persist_signals([signal])
        await self._broadcast_signal(signal)
        await self._execute_signal(signal)
        return True

    async def _execute_signal(self, signal: Signal) -> None:
        """Execute a trading signal via the exchange."""
        if signal.direction == "BUY":
            existing = self._positions.get(signal.symbol)
            if existing:
                logger.info(
                    "Skipping BUY — already holding position",
                    symbol=signal.symbol,
                    amount=existing.amount,
                    entry=existing.entry_price,
                )
                return

            last_buy_ts = self._last_trade_time.get(signal.symbol)
            cooldown = self._settings.trading.poll_interval_seconds * 3
            if last_buy_ts is not None:
                elapsed = (datetime.now(UTC) - last_buy_ts).total_seconds()
                if elapsed < cooldown:
                    logger.info(
                        "Skipping BUY — cooldown active",
                        symbol=signal.symbol,
                        elapsed_s=int(elapsed),
                        cooldown_s=cooldown,
                    )
                    return

        balance = await self._exchange.get_balance()
        ticker = await self._exchange.get_ticker(signal.symbol)
        base, quote = signal.symbol.split("/")

        max_order = self._settings.risk.max_single_order_usdt
        position_pct = self._settings.risk.max_position_pct

        if signal.direction == "BUY":
            available = balance.get(quote, 0.0)
            total_portfolio = sum(balance.values())
            max_for_symbol = total_portfolio * position_pct
            budget = min(available * position_pct, max_order, max_for_symbol)
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

            fill_price = order.filled_price or ticker.last

            if signal.direction == "BUY":
                existing = self._positions.get(signal.symbol)
                if existing:
                    total_amount = existing.amount + order.filled_amount
                    avg_price = (
                        (existing.entry_price * existing.amount + fill_price * order.filled_amount)
                        / total_amount
                    )
                    existing.amount = total_amount
                    existing.entry_price = avg_price
                    if fill_price > existing.peak_price:
                        existing.peak_price = fill_price
                else:
                    pos = OpenPosition(
                        symbol=signal.symbol,
                        amount=order.filled_amount,
                        entry_price=fill_price,
                        peak_price=fill_price,
                    )
                    pos.set_risk(
                        self._settings.risk.stop_loss_pct,
                        self._settings.risk.trailing_stop_pct,
                    )
                    self._positions[signal.symbol] = pos
            elif signal.direction == "SELL":
                self._positions.pop(signal.symbol, None)

            trade = Trade(
                id=str(uuid.uuid4()),
                symbol=order.symbol,
                side=OrderSide(signal.direction),
                amount=order.filled_amount,
                price=fill_price,
                signal=signal,
            )
            await self._db.insert_trade(trade)
            await self._db.insert_order(order)
            await self._notify_trade(trade, signal)
            self._last_trade_time[signal.symbol] = datetime.now(UTC)

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
