from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from backend.config import RiskConfig, Settings, TradingConfig, load_settings
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


@pytest.fixture
def settings():
    base = load_settings()
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
        risk=base.risk,
    )


@pytest.fixture
async def db(tmp_path):
    database = Database(db_path=tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


def _recent_ohlcv(periods: int = 20) -> pd.DataFrame:
    """OHLCV DataFrame with timestamps ending near 'now' so stale-data guard passes.

    Volume on the last candle is above the SMA-20 * 1.2 threshold so the
    volume confirmation guard passes by default.
    """
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(hours=periods - 1)
    volumes = [100.0] * periods
    volumes[-1] = 200.0
    return pd.DataFrame({
        "timestamp": pd.date_range(start, periods=periods, freq="h"),
        "open": [65000.0] * periods,
        "high": [65200.0] * periods,
        "low": [64800.0] * periods,
        "close": [65100.0] * periods,
        "volume": volumes,
    })


@pytest.fixture
def mock_exchange():
    exchange = AsyncMock()
    exchange.get_balance.return_value = {
        "USDT": 10000.0, "BTC": 0.0,
    }
    exchange.get_ticker.return_value = Ticker(
        symbol="BTC/USDT", bid=65000.0, ask=65010.0, last=65005.0,
    )
    exchange.get_ohlcv.return_value = _recent_ohlcv()
    exchange.create_order.return_value = Order(
        id="o-1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        amount=0.015,
        price=65005.0,
        status=OrderStatus.FILLED,
        filled_amount=0.015,
        filled_price=65005.0,
    )
    exchange.get_open_orders.return_value = []
    return exchange


def _buy_strategy():
    strategy = AsyncMock()
    strategy.name = "test_buy"
    strategy.analyze.return_value = Signal(
        symbol="BTC/USDT",
        direction="BUY",
        confidence=0.8,
        strategy_name="test_buy",
        reason="Test buy signal",
    )
    return strategy


def _sell_strategy():
    strategy = AsyncMock()
    strategy.name = "test_sell"
    strategy.analyze.return_value = Signal(
        symbol="BTC/USDT",
        direction="SELL",
        confidence=0.7,
        strategy_name="test_sell",
        reason="Test sell signal",
    )
    return strategy


def _hold_strategy():
    strategy = AsyncMock()
    strategy.name = "test_hold"
    strategy.analyze.return_value = Signal(
        symbol="BTC/USDT",
        direction="HOLD",
        confidence=0.0,
        strategy_name="test_hold",
        reason="No signal",
    )
    return strategy


class TestSignalAggregation:
    def test_all_hold_returns_hold(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="a", reason="none",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="b", reason="none",
            ),
        ]

        result = TradingEngine._aggregate_signals(signals)

        assert result.direction == "HOLD"
        assert result.strategy_name == "aggregator"

    def test_buy_majority_returns_buy(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.8, strategy_name="rsi", reason="Oversold",
            ),
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.6, strategy_name="macd", reason="Crossover",
            ),
            Signal(
                symbol="BTC/USDT", direction="SELL",
                confidence=0.3, strategy_name="bollinger", reason="Upper band",
            ),
        ]

        result = TradingEngine._aggregate_signals(signals)

        assert result.direction == "BUY"
        assert result.confidence == pytest.approx(0.7)
        assert "rsi" in result.reason
        assert "macd" in result.reason

    def test_sell_majority_returns_sell(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="SELL",
                confidence=0.9, strategy_name="rsi", reason="Overbought",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="macd", reason="No signal",
            ),
        ]

        result = TradingEngine._aggregate_signals(signals)

        assert result.direction == "SELL"
        assert result.confidence == pytest.approx(0.9)

    def test_tied_signals_return_hold(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.5, strategy_name="a", reason="up",
            ),
            Signal(
                symbol="BTC/USDT", direction="SELL",
                confidence=0.5, strategy_name="b", reason="down",
            ),
        ]

        result = TradingEngine._aggregate_signals(signals)

        assert result.direction == "HOLD"
        assert "tied" in result.reason.lower()


