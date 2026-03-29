"""Optuna-based parameter optimizer for backtest strategies."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import optuna
import pandas as pd

from backend.backtest.ai_filter import AIFilterConfig
from backend.backtest.engine import BacktestEngine, EngineConfig
from backend.backtest.exchange import BacktestExchange
from backend.backtest.report import generate_report
from backend.backtest.walk_forward import WalkForwardConfig, run_walk_forward
from backend.config import (
    BollingerConfig,
    MACDConfig,
    RiskConfig,
    RSIConfig,
)
from backend.core.logger import get_logger
from backend.strategies import STRATEGY_REGISTRY
from backend.strategies.base import StrategyBase

logger = get_logger("optimizer")

PARAM_SPACES: dict[str, dict[str, dict]] = {
    "strategy": {
        "rsi_period": {"type": "int", "low": 7, "high": 21},
        "rsi_oversold": {"type": "int", "low": 20, "high": 40},
        "rsi_overbought": {"type": "int", "low": 60, "high": 80},
        "macd_fast": {"type": "int", "low": 5, "high": 16},
        "macd_slow": {"type": "int", "low": 20, "high": 40},
        "macd_signal": {"type": "int", "low": 4, "high": 12},
        "boll_period": {"type": "int", "low": 10, "high": 30},
        "boll_std_dev": {"type": "float", "low": 1.5, "high": 3.0},
    },
    "risk": {
        "stop_loss_pct": {"type": "float", "low": 0.01, "high": 0.08},
        "trailing_stop_pct": {"type": "float", "low": 0.01, "high": 0.05},
        "max_position_pct": {"type": "float", "low": 0.05, "high": 0.25},
        "min_confidence": {"type": "float", "low": 0.2, "high": 0.7},
        "risk_per_trade_pct": {"type": "float", "low": 0.005, "high": 0.03},
    },
    "atr": {
        "atr_stop_multiplier": {"type": "float", "low": 1.0, "high": 3.5},
        "atr_tp_multiplier": {"type": "float", "low": 2.0, "high": 6.0},
        "atr_trailing_multiplier": {"type": "float", "low": 0.8, "high": 3.0},
        "partial_tp_ratio": {"type": "float", "low": 0.3, "high": 0.7},
    },
    "guards": {
        "volume_min_multiplier": {"type": "float", "low": 0.0, "high": 2.0},
        "ema_trend_period": {"type": "int", "low": 20, "high": 100},
        "ema_trend_enabled": {"type": "categorical", "choices": [True, False]},
    },
    "engine": {
        "cooldown_candles": {"type": "int", "low": 0, "high": 10},
        "use_dynamic_sizing": {
            "type": "categorical",
            "choices": [True, False],
        },
    },
}

def _score_sharpe(r) -> float:
    if math.isfinite(r.sharpe_ratio):
        return r.sharpe_ratio
    return r.total_return_pct / 100


def _score_calmar(r) -> float:
    if r.max_drawdown_pct > 0.01:
        return r.total_return_pct / r.max_drawdown_pct
    return r.total_return_pct


SCORING_FUNCTIONS = {
    "sharpe": _score_sharpe,
    "return": lambda r: r.total_return_pct,
    "calmar": _score_calmar,
}


@dataclass
class TrialResult:
    number: int
    params: dict
    score: float
    metrics: dict

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "params": self.params,
            "score": round(self.score, 4),
            "metrics": self.metrics,
        }


@dataclass
class OptimizationResult:
    trials: list[TrialResult] = field(default_factory=list)
    best_params: dict = field(default_factory=dict)
    best_metrics: dict = field(default_factory=dict)
    best_score: float = 0.0
    validation: dict | None = None

    def to_dict(self) -> dict:
        return {
            "trials": [t.to_dict() for t in self.trials],
            "best_params": self.best_params,
            "best_metrics": self.best_metrics,
            "best_score": round(self.best_score, 4),
            "validation": self.validation,
        }


def _suggest_param(trial: optuna.Trial, name: str, spec: dict):
    if spec["type"] == "int":
        return trial.suggest_int(name, spec["low"], spec["high"])
    if spec["type"] == "float":
        return trial.suggest_float(name, spec["low"], spec["high"])
    if spec["type"] == "categorical":
        return trial.suggest_categorical(name, spec["choices"])
    raise ValueError(f"Unknown param type: {spec['type']}")


def _build_configs_from_params(
    params: dict,
    strategy_names: list[str],
    base_fee: float,
    base_slippage: float,
) -> tuple[
    list[StrategyBase], RiskConfig, EngineConfig, float, float,
]:
    rsi_cfg = RSIConfig(
        period=params.get("rsi_period", 14),
        oversold=params.get("rsi_oversold", 30),
        overbought=params.get("rsi_overbought", 70),
    )
    macd_cfg = MACDConfig(
        fast=params.get("macd_fast", 12),
        slow=params.get("macd_slow", 26),
        signal=params.get("macd_signal", 9),
    )
    boll_cfg = BollingerConfig(
        period=params.get("boll_period", 20),
        std_dev=params.get("boll_std_dev", 2.0),
    )
    config_map = {"rsi": rsi_cfg, "macd": macd_cfg, "bollinger": boll_cfg}

    strats = []
    for name in strategy_names:
        cls = STRATEGY_REGISTRY.get(name)
        if cls:
            cfg = config_map.get(name)
            strats.append(cls(cfg) if cfg else cls())

    risk_config = RiskConfig(
        max_position_pct=params.get("max_position_pct", 0.10),
        stop_loss_pct=params.get("stop_loss_pct", 0.03),
        trailing_stop_pct=params.get("trailing_stop_pct", 0.02),
        max_drawdown_pct=params.get("max_drawdown_pct", 0.15),
        daily_loss_limit_pct=params.get("daily_loss_limit_pct", 0.05),
        max_single_order_usdt=params.get("max_single_order_usdt", 1000.0),
        min_confidence=params.get("min_confidence", 0.4),
        atr_stop_multiplier=params.get("atr_stop_multiplier", 2.0),
        atr_tp_multiplier=params.get("atr_tp_multiplier", 3.0),
        atr_trailing_multiplier=params.get("atr_trailing_multiplier", 1.5),
        volume_min_multiplier=params.get("volume_min_multiplier", 1.2),
        ema_trend_period=params.get("ema_trend_period", 50),
        ema_trend_enabled=params.get("ema_trend_enabled", True),
        risk_per_trade_pct=params.get("risk_per_trade_pct", 0.01),
        partial_tp_ratio=params.get("partial_tp_ratio", 0.5),
    )

    engine_cfg = EngineConfig(
        cooldown_candles=params.get("cooldown_candles", 0),
        use_dynamic_sizing=params.get("use_dynamic_sizing", False),
    )

    return strats, risk_config, engine_cfg, base_fee, base_slippage


async def run_optimization(
    ohlcv: pd.DataFrame,
    symbol: str,
    balance: float,
    strategy_names: list[str],
    tune_groups: list[str],
    n_trials: int = 50,
    scoring: str = "sharpe",
    fee_rate: float = 0.001,
    slippage_rate: float = 0.0005,
    validate_best: bool = True,
) -> OptimizationResult:
    """Run Optuna optimization over the given parameter groups."""
    score_fn = SCORING_FUNCTIONS.get(scoring, SCORING_FUNCTIONS["sharpe"])

    active_spaces: dict[str, dict] = {}
    for group in tune_groups:
        if group in PARAM_SPACES:
            active_spaces.update(PARAM_SPACES[group])

    if not active_spaces:
        raise ValueError(f"No valid tune groups: {tune_groups}")

    trial_results: list[TrialResult] = []

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")

    logger.info(
        "Optimization started",
        symbol=symbol,
        n_trials=n_trials,
        scoring=scoring,
        tune_groups=tune_groups,
        params=list(active_spaces.keys()),
    )

    async def _objective_wrapper(trial: optuna.Trial) -> float:
        params = {}
        for pname, spec in active_spaces.items():
            params[pname] = _suggest_param(trial, pname, spec)

        strats, risk_cfg, engine_cfg, fee, slip = _build_configs_from_params(
            params, strategy_names, fee_rate, slippage_rate,
        )

        if not strats:
            return float("-inf")

        exchange = BacktestExchange(
            ohlcv=ohlcv.copy(),
            initial_balance_usdt=balance,
            symbol=symbol,
            fee_rate=fee,
            slippage_rate=slip,
        )
        engine = BacktestEngine(
            exchange=exchange,
            strategies=strats,
            symbol=symbol,
            risk_config=risk_cfg,
            engine_config=engine_cfg,
        )
        result = await engine.run()
        report = generate_report(result)

        score = score_fn(report)
        if not math.isfinite(score):
            score = -999.0

        metrics = {
            "sharpe": round(report.sharpe_ratio, 4),
            "return_pct": round(report.total_return_pct, 2),
            "max_drawdown_pct": round(report.max_drawdown_pct, 2),
            "win_rate": round(report.win_rate, 1),
            "total_trades": report.total_trades,
            "sortino": round(report.sortino_ratio, 4),
        }

        trial_results.append(TrialResult(
            number=trial.number,
            params=params,
            score=score,
            metrics=metrics,
        ))

        return score

    for i in range(n_trials):
        trial = study.ask()
        value = await _objective_wrapper(trial)
        study.tell(trial, value)

        if (i + 1) % 10 == 0:
            logger.info(
                "Optimization progress",
                completed=i + 1,
                total=n_trials,
                best_so_far=round(study.best_value, 4),
            )

    trial_results.sort(key=lambda t: t.score, reverse=True)

    best = trial_results[0] if trial_results else None
    opt_result = OptimizationResult(
        trials=trial_results,
        best_params=best.params if best else {},
        best_metrics=best.metrics if best else {},
        best_score=best.score if best else 0.0,
    )

    if validate_best and best:
        logger.info("Running walk-forward validation on best params")
        strats, risk_cfg, engine_cfg, fee, slip = _build_configs_from_params(
            best.params, strategy_names, fee_rate, slippage_rate,
        )
        wf_result = await run_walk_forward(
            ohlcv=ohlcv,
            symbol=symbol,
            balance=balance,
            strategies=strats,
            risk_config=risk_cfg,
            ai_filter_config=AIFilterConfig(),
            engine_config=engine_cfg,
            wf_config=WalkForwardConfig(n_folds=3, train_pct=0.7),
            fee_rate=fee,
            slippage_rate=slip,
        )
        opt_result.validation = wf_result.to_dict()

    logger.info(
        "Optimization completed",
        best_score=round(opt_result.best_score, 4),
        best_params=opt_result.best_params,
    )

    return opt_result
