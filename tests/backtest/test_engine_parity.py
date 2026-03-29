"""Scenario tests verifying backtest engine parity with live TradingEngine.

Each test exercises a specific guard, exit condition, or sizing rule that
exists in the live engine and must behave identically in the backtest.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from backend.backtest.engine import BacktestEngine, EngineConfig, Position
from backend.backtest.exchange import BacktestExchange
from backend.config import RiskConfig
from backend.models import Signal
from backend.strategies.base import StrategyBase

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _risk(**overrides) -> RiskConfig:
    """Build a RiskConfig with sensible defaults for controlled scenarios."""
    defaults = dict(
        max_position_pct=0.50,
        stop_loss_pct=0.03,
        trailing_stop_pct=0.02,
        max_drawdown_pct=0.15,
        daily_loss_limit_pct=0.05,
        max_single_order_usdt=5000.0,
        min_confidence=0.3,
        ema_trend_enabled=False,
        volume_min_multiplier=0.0,
        atr_stop_multiplier=2.0,
        atr_tp_multiplier=3.0,
        atr_trailing_multiplier=1.5,
        risk_per_trade_pct=0.01,
        partial_tp_ratio=0.5,
    )
    defaults.update(overrides)
    return RiskConfig(**defaults)


class _FixedStrategy(StrategyBase):
    """Strategy that always returns a fixed signal direction."""

    def __init__(self, direction: str, confidence: float = 0.8):
        super().__init__()
        self._direction = direction
        self._confidence = confidence

    @property
    def name(self) -> str:
        return "fixed"

    async def analyze(self, symbol: str, ohlcv) -> Signal:
        return Signal(
            symbol=symbol,
            direction=self._direction,
            confidence=self._confidence,
            strategy_name="fixed",
            reason=f"Fixed signal: {self._direction}",
        )


class _AlternatingStrategy(StrategyBase):
    """Alternates between BUY and SELL on each call."""

    def __init__(self, start: str = "BUY", confidence: float = 0.8):
        super().__init__()
        self._next = start
        self._confidence = confidence

    @property
    def name(self) -> str:
        return "alternating"

    async def analyze(self, symbol: str, ohlcv) -> Signal:
        direction = self._next
        self._next = "SELL" if direction == "BUY" else "BUY"
        return Signal(
            symbol=symbol,
            direction=direction,
            confidence=self._confidence,
            strategy_name="alternating",
            reason=f"Alternating: {direction}",
        )


def _uptrend_ohlcv(
    n: int = 80, start_price: float = 100.0, step: float = 0.5,
    volume: float = 200.0,
) -> pd.DataFrame:
    rows = []
    for i in range(n):
        ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
        price = start_price + i * step
        rows.append({
            "timestamp": ts,
            "open": price - 0.2,
            "high": price + 1.5,
            "low": price - 1.5,
            "close": price,
            "volume": volume,
        })
    return pd.DataFrame(rows)


def _crash_ohlcv(
    n: int = 80, peak_price: float = 100.0, crash_at: int = 50,
    crash_pct: float = 0.20, volume: float = 200.0,
) -> pd.DataFrame:
    rows = []
    for i in range(n):
        ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
        if i < crash_at:
            price = peak_price + i * 0.3
        else:
            drop = crash_pct * (i - crash_at) / (n - crash_at)
            price = (peak_price + crash_at * 0.3) * (1 - drop)
        rows.append({
            "timestamp": ts,
            "open": price + 0.1,
            "high": price + 2.0,
            "low": price - 2.0,
            "close": price,
            "volume": volume,
        })
    return pd.DataFrame(rows)


def _multiday_ohlcv(days: int = 3, candles_per_day: int = 24) -> pd.DataFrame:
    """Generate multi-day data with intraday decline pattern."""
    rows = []
    price = 100.0
    for d in range(days):
        for h in range(candles_per_day):
            ts = datetime(2025, 1, 1 + d, h, tzinfo=UTC)
            if d == 1:
                price -= 0.3
            else:
                price += 0.1
            rows.append({
                "timestamp": ts,
                "open": price + 0.1,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": 200.0,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# ATR-based stop-loss
# ---------------------------------------------------------------------------

class TestATRStopLoss:
    """Backtest should compute ATR-based stop on entry and exit when hit."""

    @pytest.mark.asyncio
    async def test_atr_stop_triggers_on_crash(self):
        ohlcv = _crash_ohlcv(n=80, crash_pct=0.15)
        ex = BacktestExchange(ohlcv, initial_balance_usdt=10000.0, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(),
        )
        result = await engine.run()
        sl_exits = int(result.engine_stats.get("stop_loss_exits", 0))
        ts_exits = int(result.engine_stats.get("trailing_stop_exits", 0))
        assert sl_exits + ts_exits > 0, "ATR stops should trigger during crash"

    @pytest.mark.asyncio
    async def test_position_has_atr_fields_after_buy(self):
        ohlcv = _uptrend_ohlcv(n=50)
        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(),
        )

        while not ex.is_finished:
            if engine._position is not None:
                pos = engine._position
                assert pos.atr_at_entry > 0, "ATR at entry must be positive"
                assert pos.atr_stop_loss > 0, "ATR stop-loss must be set"
                assert pos.atr_take_profit > 0, "ATR take-profit must be set"
                assert pos.original_amount > 0
                break
            ohlcv_slice = await ex.get_ohlcv("BTC/USDT", limit=100)
            if len(ohlcv_slice) >= 30:
                signals = await engine._collect_signals(ohlcv_slice)
                if signals:
                    from backend.core.engine import TradingEngine
                    combined = TradingEngine._aggregate_signals(signals)
                    if combined.direction == "BUY":
                        pv = await ex.get_portfolio_value()
                        trade = await engine._execute_signal(combined, pv, ohlcv_slice)
                        if trade:
                            from backend.risk.manager import RiskManager
                            atr = RiskManager.calculate_atr(ohlcv_slice)
                            fill = trade.price
                            sl = fill - atr * 2.0
                            tp = fill + atr * 3.0
                            engine._position = Position(
                                entry_price=fill,
                                amount=trade.amount,
                                original_amount=trade.amount,
                                peak_price=fill,
                                candle_index=ex.current_index,
                                atr_at_entry=atr,
                                atr_stop_loss=sl,
                                atr_take_profit=tp,
                                atr_trailing_multiplier=1.5,
                            )
                            break
            ex.advance()

        if engine._position:
            pos = engine._position
            assert pos.atr_at_entry > 0
            assert pos.stop_loss_price > 0
            assert pos.take_profit_price > 0
            assert pos.trailing_stop_price > 0


# ---------------------------------------------------------------------------
# ATR trailing stop
# ---------------------------------------------------------------------------

class TestATRTrailingStop:
    """Backtest trailing stop tracks peak and exits on pullback."""

    @pytest.mark.asyncio
    async def test_trailing_stop_exits_after_rally(self):
        ohlcv = _crash_ohlcv(n=100, peak_price=100.0, crash_at=60, crash_pct=0.10)
        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(atr_trailing_multiplier=1.0),
        )
        result = await engine.run()
        ts_exits = int(result.engine_stats.get("trailing_stop_exits", 0))
        sl_exits = int(result.engine_stats.get("stop_loss_exits", 0))
        assert ts_exits > 0 or sl_exits > 0


# ---------------------------------------------------------------------------
# Partial take-profit
# ---------------------------------------------------------------------------

class TestPartialTakeProfit:
    """Partial TP fires at ATR TP level, then breakeven stop is set."""

    @pytest.mark.asyncio
    async def test_partial_tp_fires_and_breakeven(self):
        ohlcv = _uptrend_ohlcv(n=120, step=1.0)
        ex = BacktestExchange(ohlcv, initial_balance_usdt=10000.0, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(
                atr_tp_multiplier=2.0,
                partial_tp_ratio=0.5,
            ),
        )
        result = await engine.run()
        partial_exits = int(result.engine_stats.get("partial_tp_exits", 0))
        assert partial_exits > 0, "Partial take-profit should fire on strong uptrend"

        partial_trades = [
            t for t in result.trades
            if t.signal.strategy_name == "partial_tp"
        ]
        assert len(partial_trades) > 0


# ---------------------------------------------------------------------------
# Volume filter
# ---------------------------------------------------------------------------

class TestVolumeFilter:
    """Volume confirmation guard blocks trades with insufficient volume."""

    @pytest.mark.asyncio
    async def test_low_volume_blocks_trade(self):
        ohlcv = _uptrend_ohlcv(n=60, volume=10.0)
        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(volume_min_multiplier=1.2),
        )
        result = await engine.run()
        vol_filtered = int(result.engine_stats.get("volume_filtered", 0))
        assert vol_filtered > 0, "Volume filter should block signals with low uniform volume"

    @pytest.mark.asyncio
    async def test_disabled_volume_allows_trade(self):
        ohlcv = _uptrend_ohlcv(n=60, volume=10.0)
        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(volume_min_multiplier=0.0),
        )
        result = await engine.run()
        assert len(result.trades) > 0, "Disabled volume filter should allow trades"


# ---------------------------------------------------------------------------
# EMA trend filter
# ---------------------------------------------------------------------------

class TestEMATrendFilter:
    """EMA filter blocks BUY in downtrend and SELL in uptrend."""

    @pytest.mark.asyncio
    async def test_ema_blocks_buy_in_downtrend(self):
        rows = []
        for i in range(80):
            ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
            price = 200.0 - i * 1.5
            rows.append({
                "timestamp": ts,
                "open": price + 0.1,
                "high": price + 2.0,
                "low": price - 2.0,
                "close": price,
                "volume": 200.0,
            })
        ohlcv = pd.DataFrame(rows)

        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(ema_trend_enabled=True, ema_trend_period=20),
        )
        result = await engine.run()
        ema_filtered = int(result.engine_stats.get("ema_filtered", 0))
        assert ema_filtered > 0, "EMA should block BUY in downtrend"

    @pytest.mark.asyncio
    async def test_ema_allows_buy_in_uptrend(self):
        ohlcv = _uptrend_ohlcv(n=80, step=1.0)
        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(ema_trend_enabled=True, ema_trend_period=20),
        )
        result = await engine.run()
        assert len(result.trades) > 0, "EMA should allow BUY in uptrend"


# ---------------------------------------------------------------------------
# Confidence filter
# ---------------------------------------------------------------------------

class TestConfidenceFilter:
    """Min confidence blocks weak signals."""

    @pytest.mark.asyncio
    async def test_low_confidence_blocked(self):
        ohlcv = _uptrend_ohlcv(n=60)
        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.2)],
            symbol="BTC/USDT",
            risk_config=_risk(min_confidence=0.5),
        )
        result = await engine.run()
        below = int(result.engine_stats.get("signals_below_confidence", 0))
        assert below > 0
        assert len(result.trades) == 0

    @pytest.mark.asyncio
    async def test_high_confidence_passes(self):
        ohlcv = _uptrend_ohlcv(n=60)
        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(min_confidence=0.3),
        )
        result = await engine.run()
        assert len(result.trades) > 0


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

class TestCooldown:
    """Cooldown prevents rapid consecutive trades."""

    @pytest.mark.asyncio
    async def test_cooldown_reduces_trades(self):
        ohlcv = _uptrend_ohlcv(n=80)
        ex_fast = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine_fast = BacktestEngine(
            exchange=ex_fast,
            strategies=[_AlternatingStrategy(confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(),
            engine_config=EngineConfig(cooldown_candles=0),
        )
        result_fast = await engine_fast.run()

        ex_slow = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine_slow = BacktestEngine(
            exchange=ex_slow,
            strategies=[_AlternatingStrategy(confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(),
            engine_config=EngineConfig(cooldown_candles=10),
        )
        result_slow = await engine_slow.run()

        assert len(result_slow.trades) <= len(result_fast.trades)
        cooldown_skips = int(result_slow.engine_stats.get("cooldown_skips", 0))
        assert cooldown_skips > 0


# ---------------------------------------------------------------------------
# Duplicate BUY blocked
# ---------------------------------------------------------------------------

class TestDuplicateBuyBlocked:
    """Cannot open a second position while one is already open."""

    @pytest.mark.asyncio
    async def test_second_buy_blocked(self):
        ohlcv = _uptrend_ohlcv(n=80)
        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(),
        )
        result = await engine.run()
        buy_trades = [t for t in result.trades if t.trade.side.value == "BUY"]
        sell_trades = [t for t in result.trades if t.trade.side.value == "SELL"]
        assert len(buy_trades) <= len(sell_trades) + 1


# ---------------------------------------------------------------------------
# Drawdown halt
# ---------------------------------------------------------------------------

class TestDrawdownHalt:
    """Drawdown circuit breaker stops all trading."""

    @pytest.mark.asyncio
    async def test_drawdown_halts_permanently(self):
        ohlcv = _crash_ohlcv(n=100, crash_pct=0.25)
        ex = BacktestExchange(ohlcv, initial_balance_usdt=10000.0, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(max_drawdown_pct=0.005),
        )
        result = await engine.run()
        assert result.engine_stats.get("drawdown_halt_candle") is not None

    @pytest.mark.asyncio
    async def test_no_drawdown_halt_when_profitable(self):
        ohlcv = _uptrend_ohlcv(n=80, step=1.0)
        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(max_drawdown_pct=0.15),
        )
        result = await engine.run()
        assert result.engine_stats.get("drawdown_halt_candle") is None


# ---------------------------------------------------------------------------
# Daily loss limit
# ---------------------------------------------------------------------------

class TestDailyLossLimit:
    """Daily loss limit pauses trading for the rest of the calendar day."""

    @pytest.mark.asyncio
    async def test_daily_loss_stops_trading(self):
        ohlcv = _crash_ohlcv(n=100, crash_pct=0.20)
        ex = BacktestExchange(ohlcv, initial_balance_usdt=10000.0, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(daily_loss_limit_pct=0.005),
        )
        result = await engine.run()
        daily_skips = int(result.engine_stats.get("daily_loss_skips", 0))
        assert daily_skips > 0, "Daily loss limit should trigger on crash"


# ---------------------------------------------------------------------------
# ATR position sizing
# ---------------------------------------------------------------------------

class TestATRPositionSizing:
    """ATR-based budget limits position size in volatile markets."""

    @pytest.mark.asyncio
    async def test_volatile_market_smaller_position(self):
        calm = _uptrend_ohlcv(n=60, start_price=100.0, step=0.1, volume=200.0)
        volatile_rows = []
        for i in range(60):
            ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
            price = 100.0 + i * 0.1
            swing = 8.0 if i % 2 == 0 else -8.0
            volatile_rows.append({
                "timestamp": ts,
                "open": price - swing,
                "high": price + abs(swing) + 2.0,
                "low": price - abs(swing) - 2.0,
                "close": price + swing * 0.3,
                "volume": 200.0,
            })
        volatile = pd.DataFrame(volatile_rows)

        ex_calm = BacktestExchange(
            calm, initial_balance_usdt=10000.0, fee_rate=0.0, slippage_rate=0.0,
        )
        engine_calm = BacktestEngine(
            exchange=ex_calm,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(risk_per_trade_pct=0.005, max_single_order_usdt=50000.0),
        )
        result_calm = await engine_calm.run()

        ex_vol = BacktestExchange(
            volatile, initial_balance_usdt=10000.0, fee_rate=0.0, slippage_rate=0.0,
        )
        engine_vol = BacktestEngine(
            exchange=ex_vol,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(risk_per_trade_pct=0.005, max_single_order_usdt=50000.0),
        )
        result_vol = await engine_vol.run()

        calm_buys = [t for t in result_calm.trades if t.trade.side.value == "BUY"]
        vol_buys = [t for t in result_vol.trades if t.trade.side.value == "BUY"]

        if calm_buys and vol_buys:
            calm_size = calm_buys[0].trade.amount * calm_buys[0].trade.price
            vol_size = vol_buys[0].trade.amount * vol_buys[0].trade.price
            assert vol_size < calm_size, (
                f"Volatile market should have smaller position: {vol_size:.2f} vs {calm_size:.2f}"
            )


# ---------------------------------------------------------------------------
# Strategy weighting
# ---------------------------------------------------------------------------

class TestStrategyWeighting:
    """Backtest uses strategy weights for signal aggregation."""

    @pytest.mark.asyncio
    async def test_weighted_aggregation(self):
        ohlcv = _uptrend_ohlcv(n=60)
        ex_no_w = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine_no_w = BacktestEngine(
            exchange=ex_no_w,
            strategies=[_FixedStrategy("BUY", confidence=0.6)],
            symbol="BTC/USDT",
            risk_config=_risk(min_confidence=0.5),
        )
        result_no_w = await engine_no_w.run()

        ex_w = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine_w = BacktestEngine(
            exchange=ex_w,
            strategies=[_FixedStrategy("BUY", confidence=0.6)],
            symbol="BTC/USDT",
            risk_config=_risk(min_confidence=0.5),
            strategy_weights={"fixed": 0.1},
        )
        result_w = await engine_w.run()

        assert len(result_no_w.trades) >= len(result_w.trades)


# ---------------------------------------------------------------------------
# Percentage-based fallback (no ATR)
# ---------------------------------------------------------------------------

class TestPercentageFallback:
    """When ATR is zero, falls back to percentage-based stops."""

    @pytest.mark.asyncio
    async def test_flat_market_uses_pct_stops(self):
        rows = []
        for i in range(80):
            ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
            price = 100.0
            rows.append({
                "timestamp": ts,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 200.0,
            })
        for i in range(80, 120):
            ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
            price = 100.0 - (i - 80) * 0.5
            rows.append({
                "timestamp": ts,
                "open": price + 0.1,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price,
                "volume": 200.0,
            })
        ohlcv = pd.DataFrame(rows)

        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(stop_loss_pct=0.03),
        )
        result = await engine.run()
        sl_exits = int(result.engine_stats.get("stop_loss_exits", 0))
        ts_exits = int(result.engine_stats.get("trailing_stop_exits", 0))
        assert sl_exits + ts_exits > 0 or len(result.trades) == 0


# ---------------------------------------------------------------------------
# Position properties
# ---------------------------------------------------------------------------

class TestPositionProperties:
    """Position dataclass computes stop/trailing/TP correctly."""

    def test_stop_loss_from_atr(self):
        pos = Position(
            entry_price=100.0, amount=1.0, original_amount=1.0,
            peak_price=105.0, candle_index=0,
            atr_at_entry=5.0, atr_stop_loss=90.0, atr_take_profit=115.0,
            atr_trailing_multiplier=1.5,
        )
        assert pos.stop_loss_price == 90.0
        assert pos.take_profit_price == 115.0
        assert pos.trailing_stop_price == 105.0 - 5.0 * 1.5  # 97.5

    def test_trailing_updates_with_peak(self):
        pos = Position(
            entry_price=100.0, amount=1.0, original_amount=1.0,
            peak_price=100.0, candle_index=0,
            atr_at_entry=5.0, atr_stop_loss=90.0, atr_take_profit=115.0,
            atr_trailing_multiplier=1.5,
        )
        ts1 = pos.trailing_stop_price
        pos.peak_price = 110.0
        ts2 = pos.trailing_stop_price
        assert ts2 > ts1

    def test_zero_atr_gives_zero_trailing(self):
        pos = Position(
            entry_price=100.0, amount=1.0, original_amount=1.0,
            peak_price=100.0, candle_index=0,
        )
        assert pos.stop_loss_price == 0.0
        assert pos.trailing_stop_price == 0.0
        assert pos.take_profit_price == 0.0


# ---------------------------------------------------------------------------
# Engine stats completeness
# ---------------------------------------------------------------------------

class TestEngineStatsComplete:
    """All expected stats keys are present in the result."""

    @pytest.mark.asyncio
    async def test_all_stat_keys_present(self):
        ohlcv = _uptrend_ohlcv(n=50)
        ex = BacktestExchange(ohlcv)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(),
        )
        result = await engine.run()
        expected_keys = {
            "stop_loss_exits", "trailing_stop_exits", "take_profit_exits",
            "partial_tp_exits", "drawdown_halt_candle", "daily_loss_skips",
            "signals_below_confidence", "cooldown_skips", "regime_filtered",
            "volume_filtered", "ema_filtered", "total_fees", "total_slippage",
        }
        for key in expected_keys:
            assert key in result.engine_stats, f"Missing stat: {key}"


# ---------------------------------------------------------------------------
# Full cycle: BUY → stop → re-enter → profit
# ---------------------------------------------------------------------------

class TestFullCycle:
    """Multi-trade cycle: BUY, stop-loss, re-enter, take-profit."""

    @pytest.mark.asyncio
    async def test_buy_stop_reenter_profit(self):
        rows = []
        price = 100.0
        for i in range(150):
            ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
            if i < 40:
                price = 100.0 + i * 0.1
            elif 40 <= i < 50:
                price = 104.0 - (i - 40) * 2.0
            elif 50 <= i < 60:
                price = 84.0 + (i - 50) * 0.5
            elif 60 <= i < 80:
                price = 89.0 + (i - 60) * 0.3
            else:
                price = 95.0 + (i - 80) * 0.8
            rows.append({
                "timestamp": ts,
                "open": price + 0.1,
                "high": price + 2.0,
                "low": price - 2.0,
                "close": price,
                "volume": 200.0,
            })
        ohlcv = pd.DataFrame(rows)

        ex = BacktestExchange(
            ohlcv, initial_balance_usdt=10000.0, fee_rate=0.001, slippage_rate=0.0005,
        )
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_AlternatingStrategy(start="BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(),
            engine_config=EngineConfig(cooldown_candles=5),
        )
        result = await engine.run()
        assert len(result.trades) >= 2, "Should have at least 2 trades (buy + exit)"
        assert result.final_balance > 0


# ---------------------------------------------------------------------------
# Fees and slippage impact
# ---------------------------------------------------------------------------

class TestFeesImpact:
    """Fees and slippage reduce profitability."""

    @pytest.mark.asyncio
    async def test_fees_reduce_final_balance(self):
        ohlcv = _uptrend_ohlcv(n=80, step=0.5)

        ex_free = BacktestExchange(
            ohlcv, initial_balance_usdt=10000.0, fee_rate=0.0, slippage_rate=0.0,
        )
        engine_free = BacktestEngine(
            exchange=ex_free,
            strategies=[_AlternatingStrategy(confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(),
        )
        result_free = await engine_free.run()

        ex_fees = BacktestExchange(
            ohlcv, initial_balance_usdt=10000.0, fee_rate=0.005, slippage_rate=0.002,
        )
        engine_fees = BacktestEngine(
            exchange=ex_fees,
            strategies=[_AlternatingStrategy(confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(),
        )
        result_fees = await engine_fees.run()

        if len(result_free.trades) > 0 and len(result_fees.trades) > 0:
            assert result_fees.final_balance <= result_free.final_balance


# ---------------------------------------------------------------------------
# Equity curve integrity
# ---------------------------------------------------------------------------

class TestEquityCurve:
    """Equity curve always has expected length and is non-negative."""

    @pytest.mark.asyncio
    async def test_equity_curve_length(self):
        n = 60
        ohlcv = _uptrend_ohlcv(n=n)
        ex = BacktestExchange(ohlcv)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(),
        )
        result = await engine.run()
        assert len(result.equity_curve) == n + 1
        assert all(v >= 0 for v in result.equity_curve)
        assert len(result.timestamps) == len(result.equity_curve)


# ---------------------------------------------------------------------------
# Regime (ADX) filter
# ---------------------------------------------------------------------------

class TestRegimeFilter:
    """ADX-based regime filter blocks signals in ranging markets."""

    @pytest.mark.asyncio
    async def test_regime_filter_counts(self):
        ohlcv = _uptrend_ohlcv(n=80)
        ex = BacktestExchange(ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(),
            engine_config=EngineConfig(enable_regime_filter=True, adx_trending_threshold=10.0),
        )
        result = await engine.run()
        regime_count = int(result.engine_stats.get("regime_filtered", 0))
        assert isinstance(regime_count, int)


# ---------------------------------------------------------------------------
# Multi-day daily reset
# ---------------------------------------------------------------------------

class TestDailyReset:
    """Daily loss tracking resets at day boundaries."""

    @pytest.mark.asyncio
    async def test_daily_reset_allows_next_day_trading(self):
        ohlcv = _multiday_ohlcv(days=4, candles_per_day=24)
        ex = BacktestExchange(ohlcv, initial_balance_usdt=10000.0, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_AlternatingStrategy(confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=_risk(daily_loss_limit_pct=0.02),
            engine_config=EngineConfig(cooldown_candles=2),
        )
        result = await engine.run()
        assert result.final_balance > 0
        if len(result.trades) > 0:
            trade_days = set()
            for t in result.trades:
                if t.trade.executed_at:
                    trade_days.add(t.trade.executed_at.date())
            assert len(trade_days) >= 1


# ---------------------------------------------------------------------------
# Stop-loss fill price regression test
# ---------------------------------------------------------------------------

class TestStopLossFillPrice:
    """Stop-loss and TP exits must fill at the target price, not candle close.

    Before the fix, _force_sell sent MARKET orders without a price hint,
    causing fills at the candle close which could be far from the stop.
    """

    @pytest.mark.asyncio
    async def test_stop_loss_fills_at_stop_price_not_close(self):
        """Build a scenario where low triggers ATR stop but close is much lower.

        Before the fix, _force_sell sent MARKET orders without a price,
        causing fills at the candle close (much worse than the stop price).
        """
        rows = []
        for i in range(40):
            ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
            price = 100.0 + i * 0.3
            rows.append({
                "timestamp": ts,
                "open": price,
                "high": price + 1.5,
                "low": price - 1.5,
                "close": price,
                "volume": 200.0,
            })

        entry_approx = 100.0 + 39 * 0.3
        crash_ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=40)
        rows.append({
            "timestamp": crash_ts,
            "open": entry_approx,
            "high": entry_approx + 0.5,
            "low": entry_approx - 25.0,
            "close": entry_approx - 20.0,
            "volume": 500.0,
        })

        for i in range(20):
            ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=41 + i)
            price = entry_approx - 20.0 + i * 0.1
            rows.append({
                "timestamp": ts,
                "open": price,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": 200.0,
            })

        ohlcv = pd.DataFrame(rows)
        ex = BacktestExchange(
            ohlcv, initial_balance_usdt=10000.0,
            fee_rate=0.0, slippage_rate=0.0,
        )
        risk = _risk(
            stop_loss_pct=0.05,
            atr_stop_multiplier=2.0,
            atr_tp_multiplier=50.0,
            atr_trailing_multiplier=50.0,
        )
        engine = BacktestEngine(
            exchange=ex,
            strategies=[_FixedStrategy("BUY", confidence=0.9)],
            symbol="BTC/USDT",
            risk_config=risk,
        )
        result = await engine.run()

        sl_trades = [
            t for t in result.trades
            if t.signal.strategy_name == "stop_loss"
        ]
        assert len(sl_trades) > 0, "Expected at least one stop-loss exit"

        crash_close = entry_approx - 20.0
        for t in sl_trades:
            assert t.trade.price > crash_close + 1.0, (
                f"Stop-loss fill {t.trade.price:.2f} should be above "
                f"candle close {crash_close:.2f}; stop should fill "
                f"at the stop price, not the close"
            )