class TestTradingEngine:
    async def test_tick_executes_buy_order(
        self, settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_buy_strategy()],
        )

        await engine._tick()

        mock_exchange.create_order.assert_called_once()
        call_kwargs = mock_exchange.create_order.call_args
        assert call_kwargs.kwargs["side"] == "BUY"

        trades = await db.get_trades()
        assert len(trades) == 1

    async def test_tick_hold_does_not_trade(
        self, settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_hold_strategy()],
        )

        await engine._tick()

        mock_exchange.create_order.assert_not_called()

    async def test_tick_sell_with_no_position_skips(
        self, settings, mock_exchange, db,
    ):
        mock_exchange.get_balance.return_value = {
            "USDT": 10000.0, "BTC": 0.0,
        }
        engine = TradingEngine(
            settings=settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_sell_strategy()],
        )

        await engine._tick()

        mock_exchange.create_order.assert_not_called()

    async def test_tick_sell_with_position_executes(
        self, settings, mock_exchange, db,
    ):
        mock_exchange.get_balance.return_value = {
            "USDT": 5000.0, "BTC": 0.1,
        }
        mock_exchange.create_order.return_value = Order(
            id="o-sell",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=0.1,
            price=65005.0,
            status=OrderStatus.FILLED,
            filled_amount=0.1,
            filled_price=65005.0,
        )
        engine = TradingEngine(
            settings=settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_sell_strategy()],
        )

        await engine._tick()

        mock_exchange.create_order.assert_called_once()
        call_kwargs = mock_exchange.create_order.call_args
        assert call_kwargs.kwargs["side"] == "SELL"

    async def test_start_stop_lifecycle(
        self, settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_hold_strategy()],
        )

        assert not engine.is_running

        async def stop_soon():
            await asyncio.sleep(0.1)
            await engine.stop()

        task = asyncio.create_task(stop_soon())
        await engine.start()
        await task

        assert not engine.is_running

    async def test_snapshot_portfolio_saves_to_db(
        self, settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=settings,
            exchange=mock_exchange,
            database=db,
            strategies=[],
        )

        await engine._snapshot_portfolio()

        history = await db.get_portfolio_history()
        assert len(history) == 1
        assert history[0]["total_value_usdt"] == 10000.0

    async def test_tick_persists_signals(
        self, settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_buy_strategy(), _hold_strategy()],
        )

        await engine._tick()

        signals = await db.get_signals(limit=10)
        names = [s["strategy_name"] for s in signals]
        assert "aggregator" in names
        assert "test_buy" in names
        assert "test_hold" in names

    async def test_tick_hold_still_persists_signals(
        self, settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_hold_strategy()],
        )

        await engine._tick()

        signals = await db.get_signals(limit=10)
        assert len(signals) >= 2
        agg = [s for s in signals if s["strategy_name"] == "aggregator"]
        assert len(agg) == 1
        assert agg[0]["direction"] == "HOLD"


class TestOpenPosition:
    def test_to_dict_with_profit(self):
        pos = OpenPosition(
            symbol="BTC/USDT",
            amount=0.1,
            entry_price=60000.0,
            peak_price=66000.0,
        )
        pos.set_risk(0.03, 0.02)

        result = pos.to_dict(current_price=65000.0)

        assert result["pnl"] == 500.0
        assert result["stop_loss_price"] == 60000.0 * 0.97
        assert result["trailing_stop_price"] == 66000.0 * 0.98
        assert len(result["exit_conditions"]) == 3

    def test_to_dict_with_loss(self):
        pos = OpenPosition(
            symbol="ETH/USDT",
            amount=1.0,
            entry_price=2000.0,
            peak_price=2000.0,
        )
        pos.set_risk(0.03, 0.02)

        result = pos.to_dict(current_price=1950.0)

        assert result["pnl"] == -50.0
        assert result["pnl_pct"] == pytest.approx(-2.5)


