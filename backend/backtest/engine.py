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


@dataclass(frozen=True)
class EngineConfig:
    min_confidence: float = 0.0
    cooldown_candles: int = 0
    use_dynamic_sizing: bool = False
    enable_regime_filter: bool = False
    adx_period: int = 14
    adx_trending_threshold: float = 25.0
    take_profit_pct: float = 0.0
    take_profit_ratio: float = 0.5


@dataclass
class BacktestTrade:
    trade: Trade
    signal: Signal
    portfolio_value: float


@dataclass
class Position:
    entry_price: float
    amount: float
    peak_price: float
    candle_index: int


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
    engine_stats: dict[str, object] = field(default_factory=dict)


class BacktestEngine:
    """Replays historical data through strategies and simulates trades."""

    def __init__(
        self,
        exchange: BacktestExchange,
        strategies: list[StrategyBase],
        symbol: str = "BTC/USDT",
        risk_config: RiskConfig | None = None,
        ai_filter_config: AIFilterConfig | None = None,
        engine_config: EngineConfig | None = None,
    ) -> None:
        self._exchange = exchange
        self._strategies = strategies
        self._symbol = symbol
        self._risk = risk_config or RiskConfig()
        self._ai_filter = AISimulationFilter(ai_filter_config)
        self._cfg = engine_config or EngineConfig()

        self._position: Position | None = None
        self._last_trade_index = -999
        self._peak_portfolio = 0.0
        self._drawdown_halted = False

        self._stats = {
            "stop_loss_exits": 0,
            "trailing_stop_exits": 0,
            "take_profit_exits": 0,
            "drawdown_halt_candle": None,
            "signals_below_confidence": 0,
            "cooldown_skips": 0,
            "regime_filtered": 0,
            "total_fees": 0.0,
            "total_slippage": 0.0,
        }

    async def run(self) -> BacktestResult:
        """Run the backtest across all candles and return results."""
        initial_value = await self._exchange.get_portfolio_value()
        self._peak_portfolio = initial_value
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

            if portfolio_value > self._peak_portfolio:
                self._peak_portfolio = portfolio_value

            row = self._exchange._current_row()
            result.timestamps.append(str(row["timestamp"]))
            current_price = float(row["close"])

            if self._check_drawdown_halt(portfolio_value, initial_value):
                if not self._exchange.advance():
                    break
                continue

            if self._position:
                exit_trade = await self._check_position_exits(
                    current_price, row, portfolio_value, result,
                )
                if exit_trade:
                    self._position = None

            ohlcv = await self._exchange.get_ohlcv(self._symbol, limit=100)

            if len(ohlcv) >= MIN_CANDLES_FOR_STRATEGY and not self._drawdown_halted:
                if self._cfg.enable_regime_filter:
                    if self._is_regime_filtered(ohlcv):
                        self._stats["regime_filtered"] += 1
                        if not self._exchange.advance():
                            break
                        continue

                signals = await self._collect_signals(ohlcv)

                if signals:
                    combined = TradingEngine._aggregate_signals(signals)
                    combined = self._ai_filter.evaluate(combined, ohlcv)
                    result.signals.append(combined)

                    if combined.direction != "HOLD":
                        if not self._passes_filters(combined):
                            if not self._exchange.advance():
                                break
                            continue

                        trade = await self._execute_signal(
                            combined, portfolio_value
                        )
                        if trade:
                            self._last_trade_index = self._exchange.current_index
                            pv = await self._exchange.get_portfolio_value()
                            result.trades.append(
                                BacktestTrade(
                                    trade=trade,
                                    signal=combined,
                                    portfolio_value=pv,
                                )
                            )
                            if combined.direction == "BUY":
                                self._position = Position(
                                    entry_price=trade.price,
                                    amount=trade.amount,
                                    peak_price=trade.price,
                                    candle_index=self._exchange.current_index,
                                )
                            elif combined.direction == "SELL":
                                self._position = None

            if not self._exchange.advance():
                break

        result.final_balance = await self._exchange.get_portfolio_value()
        result.equity_curve.append(result.final_balance)
        final_row = self._exchange._current_row()
        result.timestamps.append(str(final_row["timestamp"]))
        result.ai_filter_stats = self._ai_filter.stats.to_dict()

        self._stats["total_fees"] = self._exchange.total_fees_paid
        self._stats["total_slippage"] = self._exchange.total_slippage_cost
        result.engine_stats = dict(self._stats)

        logger.info(
            "Backtest completed",
            symbol=self._symbol,
            initial=result.initial_balance,
            final=result.final_balance,
            return_pct=(
                f"{(result.final_balance / result.initial_balance - 1) * 100:.2f}%"
            ),
            total_trades=len(result.trades),
            fees=f"${self._exchange.total_fees_paid:.2f}",
            slippage=f"${self._exchange.total_slippage_cost:.2f}",
        )

        return result

    def _check_drawdown_halt(
        self, portfolio_value: float, initial_value: float,
    ) -> bool:
        if self._risk.max_drawdown_pct <= 0:
            return False
        drawdown = 1.0 - (portfolio_value / self._peak_portfolio)
        if drawdown >= self._risk.max_drawdown_pct:
            if not self._drawdown_halted:
                self._drawdown_halted = True
                self._stats["drawdown_halt_candle"] = self._exchange.current_index
                logger.warning(
                    "Drawdown circuit breaker triggered",
                    drawdown=f"{drawdown * 100:.1f}%",
                    limit=f"{self._risk.max_drawdown_pct * 100:.1f}%",
                )
            return True
        return False

    async def _check_position_exits(
        self,
        current_price: float,
        row,
        portfolio_value: float,
        result: BacktestResult,
    ) -> Trade | None:
        pos = self._position
        if not pos:
            return None

        low_price = float(row["low"])
        high_price = float(row["high"])

        if high_price > pos.peak_price:
            pos.peak_price = high_price

        sl_price = pos.entry_price * (1.0 - self._risk.stop_loss_pct)
        if low_price <= sl_price and self._risk.stop_loss_pct > 0:
            trade = await self._force_sell(sl_price, pos)
            if trade:
                self._stats["stop_loss_exits"] += 1
                pv = await self._exchange.get_portfolio_value()
                result.trades.append(BacktestTrade(
                    trade=trade,
                    signal=Signal(
                        symbol=self._symbol,
                        direction="SELL",
                        confidence=1.0,
                        strategy_name="stop_loss",
                        reason=f"Stop-loss at {sl_price:.2f} (entry {pos.entry_price:.2f})",
                    ),
                    portfolio_value=pv,
                ))
                return trade

        if self._risk.trailing_stop_pct > 0:
            ts_price = pos.peak_price * (1.0 - self._risk.trailing_stop_pct)
            if low_price <= ts_price and ts_price > sl_price:
                trade = await self._force_sell(ts_price, pos)
                if trade:
                    self._stats["trailing_stop_exits"] += 1
                    pv = await self._exchange.get_portfolio_value()
                    result.trades.append(BacktestTrade(
                        trade=trade,
                        signal=Signal(
                            symbol=self._symbol,
                            direction="SELL",
                            confidence=1.0,
                            strategy_name="trailing_stop",
                            reason=(
                                f"Trailing stop at {ts_price:.2f} "
                                f"(peak {pos.peak_price:.2f})"
                            ),
                        ),
                        portfolio_value=pv,
                    ))
                    return trade

        tp_pct = self._cfg.take_profit_pct
        if tp_pct > 0:
            tp_price = pos.entry_price * (1.0 + tp_pct)
            if high_price >= tp_price:
                sell_amount = pos.amount * self._cfg.take_profit_ratio
                if sell_amount > 0:
                    trade = await self._force_sell(
                        tp_price, pos, amount_override=sell_amount,
                    )
                    if trade:
                        self._stats["take_profit_exits"] += 1
                        pos.amount -= sell_amount
                        if pos.amount <= 1e-10:
                            pv = await self._exchange.get_portfolio_value()
                            result.trades.append(BacktestTrade(
                                trade=trade,
                                signal=Signal(
                                    symbol=self._symbol,
                                    direction="SELL",
                                    confidence=1.0,
                                    strategy_name="take_profit",
                                    reason=f"Take profit at {tp_price:.2f}",
                                ),
                                portfolio_value=pv,
                            ))
                            return trade
                        pv = await self._exchange.get_portfolio_value()
                        result.trades.append(BacktestTrade(
                            trade=trade,
                            signal=Signal(
                                symbol=self._symbol,
                                direction="SELL",
                                confidence=0.8,
                                strategy_name="take_profit_partial",
                                reason=(
                                    f"Partial take-profit {self._cfg.take_profit_ratio:.0%} "
                                    f"at {tp_price:.2f}"
                                ),
                            ),
                            portfolio_value=pv,
                        ))

        return None

    async def _force_sell(
        self, target_price: float, pos: Position,
        amount_override: float | None = None,
    ) -> Trade | None:
        amount = amount_override if amount_override else pos.amount
        base = self._symbol.split("/")[0]
        available = (await self._exchange.get_balance()).get(base, 0.0)
        amount = min(amount, available)
        if amount <= 0:
            return None
        try:
            order = await self._exchange.create_order(
                symbol=self._symbol,
                side="SELL",
                order_type="MARKET",
                amount=amount,
            )
            return Trade(
                id=str(uuid.uuid4()),
                symbol=order.symbol,
                side=OrderSide.SELL,
                amount=order.filled_amount,
                price=order.filled_price or target_price,
                signal=None,
                executed_at=order.created_at,
            )
        except ExchangeError:
            return None

    def _passes_filters(self, signal: Signal) -> bool:
        if signal.confidence < self._cfg.min_confidence:
            self._stats["signals_below_confidence"] += 1
            return False

        candles_since = (
            self._exchange.current_index - self._last_trade_index
        )
        if self._cfg.cooldown_candles > 0 and candles_since < self._cfg.cooldown_candles:
            self._stats["cooldown_skips"] += 1
            return False

        return True

    def _is_regime_filtered(self, ohlcv) -> bool:
        import pandas_ta as ta

        adx_df = ta.adx(
            ohlcv["high"], ohlcv["low"], ohlcv["close"],
            length=self._cfg.adx_period,
        )
        if adx_df is None or adx_df.empty:
            return False

        col = next(
            (c for c in adx_df.columns if c.startswith("ADX_")), None,
        )
        if not col:
            return False

        import pandas as pd

        adx_val = adx_df[col].iloc[-1]
        if pd.isna(adx_val):
            return False

        return float(adx_val) > self._cfg.adx_trending_threshold

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

        if self._cfg.use_dynamic_sizing:
            position_pct = position_pct * signal.confidence

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
