"""End-to-end scenario tests for the trading engine.

Each test simulates a full multi-tick trading cycle (BUY → price movement →
exit condition) with realistic OHLCV data and verifies that every guard,
stop, and partial exit fires at the right time.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from backend.config import (
    RiskConfig,
    Settings,
    StrategiesConfig,
    TradingConfig,
    load_settings,
)
from backend.core.engine import OpenPosition, TradingEngine
from backend.database import Database
from backend.models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Signal,
    Ticker,
)


def _ohlcv_with_trend(
    periods: int = 60,
    start_price: float = 60000.0,
    step: float = 100.0,
    volume_base: float = 120.0,
) -> pd.DataFrame:
    """OHLCV with an upward trend, recent timestamps, and volume above SMA-20."""
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(hours=periods - 1)
    closes = [start_price + i * step for i in range(periods)]
    return pd.DataFrame({
        "timestamp": pd.date_range(start, periods=periods, freq="h"),
        "open": [c - 50 for c in closes],
        "high": [c + 100 for c in closes],
        "low": [c - 100 for c in closes],
        "close": closes,
        "volume": [volume_base] * (periods - 1) + [volume_base * 2],
    })


def _ohlcv_with_downtrend(
    periods: int = 60,
    start_price: float = 70000.0,
    step: float = -100.0,
    volume_base: float = 120.0,
) -> pd.DataFrame:
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(hours=periods - 1)
    closes = [start_price + i * step for i in range(periods)]
    return pd.DataFrame({
        "timestamp": pd.date_range(start, periods=periods, freq="h"),
        "open": [c + 50 for c in closes],
        "high": [c + 100 for c in closes],
        "low": [c - 100 for c in closes],
        "close": closes,
        "volume": [volume_base] * (periods - 1) + [volume_base * 2],
    })


def _scenario_settings(**risk_overrides) -> Settings:
    base = load_settings()
    risk_kwargs = {
        "max_position_pct": 0.10,
        "stop_loss_pct": 0.03,
        "trailing_stop_pct": 0.02,
        "max_drawdown_pct": 0.15,
        "daily_loss_limit_pct": 0.05,
        "max_single_order_usdt": 1000.0,
        "min_confidence": 0.4,
        "max_concurrent_positions": 3,
        "max_data_age_seconds": 86400,
        "max_price_deviation_pct": 0.10,
        "circuit_breaker_threshold": 5,
        "atr_stop_multiplier": 2.0,
        "atr_tp_multiplier": 3.0,
        "atr_trailing_multiplier": 1.5,
        "volume_min_multiplier": 1.2,
        "ema_trend_period": 50,
        "ema_trend_enabled": True,
        "risk_per_trade_pct": 0.01,
        "partial_tp_ratio": 0.5,
    }
    risk_kwargs.update(risk_overrides)
    return Settings(
        trading=TradingConfig(
            mode="paper",
            pairs=["BTC/USDT"],
            timeframe="1h",
            poll_interval_seconds=1,
        ),
        paper_trading=base.paper_trading,
        exchange=base.exchange,
        strategies=base.strategies,
        ai=base.ai,
        risk=RiskConfig(**risk_kwargs),
    )


def _strategy_returning(direction: str, confidence: float = 0.8):
    strat = AsyncMock()
    strat.name = f"test_{direction.lower()}"
    strat.analyze.return_value = Signal(
        symbol="BTC/USDT",
        direction=direction,
        confidence=confidence,
        strategy_name=f"test_{direction.lower()}",
        reason=f"Test {direction} signal",
    )
    return strat


@pytest.fixture
async def db(tmp_path):
    database = Database(db_path=tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


def _make_order(
    side: str, amount: float, price: float, order_id: str = "o-1",
) -> Order:
    return Order(
        id=order_id,
        symbol="BTC/USDT",
        side=OrderSide(side),
        order_type=OrderType.MARKET,
        amount=amount,
        price=price,
        status=OrderStatus.FILLED,
        filled_amount=amount,
        filled_price=price,
    )


class TestBuyToTakeProfitCycle:
    """Simulate: BUY → price rises → partial TP fires → remainder trails."""

    async def test_full_cycle(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        last_close = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=last_close, ask=last_close + 10,
            last=last_close,
        )
        exchange.create_order.return_value = _make_order(
            "BUY", 0.015, last_close,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()

        assert "BTC/USDT" in engine._positions
        pos = engine._positions["BTC/USDT"]
        assert pos.atr_at_entry > 0, "ATR should be computed at entry"
        assert pos.atr_take_profit > pos.entry_price
        assert pos.atr_stop_loss < pos.entry_price
        assert pos.partial_exits_done == 0

        tp_price = pos.atr_take_profit + 100.0
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=tp_price, ask=tp_price + 10,
            last=tp_price,
        )
        exchange.get_balance.return_value = {"USDT": 5000.0, "BTC": 0.015}
        exchange.create_order.return_value = _make_order(
            "SELL", 0.0075, tp_price, "o-tp",
        )

        exited = await engine._check_position_exit("BTC/USDT")

        assert exited is True
        assert pos.partial_exits_done == 1
        assert "BTC/USDT" in engine._positions, "Position should still exist (partial)"
        assert pos.atr_stop_loss == pos.entry_price, "Stop moved to breakeven"

        trades = await db.get_trades()
        sell_trades = [t for t in trades if t.side == OrderSide.SELL]
        assert len(sell_trades) == 1


class TestBuyToStopLossCycle:
    """Simulate: BUY → price drops → ATR stop-loss fires full exit."""

    async def test_atr_stop_loss_closes_position(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        last_close = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=last_close, ask=last_close + 10,
            last=last_close,
        )
        exchange.create_order.return_value = _make_order(
            "BUY", 0.015, last_close,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()
        pos = engine._positions["BTC/USDT"]
        sl_price = pos.stop_loss_price

        crash_price = sl_price - 100.0
        usdt_after_buy = 10000.0 - 0.015 * last_close
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=crash_price, ask=crash_price + 10,
            last=crash_price,
        )
        exchange.get_balance.return_value = {
            "USDT": usdt_after_buy, "BTC": 0.015,
        }
        exchange.create_order.return_value = _make_order(
            "SELL", 0.015, crash_price, "o-sl",
        )

        exited = await engine._check_position_exit("BTC/USDT")

        assert exited is True
        assert "BTC/USDT" not in engine._positions


class TestBuyToTrailingStopCycle:
    """BUY → price rises past entry → price drops → trailing stop fires."""

    async def test_trailing_stop_after_rally(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        entry_price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=entry_price, ask=entry_price + 10,
            last=entry_price,
        )
        exchange.create_order.return_value = _make_order(
            "BUY", 0.015, entry_price,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )
        await engine._tick()
        pos = engine._positions["BTC/USDT"]
        usdt_after_buy = 10000.0 - 0.015 * entry_price

        rally_price = entry_price + 500.0
        assert rally_price < pos.atr_take_profit, "Rally must stay below TP"
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=rally_price, ask=rally_price + 10,
            last=rally_price,
        )
        exchange.get_balance.return_value = {
            "USDT": usdt_after_buy, "BTC": 0.015,
        }
        await engine._check_position_exit("BTC/USDT")
        assert pos.peak_price == rally_price

        ts_price = pos.trailing_stop_price
        drop_price = ts_price - 50.0
        assert drop_price > pos.stop_loss_price, "Drop must be above SL for TS to fire"
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=drop_price, ask=drop_price + 10,
            last=drop_price,
        )
        exchange.create_order.return_value = _make_order(
            "SELL", 0.015, drop_price, "o-ts",
        )

        exited = await engine._check_position_exit("BTC/USDT")
        assert exited is True
        assert "BTC/USDT" not in engine._positions


class TestEMATrendBlocksBuy:
    """BUY signal in a downtrend should be blocked by EMA filter."""

    async def test_downtrend_blocks_buy(self, db):
        s = _scenario_settings(ema_trend_enabled=True, ema_trend_period=50)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_downtrend(60)
        last_close = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=last_close, ask=last_close + 10,
            last=last_close,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.9)],
        )

        await engine._tick()

        exchange.create_order.assert_not_called()
        assert "BTC/USDT" not in engine._positions

    async def test_downtrend_allows_sell(self, db):
        s = _scenario_settings(ema_trend_enabled=True, ema_trend_period=50)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_downtrend(60)
        last_close = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 5000.0, "BTC": 0.1}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=last_close, ask=last_close + 10,
            last=last_close,
        )
        exchange.create_order.return_value = _make_order(
            "SELL", 0.1, last_close, "o-sell",
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("SELL", 0.8)],
        )

        await engine._tick()

        exchange.create_order.assert_called_once()


class TestVolumFilterBlocksSignal:
    """Signal with low volume should be rejected."""

    async def test_low_volume_blocks_buy(self, db):
        s = _scenario_settings(volume_min_multiplier=1.5)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        ohlcv["volume"] = 100.0
        last_close = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=last_close, ask=last_close + 10,
            last=last_close,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.9)],
        )

        await engine._tick()

        exchange.create_order.assert_not_called()


class TestWeightedAggregationScenario:
    """Weighted strategies should control which direction wins."""

    async def test_weight_flips_to_sell(self, db):
        s = _scenario_settings()
        s_with_weights = Settings(
            trading=s.trading,
            paper_trading=s.paper_trading,
            exchange=s.exchange,
            strategies=StrategiesConfig(
                enabled=["rsi", "macd"],
                weights={"test_buy": 0.5, "test_sell": 2.0},
            ),
            ai=s.ai,
            risk=s.risk,
        )

        exchange = AsyncMock()
        ohlcv = _ohlcv_with_downtrend(60)
        last_close = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 5000.0, "BTC": 0.1}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=last_close, ask=last_close + 10,
            last=last_close,
        )
        exchange.create_order.return_value = _make_order(
            "SELL", 0.1, last_close, "o-sell",
        )

        buy_strat = _strategy_returning("BUY", 0.6)
        sell_strat = _strategy_returning("SELL", 0.5)

        engine = TradingEngine(
            settings=s_with_weights, exchange=exchange, database=db,
            strategies=[buy_strat, sell_strat],
        )

        await engine._tick()

        exchange.create_order.assert_called_once()
        call_kwargs = exchange.create_order.call_args
        assert call_kwargs.kwargs["side"] == "SELL"


class TestMultiTickFullCycle:
    """Full multi-tick scenario: BUY tick 1 → HOLD ticks 2-3 → SELL tick 4."""

    async def test_buy_hold_hold_sell(self, db):
        s = _scenario_settings(ema_trend_enabled=False)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        buy_price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=buy_price, ask=buy_price + 10,
            last=buy_price,
        )
        exchange.create_order.return_value = _make_order(
            "BUY", 0.015, buy_price,
        )
        exchange.get_open_orders.return_value = []

        step = [0]
        buy_strat = AsyncMock()
        buy_strat.name = "scenario"

        async def dynamic_signal(symbol, data):
            tick = step[0]
            step[0] += 1
            if tick == 0:
                return Signal(
                    symbol=symbol, direction="BUY", confidence=0.8,
                    strategy_name="scenario", reason="Buy entry",
                )
            if tick <= 2:
                return Signal(
                    symbol=symbol, direction="HOLD", confidence=0.0,
                    strategy_name="scenario", reason="Holding",
                )
            return Signal(
                symbol=symbol, direction="SELL", confidence=0.9,
                strategy_name="scenario", reason="Sell exit",
            )

        buy_strat.analyze.side_effect = dynamic_signal

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[buy_strat],
        )

        await engine._tick()
        assert "BTC/USDT" in engine._positions
        buy_trades = await db.get_trades()
        assert len(buy_trades) == 1

        usdt_after_buy = 10000.0 - 0.015 * buy_price
        exchange.create_order.reset_mock()
        exchange.get_balance.return_value = {
            "USDT": usdt_after_buy, "BTC": 0.015,
        }
        safe_price = buy_price + 500
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=safe_price, ask=safe_price + 10,
            last=safe_price,
        )

        await engine._tick()
        exchange.create_order.assert_not_called()

        await engine._tick()
        exchange.create_order.assert_not_called()

        sell_price = buy_price + 1000
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=sell_price, ask=sell_price + 10,
            last=sell_price,
        )
        exchange.create_order.return_value = _make_order(
            "SELL", 0.015, sell_price, "o-sell",
        )
        engine._last_trade_time.clear()

        await engine._tick()

        exchange.create_order.assert_called_once()
        assert "BTC/USDT" not in engine._positions
        all_trades = await db.get_trades()
        assert len(all_trades) == 2
        sides = [t.side for t in all_trades]
        assert OrderSide.BUY in sides
        assert OrderSide.SELL in sides


class TestPartialThenTrailingStop:
    """Partial TP at target, then trailing stop closes remainder."""

    async def test_partial_tp_then_trailing_stop(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        entry = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=entry, ask=entry + 10, last=entry,
        )
        exchange.create_order.return_value = _make_order(
            "BUY", 0.02, entry,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )
        await engine._tick()
        pos = engine._positions["BTC/USDT"]
        tp = pos.atr_take_profit
        usdt_after_buy = 10000.0 - 0.02 * entry

        tp_hit = tp + 200
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=tp_hit, ask=tp_hit + 10, last=tp_hit,
        )
        exchange.get_balance.return_value = {
            "USDT": usdt_after_buy, "BTC": 0.02,
        }
        exchange.create_order.return_value = _make_order(
            "SELL", 0.01, tp_hit, "o-tp",
        )

        exited = await engine._check_position_exit("BTC/USDT")
        assert exited is True
        assert pos.partial_exits_done == 1
        assert pos.amount == pytest.approx(0.01)

        usdt_after_partial = usdt_after_buy + 0.01 * tp_hit
        rally_peak = tp_hit + 500
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=rally_peak, ask=rally_peak + 10,
            last=rally_peak,
        )
        exchange.get_balance.return_value = {
            "USDT": usdt_after_partial, "BTC": 0.01,
        }
        await engine._check_position_exit("BTC/USDT")
        assert pos.peak_price == rally_peak

        ts_target = pos.trailing_stop_price
        drop = ts_target - 50
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=drop, ask=drop + 10, last=drop,
        )
        exchange.get_balance.return_value = {
            "USDT": usdt_after_partial, "BTC": 0.01,
        }
        exchange.create_order.return_value = _make_order(
            "SELL", 0.01, drop, "o-ts",
        )

        exited = await engine._check_position_exit("BTC/USDT")
        assert exited is True
        assert "BTC/USDT" not in engine._positions

        all_trades = await db.get_trades()
        sell_trades = [t for t in all_trades if t.side == OrderSide.SELL]
        assert len(sell_trades) == 2


class TestAllGuardsCombined:
    """All guards active: only a valid signal in the right conditions trades."""

    async def test_valid_signal_passes_all_guards(self, db):
        s = _scenario_settings(
            min_confidence=0.5,
            volume_min_multiplier=1.2,
            ema_trend_enabled=True,
            ema_trend_period=50,
            max_concurrent_positions=3,
        )
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        last_close = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=last_close, ask=last_close + 10,
            last=last_close,
        )
        exchange.create_order.return_value = _make_order(
            "BUY", 0.015, last_close,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()

        exchange.create_order.assert_called_once()
        assert "BTC/USDT" in engine._positions
        pos = engine._positions["BTC/USDT"]
        assert pos.atr_at_entry > 0
        assert pos.atr_stop_loss > 0
        assert pos.atr_take_profit > 0

    async def test_low_confidence_blocked_even_with_trend(self, db):
        s = _scenario_settings(min_confidence=0.7)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        last_close = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=last_close, ask=last_close + 10,
            last=last_close,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.5)],
        )

        await engine._tick()

        exchange.create_order.assert_not_called()


# ---------------------------------------------------------------------------
# Position management edge cases
# ---------------------------------------------------------------------------


class TestDuplicateBuyBlocked:
    """BUY signal when already holding should be silently skipped."""

    async def test_holding_position_blocks_second_buy(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, price)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()
        assert "BTC/USDT" in engine._positions
        first_amount = engine._positions["BTC/USDT"].amount

        exchange.create_order.reset_mock()
        usdt_after = 10000.0 - 0.015 * price
        exchange.get_balance.return_value = {
            "USDT": usdt_after, "BTC": 0.015,
        }
        engine._last_trade_time.clear()

        await engine._tick()

        exchange.create_order.assert_not_called()
        assert engine._positions["BTC/USDT"].amount == first_amount


class TestCooldownPreventsRapidBuy:
    """Second BUY immediately after the first should be blocked by cooldown."""

    async def test_cooldown_blocks_immediate_rebuy(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, price)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )
        await engine._tick()

        engine._positions.pop("BTC/USDT", None)
        exchange.create_order.reset_mock()
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}

        await engine._tick()

        exchange.create_order.assert_not_called()


class TestMaxConcurrentPositionsBlocks:
    """When max_concurrent_positions is reached, new BUYs are blocked."""

    async def test_third_pair_blocked(self, db):
        s = _scenario_settings(max_concurrent_positions=2)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.9)],
        )

        for sym in ["ETH/USDT", "SOL/USDT"]:
            pos = OpenPosition(
                symbol=sym, amount=1.0, entry_price=100.0, peak_price=100.0,
            )
            pos.set_risk(0.03, 0.02)
            engine._positions[sym] = pos

        await engine._tick()
        exchange.create_order.assert_not_called()


class TestSellWithNoPositionSkipped:
    """SELL signal when holding nothing should not create an order."""

    async def test_no_holdings_sell_skipped(self, db):
        s = _scenario_settings(ema_trend_enabled=False)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("SELL", 0.9)],
        )

        await engine._tick()
        exchange.create_order.assert_not_called()


class TestInsufficientBudgetSkipped:
    """BUY with near-zero USDT balance should not place an order."""

    async def test_no_usdt_blocks_buy(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 0.50, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.9)],
        )

        await engine._tick()
        exchange.create_order.assert_not_called()


# ---------------------------------------------------------------------------
# Risk manager portfolio-level scenarios
# ---------------------------------------------------------------------------


class TestDrawdownHaltScenario:
    """When drawdown threshold is breached, engine halts permanently."""

    async def test_drawdown_halts_all_subsequent_ticks(self, db):
        s = _scenario_settings(max_drawdown_pct=0.10)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.9)],
        )
        engine._risk_manager.set_initial_portfolio_value(10000.0)

        exchange.get_balance.return_value = {"USDT": 8500.0}
        await engine._tick()
        exchange.create_order.assert_not_called()
        assert engine._halted is True

        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.create_order.reset_mock()
        await engine._tick()
        exchange.create_order.assert_not_called()


class TestDailyLossLimitScenario:
    """Daily loss limit pauses the tick but does not halt permanently."""

    async def test_daily_loss_blocks_then_recovers(self, db):
        s = _scenario_settings(daily_loss_limit_pct=0.03, max_drawdown_pct=0.50)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.9)],
        )
        engine._risk_manager.set_initial_portfolio_value(10000.0)

        exchange.get_balance.return_value = {"USDT": 9600.0}
        await engine._tick()
        exchange.create_order.assert_not_called()
        assert engine._halted is False


class TestPriceSanityCheckScenario:
    """Ticker wildly deviating from OHLCV last close blocks the trade."""

    async def test_wild_ticker_rejected(self, db):
        s = _scenario_settings(max_price_deviation_pct=0.05, ema_trend_enabled=False)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        last_close = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        wild_price = last_close * 1.15
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=wild_price, ask=wild_price + 10,
            last=wild_price,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.9)],
        )

        await engine._tick()
        exchange.create_order.assert_not_called()

    async def test_normal_deviation_allowed(self, db):
        s = _scenario_settings(max_price_deviation_pct=0.05)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        last_close = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        normal_price = last_close * 1.01
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=normal_price, ask=normal_price + 10,
            last=normal_price,
        )
        exchange.create_order.return_value = _make_order(
            "BUY", 0.015, normal_price,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()
        exchange.create_order.assert_called_once()


# ---------------------------------------------------------------------------
# Data quality scenarios
# ---------------------------------------------------------------------------


class TestStaleDataScenario:
    """Old OHLCV timestamps should skip the symbol entirely."""

    async def test_stale_data_skips_symbol(self, db):
        s = _scenario_settings(max_data_age_seconds=600)
        exchange = AsyncMock()
        stale_ohlcv = pd.DataFrame({
            "timestamp": pd.date_range("2020-01-01", periods=60, freq="h"),
            "open": [65000.0] * 60,
            "high": [65200.0] * 60,
            "low": [64800.0] * 60,
            "close": [65100.0] * 60,
            "volume": [120.0] * 60,
        })

        exchange.get_ohlcv.return_value = stale_ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=65000.0, ask=65010.0, last=65005.0,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.9)],
        )

        await engine._tick()
        exchange.create_order.assert_not_called()


class TestEmptyOHLCVScenario:
    """Empty OHLCV data should be treated as stale."""

    async def test_empty_dataframe_skips(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        exchange.get_ohlcv.return_value = pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        exchange.get_balance.return_value = {"USDT": 10000.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=65000.0, ask=65010.0, last=65005.0,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.9)],
        )

        await engine._tick()
        exchange.create_order.assert_not_called()


# ---------------------------------------------------------------------------
# Exit logic edge cases
# ---------------------------------------------------------------------------


class TestPeakPriceUpdatesWithoutExit:
    """Rising price should update peak but NOT trigger any exit."""

    async def test_gradual_rise_no_exit(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        entry = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=entry, ask=entry + 10, last=entry,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, entry)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )
        await engine._tick()
        pos = engine._positions["BTC/USDT"]

        for bump in [50, 100, 150, 200]:
            p = entry + bump
            if p >= pos.atr_take_profit:
                break
            exchange.get_ticker.return_value = Ticker(
                symbol="BTC/USDT", bid=p, ask=p + 10, last=p,
            )
            exited = await engine._check_position_exit("BTC/USDT")
            assert exited is False
            assert pos.peak_price == p


class TestPartialTPOnlyFiresOnce:
    """Second time price hits TP, partial exit should NOT fire again."""

    async def test_second_tp_hit_no_partial(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        entry = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=entry, ask=entry + 10, last=entry,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.02, entry)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )
        await engine._tick()
        pos = engine._positions["BTC/USDT"]
        tp = pos.atr_take_profit

        usdt_after = 10000.0 - 0.02 * entry
        tp_hit = tp + 100
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=tp_hit, ask=tp_hit + 10, last=tp_hit,
        )
        exchange.get_balance.return_value = {"USDT": usdt_after, "BTC": 0.02}
        exchange.create_order.return_value = _make_order(
            "SELL", 0.01, tp_hit, "o-tp1",
        )
        await engine._check_position_exit("BTC/USDT")
        assert pos.partial_exits_done == 1

        exchange.create_order.reset_mock()
        exchange.get_balance.return_value = {
            "USDT": usdt_after + 0.01 * tp_hit, "BTC": 0.01,
        }
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=tp_hit + 200, ask=tp_hit + 210,
            last=tp_hit + 200,
        )
        exited = await engine._check_position_exit("BTC/USDT")
        assert exited is False
        assert pos.partial_exits_done == 1
        exchange.create_order.assert_not_called()


class TestBreakevenStopAfterPartialTP:
    """After partial TP, stop-loss is moved to entry (breakeven)."""

    async def test_breakeven_stop_triggers_at_entry(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        entry = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=entry, ask=entry + 10, last=entry,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.02, entry)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )
        await engine._tick()
        pos = engine._positions["BTC/USDT"]
        tp = pos.atr_take_profit

        usdt_after = 10000.0 - 0.02 * entry
        tp_hit = tp + 100
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=tp_hit, ask=tp_hit + 10, last=tp_hit,
        )
        exchange.get_balance.return_value = {"USDT": usdt_after, "BTC": 0.02}
        exchange.create_order.return_value = _make_order(
            "SELL", 0.01, tp_hit, "o-tp",
        )
        await engine._check_position_exit("BTC/USDT")

        assert pos.atr_stop_loss == pos.entry_price
        assert pos.stop_loss_price == entry

        drop_to_entry = entry - 10
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=drop_to_entry, ask=drop_to_entry + 10,
            last=drop_to_entry,
        )
        usdt_after_partial = usdt_after + 0.01 * tp_hit
        exchange.get_balance.return_value = {
            "USDT": usdt_after_partial, "BTC": 0.01,
        }
        exchange.create_order.return_value = _make_order(
            "SELL", 0.01, drop_to_entry, "o-be",
        )

        exited = await engine._check_position_exit("BTC/USDT")
        assert exited is True
        assert "BTC/USDT" not in engine._positions


class TestStopLossVsTrailingStopPriority:
    """When trailing stop is above stop-loss, it should fire first on a drop.
    When price drops below SL (which is lower), SL fires instead.
    """

    async def test_sl_fires_on_deep_crash(self, db):
        """Price crashes below both SL and TS — SL fires (SL < TS)."""
        s = _scenario_settings()
        exchange = AsyncMock()

        pos = OpenPosition(
            symbol="BTC/USDT", amount=0.1,
            entry_price=65000.0, peak_price=66500.0,
            atr_at_entry=200.0, atr_stop_loss=64600.0,
            atr_take_profit=67000.0, atr_trailing_multiplier=1.5,
        )
        pos.set_risk(0.03, 0.02)

        crash_price = 64500.0
        assert crash_price < pos.stop_loss_price
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=crash_price, ask=crash_price + 10,
            last=crash_price,
        )
        exchange.get_balance.return_value = {"USDT": 9000.0, "BTC": 0.1}
        exchange.create_order.return_value = _make_order(
            "SELL", 0.1, crash_price, "o-sl",
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[],
        )
        engine._positions["BTC/USDT"] = pos

        exited = await engine._check_position_exit("BTC/USDT")
        assert exited is True
        assert "BTC/USDT" not in engine._positions


class TestPriceOscillationNoExit:
    """Price oscillating within safe range should never trigger an exit."""

    async def test_five_ticks_safe_range(self, db):
        """Prices oscillating between SL and TP should not trigger exit.

        SL = 64600, TS = peak(65500) - ATR(200)*1.5 = 65200, TP = 66500.
        Safe band: above 65200 and below 66500.
        """
        s = _scenario_settings()
        exchange = AsyncMock()
        exchange.get_balance.return_value = {"USDT": 9000.0, "BTC": 0.1}

        pos = OpenPosition(
            symbol="BTC/USDT", amount=0.1,
            entry_price=65000.0, peak_price=65500.0,
            atr_at_entry=200.0, atr_stop_loss=64600.0,
            atr_take_profit=66500.0, atr_trailing_multiplier=1.5,
        )
        pos.set_risk(0.03, 0.02)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[],
        )
        engine._positions["BTC/USDT"] = pos

        safe_prices = [65300.0, 65400.0, 65350.0, 65500.0, 65450.0]
        for p in safe_prices:
            exchange.get_ticker.return_value = Ticker(
                symbol="BTC/USDT", bid=p, ask=p + 10, last=p,
            )
            exited = await engine._check_position_exit("BTC/USDT")
            assert exited is False
            assert "BTC/USDT" in engine._positions

        exchange.create_order.assert_not_called()


# ---------------------------------------------------------------------------
# EMA filter extra cases
# ---------------------------------------------------------------------------


class TestEMATrendExtras:
    """Additional EMA filter scenarios."""

    async def test_ema_disabled_allows_counter_trend(self, db):
        s = _scenario_settings(ema_trend_enabled=False)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_downtrend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, price)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()
        exchange.create_order.assert_called_once()

    async def test_uptrend_blocks_sell(self, db):
        s = _scenario_settings(ema_trend_enabled=True, ema_trend_period=50)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 5000.0, "BTC": 0.1}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("SELL", 0.9)],
        )

        await engine._tick()
        exchange.create_order.assert_not_called()

    async def test_hold_signal_ignores_ema(self, db):
        s = _scenario_settings(ema_trend_enabled=True)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_downtrend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )

        hold_strat = AsyncMock()
        hold_strat.name = "hold"
        hold_strat.analyze.return_value = Signal(
            symbol="BTC/USDT", direction="HOLD", confidence=0.0,
            strategy_name="hold", reason="No signal",
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[hold_strat],
        )

        await engine._tick()
        exchange.create_order.assert_not_called()


# ---------------------------------------------------------------------------
# Volume filter extra cases
# ---------------------------------------------------------------------------


class TestVolumeFilterExtras:
    """Borderline volume scenarios."""

    async def test_volume_clearly_above_threshold_passes(self, db):
        s = _scenario_settings(volume_min_multiplier=1.2)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        ohlcv["volume"] = 100.0
        ohlcv.loc[ohlcv.index[-1], "volume"] = 200.0
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, price)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()
        exchange.create_order.assert_called_once()

    async def test_volume_just_below_threshold_blocked(self, db):
        s = _scenario_settings(volume_min_multiplier=1.2)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        ohlcv["volume"] = 100.0
        ohlcv.loc[ohlcv.index[-1], "volume"] = 100.0 * 1.19
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.9)],
        )

        await engine._tick()
        exchange.create_order.assert_not_called()

    async def test_short_ohlcv_bypasses_volume_filter(self, db):
        """Fewer than 20 candles should bypass the volume filter."""
        s = _scenario_settings(volume_min_multiplier=1.5)
        exchange = AsyncMock()
        end = pd.Timestamp.now(tz="UTC")
        start = end - pd.Timedelta(hours=9)
        ohlcv = pd.DataFrame({
            "timestamp": pd.date_range(start, periods=10, freq="h"),
            "open": [65000.0] * 10,
            "high": [65200.0] * 10,
            "low": [64800.0] * 10,
            "close": [c for c in range(65000, 65010)],
            "volume": [1.0] * 10,
        })

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        price = 65009.0
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, price)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()
        exchange.create_order.assert_called_once()


# ---------------------------------------------------------------------------
# Multi-strategy aggregation scenarios
# ---------------------------------------------------------------------------


class TestThreeStrategyAggregation:
    """Three strategies with different directions."""

    async def test_two_buy_one_sell_buys(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, price)

        s1 = _strategy_returning("BUY", 0.7)
        s1.name = "rsi"
        s2 = _strategy_returning("BUY", 0.6)
        s2.name = "macd"
        s3 = _strategy_returning("SELL", 0.5)
        s3.name = "bollinger"

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[s1, s2, s3],
        )

        await engine._tick()
        exchange.create_order.assert_called_once()
        assert exchange.create_order.call_args.kwargs["side"] == "BUY"

    async def test_two_sell_one_hold_sells(self, db):
        s = _scenario_settings(ema_trend_enabled=False)
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 5000.0, "BTC": 0.1}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )
        exchange.create_order.return_value = _make_order(
            "SELL", 0.1, price, "o-sell",
        )

        s1 = _strategy_returning("SELL", 0.8)
        s1.name = "rsi"
        s2 = _strategy_returning("SELL", 0.6)
        s2.name = "macd"
        hold = AsyncMock()
        hold.name = "bollinger"
        hold.analyze.return_value = Signal(
            symbol="BTC/USDT", direction="HOLD", confidence=0.0,
            strategy_name="bollinger", reason="No signal",
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[s1, s2, hold],
        )

        await engine._tick()
        exchange.create_order.assert_called_once()
        assert exchange.create_order.call_args.kwargs["side"] == "SELL"

    async def test_tied_buy_sell_results_in_hold(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )

        s1 = _strategy_returning("BUY", 0.7)
        s1.name = "rsi"
        s2 = _strategy_returning("SELL", 0.7)
        s2.name = "macd"

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[s1, s2],
        )

        await engine._tick()
        exchange.create_order.assert_not_called()


# ---------------------------------------------------------------------------
# ATR-specific scenarios
# ---------------------------------------------------------------------------


class TestATRFallbackToPercentage:
    """When OHLCV too short for ATR, percentage-based stops should be used."""

    async def test_short_ohlcv_uses_pct_stops(self, db):
        s = _scenario_settings(ema_trend_enabled=False)
        exchange = AsyncMock()
        end = pd.Timestamp.now(tz="UTC")
        start = end - pd.Timedelta(hours=9)
        ohlcv = pd.DataFrame({
            "timestamp": pd.date_range(start, periods=10, freq="h"),
            "open": [65000.0] * 10,
            "high": [65200.0] * 10,
            "low": [64800.0] * 10,
            "close": [65100.0] * 10,
            "volume": [100.0] * 9 + [250.0],
        })
        price = 65100.0

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, price)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()
        pos = engine._positions["BTC/USDT"]

        assert pos.atr_at_entry == 0.0, "ATR should be 0 with too few candles"
        expected_sl = price * (1 - 0.03)
        assert pos.stop_loss_price == pytest.approx(expected_sl)


class TestATRPositionSizingCap:
    """ATR position sizing should respect max_single_order_usdt."""

    async def test_atr_budget_capped_by_max_order(self, db):
        s = _scenario_settings(
            max_single_order_usdt=500.0,
            risk_per_trade_pct=0.05,
        )
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=10.0)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 50000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )

        captured_amounts = []
        original_create_order = AsyncMock()

        async def track_order(**kwargs):
            captured_amounts.append(kwargs.get("amount", 0))
            return _make_order("BUY", kwargs["amount"], price)

        exchange.create_order.side_effect = track_order

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()

        assert len(captured_amounts) == 1
        order_value = captured_amounts[0] * price
        assert order_value <= 500.0 + 1.0


class TestATRHighVolatilitySmallPosition:
    """High volatility → ATR larger → position should be smaller."""

    async def test_volatile_market_smaller_position(self, db):
        s_base = {
            "max_single_order_usdt": 100000.0,
            "max_position_pct": 0.90,
            "risk_per_trade_pct": 0.001,
            "ema_trend_enabled": False,
        }

        calm_ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=50.0)
        calm_ohlcv["high"] = calm_ohlcv["close"] + 50
        calm_ohlcv["low"] = calm_ohlcv["close"] - 50

        volatile_ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=50.0)
        volatile_ohlcv["high"] = volatile_ohlcv["close"] + 500
        volatile_ohlcv["low"] = volatile_ohlcv["close"] - 500

        amounts = []

        for ohlcv_data in [calm_ohlcv, volatile_ohlcv]:
            s = _scenario_settings(**s_base)
            exchange = AsyncMock()
            price = float(ohlcv_data["close"].iloc[-1])
            exchange.get_ohlcv.return_value = ohlcv_data
            exchange.get_balance.return_value = {"USDT": 100000.0, "BTC": 0.0}
            exchange.get_ticker.return_value = Ticker(
                symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
            )

            captured = []

            async def track_order(captured=captured, price=price, **kwargs):
                captured.append(kwargs.get("amount", 0))
                return _make_order("BUY", kwargs["amount"], price)

            exchange.create_order.side_effect = track_order

            engine = TradingEngine(
                settings=s, exchange=exchange, database=db,
                strategies=[_strategy_returning("BUY", 0.8)],
            )
            await engine._tick()
            amounts.append(captured[0])

        assert len(amounts) == 2
        calm_amount, volatile_amount = amounts
        assert volatile_amount < calm_amount, \
            "Volatile market should produce a smaller position"


# ---------------------------------------------------------------------------
# Multi-pair scenarios
# ---------------------------------------------------------------------------


class TestMultiPairScenario:
    """Engine processes multiple trading pairs in one tick."""

    async def test_buy_one_pair_hold_another(self, db):
        base = load_settings()
        risk_kwargs = {
            "max_position_pct": 0.10,
            "stop_loss_pct": 0.03,
            "trailing_stop_pct": 0.02,
            "max_drawdown_pct": 0.15,
            "daily_loss_limit_pct": 0.05,
            "max_single_order_usdt": 1000.0,
            "min_confidence": 0.4,
            "max_concurrent_positions": 5,
            "max_data_age_seconds": 86400,
            "max_price_deviation_pct": 0.10,
            "circuit_breaker_threshold": 5,
            "volume_min_multiplier": 1.2,
            "ema_trend_enabled": False,
        }
        s = Settings(
            trading=TradingConfig(
                mode="paper",
                pairs=["BTC/USDT", "ETH/USDT"],
                timeframe="1h",
                poll_interval_seconds=1,
            ),
            paper_trading=base.paper_trading,
            exchange=base.exchange,
            strategies=base.strategies,
            ai=base.ai,
            risk=RiskConfig(**risk_kwargs),
        )

        exchange = AsyncMock()
        btc_ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        eth_ohlcv = _ohlcv_with_trend(60, start_price=3000.0, step=5.0)

        async def get_ohlcv_side(symbol, *a, **kw):
            if symbol == "BTC/USDT":
                return btc_ohlcv
            return eth_ohlcv

        exchange.get_ohlcv.side_effect = get_ohlcv_side

        async def get_ticker_side(symbol):
            if symbol == "BTC/USDT":
                p = float(btc_ohlcv["close"].iloc[-1])
                return Ticker(symbol=symbol, bid=p, ask=p + 10, last=p)
            p = float(eth_ohlcv["close"].iloc[-1])
            return Ticker(symbol=symbol, bid=p, ask=p + 5, last=p)

        exchange.get_ticker.side_effect = get_ticker_side
        exchange.get_balance.return_value = {
            "USDT": 10000.0, "BTC": 0.0, "ETH": 0.0,
        }

        btc_price = float(btc_ohlcv["close"].iloc[-1])
        exchange.create_order.return_value = _make_order(
            "BUY", 0.015, btc_price,
        )

        tick_count = [0]
        strat = AsyncMock()
        strat.name = "multi_pair"

        async def multi_signal(symbol, data):
            tick_count[0] += 1
            if symbol == "BTC/USDT":
                return Signal(
                    symbol=symbol, direction="BUY", confidence=0.8,
                    strategy_name="multi_pair", reason="BTC buy",
                )
            return Signal(
                symbol=symbol, direction="HOLD", confidence=0.0,
                strategy_name="multi_pair", reason="ETH hold",
            )

        strat.analyze.side_effect = multi_signal

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[strat],
        )

        await engine._tick()

        assert "BTC/USDT" in engine._positions
        assert "ETH/USDT" not in engine._positions
        assert exchange.create_order.call_count == 1


# ---------------------------------------------------------------------------
# Signal persistence scenarios
# ---------------------------------------------------------------------------


class TestSignalPersistence:
    """Signals (including aggregated) should be persisted to DB."""

    async def test_all_signals_stored(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, price)

        s1 = AsyncMock()
        s1.name = "rsi"
        s1.analyze.return_value = Signal(
            symbol="BTC/USDT", direction="BUY", confidence=0.7,
            strategy_name="rsi", reason="Oversold",
        )
        s2 = AsyncMock()
        s2.name = "macd"
        s2.analyze.return_value = Signal(
            symbol="BTC/USDT", direction="BUY", confidence=0.6,
            strategy_name="macd", reason="Crossover",
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[s1, s2],
        )

        await engine._tick()

        signals = await db.get_signals(limit=20)
        names = [sig["strategy_name"] for sig in signals]
        assert "rsi" in names
        assert "macd" in names
        assert "aggregator" in names

    async def test_hold_signals_also_stored(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )

        hold = AsyncMock()
        hold.name = "cautious"
        hold.analyze.return_value = Signal(
            symbol="BTC/USDT", direction="HOLD", confidence=0.0,
            strategy_name="cautious", reason="No signal",
        )

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[hold],
        )

        await engine._tick()

        signals = await db.get_signals(limit=20)
        assert len(signals) >= 2
        names = [sig["strategy_name"] for sig in signals]
        assert "cautious" in names
        assert "aggregator" in names


# ---------------------------------------------------------------------------
# Trade record verification
# ---------------------------------------------------------------------------


class TestTradeRecordIntegrity:
    """Verify trade records in DB match execution details."""

    async def test_buy_trade_stored_correctly(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, price)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()

        trades = await db.get_trades()
        assert len(trades) == 1
        t = trades[0]
        assert t.side == OrderSide.BUY
        assert t.symbol == "BTC/USDT"
        assert t.price == price
        assert t.amount == 0.015

    async def test_full_cycle_two_trades(self, db):
        """BUY followed by stop-loss SELL should produce exactly 2 trades."""
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60, start_price=60000.0, step=100.0)
        entry = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=entry, ask=entry + 10, last=entry,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, entry)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )
        await engine._tick()
        pos = engine._positions["BTC/USDT"]
        sl = pos.stop_loss_price

        crash = sl - 50
        usdt_left = 10000.0 - 0.015 * entry
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=crash, ask=crash + 10, last=crash,
        )
        exchange.get_balance.return_value = {
            "USDT": usdt_left, "BTC": 0.015,
        }
        exchange.create_order.return_value = _make_order(
            "SELL", 0.015, crash, "o-sl",
        )

        await engine._check_position_exit("BTC/USDT")

        trades = await db.get_trades()
        assert len(trades) == 2
        buy_trades = [t for t in trades if t.side == OrderSide.BUY]
        sell_trades = [t for t in trades if t.side == OrderSide.SELL]
        assert len(buy_trades) == 1
        assert len(sell_trades) == 1


# ---------------------------------------------------------------------------
# Portfolio snapshot scenarios
# ---------------------------------------------------------------------------


class TestPortfolioSnapshotAfterTrade:
    """Portfolio snapshot should be saved after successful trade."""

    async def test_snapshot_after_buy(self, db):
        s = _scenario_settings()
        exchange = AsyncMock()
        ohlcv = _ohlcv_with_trend(60)
        price = float(ohlcv["close"].iloc[-1])

        exchange.get_ohlcv.return_value = ohlcv
        exchange.get_balance.return_value = {"USDT": 10000.0, "BTC": 0.0}
        exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=price, ask=price + 10, last=price,
        )
        exchange.create_order.return_value = _make_order("BUY", 0.015, price)

        engine = TradingEngine(
            settings=s, exchange=exchange, database=db,
            strategies=[_strategy_returning("BUY", 0.8)],
        )

        await engine._tick()

        history = await db.get_portfolio_history()
        assert len(history) >= 1