class TestPositionExitMonitoring:
    @pytest.fixture
    def risk_settings(self, settings):
        base = load_settings()
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
            risk=RiskConfig(
                max_position_pct=0.10,
                stop_loss_pct=0.03,
                trailing_stop_pct=0.02,
                max_drawdown_pct=0.15,
                daily_loss_limit_pct=0.05,
                max_single_order_usdt=1000.0,
            ),
        )

    async def test_stop_loss_triggers_sell(
        self, risk_settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=risk_settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_hold_strategy()],
        )

        pos = OpenPosition(
            symbol="BTC/USDT",
            amount=0.1,
            entry_price=65000.0,
            peak_price=65000.0,
        )
        pos.set_risk(0.03, 0.02)
        engine._positions["BTC/USDT"] = pos

        # Price drops below stop-loss (3% below 65000 = 63050)
        mock_exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=62000.0, ask=62010.0, last=62000.0,
        )
        mock_exchange.get_balance.return_value = {"USDT": 5000.0, "BTC": 0.1}
        mock_exchange.create_order.return_value = Order(
            id="o-sl",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=0.1,
            price=62000.0,
            status=OrderStatus.FILLED,
            filled_amount=0.1,
            filled_price=62000.0,
        )

        exited = await engine._check_position_exit("BTC/USDT")

        assert exited is True
        assert "BTC/USDT" not in engine._positions
        mock_exchange.create_order.assert_called_once()

    async def test_trailing_stop_triggers_sell(
        self, risk_settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=risk_settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_hold_strategy()],
        )

        pos = OpenPosition(
            symbol="BTC/USDT",
            amount=0.1,
            entry_price=60000.0,
            peak_price=70000.0,
        )
        pos.set_risk(0.03, 0.02)
        engine._positions["BTC/USDT"] = pos

        # Trailing stop = 70000 * 0.98 = 68600
        # SL = 60000 * 0.97 = 58200
        # Price at 68000 < 68600 but > 58200 → trailing stop
        mock_exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=68000.0, ask=68010.0, last=68000.0,
        )
        mock_exchange.get_balance.return_value = {"USDT": 5000.0, "BTC": 0.1}
        mock_exchange.create_order.return_value = Order(
            id="o-ts",
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=0.1,
            price=68000.0,
            status=OrderStatus.FILLED,
            filled_amount=0.1,
            filled_price=68000.0,
        )

        exited = await engine._check_position_exit("BTC/USDT")

        assert exited is True
        assert "BTC/USDT" not in engine._positions

    async def test_no_exit_when_price_safe(
        self, risk_settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=risk_settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_hold_strategy()],
        )

        pos = OpenPosition(
            symbol="BTC/USDT",
            amount=0.1,
            entry_price=65000.0,
            peak_price=66000.0,
        )
        pos.set_risk(0.03, 0.02)
        engine._positions["BTC/USDT"] = pos

        mock_exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=65500.0, ask=65510.0, last=65500.0,
        )

        exited = await engine._check_position_exit("BTC/USDT")

        assert exited is False
        assert "BTC/USDT" in engine._positions
        mock_exchange.create_order.assert_not_called()

    async def test_peak_price_updates(
        self, risk_settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=risk_settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_hold_strategy()],
        )

        pos = OpenPosition(
            symbol="BTC/USDT",
            amount=0.1,
            entry_price=65000.0,
            peak_price=66000.0,
        )
        pos.set_risk(0.03, 0.02)
        engine._positions["BTC/USDT"] = pos

        mock_exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=68000.0, ask=68010.0, last=68000.0,
        )

        await engine._check_position_exit("BTC/USDT")

        assert pos.peak_price == 68000.0

    async def test_buy_creates_position(
        self, risk_settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=risk_settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_buy_strategy()],
        )

        await engine._tick()

        assert "BTC/USDT" in engine._positions
        pos = engine._positions["BTC/USDT"]
        assert pos.amount == 0.015
        assert pos.entry_price == 65005.0

    async def test_get_positions_with_prices(
        self, risk_settings, mock_exchange, db,
    ):
        engine = TradingEngine(
            settings=risk_settings,
            exchange=mock_exchange,
            database=db,
            strategies=[],
        )

        pos = OpenPosition(
            symbol="BTC/USDT",
            amount=0.1,
            entry_price=65000.0,
            peak_price=66000.0,
        )
        pos.set_risk(0.03, 0.02)
        engine._positions["BTC/USDT"] = pos

        result = await engine.get_positions_with_prices()

        assert len(result) == 1
        assert result[0]["symbol"] == "BTC/USDT"
        assert result[0]["current_price"] == 65005.0
        assert "exit_conditions" in result[0]
        assert len(result[0]["exit_conditions"]) == 3

    async def test_no_duplicate_buy_when_position_exists(
        self, risk_settings, mock_exchange, db,
    ):
        """BUY signal should be skipped when already holding."""
        engine = TradingEngine(
            settings=risk_settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_buy_strategy()],
        )

        pos = OpenPosition(
            symbol="BTC/USDT",
            amount=0.1,
            entry_price=65000.0,
            peak_price=65500.0,
        )
        pos.set_risk(0.03, 0.02)
        engine._positions["BTC/USDT"] = pos

        mock_exchange.create_order.reset_mock()
        await engine._tick()

        mock_exchange.create_order.assert_not_called()
        assert engine._positions["BTC/USDT"].amount == 0.1

    async def test_cooldown_prevents_rapid_buys(
        self, risk_settings, mock_exchange, db,
    ):
        """Second BUY within cooldown window should be skipped."""
        from datetime import UTC, datetime

        engine = TradingEngine(
            settings=risk_settings,
            exchange=mock_exchange,
            database=db,
            strategies=[_buy_strategy()],
        )

        engine._last_trade_time["BTC/USDT"] = datetime.now(UTC)

        mock_exchange.create_order.reset_mock()
        await engine._tick()

        mock_exchange.create_order.assert_not_called()


