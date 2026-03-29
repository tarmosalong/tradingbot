from __future__ import annotations

from unittest.mock import AsyncMock

import pandas as pd
import pytest

from backend.config import RiskConfig
from backend.models import Signal
from backend.risk.manager import RiskManager


@pytest.fixture
def risk_config() -> RiskConfig:
    return RiskConfig(
        max_position_pct=0.10,
        stop_loss_pct=0.03,
        trailing_stop_pct=0.02,
        max_drawdown_pct=0.15,
        daily_loss_limit_pct=0.05,
        max_single_order_usdt=1000.0,
    )


@pytest.fixture
def risk_manager(risk_config: RiskConfig) -> RiskManager:
    db = AsyncMock()
    manager = RiskManager(risk_config, db)
    manager.set_initial_portfolio_value(10000.0)
    return manager


def _buy_signal(symbol: str = "BTC/USDT") -> Signal:
    return Signal(
        symbol=symbol,
        direction="BUY",
        confidence=0.8,
        strategy_name="test",
        reason="Test buy",
    )


def _sell_signal(symbol: str = "BTC/USDT") -> Signal:
    return Signal(
        symbol=symbol,
        direction="SELL",
        confidence=0.8,
        strategy_name="test",
        reason="Test sell",
    )


class TestRiskManagerBuy:
    async def test_buy_approved_within_limits(self, risk_manager):
        decision = await risk_manager.check_signal(
            signal=_buy_signal(),
            portfolio_value=10000.0,
            balance={"USDT": 10000.0},
            current_price=65000.0,
        )

        assert decision.approved
        assert decision.amount > 0
        assert decision.amount <= 1000.0 / 65000.0

    async def test_buy_respects_max_position_pct(self, risk_manager):
        decision = await risk_manager.check_signal(
            signal=_buy_signal(),
            portfolio_value=10000.0,
            balance={"USDT": 10000.0},
            current_price=65000.0,
        )

        max_budget = min(10000.0 * 0.10, 1000.0)
        expected_amount = max_budget / 65000.0
        assert decision.amount == pytest.approx(expected_amount, rel=0.01)

    async def test_buy_rejected_insufficient_balance(self, risk_manager):
        decision = await risk_manager.check_signal(
            signal=_buy_signal(),
            portfolio_value=10000.0,
            balance={"USDT": 0.5},
            current_price=65000.0,
        )

        assert not decision.approved
        assert "budget" in decision.reason.lower() or "small" in decision.reason.lower()

    async def test_buy_respects_max_single_order(self, risk_manager):
        decision = await risk_manager.check_signal(
            signal=_buy_signal(),
            portfolio_value=100000.0,
            balance={"USDT": 100000.0},
            current_price=65000.0,
        )

        assert decision.approved
        assert decision.amount <= 1000.0 / 65000.0 + 0.0001


class TestRiskManagerSell:
    async def test_sell_approved_with_position(self, risk_manager):
        decision = await risk_manager.check_signal(
            signal=_sell_signal(),
            portfolio_value=10000.0,
            balance={"USDT": 5000.0, "BTC": 0.1},
            current_price=65000.0,
        )

        assert decision.approved
        assert decision.amount == 0.1

    async def test_sell_rejected_no_position(self, risk_manager):
        decision = await risk_manager.check_signal(
            signal=_sell_signal(),
            portfolio_value=10000.0,
            balance={"USDT": 10000.0},
            current_price=65000.0,
        )

        assert not decision.approved
        assert "no" in decision.reason.lower()


class TestRiskManagerDrawdown:
    async def test_max_drawdown_blocks_trade(self, risk_manager):
        decision = await risk_manager.check_signal(
            signal=_buy_signal(),
            portfolio_value=8000.0,
            balance={"USDT": 8000.0},
            current_price=65000.0,
        )

        assert not decision.approved
        assert "drawdown" in decision.reason.lower()

    async def test_within_drawdown_limit_allows_trade(self, risk_manager):
        decision = await risk_manager.check_signal(
            signal=_buy_signal(),
            portfolio_value=9600.0,
            balance={"USDT": 9600.0},
            current_price=65000.0,
        )

        assert decision.approved


