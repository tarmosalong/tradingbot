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


@pytest.fixture
def mock_exchange():
    exchange = AsyncMock()
    exchange.get_balance.return_value = {
        "USDT": 10000.0, "BTC": 0.0,
    }
    exchange.get_ticker.return_value = Ticker(
        symbol="BTC/USDT", bid=65000.0, ask=65010.0, last=65005.0,
    )
    exchange.get_ohlcv.return_value = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=20, freq="h"),
            "open": [65000.0] * 20,
            "high": [65200.0] * 20,
            "low": [64800.0] * 20,
            "close": [65100.0] * 20,
            "volume": [100.0] * 20,
        }
    )
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