def _guard_settings(base_settings, **risk_overrides):
    """Build Settings with custom RiskConfig fields for guard tests."""
    risk_kwargs = {
        "max_position_pct": 0.10,
        "stop_loss_pct": 0.03,
        "trailing_stop_pct": 0.02,
        "max_drawdown_pct": 0.15,
        "daily_loss_limit_pct": 0.05,
        "max_single_order_usdt": 1000.0,
        "min_confidence": 0.4,
        "max_concurrent_positions": 3,
        "max_data_age_seconds": 3600,
        "max_price_deviation_pct": 0.05,
        "circuit_breaker_threshold": 5,
    }
    risk_kwargs.update(risk_overrides)
    return Settings(
        trading=TradingConfig(
            mode="paper",
            pairs=["BTC/USDT"],
            timeframe="1h",
            poll_interval_seconds=1,
        ),
        paper_trading=base_settings.paper_trading,
        exchange=base_settings.exchange,
        strategies=base_settings.strategies,
        ai=base_settings.ai,
        risk=RiskConfig(**risk_kwargs),
    )


class TestTradingGuards:
    """Regression tests for the 6 new engine guards."""

    @pytest.fixture
    def base_settings(self):
        return load_settings()

    async def test_risk_manager_rejects_on_drawdown(
        self, base_settings, mock_exchange, db,
    ):
        """When portfolio drops past max_drawdown_pct, no orders are placed."""
        s = _guard_settings(base_settings, max_drawdown_pct=0.10)
        engine = TradingEngine(
            settings=s,
            exchange=mock_exchange,
            database=db,
            strategies=[_buy_strategy()],
        )

        engine._risk_manager.set_initial_portfolio_value(10_000.0)

        mock_exchange.get_balance.return_value = {"USDT": 8500.0}

        await engine._tick()

        mock_exchange.create_order.assert_not_called()

    async def test_low_confidence_skipped(
        self, base_settings, mock_exchange, db,
    ):
        """Signals below min_confidence threshold are not executed."""
        s = _guard_settings(base_settings, min_confidence=0.5)

        low_conf = AsyncMock()
        low_conf.name = "low_conf"
        low_conf.analyze.return_value = Signal(
            symbol="BTC/USDT",
            direction="BUY",
            confidence=0.3,
            strategy_name="low_conf",
            reason="Weak buy",
        )

        engine = TradingEngine(
            settings=s,
            exchange=mock_exchange,
            database=db,
            strategies=[low_conf],
        )

        await engine._tick()

        mock_exchange.create_order.assert_not_called()

    async def test_stale_data_skipped(
        self, base_settings, mock_exchange, db,
    ):
        """OHLCV data older than max_data_age_seconds causes the symbol to be skipped."""
        s = _guard_settings(base_settings, max_data_age_seconds=600)

        mock_exchange.get_ohlcv.return_value = pd.DataFrame({
            "timestamp": pd.date_range(
                "2020-01-01", periods=20, freq="h",
            ),
            "open": [65000.0] * 20,
            "high": [65200.0] * 20,
            "low": [64800.0] * 20,
            "close": [65100.0] * 20,
            "volume": [100.0] * 20,
        })

        engine = TradingEngine(
            settings=s,
            exchange=mock_exchange,
            database=db,
            strategies=[_buy_strategy()],
        )

        await engine._tick()

        mock_exchange.create_order.assert_not_called()

    async def test_max_concurrent_positions(
        self, base_settings, mock_exchange, db,
    ):
        """When max_concurrent_positions is reached, new BUYs are blocked."""
        s = _guard_settings(
            base_settings,
            max_concurrent_positions=2,
        )
        engine = TradingEngine(
            settings=s,
            exchange=mock_exchange,
            database=db,
            strategies=[_buy_strategy()],
        )

        for sym in ["ETH/USDT", "SOL/USDT"]:
            pos = OpenPosition(
                symbol=sym, amount=1.0,
                entry_price=100.0, peak_price=100.0,
            )
            pos.set_risk(0.03, 0.02)
            engine._positions[sym] = pos

        await engine._tick()

        mock_exchange.create_order.assert_not_called()

    async def test_price_sanity_rejects_wild_price(
        self, base_settings, mock_exchange, db,
    ):
        """If ticker deviates >max_price_deviation_pct from last close, trade is rejected."""
        s = _guard_settings(base_settings, max_price_deviation_pct=0.05)

        ohlcv = _recent_ohlcv()
        ohlcv["close"] = 65000.0
        mock_exchange.get_ohlcv.return_value = ohlcv

        mock_exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT",
            bid=72000.0,
            ask=72010.0,
            last=72000.0,
        )

        engine = TradingEngine(
            settings=s,
            exchange=mock_exchange,
            database=db,
            strategies=[_buy_strategy()],
        )

        await engine._tick()

        mock_exchange.create_order.assert_not_called()

    async def test_circuit_breaker_pauses(
        self, base_settings, mock_exchange, db, monkeypatch,
    ):
        """After N consecutive errors, the engine pauses for 5 minutes."""
        s = _guard_settings(base_settings, circuit_breaker_threshold=3)
        engine = TradingEngine(
            settings=s,
            exchange=mock_exchange,
            database=db,
            strategies=[_buy_strategy()],
        )

        sleep_calls: list[float] = []
        original_sleep = asyncio.sleep

        async def mock_sleep(secs, **kwargs):
            sleep_calls.append(secs)
            if secs >= 300:
                engine._running = False
            else:
                await original_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", mock_sleep)

        async def exploding_tick():
            raise RuntimeError("boom")

        monkeypatch.setattr(engine, "_tick", exploding_tick)

        engine._running = True
        engine._risk_manager.set_initial_portfolio_value(10_000.0)
        await engine.start()

        assert any(s >= 300 for s in sleep_calls)