class TestRiskManagerDailyLoss:
    async def test_daily_loss_limit_blocks_trade(self, risk_manager):
        risk_manager._daily_start_value = 10000.0

        decision = await risk_manager.check_signal(
            signal=_buy_signal(),
            portfolio_value=9400.0,
            balance={"USDT": 9400.0},
            current_price=65000.0,
        )

        assert not decision.approved
        assert "daily" in decision.reason.lower()


class TestStopLoss:
    def test_buy_stop_loss(self, risk_manager):
        stop = risk_manager.calculate_stop_loss(65000.0, "BUY")
        assert stop == pytest.approx(65000.0 * 0.97)

    def test_sell_stop_loss(self, risk_manager):
        stop = risk_manager.calculate_stop_loss(65000.0, "SELL")
        assert stop == pytest.approx(65000.0 * 1.03)

    def test_trailing_stop_buy(self, risk_manager):
        stop = risk_manager.calculate_trailing_stop(66000.0, 67000.0, "BUY")
        assert stop == pytest.approx(67000.0 * 0.98)

    def test_trailing_stop_sell(self, risk_manager):
        stop = risk_manager.calculate_trailing_stop(64000.0, 63000.0, "SELL")
        assert stop == pytest.approx(63000.0 * 1.02)

    def test_stop_triggered_buy(self, risk_manager):
        assert risk_manager.should_trigger_stop(62000.0, 63000.0, "BUY")
        assert not risk_manager.should_trigger_stop(64000.0, 63000.0, "BUY")

    def test_stop_triggered_sell(self, risk_manager):
        assert risk_manager.should_trigger_stop(68000.0, 67000.0, "SELL")
        assert not risk_manager.should_trigger_stop(66000.0, 67000.0, "SELL")


class TestRiskManagerEdgeCases:
    async def test_zero_portfolio_value(self, risk_config):
        db = AsyncMock()
        manager = RiskManager(risk_config, db)

        decision = await manager.check_signal(
            signal=_buy_signal(),
            portfolio_value=0.0,
            balance={"USDT": 0.0},
            current_price=65000.0,
        )

        assert not decision.approved

    async def test_hold_signal_rejected(self, risk_manager):
        signal = Signal(
            symbol="BTC/USDT",
            direction="HOLD",
            confidence=0.0,
            strategy_name="test",
            reason="No signal",
        )
        decision = await risk_manager.check_signal(
            signal=signal,
            portfolio_value=10000.0,
            balance={"USDT": 10000.0},
            current_price=65000.0,
        )

        assert not decision.approved


class TestATRCalculation:
    def test_calculate_atr_basic(self, risk_manager):
        ohlcv = pd.DataFrame({
            "high": [110.0, 115.0, 120.0, 118.0] * 5,
            "low": [100.0, 105.0, 108.0, 106.0] * 5,
            "close": [105.0, 110.0, 115.0, 112.0] * 5,
        })
        atr = risk_manager.calculate_atr(ohlcv, period=14)
        assert atr > 0

    def test_atr_insufficient_data(self, risk_manager):
        ohlcv = pd.DataFrame({
            "high": [110.0], "low": [100.0], "close": [105.0],
        })
        assert risk_manager.calculate_atr(ohlcv, period=14) == 0.0

    def test_calculate_atr_stops(self, risk_manager):
        ohlcv = pd.DataFrame({
            "high": [110.0, 115.0, 120.0, 118.0] * 5,
            "low": [100.0, 105.0, 108.0, 106.0] * 5,
            "close": [105.0, 110.0, 115.0, 112.0] * 5,
        })
        stops = risk_manager.calculate_atr_stops(ohlcv, entry_price=112.0)
        assert stops.atr > 0
        assert stops.stop_loss < 112.0
        assert stops.take_profit > 112.0
        assert stops.trailing_stop < 112.0

    def test_atr_stops_fallback_no_data(self, risk_manager):
        ohlcv = pd.DataFrame({
            "high": [110.0], "low": [100.0], "close": [105.0],
        })
        stops = risk_manager.calculate_atr_stops(ohlcv, entry_price=100.0)
        assert stops.atr == 0.0
        assert stops.stop_loss == 100.0 * (1 - 0.03)
