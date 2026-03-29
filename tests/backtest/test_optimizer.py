"""Tests for the Optuna-based backtest parameter optimizer."""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from backend.backtest.optimizer import (
    PARAM_SPACES,
    OptimizationResult,
    TrialResult,
    _build_configs_from_params,
    run_optimization,
)


def _sample_ohlcv(n: int = 100, start_price: float = 100.0) -> pd.DataFrame:
    rows = []
    price = start_price
    for i in range(n):
        ts = datetime(2025, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i)
        price += (i % 5 - 2) * 0.3
        rows.append({
            "timestamp": ts,
            "open": price - 0.2,
            "high": price + 2.0,
            "low": price - 2.0,
            "close": price,
            "volume": 200.0 + (i % 3) * 50,
        })
    return pd.DataFrame(rows)


class TestBuildConfigs:
    def test_builds_strategies_and_risk(self):
        params = {
            "rsi_period": 10,
            "stop_loss_pct": 0.05,
            "atr_stop_multiplier": 2.5,
        }
        built = _build_configs_from_params(
            params, ["rsi", "macd"], 0.001, 0.0005,
        )
        assert len(built.strategies) == 2
        assert built.risk.stop_loss_pct == 0.05
        assert built.risk.atr_stop_multiplier == 2.5
        assert built.fee == 0.001

    def test_uses_defaults_for_missing_params(self):
        built = _build_configs_from_params(
            {}, ["rsi"], 0.001, 0.0005,
        )
        assert len(built.strategies) == 1
        assert built.risk.max_position_pct == 0.10
        assert built.risk.stop_loss_pct == 0.03

    def test_builds_ema_strategy(self):
        built = _build_configs_from_params(
            {"ema_fast_period": 7, "ema_slow_period": 25},
            ["ema"], 0.001, 0.0005,
        )
        assert len(built.strategies) == 1
        assert built.strategies[0].name == "ema"

    def test_aggregator_params(self):
        built = _build_configs_from_params(
            {"min_agreement": 3, "hold_opposition": 0.2},
            ["rsi"], 0.001, 0.0005,
        )
        assert built.min_agreement == 3
        assert built.hold_opposition == 0.2


class TestRunOptimization:
    @pytest.mark.asyncio
    async def test_single_trial(self):
        ohlcv = _sample_ohlcv(80)
        result = await run_optimization(
            ohlcv=ohlcv,
            symbol="BTC/USDT",
            balance=10000.0,
            strategy_names=["rsi"],
            tune_groups=["risk"],
            n_trials=1,
            scoring="sharpe",
            validate_best=False,
        )
        assert isinstance(result, OptimizationResult)
        assert len(result.trials) == 1
        assert result.best_params
        assert "stop_loss_pct" in result.best_params
        assert result.validation is None

    @pytest.mark.asyncio
    async def test_multiple_trials_sorted(self):
        ohlcv = _sample_ohlcv(80)
        result = await run_optimization(
            ohlcv=ohlcv,
            symbol="BTC/USDT",
            balance=10000.0,
            strategy_names=["rsi", "macd"],
            tune_groups=["atr"],
            n_trials=5,
            scoring="return",
            validate_best=False,
        )
        assert len(result.trials) == 5
        scores = [t.score for t in result.trials]
        assert scores == sorted(scores, reverse=True)
        assert result.best_score == scores[0]

    @pytest.mark.asyncio
    async def test_with_walk_forward_validation(self):
        ohlcv = _sample_ohlcv(120)
        result = await run_optimization(
            ohlcv=ohlcv,
            symbol="BTC/USDT",
            balance=10000.0,
            strategy_names=["rsi"],
            tune_groups=["risk"],
            n_trials=2,
            scoring="sharpe",
            validate_best=True,
        )
        assert result.validation is not None
        assert "folds" in result.validation
        assert "aggregate_oos" in result.validation

    @pytest.mark.asyncio
    async def test_invalid_tune_group_raises(self):
        ohlcv = _sample_ohlcv(80)
        with pytest.raises(ValueError, match="No valid tune groups"):
            await run_optimization(
                ohlcv=ohlcv,
                symbol="BTC/USDT",
                balance=10000.0,
                strategy_names=["rsi"],
                tune_groups=["nonexistent"],
                n_trials=1,
                validate_best=False,
            )

    @pytest.mark.asyncio
    async def test_all_tune_groups(self):
        ohlcv = _sample_ohlcv(80)
        result = await run_optimization(
            ohlcv=ohlcv,
            symbol="BTC/USDT",
            balance=10000.0,
            strategy_names=["rsi", "macd", "bollinger"],
            tune_groups=list(PARAM_SPACES.keys()),
            n_trials=3,
            scoring="sharpe",
            validate_best=False,
        )
        assert len(result.trials) == 3
        first_params = result.trials[0].params
        assert "rsi_period" in first_params
        assert "atr_stop_multiplier" in first_params
        assert "cooldown_candles" in first_params

    @pytest.mark.asyncio
    async def test_calmar_scoring(self):
        ohlcv = _sample_ohlcv(80)
        result = await run_optimization(
            ohlcv=ohlcv,
            symbol="BTC/USDT",
            balance=10000.0,
            strategy_names=["rsi"],
            tune_groups=["risk"],
            n_trials=2,
            scoring="calmar",
            validate_best=False,
        )
        assert len(result.trials) == 2


class TestTrialResultSerialization:
    def test_to_dict(self):
        tr = TrialResult(
            number=0,
            params={"stop_loss_pct": 0.05},
            score=1.234,
            metrics={"sharpe": 1.234, "return_pct": 5.0},
        )
        d = tr.to_dict()
        assert d["number"] == 0
        assert d["score"] == 1.234
        assert d["params"]["stop_loss_pct"] == 0.05

    def test_optimization_result_to_dict(self):
        result = OptimizationResult(
            trials=[],
            best_params={"x": 1},
            best_metrics={"sharpe": 2.0},
            best_score=2.0,
        )
        d = result.to_dict()
        assert d["best_score"] == 2.0
        assert d["best_params"] == {"x": 1}
        assert d["validation"] is None