class TestVolumeConfirmation:
    def test_low_volume_rejected(self):
        ohlcv = _recent_ohlcv(25)
        ohlcv["volume"] = 100.0
        assert not TradingEngine._check_volume_confirmation(ohlcv, 1.2)

    def test_high_volume_accepted(self):
        ohlcv = _recent_ohlcv(25)
        ohlcv["volume"] = 100.0
        ohlcv.loc[ohlcv.index[-1], "volume"] = 200.0
        assert TradingEngine._check_volume_confirmation(ohlcv, 1.2)

    def test_insufficient_data_passes(self):
        ohlcv = _recent_ohlcv(10)
        assert TradingEngine._check_volume_confirmation(ohlcv, 1.2)

    async def test_volume_guard_blocks_tick(
        self, mock_exchange, db,
    ):
        s = _guard_settings(
            load_settings(), volume_min_multiplier=1.2,
        )
        ohlcv = _recent_ohlcv(25)
        ohlcv["volume"] = 100.0
        mock_exchange.get_ohlcv.return_value = ohlcv

        engine = TradingEngine(
            settings=s, exchange=mock_exchange,
            database=db, strategies=[_buy_strategy()],
        )
        await engine._tick()
        mock_exchange.create_order.assert_not_called()


class TestEMATrendFilter:
    def test_buy_above_ema_passes(self):
        ohlcv = _recent_ohlcv(60)
        ohlcv["close"] = list(range(100, 160))
        assert TradingEngine._check_ema_trend(ohlcv, "BUY", 50) is True

    def test_buy_below_ema_rejected(self):
        ohlcv = _recent_ohlcv(60)
        ohlcv["close"] = list(range(160, 100, -1))
        assert TradingEngine._check_ema_trend(ohlcv, "BUY", 50) is False

    def test_sell_below_ema_passes(self):
        ohlcv = _recent_ohlcv(60)
        ohlcv["close"] = list(range(160, 100, -1))
        assert TradingEngine._check_ema_trend(ohlcv, "SELL", 50) is True

    def test_insufficient_data_passes(self):
        ohlcv = _recent_ohlcv(10)
        assert TradingEngine._check_ema_trend(ohlcv, "BUY", 50) is True

    async def test_ema_filter_blocks_counter_trend(
        self, mock_exchange, db,
    ):
        s = _guard_settings(
            load_settings(),
            ema_trend_enabled=True, ema_trend_period=50,
        )
        ohlcv = _recent_ohlcv(60)
        ohlcv["close"] = list(range(160, 100, -1))
        ohlcv.loc[ohlcv.index[-1], "volume"] = 999.0
        mock_exchange.get_ohlcv.return_value = ohlcv

        engine = TradingEngine(
            settings=s, exchange=mock_exchange,
            database=db, strategies=[_buy_strategy()],
        )
        await engine._tick()
        mock_exchange.create_order.assert_not_called()


