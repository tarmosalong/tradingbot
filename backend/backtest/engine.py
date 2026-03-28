from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from backend.backtest.ai_filter import AIFilterConfig, AISimulationFilter
from backend.backtest.exchange import BacktestExchange
from backend.config import RiskConfig
from backend.core.engine import TradingEngine
from backend.core.exceptions import ExchangeError, StrategyError
from backend.core.logger import get_logger
from backend.models import OrderSide, Signal, Trade
from backend.strategies.base import StrategyBase

logger = get_logger("backtest_engine")

MIN_CANDLES_FOR_STRATEGY = 30


@dataclass
class BacktestTrade:
    trade: Trade
    signal: Signal
    portfolio_value: float


@dataclass
class BacktestResult:
    symbol: str
    initial_balance: float
    final_balance: float
    equity_curve: list[float] = field(default_factory=list)
    timestamps: list[str] = field(default_factory=list)
    trades: list[BacktestTrade] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    ai_filter_stats: dict[str, int] = field(default_factory=dict)


class BacktestEngine:
    """Replays historical data through strategies and simulates trades."""

    def __init__(
        self,
        exchange: BacktestExchange,
        strategies: list[StrategyBase],
        symbol: str = "BTC/USDT",
        risk_config: RiskConfig | None = None,
        ai_filter_config: AIFilterConfig | None = None,
    ) -> None:
        self._exchange = exchange
        self._strategies = strategies
        self._symbol = symbol
        self._risk = risk_config or RiskConfig()
        self._ai_filter = AISimulationFilter(ai_filter_config)

    async def run(self) -> BacktestResult:
        """Run the backtest across all candles and return results."""
        initial_value = await self._exchange.get_portfolio_value()
        result = BacktestResult(
            symbol=self._symbol,
            initial_balance=initial_value,
            final_balance=initial_value,
        )

        logger.info(
            "Backtest started",
            symbol=self._symbol,
            candles=self._exchange.total_candles,
            strategies=[s.name for s in self._strategies],
        )

        while True:
            portfolio_value = await self._exchange.get_portfolio_value()
            result.equity_curve.append(portfolio_value)

            row = self._exchange._current_row()
            result.timestamps.append(str(row["timestamp"]))

            ohlcv = await self._exchange.get_ohlcv(self._symbol, limit=100)

            if len(ohlcv) >= MIN_CANDLES_FOR_STRATEGY:
                signals = await self._collect_signals(ohlcv)

                if signals:
                    combined = TradingEngine._aggregate_signals(signals)
                    combined = self._ai_filter.evaluate(combined, ohlcv)
                    result.signals.append(combined)

                    if combined.direction != "HOLD":
                        trade = await self._execute_signal(
                            combined, portfolio_value
                        )
                        if trade:
                            pv = await self._exchange.get_portfolio_value()
                            result.trades.append(
                                BacktestTrade(
                                    trade=trade,
                                    signal=combined,
                                    portfolio_value=pv,
                                )
                            )

            if not self._exchange.advance():
                break

        result.final_balance = await self._exchange.get_portfolio_value()
        result.equity_curve.append(result.final_balance)
        final_row = self._exchange._current_row()
        result.timestamps.append(str(final_row["timestamp"]))
        result.ai_filter_stats = self._ai_filter.stats.to_dict()

        logger.info(
            "Backtest completed",
            symbol=self._symbol,
            initial=result.initial_balance,
            final=result.final_balance,
            return_pct=f"{(result.final_balance / result.initial_balance - 1) * 100:.2f}%",
            total_trades=len(result.trades),
        )

        return result

    async def _collect_signals(self, ohlcv) -> list[Signal]:
        signals: list[Signal] = []
        for strategy in self._strategies:
            try:
                signal = await strategy.analyze(self._symbol, ohlcv)
                signals.append(signal)
            except StrategyError:
                logger.debug(
                    "Strategy failed in backtest",
                    strategy=strategy.name,
                )
        return signals

    async def _execute_signal(
        self, signal: Signal, portfolio_value: float
    ) -> Trade | None:
        balance = await self._exchange.get_balance()
        ticker = await self._exchange.get_ticker(self._symbol)
        base, quote = self._symbol.split("/")

        max_order = self._risk.max_single_order_usdt
        position_pct = self._risk.max_position_pct

        if signal.direction == "BUY":
            available = balance.get(quote, 0.0)
            budget = min(available * position_pct, max_order)
            if budget < 1.0:
                return None
            amount = budget / ticker.last
        elif signal.direction == "SELL":
            available = balance.get(base, 0.0)
            if available <= 0:
                return None
            amount = available
        else:
            return None

        try:
            order = await self._exchange.create_order(
                symbol=self._symbol,
                side=signal.direction,
                order_type="MARKET",
                amount=amount,
            )
            return Trade(
                id=str(uuid.uuid4()),
                symbol=order.symbol,
                side=OrderSide(signal.direction),
                amount=order.filled_amount,
                price=order.filled_price or ticker.last,
                signal=signal,
                executed_at=order.created_at,
            )
        except ExchangeError:
            logger.debug("Backtest order failed", symbol=self._symbol)
            return None
