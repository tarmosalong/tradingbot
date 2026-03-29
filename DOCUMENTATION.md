# Trading Bot — Complete Technical Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Project Structure](#project-structure)
4. [Configuration](#configuration)
5. [Backend Modules](#backend-modules)
6. [Strategies](#strategies)
7. [Backtest System](#backtest-system)
8. [AI Integration](#ai-integration)
9. [Risk Management](#risk-management)
10. [Frontend](#frontend)
11. [API Reference](#api-reference)
12. [Data Flow Diagrams](#data-flow-diagrams)

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
- AI: Anthropic Claude Opus 4.6
- Indicators: pandas-ta
- Database: SQLite (aiosqlite)

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
    AGG --> RSI & MACD & BOLL
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
│   │   └── runner.py           # CLI backtest runner
│   ├── core/
│   │   ├── engine.py           # TradingEngine (live loop)
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
│   │   ├── technical.py        # RSI, MACD, Bollinger
│   │   ├── ai_strategy.py      # Claude AI strategy
│   │   └── sentiment.py        # News sentiment strategy
│   ├── ai/
│   │   ├── claude_client.py    # Anthropic API wrapper
│   │   ├── market_analyzer.py  # Market analysis with prompts
│   │   ├── sentiment_analyzer.py # News sentiment
│   │   └── prompts.py          # System + user prompts
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
| `enabled` | list[str] | `["rsi", "macd", "bollinger"]` | Active strategies |
| `rsi` | RSIConfig | — | RSI parameters |
| `macd` | MACDConfig | — | MACD parameters |
| `bollinger` | BollingerConfig | — | Bollinger parameters |

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

#### AIConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | str | `"claude-opus-4-6"` | Claude model ID |
| `max_calls_per_minute` | int | `10` | API rate limit |
| `analysis_cache_ttl_seconds` | int | `300` | Market analysis cache TTL |
| `sentiment_cache_ttl_seconds` | int | `900` | Sentiment cache TTL |
| `max_tokens_analysis` | int | `4096` | Max tokens for analysis |
| `max_tokens_sentiment` | int | `1024` | Max tokens for sentiment |

#### RiskConfig
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_position_pct` | float | `0.10` | Max position size (% of balance) |
| `stop_loss_pct` | float | `0.03` | Fixed stop-loss % |
| `trailing_stop_pct` | float | `0.02` | Trailing stop % from peak |
| `max_drawdown_pct` | float | `0.15` | Max drawdown before trading halt |
| `daily_loss_limit_pct` | float | `0.05` | Daily loss limit |
| `max_single_order_usdt` | float | `1000.0` | Max single order value in USDT |

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

    RSI --> |"Signal"| AGG["Aggregator<br/>Weighted vote"]
    MACD --> |"Signal"| AGG
    BOLL --> |"Signal"| AGG

    AGG --> |"Combined Signal"| FILTER["AI Filter<br/>(optional)"]
    FILTER --> |"Final Signal"| EXEC["Execute or HOLD"]
```

### Signal Aggregation

```mermaid
graph TD
    SIG["All non-HOLD<br/>signals"] --> WEIGHT["Compute weights<br/>BUY weight = Σ confidence<br/>SELL weight = Σ confidence"]
    WEIGHT --> CMP{"BUY > SELL?"}
    CMP -->|Yes| BUY_DIR["Direction = BUY<br/>Avg confidence"]
    CMP -->|No| CMP2{"SELL > BUY?"}
    CMP2 -->|Yes| SELL_DIR["Direction = SELL<br/>Avg confidence"]
    CMP2 -->|Tie| HOLD["Direction = HOLD"]
    BUY_DIR --> FINAL["Aggregated Signal"]
    SELL_DIR --> FINAL
    HOLD --> FINAL
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

## Risk Management

### Risk Controls in Backtest

```mermaid
graph TD
    SIGNAL["Aggregated<br/>signal"] --> CONF{"Confidence<br/>>= min?"}
    CONF -->|No| SKIP1["Skip: too weak"]
    CONF -->|Yes| CD{"Cooldown<br/>passed?"}
    CD -->|No| SKIP2["Skip: cooldown"]
    CD -->|Yes| SIZE["Compute size<br/>max_position_pct<br/>× confidence (dynamic)"]
    SIZE --> CAP["Cap: max_single_order_usdt"]
    CAP --> EXEC["Create Order<br/>+ fee + slippage"]
    EXEC --> POS["Position tracked"]

    POS --> |"Every candle"| SL{"low ≤ entry<br/>× (1 - stop_loss)?"}
    SL -->|Yes| EXIT_SL["Force SELL<br/>stop-loss"]
    SL -->|No| TS{"low ≤ peak<br/>× (1 - trailing_stop)?"}
    TS -->|Yes| EXIT_TS["Force SELL<br/>trailing stop"]
    TS -->|No| TP{"high ≥ entry<br/>× (1 + take_profit)?"}
    TP -->|Yes| EXIT_TP["Partial SELL<br/>take-profit"]
    TP -->|No| CONT["Continue"]

    DD{"Portfolio drawdown<br/>> max_drawdown?"}
    DD -->|Yes| HALT["CIRCUIT BREAKER<br/>Trading halted"]
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
    DASH --> CP["ConfigPanel<br/>Bot settings"]
    DASH --> TT["TradesTable<br/>Recent trades"]

    BTP --> FORM["Input Form<br/>Symbol, dates, balance"]
    BTP --> STRAT["Strategy Toggles<br/>RSI, MACD, Bollinger"]
    BTP --> AITOGGLE["AI Crash Filter<br/>Toggle + Strength"]
    BTP --> ADV["Advanced Settings"]
    BTP --> RESULTS["Results"]

    ADV --> COSTS["Trading Costs<br/>Fee, Slippage, Min conf, Cooldown"]
    ADV --> POSMGMT["Position Mgmt<br/>Dynamic sizing, ADX, TP"]
    ADV --> RISK["Risk Mgmt<br/>Stop-loss, Trailing, Max order"]
    ADV --> STRAT_P["Strategy Params<br/>RSI/MACD/Bollinger sliders"]
    ADV --> AI_P["AI Filter Params<br/>Crash lookback, thresholds"]

    RESULTS --> CARDS["Stat Cards<br/>Return, Sharpe, Win rate..."]
    RESULTS --> CANDLE["CandlestickChart<br/>+ Trade markers"]
    RESULTS --> EQUITY["Equity Curve<br/>Recharts area"]
    RESULTS --> AISTATS["AI Filter Stats"]
    RESULTS --> ENGSTATS["Engine Stats<br/>Fees, stops, skips"]
    RESULTS --> SIGSPLIT["Strategy Signals<br/>BUY/SELL/HOLD bars"]
    RESULTS --> TRADES["Trade History<br/>Table"]
```

---

## API Reference

### REST Endpoints

All REST endpoints are prefixed with `/api`.

| Method | Path | Parameters | Response |
|--------|------|------------|----------|
| `GET` | `/api/health` | — | `{"status": "ok"}` |
| `GET` | `/api/config` | — | Bot configuration (mode, pairs, risk etc) |
| `GET` | `/api/trades` | `?symbol=&limit=50` | List of trades |
| `GET` | `/api/orders` | `?symbol=` | Open orders |
| `GET` | `/api/portfolio` | `?limit=100` | Portfolio history |
| `POST` | `/api/backtest` | JSON body (see below) | Report + equity + OHLCV + trades |

### WebSocket

| Path | Description |
|------|-------------|
| `/ws` | Live updates (trades, portfolio changes) |

### POST `/api/backtest` Request

```json
{
  "symbol": "BTC/USDT",
  "timeframe": "1h",
  "start": "2025-01-01",
  "end": "2025-06-30",
  "balance": 10000.0,
  "strategies": ["rsi", "macd", "bollinger"],
  "rsi": { "period": 14, "oversold": 30, "overbought": 70 },
  "macd": { "fast": 12, "slow": 26, "signal": 9 },
  "bollinger": { "period": 20, "std_dev": 2.0 },
  "risk": {
    "max_position_pct": 0.10,
    "stop_loss_pct": 0.03,
    "trailing_stop_pct": 0.02,
    "max_single_order_usdt": 1000.0
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
  }
}
```

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
      "drawdown_halt_candle": null,
      "signals_below_confidence": 5,
      "cooldown_skips": 8,
      "regime_filtered": 120,
      "total_fees": 23.45,
      "total_slippage": 11.22
    }
  },
  "equity_curve": [10000.0, 10002.5, "..."],
  "timestamps": ["2025-01-01T00:00:00+00:00", "..."],
  "ohlcv": [{ "time": 1735689600, "open": 42000, "high": 42500, "low": 41800, "close": 42200, "volume": 150.5 }],
  "trades": [{ "symbol": "BTC/USDT", "side": "BUY", "amount": 0.0023, "price": 42150.0, "executed_at": "2025-01-15T14:00:00+00:00", "portfolio_value": 10050.0 }]
}
```

---

## Data Flow Diagrams

### Live Trading Flow

```mermaid
sequenceDiagram
    participant Timer as Scheduler (60s)
    participant Engine as TradingEngine
    participant Exchange as Binance/Paper
    participant Strategies as RSI + MACD + BB
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
TRADING_MODE=paper          # paper | live | backtest
LOG_LEVEL=INFO              # DEBUG | INFO | WARNING
```

---

## Getting Started

```bash
# Backend (API server)
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000

# Frontend (dev server)
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
| `tests/backtest/test_exchange.py` | 11 | Exchange balances, orders, insufficient funds |
| `tests/backtest/test_data_loader.py` | 3 | CSV round-trip, timezone handling |
| `tests/backtest/test_report.py` | 7 | Drawdown, returns, Sharpe, report generation |
| **Total backtest** | **46** | |
| `tests/` (all) | **52+** | + core engine, strategies, AI, API, database |
