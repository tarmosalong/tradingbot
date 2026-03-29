from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from backend.backtest.ai_filter import AIFilterConfig
from backend.backtest.engine import EngineConfig
from backend.backtest.walk_forward import (
    WalkForwardConfig,
    run_walk_forward,
    split_folds,
)
from backend.config import RiskConfig


def _make_ohlcv(n: int = 200, base_price: float = 100.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data with a gentle uptrend."""
    rows = []
    price = base_price
    start = datetime(2025, 1, 1, tzinfo=UTC)
    for i in range(n):
        drift = 0.002 if i % 3 != 0 else -0.001
        price *= 1 + drift
        rows.append({
            "timestamp": start + timedelta(hours=i),
            "open": price * 0.999,
            "high": price * 1.005,
            "low": price * 0.995,
            "close": price,
            "volume": 100 + i * 0.5,
        })
    return pd.DataFrame(rows)


class TestSplitFolds:
    def test_rolling_creates_correct_number_of_folds(self):
        ohlcv = _make_ohlcv(300)
        config = WalkForwardConfig(n_folds=3, train_pct=0.7, step_type="rolling")
        folds = split_folds(ohlcv, config)
        assert len(folds) == 3

    def test_train_test_sizes_match_pct(self):
        ohlcv = _make_ohlcv(300)
        config = WalkForwardConfig(n_folds=3, train_pct=0.7, step_type="rolling")
        folds = split_folds(ohlcv, config)
        for train, test in folds:
            total = len(train) + len(test)
            assert abs(len(train) / total - 0.7) < 0.05

    def test_no_overlap_between_folds(self):
        ohlcv = _make_ohlcv(300)
        config = WalkForwardConfig(n_folds=3, train_pct=0.7, step_type="rolling")
        folds = split_folds(ohlcv, config)
        for i in range(len(folds) - 1):
            _, test_prev = folds[i]
            train_next, _ = folds[i + 1]
            last_prev = test_prev["timestamp"].iloc[-1]
            first_next = train_next["timestamp"].iloc[0]
            assert first_next > last_prev or first_next == last_prev

    def test_expanding_train_grows(self):
        ohlcv = _make_ohlcv(300)
        config = WalkForwardConfig(n_folds=3, train_pct=0.7, step_type="expanding")
        folds = split_folds(ohlcv, config)
        if len(folds) >= 2:
            assert len(folds[1][0]) >= len(folds[0][0])

    def test_single_fold(self):
        ohlcv = _make_ohlcv(100)
        config = WalkForwardConfig(n_folds=1, train_pct=0.7)
        folds = split_folds(ohlcv, config)
        assert len(folds) == 1

    def test_too_small_data_reduces_folds(self):
        ohlcv = _make_ohlcv(50)
        config = WalkForwardConfig(n_folds=5, train_pct=0.7)
        folds = split_folds(ohlcv, config)
        assert len(folds) >= 1

    def test_empty_data_returns_no_folds(self):
        ohlcv = _make_ohlcv(5)
        config = WalkForwardConfig(n_folds=3, train_pct=0.7)
        folds = split_folds(ohlcv, config)
        assert len(folds) == 0


class TestRunWalkForward:
    @pytest.mark.asyncio
    async def test_walk_forward_runs_and_returns_folds(self):
        ohlcv = _make_ohlcv(200)
        from backend.config import RSIConfig
        from backend.strategies.technical import RSIStrategy

        strategies = [RSIStrategy(RSIConfig())]
        wf_config = WalkForwardConfig(n_folds=2, train_pct=0.7)

        result = await run_walk_forward(
            ohlcv=ohlcv,
            symbol="BTC/USDT",
            balance=10000.0,
            strategies=strategies,
            risk_config=RiskConfig(),
            ai_filter_config=AIFilterConfig(),
            engine_config=EngineConfig(),
            wf_config=wf_config,
        )

        assert len(result.folds) == 2
        assert result.aggregate_oos["n_folds"] == 2
        assert "avg_return_pct" in result.aggregate_oos
        assert "avg_sharpe" in result.aggregate_oos

    @pytest.mark.asyncio
    async def test_fold_results_have_train_and_test(self):
        ohlcv = _make_ohlcv(200)
        from backend.config import RSIConfig
        from backend.strategies.technical import RSIStrategy

        strategies = [RSIStrategy(RSIConfig())]
        wf_config = WalkForwardConfig(n_folds=2, train_pct=0.7)

        result = await run_walk_forward(
            ohlcv=ohlcv,
            symbol="BTC/USDT",
            balance=10000.0,
            strategies=strategies,
            risk_config=RiskConfig(),
            ai_filter_config=AIFilterConfig(),
            engine_config=EngineConfig(),
            wf_config=wf_config,
        )

        for fold in result.folds:
            assert "total_return_pct" in fold.train_report
            assert "total_return_pct" in fold.test_report
            assert fold.fold_index >= 1

    @pytest.mark.asyncio
    async def test_to_dict_serializable(self):
        ohlcv = _make_ohlcv(200)
        from backend.config import RSIConfig
        from backend.strategies.technical import RSIStrategy

        strategies = [RSIStrategy(RSIConfig())]
        wf_config = WalkForwardConfig(n_folds=2, train_pct=0.7)

        result = await run_walk_forward(
            ohlcv=ohlcv,
            symbol="BTC/USDT",
            balance=10000.0,
            strategies=strategies,
            risk_config=RiskConfig(),
            ai_filter_config=AIFilterConfig(),
            engine_config=EngineConfig(),
            wf_config=wf_config,
        )

        d = result.to_dict()
        assert "folds" in d
        assert "aggregate_oos" in d
        assert len(d["folds"]) == 2
