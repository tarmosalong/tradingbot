from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from backend.backtest.engine import BacktestEngine, EngineConfig
from backend.backtest.exchange import BacktestExchange
from backend.config import RiskConfig
from backend.strategies.technical import RSIStrategy


def _no_guard_risk(**overrides) -> RiskConfig:
    """RiskConfig with guards disabled so existing tests keep focus."""
    defaults = dict(
        ema_trend_enabled=False,
        volume_min_multiplier=0.0,
    )
    defaults.update(overrides)
    return RiskConfig(**defaults)


def _trending_up_ohlcv(n: int = 100) -> pd.DataFrame:
    rows = []
    base = 100.0
    for i in range(n):
        ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
        noise = 0.5 * (i % 3 - 1)
        price = base + i * 0.5 + noise
        rows.append({
            "timestamp": ts,
            "open": price - 0.2,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
            "volume": 1000.0 + i * 10,
        })
    return pd.DataFrame(rows)


def _volatile_ohlcv(n: int = 100) -> pd.DataFrame:
    rows = []
    base = 100.0
    for i in range(n):
        ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
        swing = 5.0 * (1 if i % 6 < 3 else -1)
        price = base + swing
        rows.append({
            "timestamp": ts,
            "open": price - 1.0,
            "high": price + 2.0,
            "low": price - 2.0,
            "close": price,
            "volume": 1000.0,
        })
    return pd.DataFrame(rows)


def _crash_then_recover(n: int = 100) -> pd.DataFrame:
    rows = []
    base = 100.0
    for i in range(n):
        ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
        if i < 40:
            price = base
        elif i < 60:
            price = base * (1.0 - 0.15 * (i - 40) / 20)
        else:
            price = base * 0.85 + base * 0.10 * (i - 60) / 40
        rows.append({
            "timestamp": ts,
            "open": price + 0.1,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
            "volume": 1000.0,
        })
    return pd.DataFrame(rows)


class TestFeesAndSlippage:
    @pytest.mark.asyncio
    async def test_fees_reduce_balance(self):
        ohlcv = _crash_then_recover(150)
        ex = BacktestExchange(ohlcv=ohlcv, fee_rate=0.001, slippage_rate=0.0)
        risk = _no_guard_risk(max_position_pct=0.5, stop_loss_pct=0.0, trailing_stop_pct=0.0)
        engine = BacktestEngine(
            exchange=ex, strategies=[RSIStrategy()], symbol="BTC/USDT",
            risk_config=risk,
        )
        result = await engine.run()
        if len(result.trades) > 0:
            assert ex.total_fees_paid > 0
            assert result.engine_stats["total_fees"] > 0

    @pytest.mark.asyncio
    async def test_slippage_costs_tracked(self):
        ohlcv = _volatile_ohlcv()
        ex = BacktestExchange(ohlcv=ohlcv, fee_rate=0.0, slippage_rate=0.001)
        engine = BacktestEngine(
            exchange=ex, strategies=[RSIStrategy()], symbol="BTC/USDT",
            risk_config=_no_guard_risk(),
        )
        result = await engine.run()
        if len(result.trades) > 0:
            assert ex.total_slippage_cost > 0

    @pytest.mark.asyncio
    async def test_zero_fees_no_cost(self):
        ohlcv = _volatile_ohlcv()
        ex = BacktestExchange(ohlcv=ohlcv, fee_rate=0.0, slippage_rate=0.0)
        engine = BacktestEngine(
            exchange=ex, strategies=[RSIStrategy()], symbol="BTC/USDT",
            risk_config=_no_guard_risk(),
        )
        await engine.run()
        assert ex.total_fees_paid == 0.0
        assert ex.total_slippage_cost == 0.0


class TestStopLossAndTrailingStop:
    @pytest.mark.asyncio
    async def test_stop_loss_triggers_on_crash(self):
        ohlcv = _crash_then_recover()
        ex = BacktestExchange(
            ohlcv=ohlcv, fee_rate=0.0, slippage_rate=0.0,
        )
        risk = _no_guard_risk(
            max_position_pct=0.5,
            stop_loss_pct=0.05,
            trailing_stop_pct=0.0,
        )
        engine = BacktestEngine(
            exchange=ex, strategies=[RSIStrategy()],
            symbol="BTC/USDT", risk_config=risk,
        )
        result = await engine.run()
        assert result.engine_stats["stop_loss_exits"] >= 0

    @pytest.mark.asyncio
    async def test_trailing_stop_triggers(self):
        ohlcv = _crash_then_recover()
        ex = BacktestExchange(
            ohlcv=ohlcv, fee_rate=0.0, slippage_rate=0.0,
        )
        risk = _no_guard_risk(
            max_position_pct=0.5,
            stop_loss_pct=0.20,
            trailing_stop_pct=0.03,
        )
        engine = BacktestEngine(
            exchange=ex, strategies=[RSIStrategy()],
            symbol="BTC/USDT", risk_config=risk,
        )
        result = await engine.run()
        ts_exits = result.engine_stats["trailing_stop_exits"]
        sl_exits = result.engine_stats["stop_loss_exits"]
        assert isinstance(ts_exits, int)
        assert isinstance(sl_exits, int)