class TestATRStops:
    def test_atr_stop_prices_on_position(self):
        pos = OpenPosition(
            symbol="BTC/USDT", amount=0.01,
            entry_price=65000.0, peak_price=66000.0,
            atr_at_entry=500.0, atr_stop_loss=64000.0,
            atr_take_profit=66500.0, atr_trailing_multiplier=1.5,
        )
        pos.set_risk(0.03, 0.02)
        assert pos.stop_loss_price == 64000.0
        assert pos.trailing_stop_price == 66000.0 - 500.0 * 1.5
        assert pos.take_profit_price == 66500.0

    def test_fallback_to_pct_when_no_atr(self):
        pos = OpenPosition(
            symbol="BTC/USDT", amount=0.01,
            entry_price=65000.0, peak_price=66000.0,
        )
        pos.set_risk(0.03, 0.02)
        assert pos.stop_loss_price == 65000.0 * 0.97
        assert pos.trailing_stop_price == 66000.0 * 0.98

    def test_to_dict_includes_take_profit(self):
        pos = OpenPosition(
            symbol="BTC/USDT", amount=0.01,
            entry_price=65000.0, peak_price=66000.0,
            atr_at_entry=500.0, atr_stop_loss=64000.0,
            atr_take_profit=66500.0,
        )
        pos.set_risk(0.03, 0.02)
        d = pos.to_dict(65500.0)
        assert d["take_profit_price"] == 66500.0
        assert any("Take-profit" in c for c in d["exit_conditions"])

    async def test_take_profit_triggers_partial_sell(
        self, mock_exchange, db,
    ):
        s = _guard_settings(
            load_settings(), partial_tp_ratio=0.5,
        )
        engine = TradingEngine(
            settings=s, exchange=mock_exchange,
            database=db, strategies=[_hold_strategy()],
        )
        pos = OpenPosition(
            symbol="BTC/USDT", amount=0.1,
            entry_price=65000.0, peak_price=67000.0,
            atr_at_entry=500.0, atr_stop_loss=64000.0,
            atr_take_profit=66500.0, atr_trailing_multiplier=1.5,
        )
        pos.set_risk(0.03, 0.02)
        engine._positions["BTC/USDT"] = pos

        mock_exchange.get_ticker.return_value = Ticker(
            symbol="BTC/USDT", bid=67000.0, ask=67010.0, last=67000.0,
        )
        mock_exchange.get_balance.return_value = {"USDT": 5000.0, "BTC": 0.1}
        mock_exchange.create_order.return_value = Order(
            id="o-tp", symbol="BTC/USDT", side=OrderSide.SELL,
            order_type=OrderType.MARKET, amount=0.05, price=67000.0,
            status=OrderStatus.FILLED, filled_amount=0.05, filled_price=67000.0,
        )

        exited = await engine._check_position_exit("BTC/USDT")

        assert exited is True
        assert pos.partial_exits_done == 1
        assert pos.atr_stop_loss == pos.entry_price
        assert "BTC/USDT" in engine._positions


