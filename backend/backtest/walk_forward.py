"""Walk-forward validation: split data into sequential train/test folds."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from backend.backtest.ai_filter import AIFilterConfig
from backend.backtest.engine import BacktestEngine, EngineConfig
from backend.backtest.exchange import BacktestExchange
from backend.backtest.report import BacktestReport, generate_report
from backend.config import RiskConfig
from backend.core.logger import get_logger
from backend.strategies.base import StrategyBase

logger = get_logger("walk_forward")


@dataclass(frozen=True)
class WalkForwardConfig:
    n_folds: int = 3
    train_pct: float = 0.7
    step_type: str = "rolling"


@dataclass
class FoldResult:
    fold_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_report: dict = field(default_factory=dict)
    test_report: dict = field(default_factory=dict)


@dataclass
class WalkForwardResult:
    folds: list[FoldResult] = field(default_factory=list)
    aggregate_oos: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "folds": [
                {
                    "fold_index": f.fold_index,
                    "train_start": f.train_start,
                    "train_end": f.train_end,
                    "test_start": f.test_start,
                    "test_end": f.test_end,
                    "train_report": f.train_report,
                    "test_report": f.test_report,
                }
                for f in self.folds
            ],
            "aggregate_oos": self.aggregate_oos,
        }


def split_folds(
    ohlcv: pd.DataFrame,
    config: WalkForwardConfig,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Split OHLCV into sequential train/test pairs.

    Rolling: each fold is a contiguous chunk of data.
    Expanding: train set grows with each fold, test stays the same size.
    """
    n = len(ohlcv)
    n_folds = max(1, config.n_folds)
    train_pct = max(0.1, min(0.95, config.train_pct))

    if config.step_type == "expanding":
        test_size = int(n * (1.0 - train_pct) / n_folds)
        test_size = max(test_size, 10)
        folds = []
        for i in range(n_folds):
            test_end = n - (n_folds - 1 - i) * test_size
            test_start = test_end - test_size
            train_df = ohlcv.iloc[:test_start].copy().reset_index(drop=True)
            test_df = ohlcv.iloc[test_start:test_end].copy().reset_index(drop=True)
            if len(train_df) >= 30 and len(test_df) >= 5:
                folds.append((train_df, test_df))
        return folds

    fold_size = n // n_folds
    if fold_size < 40:
        fold_size = n
        n_folds = 1

    folds = []
    for i in range(n_folds):
        start = i * fold_size
        end = start + fold_size if i < n_folds - 1 else n
        chunk = ohlcv.iloc[start:end]
        split_idx = int(len(chunk) * train_pct)
        train_df = chunk.iloc[:split_idx].copy().reset_index(drop=True)
        test_df = chunk.iloc[split_idx:].copy().reset_index(drop=True)
        if len(train_df) >= 30 and len(test_df) >= 5:
            folds.append((train_df, test_df))
    return folds


async def _run_single_backtest(
    ohlcv: pd.DataFrame,
    symbol: str,
    balance: float,
    strategies: list[StrategyBase],
    risk_config: RiskConfig,
    ai_filter_config: AIFilterConfig,
    engine_config: EngineConfig,
    fee_rate: float,
    slippage_rate: float,
    strategy_weights: dict[str, float] | None = None,
    min_agreement: int = 1,
    hold_opposition: float = 0.0,
) -> BacktestReport:
    exchange = BacktestExchange(
        ohlcv=ohlcv,
        initial_balance_usdt=balance,
        symbol=symbol,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
    )
    engine = BacktestEngine(
        exchange=exchange,
        strategies=strategies,
        symbol=symbol,
        risk_config=risk_config,
        ai_filter_config=ai_filter_config,
        engine_config=engine_config,
        strategy_weights=strategy_weights,
        min_agreement=min_agreement,
        hold_opposition=hold_opposition,
    )
    result = await engine.run()
    return generate_report(result)


async def run_walk_forward(
    ohlcv: pd.DataFrame,
    symbol: str,
    balance: float,
    strategies: list[StrategyBase],
    risk_config: RiskConfig,
    ai_filter_config: AIFilterConfig,
    engine_config: EngineConfig,
    wf_config: WalkForwardConfig,
    fee_rate: float = 0.001,
    slippage_rate: float = 0.0005,
    strategy_weights: dict[str, float] | None = None,
    min_agreement: int = 1,
    hold_opposition: float = 0.0,
) -> WalkForwardResult:
    """Run walk-forward validation across all folds."""
    folds_data = split_folds(ohlcv, wf_config)
    result = WalkForwardResult()

    logger.info(
        "Walk-forward started",
        n_folds=len(folds_data),
        total_candles=len(ohlcv),
        step_type=wf_config.step_type,
    )

    oos_returns: list[float] = []
    oos_sharpes: list[float] = []
    oos_drawdowns: list[float] = []
    oos_win_rates: list[float] = []

    for i, (train_df, test_df) in enumerate(folds_data):
        train_start = str(train_df["timestamp"].iloc[0])
        train_end = str(train_df["timestamp"].iloc[-1])
        test_start = str(test_df["timestamp"].iloc[0])
        test_end = str(test_df["timestamp"].iloc[-1])

        logger.info(
            "Running fold",
            fold=i + 1,
            train_candles=len(train_df),
            test_candles=len(test_df),
        )

        train_report = await _run_single_backtest(
            train_df, symbol, balance, strategies,
            risk_config, ai_filter_config, engine_config,
            fee_rate, slippage_rate, strategy_weights,
            min_agreement, hold_opposition,
        )
        test_report = await _run_single_backtest(
            test_df, symbol, balance, strategies,
            risk_config, ai_filter_config, engine_config,
            fee_rate, slippage_rate, strategy_weights,
            min_agreement, hold_opposition,
        )

        fold = FoldResult(
            fold_index=i + 1,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            train_report=train_report.to_dict(),
            test_report=test_report.to_dict(),
        )
        result.folds.append(fold)

        oos_returns.append(test_report.total_return_pct)
        oos_sharpes.append(test_report.sharpe_ratio)
        oos_drawdowns.append(test_report.max_drawdown_pct)
        oos_win_rates.append(test_report.win_rate)

    if oos_returns:
        result.aggregate_oos = {
            "avg_return_pct": sum(oos_returns) / len(oos_returns),
            "avg_sharpe": sum(oos_sharpes) / len(oos_sharpes),
            "avg_max_drawdown_pct": sum(oos_drawdowns) / len(oos_drawdowns),
            "avg_win_rate": sum(oos_win_rates) / len(oos_win_rates),
            "worst_return_pct": min(oos_returns),
            "best_return_pct": max(oos_returns),
            "n_folds": len(oos_returns),
        }

    logger.info(
        "Walk-forward completed",
        folds=len(result.folds),
        avg_oos_return=result.aggregate_oos.get("avg_return_pct", 0),
    )

    return result