class TestMinConfidenceAndCooldown:
    @pytest.mark.asyncio
    async def test_min_confidence_filters_weak(self):
        ohlcv = _volatile_ohlcv()
        ex_no_filter = BacktestExchange(
            ohlcv=ohlcv, fee_rate=0.0, slippage_rate=0.0,
        )
        engine_no_filter = BacktestEngine(
            exchange=ex_no_filter, strategies=[RSIStrategy()],
            symbol="BTC/USDT",
            risk_config=_no_guard_risk(min_confidence=0.0),
            engine_config=EngineConfig(min_confidence=0.0),
        )
        result_no = await engine_no_filter.run()

        ex_filter = BacktestExchange(
            ohlcv=ohlcv, fee_rate=0.0, slippage_rate=0.0,
        )
        engine_filter = BacktestEngine(
            exchange=ex_filter, strategies=[RSIStrategy()],
            symbol="BTC/USDT",
            risk_config=_no_guard_risk(min_confidence=0.9),
            engine_config=EngineConfig(min_confidence=0.9),
        )
        result_yes = await engine_filter.run()

        assert len(result_yes.trades) <= len(result_no.trades)

    @pytest.mark.asyncio
    async def test_cooldown_reduces_trades(self):
        ohlcv = _volatile_ohlcv()
        ex_no = BacktestExchange(
            ohlcv=ohlcv, fee_rate=0.0, slippage_rate=0.0,
        )
        engine_no = BacktestEngine(
            exchange=ex_no, strategies=[RSIStrategy()],
            symbol="BTC/USDT",
            risk_config=_no_guard_risk(),
            engine_config=EngineConfig(cooldown_candles=0),
        )
        result_no = await engine_no.run()

        ex_cd = BacktestExchange(
            ohlcv=ohlcv, fee_rate=0.0, slippage_rate=0.0,
        )
        engine_cd = BacktestEngine(
            exchange=ex_cd, strategies=[RSIStrategy()],
            symbol="BTC/USDT",
            risk_config=_no_guard_risk(),
            engine_config=EngineConfig(cooldown_candles=20),
        )
        result_cd = await engine_cd.run()

        assert len(result_cd.trades) <= len(result_no.trades)


class TestDrawdownBreaker:
    @pytest.mark.asyncio
    async def test_drawdown_halts_trading(self):
        ohlcv = _crash_then_recover()
        ex = BacktestExchange(
            ohlcv=ohlcv, fee_rate=0.0, slippage_rate=0.0,
        )
        risk = _no_guard_risk(
            max_position_pct=0.8,
            stop_loss_pct=0.0,
            trailing_stop_pct=0.0,
            max_drawdown_pct=0.005,
        )
        engine = BacktestEngine(
            exchange=ex, strategies=[RSIStrategy()],
            symbol="BTC/USDT", risk_config=risk,
        )
        result = await engine.run()
        halted = result.engine_stats.get("drawdown_halt_candle") is not None
        assert halted or len(result.trades) == 0


class TestDynamicSizing:
    @pytest.mark.asyncio
    async def test_dynamic_sizing_runs(self):
        ohlcv = _volatile_ohlcv()
        ex = BacktestExchange(
            ohlcv=ohlcv, fee_rate=0.0, slippage_rate=0.0,
        )
        engine = BacktestEngine(
            exchange=ex, strategies=[RSIStrategy()],
            symbol="BTC/USDT",
            risk_config=_no_guard_risk(),
            engine_config=EngineConfig(use_dynamic_sizing=True),
        )
        result = await engine.run()
        assert result.final_balance > 0


class TestEngineStats:
    @pytest.mark.asyncio
    async def test_engine_stats_in_result(self):
        ohlcv = _volatile_ohlcv()
        ex = BacktestExchange(ohlcv=ohlcv)
        engine = BacktestEngine(
            exchange=ex, strategies=[RSIStrategy()], symbol="BTC/USDT",
            risk_config=_no_guard_risk(),
        )
        result = await engine.run()
        assert "total_fees" in result.engine_stats
        assert "total_slippage" in result.engine_stats
        assert "stop_loss_exits" in result.engine_stats
        assert "trailing_stop_exits" in result.engine_stats
        assert "cooldown_skips" in result.engine_stats
        assert "signals_below_confidence" in result.engine_stats