class TestStrategyWeights:
    def test_weighted_aggregation_flips_direction(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.6, strategy_name="rsi", reason="oversold",
            ),
            Signal(
                symbol="BTC/USDT", direction="SELL",
                confidence=0.5, strategy_name="macd", reason="crossover",
            ),
        ]
        result_no_weight = TradingEngine._aggregate_signals(signals)
        assert result_no_weight.direction == "BUY"

        result_weighted = TradingEngine._aggregate_signals(
            signals, {"rsi": 0.5, "macd": 2.0},
        )
        assert result_weighted.direction == "SELL"

    def test_equal_weights_same_as_unweighted(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.8, strategy_name="rsi", reason="up",
            ),
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.6, strategy_name="macd", reason="up",
            ),
        ]
        no_w = TradingEngine._aggregate_signals(signals)
        with_w = TradingEngine._aggregate_signals(
            signals, {"rsi": 1.0, "macd": 1.0},
        )
        assert no_w.confidence == pytest.approx(with_w.confidence)

    def test_default_weight_is_one(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.7, strategy_name="unknown_strat", reason="x",
            ),
        ]
        result = TradingEngine._aggregate_signals(signals, {"rsi": 2.0})
        assert result.confidence == pytest.approx(0.7)


class TestMinAgreement:
    def test_single_buy_blocked_by_min_agreement_2(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.8, strategy_name="rsi", reason="oversold",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="macd", reason="neutral",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="ema", reason="neutral",
            ),
        ]
        result = TradingEngine._aggregate_signals(
            signals, min_agreement=2,
        )
        assert result.direction == "HOLD"
        assert "need 2" in result.reason

    def test_two_buys_pass_min_agreement_2(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.7, strategy_name="rsi", reason="oversold",
            ),
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.6, strategy_name="ema", reason="crossover",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="macd", reason="neutral",
            ),
        ]
        result = TradingEngine._aggregate_signals(
            signals, min_agreement=2,
        )
        assert result.direction == "BUY"
        assert result.confidence > 0

    def test_min_agreement_1_allows_single_signal(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.6, strategy_name="rsi", reason="oversold",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="macd", reason="neutral",
            ),
        ]
        result = TradingEngine._aggregate_signals(
            signals, min_agreement=1,
        )
        assert result.direction == "BUY"


class TestHoldOpposition:
    def test_hold_opposition_blocks_weak_signal(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.1, strategy_name="rsi", reason="weak",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="macd", reason="neutral",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="ema", reason="neutral",
            ),
        ]
        result = TradingEngine._aggregate_signals(
            signals, hold_opposition=0.2,
        )
        assert result.direction == "HOLD"

    def test_hold_opposition_zero_matches_old_behavior(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.6, strategy_name="rsi", reason="oversold",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="macd", reason="neutral",
            ),
        ]
        result = TradingEngine._aggregate_signals(
            signals, hold_opposition=0.0,
        )
        assert result.direction == "BUY"
        assert result.confidence == pytest.approx(0.6)

    def test_hold_opposition_reduces_confidence(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.8, strategy_name="rsi", reason="oversold",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="macd", reason="neutral",
            ),
        ]
        with_opp = TradingEngine._aggregate_signals(
            signals, hold_opposition=0.1,
        )
        without_opp = TradingEngine._aggregate_signals(
            signals, hold_opposition=0.0,
        )
        assert with_opp.direction == "BUY"
        assert with_opp.confidence < without_opp.confidence

    def test_combined_min_agreement_and_hold_opposition(self):
        signals = [
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.7, strategy_name="rsi", reason="oversold",
            ),
            Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.6, strategy_name="ema", reason="crossover",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="macd", reason="neutral",
            ),
            Signal(
                symbol="BTC/USDT", direction="HOLD",
                confidence=0.0, strategy_name="bollinger", reason="neutral",
            ),
        ]
        result = TradingEngine._aggregate_signals(
            signals, min_agreement=2, hold_opposition=0.1,
        )
        assert result.direction == "BUY"
        assert result.confidence > 0
