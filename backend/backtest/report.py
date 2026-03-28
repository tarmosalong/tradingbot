from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.backtest.engine import BacktestResult
from backend.core.logger import get_logger

logger = get_logger("backtest_report")

TRADING_DAYS_PER_YEAR = 365
RISK_FREE_RATE = 0.04


@dataclass
class BacktestReport:
    initial_value: float = 0.0
    final_value: float = 0.0
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_trade_pnl: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    total_candles: int = 0
    strategy_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    ai_filter_stats: dict[str, int] = field(default_factory=dict)

    def print_report(self) -> None:
        lines = [
            "",
            "=" * 60,
            "  BACKTEST REPORT",
            "=" * 60,
            "",
            f"  Initial Value:       ${self.initial_value:,.2f}",
            f"  Final Value:         ${self.final_value:,.2f}",
            f"  Total Return:        {self.total_return_pct:+.2f}%",
            f"  Annualized Return:   {self.annualized_return_pct:+.2f}%",
            "",
            "  --- Risk Metrics ---",
            f"  Max Drawdown:        {self.max_drawdown_pct:.2f}%",
            f"  Sharpe Ratio:        {self.sharpe_ratio:.3f}",
            f"  Sortino Ratio:       {self.sortino_ratio:.3f}",
            "",
            "  --- Trade Statistics ---",
            f"  Total Trades:        {self.total_trades}",
            f"  Winning Trades:      {self.winning_trades}",
            f"  Losing Trades:       {self.losing_trades}",
            f"  Win Rate:            {self.win_rate:.1f}%",
            f"  Avg Trade P&L:       ${self.avg_trade_pnl:+.2f}",
            f"  Best Trade:          ${self.best_trade_pnl:+.2f}",
            f"  Worst Trade:         ${self.worst_trade_pnl:+.2f}",
            "",
        ]

        if self.strategy_stats:
            lines.append("  --- Per-Strategy Signals ---")
            for name, stats in self.strategy_stats.items():
                lines.append(
                    f"  {name:>15s}: "
                    f"BUY={stats.get('BUY', 0)} "
                    f"SELL={stats.get('SELL', 0)} "
                    f"HOLD={stats.get('HOLD', 0)}"
                )
            lines.append("")

        if self.ai_filter_stats and self.ai_filter_stats.get("signals_reviewed", 0) > 0:
            s = self.ai_filter_stats
            lines.append("  --- AI Filter ---")
            lines.append(f"  Signals reviewed:    {s.get('signals_reviewed', 0)}")
            lines.append(f"  Blocked:             {s.get('signals_blocked', 0)}")
            lines.append(f"  Reduced:             {s.get('signals_reduced', 0)}")
            lines.append(f"  Boosted:             {s.get('signals_boosted', 0)}")
            lines.append(f"  Crash detections:    {s.get('crash_detections', 0)}")
            lines.append(f"  Volatility spikes:   {s.get('volatility_detections', 0)}")
            lines.append(f"  Volume spikes:       {s.get('volume_spike_detections', 0)}")
            lines.append(f"  Recovery detections: {s.get('recovery_detections', 0)}")
            lines.append("")

        lines.append("=" * 60)
        print("\n".join(lines))

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_value": self.initial_value,
            "final_value": self.final_value,
            "total_return_pct": self.total_return_pct,
            "annualized_return_pct": self.annualized_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "avg_trade_pnl": self.avg_trade_pnl,
            "best_trade_pnl": self.best_trade_pnl,
            "worst_trade_pnl": self.worst_trade_pnl,
            "total_candles": self.total_candles,
            "strategy_stats": self.strategy_stats,
            "ai_filter_stats": self.ai_filter_stats,
        }


def generate_report(result: BacktestResult) -> BacktestReport:
    """Analyze a BacktestResult and produce a BacktestReport."""
    report = BacktestReport(
        initial_value=result.initial_balance,
        final_value=result.final_balance,
        total_candles=len(result.equity_curve),
    )

    if result.initial_balance > 0:
        report.total_return_pct = (
            (result.final_balance / result.initial_balance) - 1
        ) * 100

    report.max_drawdown_pct = _max_drawdown(result.equity_curve)

    returns = _period_returns(result.equity_curve)
    if len(returns) > 1:
        report.sharpe_ratio = _sharpe_ratio(returns)
        report.sortino_ratio = _sortino_ratio(returns)
        report.annualized_return_pct = _annualized_return(
            result.initial_balance, result.final_balance, len(returns)
        )

    trade_pnls = _compute_trade_pnls(result)
    report.total_trades = len(trade_pnls)

    if trade_pnls:
        report.winning_trades = sum(1 for p in trade_pnls if p > 0)
        report.losing_trades = sum(1 for p in trade_pnls if p <= 0)
        report.win_rate = (
            report.winning_trades / report.total_trades * 100
        )
        report.avg_trade_pnl = sum(trade_pnls) / len(trade_pnls)
        report.best_trade_pnl = max(trade_pnls)
        report.worst_trade_pnl = min(trade_pnls)

    report.strategy_stats = _strategy_stats(result)
    report.ai_filter_stats = result.ai_filter_stats

    return report


def _max_drawdown(equity_curve: list[float]) -> float:
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100


def _period_returns(equity_curve: list[float]) -> list[float]:
    if len(equity_curve) < 2:
        return []
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] > 0:
            r = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
            returns.append(r)
    return returns


def _sharpe_ratio(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    arr = np.array(returns)
    mean_r = float(np.mean(arr))
    std_r = float(np.std(arr, ddof=1))
    if std_r == 0:
        return 0.0
    rf_per_period = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
    return (mean_r - rf_per_period) / std_r * math.sqrt(TRADING_DAYS_PER_YEAR)


def _sortino_ratio(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    arr = np.array(returns)
    mean_r = float(np.mean(arr))
    downside = arr[arr < 0]
    if len(downside) == 0:
        return 0.0
    downside_std = float(np.std(downside, ddof=1))
    if downside_std == 0:
        return 0.0
    rf_per_period = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
    return (mean_r - rf_per_period) / downside_std * math.sqrt(TRADING_DAYS_PER_YEAR)


def _annualized_return(
    initial: float, final: float, num_periods: int
) -> float:
    if initial <= 0 or num_periods <= 0:
        return 0.0
    total_return = final / initial
    periods_per_year = TRADING_DAYS_PER_YEAR
    if num_periods < periods_per_year:
        periods_per_year = num_periods
    annualized = total_return ** (periods_per_year / num_periods) - 1
    return annualized * 100


def _compute_trade_pnls(result: BacktestResult) -> list[float]:
    """Estimate P&L for each trade pair (buy then sell)."""
    pnls: list[float] = []
    buys: list[float] = []

    for bt in result.trades:
        t = bt.trade
        if t.side == "BUY":
            buys.append(t.price * t.amount)
        elif t.side == "SELL" and buys:
            cost = buys.pop(0)
            revenue = t.price * t.amount
            pnls.append(revenue - cost)

    return pnls


def _strategy_stats(result: BacktestResult) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for signal in result.signals:
        name = signal.strategy_name
        if name not in stats:
            stats[name] = {"BUY": 0, "SELL": 0, "HOLD": 0}
        direction = signal.direction
        if direction in stats[name]:
            stats[name][direction] += 1
    return stats
