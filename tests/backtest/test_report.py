from __future__ import annotations

import pytest

from backend.backtest.engine import BacktestResult, BacktestTrade
from backend.backtest.report import (
    _max_drawdown,
    _period_returns,
    _sharpe_ratio,
    generate_report,
)
from backend.models import OrderSide, Signal, Trade


def _simple_result() -> BacktestResult:
    """Result with known values for easy verification."""
    return BacktestResult(
        symbol="BTC/USDT",
        initial_balance=10000.0,
        final_balance=11000.0,
        equity_curve=[10000, 10200, 10100, 10500, 10800, 11000],
        timestamps=[f"2025-01-0{i+1}" for i in range(6)],
    )


def _result_with_trades() -> BacktestResult:
    result = _simple_result()
    result.trades = [
        BacktestTrade(
            trade=Trade(
                id="1", symbol="BTC/USDT", side=OrderSide.BUY,
                amount=0.01, price=65000.0,
            ),
            signal=Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.8, strategy_name="rsi", reason="Oversold",
            ),
            portfolio_value=10200.0,
        ),
        BacktestTrade(
            trade=Trade(
                id="2", symbol="BTC/USDT", side=OrderSide.SELL,
                amount=0.01, price=67000.0,
            ),
            signal=Signal(
                symbol="BTC/USDT", direction="SELL",
                confidence=0.7, strategy_name="rsi", reason="Overbought",
            ),
            portfolio_value=10800.0,
        ),
        BacktestTrade(
            trade=Trade(
                id="3", symbol="BTC/USDT", side=OrderSide.BUY,
                amount=0.01, price=66000.0,
            ),
            signal=Signal(
                symbol="BTC/USDT", direction="BUY",
                confidence=0.6, strategy_name="macd", reason="Crossover",
            ),
            portfolio_value=10900.0,
        ),
        BacktestTrade(
            trade=Trade(
                id="4", symbol="BTC/USDT", side=OrderSide.SELL,
                amount=0.01, price=65500.0,
            ),
            signal=Signal(
                symbol="BTC/USDT", direction="SELL",
                confidence=0.5, strategy_name="macd", reason="Bearish",
            ),
            portfolio_value=11000.0,
        ),
    ]
    result.signals = [bt.signal for bt in result.trades]
    return result


class TestMaxDrawdown:
    def test_no_drawdown(self):
        assert _max_drawdown([100, 110, 120, 130]) == 0.0

    def test_known_drawdown(self):
        dd = _max_drawdown([100, 120, 90, 110])
        assert dd == pytest.approx(25.0)

    def test_single_value(self):
        assert _max_drawdown([100]) == 0.0

    def test_empty(self):
        assert _max_drawdown([]) == 0.0


class TestPeriodReturns:
    def test_basic_returns(self):
        returns = _period_returns([100, 110, 105])
        assert len(returns) == 2
        assert returns[0] == pytest.approx(0.1)
        assert returns[1] == pytest.approx(-0.04545, rel=0.01)


class TestSharpeRatio:
    def test_positive_sharpe(self):
        returns = [0.01, 0.02, 0.015, 0.005, 0.01]
        sharpe = _sharpe_ratio(returns)
        assert sharpe > 0

    def test_zero_std_returns_zero(self):
        returns = [0.01, 0.01, 0.01]
        assert _sharpe_ratio(returns) == 0.0


class TestGenerateReport:
    def test_basic_report(self):
        result = _simple_result()
        report = generate_report(result)

        assert report.initial_value == 10000.0
        assert report.final_value == 11000.0
        assert report.total_return_pct == pytest.approx(10.0)
        assert report.max_drawdown_pct > 0

    def test_report_with_trades(self):
        result = _result_with_trades()
        report = generate_report(result)

        assert report.total_trades == 2
        assert report.winning_trades == 1
        assert report.losing_trades == 1
        assert report.win_rate == pytest.approx(50.0)

    def test_to_dict(self):
        result = _simple_result()
        report = generate_report(result)
        d = report.to_dict()

        assert "initial_value" in d
        assert "sharpe_ratio" in d
        assert d["total_return_pct"] == pytest.approx(10.0)

    def test_strategy_stats(self):
        result = _result_with_trades()
        report = generate_report(result)

        assert "rsi" in report.strategy_stats
        assert report.strategy_stats["rsi"]["BUY"] == 1
        assert report.strategy_stats["rsi"]["SELL"] == 1

    def test_print_report_no_error(self, capsys):
        result = _result_with_trades()
        report = generate_report(result)
        report.print_report()

        captured = capsys.readouterr()
        assert "BACKTEST REPORT" in captured.out
        assert "10.00%" in captured.out
