# Trading Bot — Complete Technical Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Project Structure](#project-structure)
4. [Configuration](#configuration)
5. [Backend Modules](#backend-modules)
6. [Strategies](#strategies)
7. [Backtest System](#backtest-system)
8. [Walk-Forward Validation](#walk-forward-validation)
9. [AI Integration](#ai-integration)
10. [Multi-LLM Veto System](#multi-llm-veto-system)
11. [Notifications (Telegram)](#notifications-telegram)
12. [Risk Management](#risk-management)
13. [Frontend](#frontend)
14. [API Reference](#api-reference)
15. [Data Flow Diagrams](#data-flow-diagrams)

---

## Overview

Crypto trading bot supporting three modes:
- **Paper trading** — simulated trading with real-time prices
- **Live trading** — real money trading on Binance
- **Backtesting** — strategy testing against historical data

**Technology stack:**
- Backend: Python 3.12+, FastAPI, asyncio
- Frontend: React + TypeScript, Vite, TailwindCSS
- Exchange: CCXT (Binance)
- AI: Anthropic Claude Opus 4.6; optional OpenAI (GPT-4o) for multi-LLM veto
- Indicators: pandas-ta
- Database: SQLite (aiosqlite)

**Notable features:**
- **Telegram alerts** — optional trade and error notifications via Bot API (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`); wire `TelegramNotifier` into `TradingEngine` when starting the bot.
- **Walk-forward validation** — optional sequential train/test folds on the same backtest request (`walk_forward` in `POST /api/backtest`); UI in Backtest Advanced Settings.
- **Multi-LLM veto** — when `AIFilterStrategy` is constructed with a `VetoSystem`, Claude + OpenAI (and other `LLMProvider` implementations) must reach quorum before a BUY/SELL is approved. Configure via `AIConfig` (`veto_enabled`, `veto_min_agree`, `openai_model`) and `OPENAI_API_KEY`.

---

## Architecture

### System Overview

```mermaid
graph TB
    subgraph Frontend["Frontend (React + Vite)"]
        UI[Dashboard UI]
        BT[Backtest Panel]
        CC[Candlestick Chart]
    end

    subgraph API["FastAPI Server"]
        REST[REST Endpoints]
        WS[WebSocket]
    end

    subgraph Core["Trading Core"]
        TE[Trading Engine]
        AGG[Signal Aggregator]
        RM[Risk Manager]
    end

    subgraph Strategies["Strategy Layer"]
        RSI[RSI Strategy]
        MACD[MACD Strategy]
        BOLL[Bollinger Strategy]
        EMA_S[EMA Crossover]
        AIS[AI Strategy]
        SENT[Sentiment Strategy]
    end

    subgraph Exchange["Exchange Layer"]
        BIN[Binance Client]
        PAP[Paper Exchange]
        BEX[Backtest Exchange]
    end

    subgraph AILayer["AI Layer"]
        CL[Claude Client]
        MA[Market Analyzer]
        SA[Sentiment Analyzer]
    end

    subgraph Data["Data Layer"]
        DB[(SQLite DB)]
        OHLCV[OHLCV Data]
    end

    UI --> REST
    BT --> REST
    UI --> WS
    REST --> TE
    REST --> BEX
    WS --> TE
    TE --> AGG
    AGG --> RSI & MACD & BOLL & EMA_S
    AGG --> AIS & SENT
    AIS --> MA --> CL
    SENT --> SA --> CL
    TE --> RM
    TE --> BIN & PAP
    BEX --> OHLCV
    TE --> DB
```

### Trading Modes

```mermaid
graph LR
    subgraph Modes["Trading Modes"]
        direction TB
        PAPER["Paper Trading<br/>Simulated balance<br/>Real-time prices"]
        LIVE["Live Trading<br/>Real money<br/>Binance API"]
        BACK["Backtesting<br/>Historical data<br/>Simulated exchange"]
    end

    CONFIG[config.yaml<br/>trading.mode] --> PAPER
    CONFIG --> LIVE
    CONFIG --> BACK

    PAPER --> PAP_EX[PaperExchange<br/>+ BinanceClient prices]
    LIVE --> BIN_EX[BinanceClient<br/>Full API access]
    BACK --> BT_EX[BacktestExchange<br/>OHLCV replay]
```

---

## Project Structure

```
tradingbot/
├── backend/
│   ├── main.py                 # CLI entry point — live/paper trading loop
│   ├── config.py               # All configuration (dataclasses)
│   ├── models.py               # Ticker, Order, Signal, Position, Trade
│   ├── database.py             # SQLite CRUD (aiosqlite)
│   ├── api/
│   │   ├── app.py              # FastAPI factory + lifespan
│   │   ├── routes.py           # REST endpoints + backtest orchestration
│   │   ├── deps.py             # Database dependency injection
│   │   └── websocket.py        # WebSocket live updates
│   ├── backtest/
│   │   ├── engine.py           # BacktestEngine + EngineConfig
│   │   ├── exchange.py         # BacktestExchange (fees, slippage)
│   │   ├── ai_filter.py        # AI simulation filter
│   │   ├── data_loader.py      # Binance OHLCV download + CSV
│   │   ├── report.py           # BacktestReport (Sharpe, drawdown etc)
│   │   ├── walk_forward.py     # Walk-forward folds + aggregate OOS metrics
│   │   ├── optimizer.py        # Optuna parameter optimizer
│   │   └── runner.py           # CLI backtest runner
│   ├── core/
│   │   ├── engine.py           # TradingEngine (live loop)
│   │   ├── regime.py           # ADX regime detection + dynamic weights
│   │   ├── scheduler.py        # PeriodicTask utility
│   │   ├── safety.py           # Live trading safety checks
│   │   ├── logger.py           # structlog setup
│   │   └── exceptions.py       # Exception hierarchy
│   ├── exchange/
│   │   ├── base.py             # ExchangeBase ABC
│   │   ├── binance_client.py   # CCXT Binance wrapper
│   │   └── paper_exchange.py   # Simulated exchange
│   ├── strategies/
│   │   ├── base.py             # StrategyBase ABC
│   │   ├── technical.py        # RSI, MACD, Bollinger, EMA Crossover
│   │   ├── ai_strategy.py      # Claude AI strategy
│   │   └── sentiment.py        # News sentiment strategy
│   ├── ai/
│   │   ├── base_provider.py    # LLMProvider ABC (veto)
│   │   ├── claude_client.py    # Anthropic API wrapper + LLMProvider
│   │   ├── openai_client.py    # OpenAI API wrapper (veto)
│   │   ├── veto_system.py      # Multi-LLM parallel quorum
│   │   ├── market_analyzer.py  # Market analysis with prompts
│   │   ├── sentiment_analyzer.py # News sentiment
│   │   └── prompts.py          # System + user prompts
│   ├── notifications/
│   │   └── telegram.py         # TelegramNotifier (Bot API via aiohttp)
│   └── risk/
│       └── manager.py          # Pre-trade risk checks
├── frontend/
│   └── src/
│       ├── App.tsx             # Dashboard + Backtest tabs
│       ├── api.ts              # REST client
│       ├── components/
│       │   ├── BacktestPanel.tsx    # Full backtest UI
│       │   ├── CandlestickChart.tsx # Lightweight Charts
│       │   ├── Header.tsx           # Header + status
│       │   ├── StatsPanel.tsx       # Portfolio statistics
│       │   ├── PortfolioChart.tsx   # Equity curve
│       │   ├── ConfigPanel.tsx      # Bot configuration
│       │   └── TradesTable.tsx      # Trades table
│       └── hooks/
│           └── useWebSocket.ts # WS hook
├── tests/                      # Tests (mirrors backend structure)
├── config.yaml                 # Main configuration
├── .env.example                # Environment variables
├── pyproject.toml              # Project metadata + tools
└── requirements.txt            # Python dependencies
```

---

## Configuration

### Configuration Hierarchy

```mermaid
graph TD
    ENV[".env file<br/>API keys, secrets"] --> LOAD["load_settings()"]
    YAML["config.yaml<br/>Core parameters"] --> LOAD
    ENVVAR["Env variables<br/>TRADING_MODE override"] --> LOAD
    LOAD --> SETTINGS["Settings dataclass<br/>(frozen, immutable)"]

    SETTINGS --> TC["TradingConfig"]
    SETTINGS --> EC["ExchangeConfig"]
    SETTINGS --> SC["StrategiesConfig"]
    SETTINGS --> AC["AIConfig"]
    SETTINGS --> RC["RiskConfig"]
    SETTINGS --> BC["BacktestConfig"]
    SETTINGS --> PC["PaperTradingConfig"]
    SETTINGS --> TG["TelegramConfig"]
```

### All Configuration Values

#### TradingConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | str | `"paper"` | Trading mode: `paper`, `live`, `backtest` |
| `pairs` | list[str] | `["BTC/USDT", "ETH/USDT"]` | Trading pairs |
| `timeframe` | str | `"1h"` | Candle interval |
| `poll_interval_seconds` | int | `60` | Tick interval in seconds |

#### ExchangeConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | str | `"binance"` | Exchange name |
| `sandbox` | bool | `False` | Whether to use testnet |
| `rate_limit_ms` | int | `100` | API rate limit in ms |

#### StrategiesConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | list[str] | `["rsi", "macd", "bollinger"]` | Active strategies (also: `ema`, `ai_filter`, `sentiment`) |
| `rsi` | RSIConfig | — | RSI parameters |
| `macd` | MACDConfig | — | MACD parameters |
| `bollinger` | BollingerConfig | — | Bollinger parameters |
| `ema` | EMAConfig | — | EMA Crossover parameters |
| `weights` | dict[str,float] | `{}` | Per-strategy weights for aggregation (default 1.0) |
| `min_agreement` | int | `1` | Min strategies agreeing on direction before executing |
| `hold_opposition` | float | `0.0` | Penalty per HOLD signal against directional signals |
| `regime` | `RegimeConfig` | See RegimeConfig | Regime detection configuration |

#### RegimeConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable ADX-based regime detection |
| `adx_period` | int | `14` | ADX indicator period |
| `trending_threshold` | float | `25.0` | ADX value above which market is considered trending |
| `hysteresis_buffer` | float | `5.0` | Buffer zone to prevent rapid regime flipping |
| `volatile_atr_percentile` | float | `80.0` | ATR percentile above which market is classified as volatile |
| `atr_lookback` | int | `100` | Number of candles for ATR percentile calculation |
| `trending_weights` | dict | `{ema: 1.5, rsi: 0.2, macd: 0.3, bollinger: 0.2}` | Strategy weight multipliers in trending regime |
| `ranging_weights` | dict | `{ema: 0.2, rsi: 1.2, macd: 1.0, bollinger: 1.2}` | Strategy weight multipliers in ranging regime |
| `volatile_weights` | dict | `{ema: 0.5, rsi: 0.5, macd: 0.5, bollinger: 0.5}` | Strategy weight multipliers in volatile regime |

#### RSIConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `period` | int | `14` | RSI calculation period (number of candles) |
| `oversold` | int | `30` | Oversold threshold (below this → BUY) |
| `overbought` | int | `70` | Overbought threshold (above this → SELL) |

#### MACDConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `fast` | int | `12` | Fast EMA period |
| `slow` | int | `26` | Slow EMA period |
| `signal` | int | `9` | Signal line EMA period |

#### BollingerConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `period` | int | `20` | Moving average period |
| `std_dev` | float | `2.0` | Number of standard deviations for bands |

#### EMAConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `fast_period` | int | `9` | Fast EMA period (responds quickly to price) |
| `slow_period` | int | `21` | Slow EMA period (smoother trend signal) |

#### AIConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | str | `"claude-opus-4-6"` | Claude model ID |
| `max_calls_per_minute` | int | `10` | API rate limit |
| `analysis_cache_ttl_seconds` | int | `300` | Market analysis cache TTL |
| `sentiment_cache_ttl_seconds` | int | `900` | Sentiment cache TTL |
| `max_tokens_analysis` | int | `4096` | Max tokens for analysis |
| `max_tokens_sentiment` | int | `1024` | Max tokens for sentiment |
| `openai_model` | str | `"gpt-4o"` | OpenAI model for veto provider |
| `veto_enabled` | bool | `False` | Enable multi-LLM quorum on AI strategy (app wiring) |
| `veto_min_agree` | int | `2` | Minimum providers that must agree on signal direction |

#### TelegramConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `False` | Send Telegram messages when token + chat id set |
| `bot_token` | str | `""` | From `@BotFather` (or set `TELEGRAM_BOT_TOKEN` in `.env`) |
| `chat_id` | str | `""` | Target chat (or `TELEGRAM_CHAT_ID` in `.env`) |

If both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are present in `.env`, `load_settings()` enables Telegram automatically.

#### RiskConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_position_pct` | float | `0.10` | Max position size (% of balance) |
| `stop_loss_pct` | float | `0.03` | Fixed stop-loss % (fallback when ATR unavailable) |
| `trailing_stop_pct` | float | `0.02` | Trailing stop % from peak (fallback) |
| `max_drawdown_pct` | float | `0.15` | Max drawdown before trading halt |
| `daily_loss_limit_pct` | float | `0.05` | Daily loss limit |
| `max_single_order_usdt` | float | `1000.0` | Max single order value in USDT |
| `min_confidence` | float | `0.4` | Min aggregated signal confidence to execute a trade |
| `max_concurrent_positions` | int | `3` | Max simultaneous open positions |
| `max_data_age_seconds` | int | `3600` | Max OHLCV candle age before data is considered stale |
| `max_price_deviation_pct` | float | `0.05` | Max allowed price deviation from last close (anti-glitch) |
| `circuit_breaker_threshold` | int | `5` | Consecutive tick errors before 5-min pause |
| `atr_stop_multiplier` | float | `2.0` | ATR multiplier for stop-loss distance |
| `atr_tp_multiplier` | float | `3.0` | ATR multiplier for take-profit target |
| `atr_trailing_multiplier` | float | `1.5` | ATR multiplier for trailing stop distance |
| `volume_min_multiplier` | float | `1.2` | Min volume/SMA-20 ratio to confirm signals |
| `ema_trend_period` | int | `50` | EMA period for trend filter |
| `ema_trend_enabled` | bool | `True` | Only BUY above EMA, SELL below EMA |
| `risk_per_trade_pct` | float | `0.01` | Portfolio % risked per trade (ATR position sizing) |
| `partial_tp_ratio` | float | `0.5` | Fraction sold at first take-profit target |

#### BacktestConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_start` | str | `"2025-01-01"` | Default start date |
| `default_end` | str | `"2025-12-31"` | Default end date |
| `default_balance` | float | `10000.0` | Starting balance |
| `data_cache_dir` | str | `"data/cache"` | OHLCV cache directory |

---

## Backend Modules

### Data Models (`backend/models.py`)

```mermaid
classDiagram
    class Signal {
        +str symbol
        +Literal["BUY","SELL","HOLD"] direction
        +float confidence
        +str strategy_name
        +str reason
        +dict indicators
        +datetime timestamp
    }

    class Order {
        +str id
        +str symbol
        +OrderSide side
        +OrderType order_type
        +float amount
        +float price
        +OrderStatus status
        +float filled_amount
        +float filled_price
        +datetime created_at
    }

    class Trade {
        +str id
        +str symbol
        +OrderSide side
        +float amount
        +float price
        +float fee
        +float pnl
        +Signal signal
        +datetime executed_at
    }

    class Position {
        +str symbol
        +OrderSide side
        +float amount
        +float entry_price
        +float current_price
        +float unrealized_pnl
        +float stop_loss
        +float trailing_stop
    }

    class Ticker {
        +str symbol
        +float bid
        +float ask
        +float last
        +datetime timestamp
    }

    Signal --> Trade : generates
    Order --> Trade : fills into
```

### Exchange Hierarchy

```mermaid
classDiagram
    class ExchangeBase {
        <<abstract>>
        +get_balance() dict
        +get_ticker(symbol) Ticker
        +get_ohlcv(symbol, tf, limit) DataFrame
        +create_order(symbol, side, type, amount, price) Order
        +cancel_order(id, symbol)
        +get_open_orders(symbol) list~Order~
        +close()
    }

    class BinanceClient {
        -ccxt.async_support.binance _exchange
        +get_portfolio_value() float
    }

    class PaperExchange {
        -dict _balances
        -BinanceClient _price_feed
        +get_portfolio_value() float
    }

    class BacktestExchange {
        -DataFrame _ohlcv
        -int _index
        -dict _balances
        -float _fee_rate
        -float _slippage_rate
        +float total_fees_paid
        +float total_slippage_cost
        +advance() bool
        +get_portfolio_value() float
    }

    ExchangeBase <|-- BinanceClient
    ExchangeBase <|-- PaperExchange
    ExchangeBase <|-- BacktestExchange
    PaperExchange --> BinanceClient : price feed
```

---

## Strategies

### Strategy Flow

```mermaid
graph LR
    OHLCV[OHLCV Data<br/>100 candles] --> RSI["RSI Strategy<br/>period=14"]
    OHLCV --> MACD["MACD Strategy<br/>fast=12, slow=26"]
    OHLCV --> BOLL["Bollinger Strategy<br/>period=20, std=2.0"]
    OHLCV --> EMA_S["EMA Crossover<br/>fast=9, slow=21"]

    RSI --> |"Signal"| AGG["Aggregator<br/>Weighted vote<br/>+ min_agreement<br/>+ HOLD opposition"]
    MACD --> |"Signal"| AGG
    BOLL --> |"Signal"| AGG
    EMA_S --> |"Signal"| AGG

    AGG --> |"Combined Signal"| FILTER["AI Filter<br/>(optional)"]
    FILTER --> |"Final Signal"| EXEC["Execute or HOLD"]
```

### Signal Aggregation

```mermaid
graph TD
    SIG["All signals"] --> SPLIT["Split: directional<br/>vs HOLD"]
    SPLIT --> WEIGHT["BUY = Σ conf × weight - HOLD penalty<br/>SELL = Σ conf × weight - HOLD penalty"]
    WEIGHT --> CMP{"BUY > SELL?"}
    CMP -->|Yes| AGREE{"≥ min_agreement<br/>BUY strategies?"}
    CMP -->|No| CMP2{"SELL > BUY?"}
    CMP2 -->|Yes| AGREE2{"≥ min_agreement<br/>SELL strategies?"}
    CMP2 -->|Tie| HOLD["Direction = HOLD"]
    AGREE -->|Yes| BUY_DIR["Direction = BUY"]
    AGREE -->|No| HOLD
    AGREE2 -->|Yes| SELL_DIR["Direction = SELL"]
    AGREE2 -->|No| HOLD
    BUY_DIR --> FINAL["Aggregated Signal"]
    SELL_DIR --> FINAL
    HOLD --> FINAL
```

### Regime Detection

The bot uses ADX-based market regime detection to dynamically adjust strategy weights based on market conditions.

**Three Regimes:**
- **Trending** (ADX > threshold + buffer): EMA crossover strategy weight boosted, mean-reversion suppressed
- **Ranging** (ADX < threshold - buffer): RSI/MACD/Bollinger boosted, EMA suppressed  
- **Volatile** (ATR percentile > 80th): All strategy weights reduced for conservative trading

**Hysteresis** prevents whipsaw regime flipping. The ADX must cross a higher band to enter trending and a lower band to exit, avoiding rapid oscillation near the boundary.

```
Data → ADX + ATR Percentile
      │
      ├── ADX > threshold + buffer → TRENDING
      │   └── EMA ×1.5, RSI ×0.2, MACD ×0.3, Bollinger ×0.2
      │
      ├── ATR pct > 80 → VOLATILE
      │   └── All strategies ×0.5
      │
      └── Otherwise → RANGING
          └── EMA ×0.2, RSI ×1.2, MACD ×1.0, Bollinger ×1.2
```

### RSI Strategy Logic

```mermaid
graph TD
    CALC["Compute RSI<br/>(period candles)"] --> VAL{"RSI value?"}
    VAL -->|"≤ 30 (oversold)"| BUY["BUY<br/>conf = 0.5 + distance"]
    VAL -->|"≥ 70 (overbought)"| SELL["SELL<br/>conf = 0.5 + distance"]
    VAL -->|"30 < RSI < 70"| HOLD["HOLD<br/>conf = 0"]
```

### MACD Strategy Logic

```mermaid
graph TD
    CALC["Compute MACD<br/>histogram"] --> CROSS{"Histogram<br/>sign flip?"}
    CROSS -->|"prev < 0 → now > 0"| BUY["BUY (bullish crossover)<br/>conf = 0.5 + |hist| × 10"]
    CROSS -->|"prev > 0 → now < 0"| SELL["SELL (bearish crossover)<br/>conf = 0.5 + |hist| × 10"]
    CROSS -->|"No change"| HOLD["HOLD"]
```

### Bollinger Strategy Logic

```mermaid
graph TD
    CALC["Compute BB bands<br/>(period, std_dev)"] --> POS{"Price vs bands?"}
    POS -->|"Close < Lower band"| BUY["BUY<br/>conf = 0.5 + penetration"]
    POS -->|"Close > Upper band"| SELL["SELL<br/>conf = 0.5 + penetration"]
    POS -->|"Between bands"| HOLD["HOLD"]
```

### EMA Crossover Strategy Logic

```mermaid
graph TD
    CALC["Compute fast EMA<br/>and slow EMA"] --> CROSS{"Crossover?"}
    CROSS -->|"fast crosses above slow"| BUY["BUY (bullish)<br/>conf = 0.5 + gap/ATR"]
    CROSS -->|"fast crosses below slow"| SELL["SELL (bearish)<br/>conf = 0.5 + gap/ATR"]
    CROSS -->|"No crossover"| HOLD["HOLD<br/>warmth if converging"]
```

---

## Backtest System

### Complete Backtest Flow

```mermaid
graph TD
    START["Start Backtest"] --> INIT["Initialize<br/>BacktestExchange<br/>+ Strategies"]
    INIT --> LOOP{"Next<br/>candle?"}

    LOOP -->|Yes| PV["Compute portfolio<br/>value"]
    PV --> DD{"Drawdown<br/>> limit?"}
    DD -->|Yes| HALT["HALT: stopped<br/>Only advance"]
    DD -->|No| POS{"Position<br/>exists?"}

    POS -->|Yes| SL{"Stop-loss<br/>triggered?"}
    SL -->|Yes| SELL_SL["Auto SELL<br/>(stop-loss)"]
    SL -->|No| TS{"Trailing stop<br/>triggered?"}
    TS -->|Yes| SELL_TS["Auto SELL<br/>(trailing stop)"]
    TS -->|No| TP{"Take-profit<br/>triggered?"}
    TP -->|Yes| SELL_TP["Partial SELL<br/>(take-profit)"]
    TP -->|No| CONT["Continue"]

    POS -->|No| CONT
    SELL_SL --> CONT
    SELL_TS --> CONT
    SELL_TP --> CONT

    CONT --> OHLCV["Load OHLCV<br/>(100 candles)"]
    OHLCV --> DATA{">= 30<br/>candles?"}
    DATA -->|No| ADV["Advance"]
    DATA -->|Yes| REG{"ADX regime<br/>filter?"}

    REG -->|"ADX > threshold"| ADV
    REG -->|"OK"| SIG["Collect signals<br/>RSI + MACD + Bollinger"]
    SIG --> AGG["Aggregate signals"]
    AGG --> AI["AI Filter<br/>(crash/vol/spike)"]
    AI --> HOLD{"HOLD?"}
    HOLD -->|Yes| ADV
    HOLD -->|No| CONF{"Confidence<br/>>= min?"}
    CONF -->|No| ADV
    CONF -->|Yes| CD{"Cooldown<br/>passed?"}
    CD -->|No| ADV
    CD -->|Yes| EXEC["Execute Trade<br/>(fees + slippage)"]
    EXEC --> ADV

    ADV --> LOOP
    LOOP -->|No| REPORT["Generate Report<br/>Sharpe, drawdown,<br/>win rate etc"]
    HALT --> ADV
```

### EngineConfig Parameters

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `min_confidence` | float | `0.0` | Minimum signal confidence required |
| `cooldown_candles` | int | `0` | Candles between trades |
| `use_dynamic_sizing` | bool | `False` | Position size × confidence |
| `enable_regime_filter` | bool | `False` | ADX trending filter |
| `adx_period` | int | `14` | ADX indicator period |
| `adx_trending_threshold` | float | `25.0` | ADX threshold for trending market |
| `take_profit_pct` | float | `0.0` | Take-profit % (0 = disabled) |
| `take_profit_ratio` | float | `0.5` | Fraction of position to sell at TP |

### BacktestExchange Parameters

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `fee_rate` | float | `0.001` | Exchange fee per trade (0.1%) |
| `slippage_rate` | float | `0.0005` | Price slippage (0.05%) |

### Report Metrics (BacktestReport)

| Metric | Description |
|--------|-------------|
| `total_return_pct` | Total return % |
| `annualized_return_pct` | Annualized return % |
| `max_drawdown_pct` | Largest peak-to-trough decline |
| `sharpe_ratio` | Risk-adjusted return (risk-free 4%) |
| `sortino_ratio` | Like Sharpe but only downside volatility |
| `total_trades` | Total number of trades |
| `win_rate` | Percentage of profitable trades |
| `avg_trade_pnl` | Average P&L per trade |
| `best_trade_pnl` / `worst_trade_pnl` | Best/worst single trade |

---

## Walk-Forward Validation

Walk-forward splits the loaded OHLCV into sequential **train** / **test** windows, runs a full backtest on each slice with the same strategy and engine parameters, and aggregates **out-of-sample (OOS)** metrics. This reduces overfitting compared to a single in-sample run.

**Module:** [`backend/backtest/walk_forward.py`](backend/backtest/walk_forward.py)

| Parameter | Description |
|-----------|-------------|
| `n_folds` | Number of folds (e.g. 3) |
| `train_pct` | Fraction of each fold used for training (e.g. 0.7) |
| `step_type` | `rolling` — chunk the series into folds; `expanding` — growing train window with sliding test |

**API:** Enable with `walk_forward.enabled: true` on `POST /api/backtest`. Response may include `walk_forward` with `folds[]` (each with `train_report`, `test_report`) and `aggregate_oos` (`avg_return_pct`, `avg_sharpe`, `worst_return_pct`, etc.).

**UI:** Backtest panel → Advanced Settings → Walk-Forward Validation.

### Parameter Optimizer (Optuna)

Automated parameter search using Bayesian optimization (Optuna TPE sampler). Runs N backtest trials with different parameter combinations and ranks results by scoring metric. Optionally validates the best result with walk-forward to detect overfitting.

**Tunable parameter groups:**

| Group | Parameters |
|-------|-----------|
| `strategy` | RSI period/oversold/overbought, MACD fast/slow/signal, Bollinger period/std_dev, EMA fast/slow period |
| `risk` | stop_loss_pct, trailing_stop_pct, max_position_pct, min_confidence, risk_per_trade_pct |
| `atr` | atr_stop_multiplier, atr_tp_multiplier, atr_trailing_multiplier, partial_tp_ratio |
| `guards` | volume_min_multiplier, ema_trend_period, ema_trend_enabled |
| `engine` | cooldown_candles, use_dynamic_sizing |
| `aggregator` | min_agreement (1–4), hold_opposition (0.0–0.3) |
| `regime` | `regime_trending_threshold`, `regime_hysteresis_buffer`, `regime_trending_ema_weight`, `regime_trending_mr_weight`, `regime_ranging_ema_weight`, `regime_ranging_mr_weight` | ADX threshold, hysteresis, per-regime strategy weight multipliers |

**Scoring metrics:** `sharpe` (risk-adjusted return, default), `return` (total return %), `calmar` (return / max drawdown).

**`POST /api/optimize`**

```json
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "start": "2025-01-01",
  "end": "2025-06-30",
  "balance": 10000,
  "strategies": ["rsi", "macd", "bollinger"],
  "n_trials": 50,
  "scoring": "sharpe",
  "tune_groups": ["strategy", "risk", "atr"],
  "validate_best": true,
  "fee_rate": 0.001,
  "slippage_rate": 0.0005
}
```

Response:

```json
{
  "trials": [
    {
      "number": 42,
      "params": { "rsi_period": 10, "stop_loss_pct": 0.04, "atr_stop_multiplier": 2.5 },
      "score": 1.234,
      "metrics": { "sharpe": 1.234, "return_pct": 8.5, "max_drawdown_pct": 3.2, "win_rate": 55.0, "total_trades": 32 }
    }
  ],
  "best_params": { "rsi_period": 10, "stop_loss_pct": 0.04 },
  "best_metrics": { "sharpe": 1.234, "return_pct": 8.5 },
  "best_score": 1.234,
  "validation": { "folds": [], "aggregate_oos": { "avg_return_pct": 3.2, "avg_sharpe": 0.8 } }
}
```

**UI:** Header → Optimizer tab. Configure symbol, dates, trials, scoring, parameter groups. Results show best parameters, all trials table (sortable), and walk-forward validation. "Apply to Backtest" button copies optimal parameters to the Backtest panel.

---

## AI Integration

### AI Layers

```mermaid
graph TD
    subgraph Backtesting["In Backtesting (free)"]
        AIF["AI Simulation Filter<br/>Mathematical heuristics"]
    end

    subgraph LiveTrading["In Live Trading ($)"]
        AIS["AI Strategy<br/>Claude analyzes market"]
        ATF["AI Trade Filter<br/>Claude approves trades"]
        ASA["Sentiment Analysis<br/>Claude + news"]
    end

    AIF --> |"Crash detection"| CRASH["Rapid price drop"]
    AIF --> |"Volatility spike"| VOL["High volatility"]
    AIF --> |"Volume spike"| VSPIKE["Panic selling"]
    AIF --> |"Recovery"| REC["Price bounce-back"]

    AIS --> CL["Claude API<br/>claude-opus-4-6"]
    ATF --> CL
    ASA --> NEWS["CryptoPanic<br/>news feed"] --> CL
```

### AI Crash Filter Config

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `False` | Filter on/off |
| `strength` | float | `0.5` | Filtering intensity (0–1) |
| `crash_lookback` | int | `10` | Candles for crash detection |
| `crash_threshold_pct` | float | `-5.0` | Crash threshold % |
| `volatility_lookback` | int | `20` | Volatility calculation period |
| `volatility_multiplier` | float | `2.0` | Volatility spike multiplier |
| `volume_spike_multiplier` | float | `2.5` | Volume spike multiplier |
| `recovery_boost` | float | `1.3` | Recovery BUY confidence boost |
| `min_confidence_threshold` | float | `0.3` | Min confidence before blocking |

### AI Filter Effect on Signals

```mermaid
graph LR
    subgraph Input["Input Signal"]
        BUY_IN["BUY conf=0.7"]
        SELL_IN["SELL conf=0.6"]
    end

    subgraph Crash["Crash Detected"]
        BUY_CRASH["BUY → HOLD<br/>(blocked)"]
        SELL_CRASH["SELL conf=0.8<br/>(boosted)"]
    end

    subgraph Recovery["Recovery Detected"]
        BUY_REC["BUY conf=0.9<br/>(boosted)"]
    end

    subgraph Flat["Normal Market"]
        BUY_FLAT["BUY conf=0.7<br/>(unchanged)"]
    end

    BUY_IN --> |"Crash"| BUY_CRASH
    BUY_IN --> |"Recovery"| BUY_REC
    BUY_IN --> |"Flat"| BUY_FLAT
    SELL_IN --> |"Crash"| SELL_CRASH
```

---

## Multi-LLM Veto System

Optional second opinion for live **AI filter strategy** signals. Multiple `LLMProvider` implementations (e.g. `ClaudeClient`, `OpenAIClient`) are queried in parallel; a trade direction is **approved** only if at least `veto_min_agree` providers return the same `direction` (`BUY` / `SELL`) as the proposed signal.

| File | Role |
|------|------|
| [`backend/ai/base_provider.py`](backend/ai/base_provider.py) | `LLMProvider` ABC — `analyze(system_prompt, user_prompt) -> dict` |
| [`backend/ai/openai_client.py`](backend/ai/openai_client.py) | OpenAI Chat Completions, JSON response format |
| [`backend/ai/veto_system.py`](backend/ai/veto_system.py) | `VetoSystem` — `asyncio.gather`, quorum, timeout |
| [`backend/ai/claude_client.py`](backend/ai/claude_client.py) | Implements `LLMProvider` via uncached `analyze()` |

[`AIFilterStrategy`](backend/strategies/ai_strategy.py) accepts optional `veto_system: VetoSystem | None`. When set and Claude proposes BUY/SELL, `evaluate()` runs before returning the signal; on veto, the strategy returns HOLD.

**Secrets:** `OPENAI_API_KEY` in `.env` (see `.env.example`).

---

## Notifications (Telegram)

[`TelegramNotifier`](backend/notifications/telegram.py) sends Markdown messages through the Telegram Bot HTTP API (uses `aiohttp`, no extra dependency).

| Method | Use |
|--------|-----|
| `send_trade(trade, signal)` | After a filled order |
| `send_alert(message, level)` | Errors / circuit breaker |
| `send_daily_summary(stats)` | Optional daily digest |

**Wiring:** Pass `TelegramNotifier(load_settings().telegram)` into `TradingEngine(..., notifier=...)` and call `await notifier.start()` / `close()` around the trading loop lifecycle. The API server lifespan does not start the engine by default; integrate where you launch `TradingEngine`.

---

## Risk Management

### Live Engine Guards

The live/paper trading engine applies the following guards on every tick:

| Guard | Config Field | Behaviour |
|-------|-------------|-----------|
| **RiskManager integration** | `max_drawdown_pct`, `daily_loss_limit_pct` | Portfolio-level drawdown halts all trading; daily loss limit skips the tick |
| **Min confidence** | `min_confidence` | Aggregated signals below this threshold are ignored |
| **Volume confirmation** | `volume_min_multiplier` | Rejects signals when current candle volume < SMA-20 × multiplier |
| **EMA trend filter** | `ema_trend_period`, `ema_trend_enabled` | Only BUY when price > EMA, only SELL when price < EMA |
| **Stale data** | `max_data_age_seconds` | If the latest OHLCV candle is older than this, the symbol is skipped |
| **Max concurrent positions** | `max_concurrent_positions` | New BUYs are blocked when this many positions are already open |
| **Price sanity** | `max_price_deviation_pct` | If the ticker price deviates more than this % from the last candle close, the trade is rejected |
| **ATR dynamic stops** | `atr_stop_multiplier`, `atr_tp_multiplier`, `atr_trailing_multiplier` | Stop-loss, take-profit, and trailing stop derived from ATR-14 at entry (falls back to fixed % when ATR unavailable) |
| **ATR position sizing** | `risk_per_trade_pct` | Sizes positions inversely to volatility: `risk_amount / (ATR × stop_mult)` |
| **Partial take-profit** | `partial_tp_ratio` | Sells a fraction at ATR TP target, moves stop to breakeven for remainder |
| **Strategy weights** | `strategies.weights` | Per-strategy multiplier on confidence (e.g. `{"macd": 1.5, "rsi": 0.8}`) |
| **Min agreement** | `strategies.min_agreement` | Minimum strategies that must agree on BUY/SELL before executing (default 1) |
| **HOLD opposition** | `strategies.hold_opposition` | Penalty weight each HOLD signal applies against directional signals (default 0.0) |
| **Circuit breaker** | `circuit_breaker_threshold` | After N consecutive tick errors, the engine pauses for 5 minutes |
| **Duplicate BUY block** | — | Skips BUY if already holding a position for that symbol |
| **Trade cooldown** | `poll_interval_seconds × 3` | Prevents rapid-fire BUYs on the same symbol |

### Risk Controls in Backtest (Full Parity with Live Engine)

The backtest engine now mirrors every guard and exit condition from the live engine:

| Guard / Feature | Backtest Implementation |
|----------------|------------------------|
| **ATR-based stops** | `RiskManager.calculate_atr()` → stop-loss at `entry - ATR × atr_stop_multiplier` |
| **ATR trailing stop** | `peak - ATR × atr_trailing_multiplier`, updates with new highs |
| **ATR take-profit** | `entry + ATR × atr_tp_multiplier` |
| **Partial take-profit** | Sells `partial_tp_ratio` at ATR TP, moves stop to breakeven |
| **ATR position sizing** | `risk_per_trade_pct × portfolio / (ATR × stop_mult)` caps budget |
| **Volume confirmation** | Same `_check_volume_confirmation()` as live engine |
| **EMA trend filter** | Same `_check_ema_trend()` as live engine |
| **Min confidence** | Max of `EngineConfig.min_confidence` and `RiskConfig.min_confidence` |
| **Cooldown** | Candle-based cooldown between trades |
| **Duplicate BUY block** | No second BUY while position is open |
| **Drawdown halt** | Peak-to-trough drawdown circuit breaker (permanent) |
| **Daily loss limit** | Tracks daily P&L with calendar-day reset |
| **Strategy weighting** | `strategy_weights` dict passed to `_aggregate_signals()` |
| **Min agreement** | `min_agreement` passed through to aggregator (same logic as live) |
| **HOLD opposition** | `hold_opposition` passed through to aggregator (same logic as live) |
| **Percentage fallback** | Falls back to `stop_loss_pct`/`trailing_stop_pct` when ATR is zero |

```mermaid
graph TD
    SIGNAL["Aggregated<br/>signal (weighted)"] --> CONF{"Confidence<br/>>= min?"}
    CONF -->|No| SKIP1["Skip: too weak"]
    CONF -->|Yes| DUP{"Already<br/>holding?"}
    DUP -->|BUY + position| SKIP_DUP["Skip: duplicate"]
    DUP -->|OK| VOL{"Volume<br/>confirmed?"}
    VOL -->|No| SKIP_VOL["Skip: low volume"]
    VOL -->|Yes| EMA{"EMA trend<br/>aligned?"}
    EMA -->|No| SKIP_EMA["Skip: wrong trend"]
    EMA -->|Yes| CD{"Cooldown<br/>passed?"}
    CD -->|No| SKIP_CD["Skip: cooldown"]
    CD -->|Yes| SIZE["ATR position sizing<br/>+ max_position_pct<br/>+ max_single_order_usdt"]
    SIZE --> EXEC["Create Order<br/>+ fee + slippage"]
    EXEC --> POS["Position with ATR stops"]

    POS --> |"Every candle"| PTP{"high ≥ ATR TP?<br/>(partial exits=0)"}
    PTP -->|Yes| EXIT_PTP["Partial SELL<br/>+ breakeven stop"]
    PTP -->|No| SL{"low ≤ ATR SL?"}
    SL -->|Yes| EXIT_SL["Force SELL<br/>stop-loss"]
    SL -->|No| TS{"low ≤ ATR trailing?<br/>(peak - ATR × mult)"}
    TS -->|Yes| EXIT_TS["Force SELL<br/>trailing stop"]
    TS -->|No| CONT["Continue"]

    DD{"Portfolio drawdown<br/>> max_drawdown?"}
    DD -->|Yes| HALT["HALT: permanent"]
    DL{"Daily loss<br/>> daily_limit?"}
    DL -->|Yes| SKIP_DAY["Skip: daily limit"]
```

---

## Frontend

### Component Hierarchy

```mermaid
graph TD
    APP["App.tsx"] --> HEAD["Header<br/>Logo, mode, status"]
    APP --> TABS["Tab Navigation<br/>Dashboard | Backtest"]

    TABS --> |Dashboard| DASH["Dashboard View"]
    TABS --> |Backtest| BTP["BacktestPanel"]

    DASH --> SP["StatsPanel<br/>4 stat cards"]
    DASH --> PC["PortfolioChart<br/>Equity curve"]
    DASH --> CP["ConfigPanel<br/>Bot settings + paper trading info"]
    DASH --> TT["TradesTable<br/>Recent trades"]

    BTP --> FORM["Input Form<br/>Symbol, dates, balance"]
    BTP --> STRAT["Strategy Toggles<br/>RSI, MACD, Bollinger, EMA"]
    BTP --> AITOGGLE["AI Crash Filter<br/>Toggle + Strength"]
    BTP --> ADV["Advanced Settings"]
    BTP --> RESULTS["Results"]

    ADV --> COSTS["Trading Costs<br/>Fee, Slippage, Min conf, Cooldown"]
    ADV --> POSMGMT["Position Mgmt<br/>Dynamic sizing, ADX, TP"]
    ADV --> RISK["Risk Mgmt<br/>Stop-loss, Trailing, Max order"]
    ADV --> STRAT_P["Strategy Params<br/>RSI/MACD/Bollinger sliders"]
    ADV --> AI_P["AI Filter Params<br/>Crash lookback, thresholds"]
    ADV --> WF["Walk-Forward<br/>Folds, train %, step type"]

    RESULTS --> CARDS["Stat Cards<br/>Return, Sharpe, Win rate..."]
    RESULTS --> CANDLE["CandlestickChart<br/>+ Trade markers"]
    RESULTS --> EQUITY["Equity Curve<br/>Recharts area"]
    RESULTS --> AISTATS["AI Filter Stats"]
    RESULTS --> ENGSTATS["Engine Stats<br/>Fees, stops, skips"]
    RESULTS --> SIGSPLIT["Strategy Signals<br/>BUY/SELL/HOLD bars"]
    RESULTS --> WFRES["Walk-Forward Table<br/>OOS aggregate"]
    RESULTS --> TRADES["Trade History<br/>Table"]
```

---

## API Reference

### REST Endpoints

All REST endpoints are prefixed with `/api`.

| Method | Path | Parameters | Response |
|--------|------|------------|----------|
| `GET` | `/api/health` | — | `{"status": "ok"}` |
| `GET` | `/api/config` | — | Bot configuration (mode, pairs, `paper_trading.initial_balance_usdt`, risk, strategies) |
| `GET` | `/api/trades` | `?symbol=&limit=50` | List of trades |
| `GET` | `/api/orders` | `?symbol=` | Open orders |
| `GET` | `/api/portfolio` | `?limit=100` | Portfolio history |
| `GET` | `/api/signals` | `?symbol=&strategy=&limit=50` | Signal log: per-strategy + aggregated signals from each engine cycle |
| `GET` | `/api/bot/status` | — | In-process paper loop: `state`, `mode`, `control_enabled`, `last_error` |
| `POST` | `/api/bot/start` | — | Starts `TradingEngine` inside the API process (**`trading.mode` must be `paper`**). `403` if `BOT_CONTROL_ENABLED` is false |
| `POST` | `/api/bot/stop` | — | Stops the in-process loop (may take up to one poll interval) |
| `PATCH` | `/api/bot/settings` | JSON body (all optional): `initial_balance_usdt`, `pairs`, `timeframe`, `poll_interval_seconds`, `strategies` | Merges allowed fields into project `config.yaml`. `strategies` replaces `strategies.enabled` and must include at least one of `rsi` / `macd` / `bollinger`. **`409` if the bot is not stopped** |
| `POST` | `/api/backtest` | JSON body (see below) | Report + equity + OHLCV + trades |

**Paper dashboard control:** With `trading.mode: paper`, the React dashboard can start/stop the bot and edit paper settings without restarting uvicorn. Changing `initial_balance_usdt` affects the next run, not an already-running simulated book. Disable remote start/stop with `BOT_CONTROL_ENABLED=false` in `.env`.

If the dashboard shows **Not Found** for bot actions, the API process is missing `/api/bot/*` routes — restart it with the current code using `uvicorn backend.api.app:app` (port `8000` must match the Vite proxy in `frontend/vite.config.ts`).

### WebSocket

| Path | Description |
|------|-------------|
| `/ws` | Live updates — message types: `pong`, `signal` (per-cycle aggregated signal with `symbol`, `direction`, `confidence`, `reason`, `indicators`, `timestamp`) |

### POST `/api/backtest` Request

```json
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "start": "2025-01-01",
  "end": "2025-06-30",
  "balance": 10000.0,
  "strategies": ["rsi", "macd", "bollinger", "ema"],
  "strategy_weights": { "rsi": 1.0, "macd": 1.5, "bollinger": 0.8, "ema": 1.2 },
  "rsi": { "period": 14, "oversold": 30, "overbought": 70 },
  "macd": { "fast": 12, "slow": 26, "signal": 9 },
  "bollinger": { "period": 20, "std_dev": 2.0 },
  "ema": { "fast_period": 9, "slow_period": 21 },
  "regime": {
    "enabled": true,
    "trending_threshold": 25.0,
    "hysteresis_buffer": 5.0,
    "trending_ema_weight": 1.5,
    "trending_mr_weight": 0.2,
    "ranging_ema_weight": 0.2,
    "ranging_mr_weight": 1.2
  },
  "min_agreement": 2,
  "hold_opposition": 0.1,
  "risk": {
    "max_position_pct": 0.10,
    "stop_loss_pct": 0.03,
    "trailing_stop_pct": 0.02,
    "max_single_order_usdt": 1000.0,
    "max_drawdown_pct": 0.15,
    "daily_loss_limit_pct": 0.05,
    "min_confidence": 0.4,
    "atr_stop_multiplier": 2.0,
    "atr_tp_multiplier": 3.0,
    "atr_trailing_multiplier": 1.5,
    "volume_min_multiplier": 1.2,
    "ema_trend_period": 50,
    "ema_trend_enabled": true,
    "risk_per_trade_pct": 0.01,
    "partial_tp_ratio": 0.5
  },
  "ai_filter": {
    "enabled": false,
    "strength": 0.5,
    "crash_lookback": 10,
    "crash_threshold_pct": -5.0,
    "volatility_multiplier": 2.0,
    "volume_spike_multiplier": 2.5,
    "recovery_boost": 1.3
  },
  "engine": {
    "fee_rate": 0.001,
    "slippage_rate": 0.0005,
    "min_confidence": 0.0,
    "cooldown_candles": 0,
    "use_dynamic_sizing": false,
    "enable_regime_filter": false,
    "adx_trending_threshold": 25.0,
    "take_profit_pct": 0.0,
    "take_profit_ratio": 0.5
  },
  "walk_forward": {
    "enabled": false,
    "n_folds": 3,
    "train_pct": 0.7,
    "step_type": "rolling"
  }
}
```

When `walk_forward.enabled` is `true`, the response includes a `walk_forward` object with `folds` and `aggregate_oos` in addition to the full-period backtest above.

### POST `/api/backtest` Response

```json
{
  "report": {
    "initial_value": 10000.0,
    "final_value": 10850.0,
    "total_return_pct": 8.5,
    "annualized_return_pct": 17.2,
    "max_drawdown_pct": 5.3,
    "sharpe_ratio": 1.24,
    "sortino_ratio": 1.89,
    "total_trades": 23,
    "winning_trades": 14,
    "losing_trades": 9,
    "win_rate": 60.9,
    "avg_trade_pnl": 36.96,
    "best_trade_pnl": 210.50,
    "worst_trade_pnl": -85.20,
    "strategy_stats": { "aggregator": { "BUY": 12, "SELL": 11, "HOLD": 3800 } },
    "ai_filter_stats": { "signals_reviewed": 0, "..." : "..." },
    "engine_stats": {
      "stop_loss_exits": 3,
      "trailing_stop_exits": 2,
      "take_profit_exits": 1,
      "partial_tp_exits": 1,
      "drawdown_halt_candle": null,
      "daily_loss_skips": 0,
      "signals_below_confidence": 5,
      "cooldown_skips": 8,
      "regime_filtered": 120,
      "volume_filtered": 15,
      "ema_filtered": 8,
      "total_fees": 23.45,
      "total_slippage": 11.22
    }
  },
  "equity_curve": [10000.0, 10002.5, "..."],
  "timestamps": ["2025-01-01T00:00:00+00:00", "..."],
  "ohlcv": [{ "time": 1735689600, "open": 42000, "high": 42500, "low": 41800, "close": 42200, "volume": 150.5 }],
  "trades": [{ "symbol": "BTC/USDT", "side": "BUY", "amount": 0.0023, "price": 42150.0, "executed_at": "2025-01-15T14:00:00+00:00", "portfolio_value": 10050.0 }],
  "walk_forward": {
    "folds": [
      {
        "fold_index": 1,
        "train_start": "...",
        "train_end": "...",
        "test_start": "...",
        "test_end": "...",
        "train_report": { "total_return_pct": 0, "sharpe_ratio": 0 },
        "test_report": { "total_return_pct": 0, "sharpe_ratio": 0 }
      }
    ],
    "aggregate_oos": {
      "avg_return_pct": 0,
      "avg_sharpe": 0,
      "n_folds": 3
    }
  }
}
```

Omitted when `walk_forward.enabled` is `false`.

---

## Data Flow Diagrams

### Live Trading Flow

```mermaid
sequenceDiagram
    participant Timer as Scheduler (60s)
    participant Engine as TradingEngine
    participant Exchange as Binance/Paper
    participant Strategies as RSI + MACD + BB + EMA
    participant Risk as RiskManager
    participant DB as SQLite

    loop Every 60 seconds
        Timer->>Engine: _tick()
        Engine->>Exchange: get_ohlcv(symbol, limit=100)
        Exchange-->>Engine: OHLCV DataFrame

        par Parallel strategy execution
            Engine->>Strategies: RSI.analyze()
            Engine->>Strategies: MACD.analyze()
            Engine->>Strategies: Bollinger.analyze()
            Engine->>Strategies: EMA.analyze()
        end

        Strategies-->>Engine: [Signal, Signal, Signal]
        Engine->>Engine: _aggregate_signals()
        Engine->>Risk: Pre-trade check

        alt Signal = BUY or SELL
            Engine->>Exchange: create_order()
            Exchange-->>Engine: Order (filled)
            Engine->>DB: save_trade()
        else Signal = HOLD
            Note over Engine: No action
        end
    end
```

### Backtest Data Flow

```mermaid
sequenceDiagram
    participant Browser as Frontend
    participant API as /api/backtest
    participant Loader as DataLoader
    participant Binance as Binance API
    participant Engine as BacktestEngine
    participant Exchange as BacktestExchange
    participant Report as ReportGenerator

    Browser->>API: POST {symbol, dates, params}
    API->>Loader: load_from_binance()
    Loader->>Binance: Fetch OHLCV (paginated)
    Binance-->>Loader: Historical candles
    Loader-->>API: DataFrame

    API->>Exchange: new BacktestExchange(ohlcv, fees)
    API->>Engine: new BacktestEngine(exchange, strategies)
    API->>Engine: run()

    loop Every candle
        Engine->>Exchange: get_portfolio_value()
        Engine->>Engine: check_position_exits()
        Engine->>Exchange: get_ohlcv(limit=100)
        Engine->>Engine: collect_signals() + aggregate()
        Engine->>Engine: AI filter + confidence/cooldown
        alt Trade
            Engine->>Exchange: create_order() [+fees +slippage]
        end
        Engine->>Exchange: advance()
    end

    Engine-->>API: BacktestResult
    API->>Report: generate_report(result)
    Report-->>API: BacktestReport
    API-->>Browser: {report, equity, ohlcv, trades}
```

---

## Environment Variables (.env)

```bash
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
ANTHROPIC_API_KEY=your_anthropic_api_key
OPENAI_API_KEY=             # Multi-LLM veto (OpenAI provider)
TELEGRAM_BOT_TOKEN=         # Optional trade / alert notifications
TELEGRAM_CHAT_ID=
TRADING_MODE=paper          # paper | live | backtest
LOG_LEVEL=INFO              # DEBUG | INFO | WARNING
```

---

## Getting Started

```bash
# Backend (API server) — required for dashboard + /api/bot/* Start/Stop
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --reload

# Frontend (dev server; proxies /api and /ws to port 8000)
cd frontend && npm run dev

# Live/Paper trading bot
python -m backend.main

# CLI backtest
python -m backend.backtest --symbol BTC/USDT --start 2025-01-01 --end 2025-06-30

# Tests
python -m pytest tests/ -v

# Lint
ruff check backend/ tests/
```

---

## Test Coverage

| Module | Test Count | Covered Functionality |
|--------|------------|----------------------|
| `tests/backtest/test_ai_filter.py` | 11 | Crash detection, recovery, strength, stats |
| `tests/backtest/test_engine.py` | 4 | Base engine execution, trending data, equity curve |
| `tests/backtest/test_engine_advanced.py` | 10 | Fees, slippage, stop-loss, trailing, cooldown, drawdown, dynamic sizing |
| `tests/backtest/test_engine_parity.py` | 30 | ATR stops/TP/trailing, volume filter, EMA filter, confidence, cooldown, drawdown halt, daily loss limit, ATR sizing, strategy weights, partial TP, percentage fallback, regime filter, multi-day reset, full cycle, min_agreement parity, EMA strategy parity |
| `tests/backtest/test_exchange.py` | 12 | Exchange balances, orders, insufficient funds |
| `tests/backtest/test_data_loader.py` | 3 | CSV round-trip, timezone handling |
| `tests/backtest/test_report.py` | 12 | Drawdown, returns, Sharpe, report generation |
| `tests/backtest/test_walk_forward.py` | 10 | Fold splitting, rolling/expanding, OOS aggregation |
| `tests/backtest/test_optimizer.py` | 12 | Optuna integration, parameter building, EMA + aggregator configs, scoring metrics, walk-forward validation |
| **Total `tests/backtest/`** | **104** | (all backtest-related modules) |
| `tests/notifications/test_telegram.py` | 11 | Telegram API payload, disabled path, session lifecycle |
| `tests/ai/test_openai_client.py` | 5 | OpenAI JSON parsing, LLMProvider |
| `tests/ai/test_veto_system.py` | 9 | Quorum, failures, timeouts |
| `tests/test_database.py` | 11 | Trades, orders, portfolio snapshots, signal log insert/query/filters |
| `tests/core/test_engine.py` | 35+ | Signal aggregation, tick execution, ATR stops, volume filter, EMA trend, strategy weights, partial TP, min_agreement, hold_opposition |
| `tests/core/test_engine_scenarios.py` | 63 | End-to-end scenarios: slippage, whipsaw, flash crash, exchange errors, multi-position, halt persistence |
| `tests/api/test_routes.py` | 13 | REST endpoints: health, config, trades, orders, portfolio, signals |
| `tests/strategies/test_ema_strategy.py` | 8 | EMA crossover: bullish/bearish signals, HOLD, confidence scaling, config |
| `core/regime.py` | 23 | Regime classification, hysteresis, weight maps, ATR percentile |
| `tests/` (all) | **419** | Full suite — `pytest tests/ -v` |
