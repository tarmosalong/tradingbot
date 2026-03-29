from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ExchangeConfig:
    name: str = "binance"
    sandbox: bool = False
    rate_limit_ms: int = 100


@dataclass(frozen=True)
class PaperTradingConfig:
    initial_balance_usdt: float = 10_000.0


@dataclass(frozen=True)
class RSIConfig:
    period: int = 14
    oversold: int = 30
    overbought: int = 70


@dataclass(frozen=True)
class MACDConfig:
    fast: int = 12
    slow: int = 26
    signal: int = 9


@dataclass(frozen=True)
class BollingerConfig:
    period: int = 20
    std_dev: float = 2.0


@dataclass(frozen=True)
class EMAConfig:
    fast_period: int = 9
    slow_period: int = 21


def _default_trending_weights() -> dict[str, float]:
    return {"ema": 1.5, "rsi": 0.2, "macd": 0.3, "bollinger": 0.2}


def _default_ranging_weights() -> dict[str, float]:
    return {"ema": 0.2, "rsi": 1.2, "macd": 1.0, "bollinger": 1.2}


def _default_volatile_weights() -> dict[str, float]:
    return {"ema": 0.5, "rsi": 0.5, "macd": 0.5, "bollinger": 0.5}


@dataclass(frozen=True)
class RegimeConfig:
    enabled: bool = False
    adx_period: int = 14
    trending_threshold: float = 25.0
    hysteresis_buffer: float = 5.0
    volatile_atr_percentile: float = 80.0
    atr_lookback: int = 100
    trending_weights: dict[str, float] = field(default_factory=_default_trending_weights)
    ranging_weights: dict[str, float] = field(default_factory=_default_ranging_weights)
    volatile_weights: dict[str, float] = field(default_factory=_default_volatile_weights)


@dataclass(frozen=True)
class StrategiesConfig:
    enabled: list[str] = field(default_factory=lambda: ["rsi", "macd", "bollinger"])
    rsi: RSIConfig = field(default_factory=RSIConfig)
    macd: MACDConfig = field(default_factory=MACDConfig)
    bollinger: BollingerConfig = field(default_factory=BollingerConfig)
    ema: EMAConfig = field(default_factory=EMAConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    weights: dict[str, float] = field(default_factory=dict)
    min_agreement: int = 1
    hold_opposition: float = 0.0


@dataclass(frozen=True)
class AIConfig:
    model: str = "claude-opus-4-6"
    max_calls_per_minute: int = 10
    analysis_cache_ttl_seconds: int = 300
    sentiment_cache_ttl_seconds: int = 900
    max_tokens_analysis: int = 4096
    max_tokens_sentiment: int = 1024
    openai_model: str = "gpt-4o"
    veto_enabled: bool = False
    veto_min_agree: int = 2


@dataclass(frozen=True)
class RiskConfig:
    max_position_pct: float = 0.10
    stop_loss_pct: float = 0.03
    trailing_stop_pct: float = 0.02
    max_drawdown_pct: float = 0.15
    daily_loss_limit_pct: float = 0.05
    max_single_order_usdt: float = 1000.0
    min_confidence: float = 0.4
    max_concurrent_positions: int = 3
    max_data_age_seconds: int = 3600
    max_price_deviation_pct: float = 0.05
    circuit_breaker_threshold: int = 5
    atr_stop_multiplier: float = 2.0
    atr_tp_multiplier: float = 3.0
    atr_trailing_multiplier: float = 1.5
    volume_min_multiplier: float = 1.2
    ema_trend_period: int = 50
    ema_trend_enabled: bool = True
    risk_per_trade_pct: float = 0.01
    partial_tp_ratio: float = 0.5


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


@dataclass(frozen=True)
class BacktestConfig:
    default_start: str = "2025-01-01"
    default_end: str = "2025-12-31"
    default_balance: float = 10_000.0
    data_cache_dir: str = "data/cache"


@dataclass(frozen=True)
class TradingConfig:
    mode: str = "paper"
    pairs: list[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    timeframe: str = "1h"
    poll_interval_seconds: int = 60


@dataclass(frozen=True)
class Settings:
    trading: TradingConfig = field(default_factory=TradingConfig)
    paper_trading: PaperTradingConfig = field(default_factory=PaperTradingConfig)
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    strategies: StrategiesConfig = field(default_factory=StrategiesConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)

    binance_api_key: str = ""
    binance_api_secret: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    log_level: str = "INFO"


def _resolve_type(dataclass_type: type, field_name: str) -> type | None:
    """Resolve a field's actual type, handling stringified annotations from __future__."""
    import typing

    hints = typing.get_type_hints(dataclass_type)
    return hints.get(field_name)


def _build_nested(dataclass_type: type, raw: dict) -> object:
    """Recursively build a frozen dataclass from a dict, ignoring unknown keys."""
    field_names = {f.name for f in dataclass_type.__dataclass_fields__.values()}
    kwargs = {}
    for name in field_names:
        if name not in raw:
            continue
        child_type = _resolve_type(dataclass_type, name)
        is_nested = (
            isinstance(raw[name], dict)
            and child_type
            and hasattr(child_type, "__dataclass_fields__")
        )
        if is_nested:
            kwargs[name] = _build_nested(child_type, raw[name])
        else:
            kwargs[name] = raw[name]
    return dataclass_type(**kwargs)


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from .env + config.yaml, with env vars taking precedence."""
    root = _project_root()
    load_dotenv(root / ".env")

    if config_path is None:
        config_path = root / "config.yaml"

    raw: dict = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            raw = yaml.safe_load(f) or {}

    trading = _build_nested(TradingConfig, raw.get("trading", {}))
    paper_trading = _build_nested(PaperTradingConfig, raw.get("paper_trading", {}))
    exchange = _build_nested(ExchangeConfig, raw.get("exchange", {}))
    strategies = _build_nested(StrategiesConfig, raw.get("strategies", {}))
    ai = _build_nested(AIConfig, raw.get("ai", {}))
    risk = _build_nested(RiskConfig, raw.get("risk", {}))
    backtest = _build_nested(BacktestConfig, raw.get("backtest", {}))
    telegram = _build_nested(TelegramConfig, raw.get("telegram", {}))

    mode_override = os.getenv("TRADING_MODE")
    if mode_override:
        trading = TradingConfig(
            mode=mode_override,
            pairs=trading.pairs,
            timeframe=trading.timeframe,
            poll_interval_seconds=trading.poll_interval_seconds,
        )

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        telegram = TelegramConfig(
            enabled=True,
            bot_token=tg_token,
            chat_id=tg_chat,
        )

    return Settings(
        trading=trading,
        paper_trading=paper_trading,
        exchange=exchange,
        strategies=strategies,
        ai=ai,
        risk=risk,
        backtest=backtest,
        telegram=telegram,
        binance_api_key=os.getenv("BINANCE_API_KEY", ""),
        binance_api_secret=os.getenv("BINANCE_API_SECRET", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        log_level=os.getenv("LOG_LEVEL", raw.get("logging", {}).get("level", "INFO")),
    )
