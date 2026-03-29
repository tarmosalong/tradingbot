import { useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { CandlestickChart } from './CandlestickChart';
import type { OhlcvCandle, TradeMarker } from './CandlestickChart';

interface AIFilterStats {
  signals_reviewed: number;
  signals_blocked: number;
  signals_reduced: number;
  signals_boosted: number;
  crash_detections: number;
  volatility_detections: number;
  volume_spike_detections: number;
  recovery_detections: number;
}

interface EngineStats {
  stop_loss_exits: number;
  trailing_stop_exits: number;
  take_profit_exits: number;
  drawdown_halt_candle: number | null;
  signals_below_confidence: number;
  cooldown_skips: number;
  regime_filtered: number;
  total_fees: number;
  total_slippage: number;
}

interface BacktestReport {
  initial_value: number;
  final_value: number;
  total_return_pct: number;
  annualized_return_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  avg_trade_pnl: number;
  best_trade_pnl: number;
  worst_trade_pnl: number;
  strategy_stats?: Record<string, Record<string, number>>;
  ai_filter_stats?: AIFilterStats;
  engine_stats?: EngineStats;
}

interface BacktestTrade {
  symbol: string;
  side: string;
  amount: number;
  price: number;
  executed_at: string;
  portfolio_value: number;
}

interface WalkForwardFold {
  fold_index: number;
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  train_report: BacktestReport;
  test_report: BacktestReport;
}

interface WalkForwardResult {
  folds: WalkForwardFold[];
  aggregate_oos: {
    avg_return_pct: number;
    avg_sharpe: number;
    avg_max_drawdown_pct: number;
    avg_win_rate: number;
    worst_return_pct: number;
    best_return_pct: number;
    n_folds: number;
  };
}

interface BacktestResult {
  report: BacktestReport;
  equity_curve: number[];
  timestamps: string[];
  ohlcv: OhlcvCandle[];
  trades: BacktestTrade[];
  walk_forward?: WalkForwardResult;
}

const AVAILABLE_STRATEGIES = [
  {
    id: 'rsi',
    label: 'RSI',
    description: 'Relative Strength Index – Momentum oscillator (0–100) that identifies overbought/oversold conditions. Generates BUY when below oversold threshold, SELL when above overbought.',
  },
  {
    id: 'macd',
    label: 'MACD',
    description: 'Moving Average Convergence Divergence – Trend-following indicator that tracks the relationship between two moving averages. Generates signals on histogram crossovers (bullish/bearish momentum shifts).',
  },
  {
    id: 'bollinger',
    label: 'Bollinger',
    description: 'Bollinger Bands – Volatility-based bands around a moving average. Generates BUY when price drops below lower band (oversold), SELL when price rises above upper band (overbought).',
  },
] as const;

const POPULAR_SYMBOLS = [
  'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT',
  'XRP/USDT', 'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT',
];

export function BacktestPanel() {
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [start, setStart] = useState('2025-01-01');
  const [end, setEnd] = useState('2025-06-30');
  const [balance, setBalance] = useState('10000');
  const [enabledStrategies, setEnabledStrategies] = useState<Set<string>>(
    new Set(['rsi', 'macd', 'bollinger']),
  );
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [rsiOversold, setRsiOversold] = useState(30);
  const [rsiOverbought, setRsiOverbought] = useState(70);

  const [macdFast, setMacdFast] = useState(12);
  const [macdSlow, setMacdSlow] = useState(26);
  const [macdSignal, setMacdSignal] = useState(9);

  const [bollPeriod, setBollPeriod] = useState(20);
  const [bollStdDev, setBollStdDev] = useState(2.0);

  const [riskMaxPos, setRiskMaxPos] = useState(10);
  const [riskStopLoss, setRiskStopLoss] = useState(3);
  const [riskTrailingStop, setRiskTrailingStop] = useState(2);
  const [riskMaxOrder, setRiskMaxOrder] = useState(1000);

  const [feeRate, setFeeRate] = useState(0.1);
  const [slippageRate, setSlippageRate] = useState(0.05);
  const [minConfidence, setMinConfidence] = useState(0);
  const [cooldownCandles, setCooldownCandles] = useState(0);
  const [dynamicSizing, setDynamicSizing] = useState(false);
  const [regimeFilter, setRegimeFilter] = useState(false);
  const [adxThreshold, setAdxThreshold] = useState(25);
  const [takeProfitPct, setTakeProfitPct] = useState(0);
  const [takeProfitRatio, setTakeProfitRatio] = useState(50);

  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiStrength, setAiStrength] = useState(0.5);
  const [aiCrashLookback, setAiCrashLookback] = useState(10);
  const [aiCrashThreshold, setAiCrashThreshold] = useState(-5);
  const [aiVolMultiplier, setAiVolMultiplier] = useState(2.0);
  const [aiVolSpikeMultiplier, setAiVolSpikeMultiplier] = useState(2.5);
  const [aiRecoveryBoost, setAiRecoveryBoost] = useState(1.3);

  const [wfEnabled, setWfEnabled] = useState(false);
  const [wfFolds, setWfFolds] = useState(3);
  const [wfTrainPct, setWfTrainPct] = useState(70);
  const [wfStepType, setWfStepType] = useState<'rolling' | 'expanding'>('rolling');

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const toggleStrategy = (id: string) => {
    setEnabledStrategies((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        if (next.size > 1) next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const runBacktest = async () => {
    if (!start || !end) {
      setError('Start and end dates are required');
      return;
    }
    if (!symbol) {
      setError('Symbol is required');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    setElapsed(0);

    const t0 = Date.now();
    const timer = setInterval(() => setElapsed(Date.now() - t0), 100);

    try {
      const res = await fetch('/api/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          timeframe,
          start,
          end,
          balance: parseFloat(balance),
          strategies: Array.from(enabledStrategies),
          rsi: { period: rsiPeriod, oversold: rsiOversold, overbought: rsiOverbought },
          macd: { fast: macdFast, slow: macdSlow, signal: macdSignal },
          bollinger: { period: bollPeriod, std_dev: bollStdDev },
          risk: {
            max_position_pct: riskMaxPos / 100,
            stop_loss_pct: riskStopLoss / 100,
            trailing_stop_pct: riskTrailingStop / 100,
            max_single_order_usdt: riskMaxOrder,
          },
          ai_filter: {
            enabled: aiEnabled,
            strength: aiStrength,
            crash_lookback: aiCrashLookback,
            crash_threshold_pct: aiCrashThreshold,
            volatility_multiplier: aiVolMultiplier,
            volume_spike_multiplier: aiVolSpikeMultiplier,
            recovery_boost: aiRecoveryBoost,
          },
          engine: {
            fee_rate: feeRate / 100,
            slippage_rate: slippageRate / 100,
            min_confidence: minConfidence / 100,
            cooldown_candles: cooldownCandles,
            use_dynamic_sizing: dynamicSizing,
            enable_regime_filter: regimeFilter,
            adx_trending_threshold: adxThreshold,
            take_profit_pct: takeProfitPct / 100,
            take_profit_ratio: takeProfitRatio / 100,
          },
          walk_forward: {
            enabled: wfEnabled,
            n_folds: wfFolds,
            train_pct: wfTrainPct / 100,
            step_type: wfStepType,
          },
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        setError(`Server error (${res.status}): ${text.slice(0, 200)}`);
        return;
      }
      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setResult(data);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Backtest failed');
    } finally {
      clearInterval(timer);
      setLoading(false);
    }
  };

  const equityChartData =
    result?.equity_curve.map((value, i) => ({
      time: result.timestamps[i]
        ? new Date(result.timestamps[i]).toLocaleDateString()
        : String(i),
      value,
    })) ?? [];

  const isUp = result ? result.report.total_return_pct >= 0 : true;

  const tradeMarkers: TradeMarker[] =
    result?.trades.map((t) => ({
      time: Math.floor(new Date(t.executed_at).getTime() / 1000),
      side: t.side,
      price: t.price,
      amount: t.amount,
    })) ?? [];

  return (
    <div className="space-y-4">
      {/* Config panel */}
      <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)] p-4">
        <h2 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
          Run Backtest
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <div title="Crypto trading pair to backtest. The base currency is traded against USDT stablecoin.">
            <label className="block text-xs text-[var(--text-secondary)] mb-1 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help">Symbol</label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
            >
              {POPULAR_SYMBOLS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div title="Candle interval for the price data. Smaller = more data points and more signals. 1h is a good starting point.">
            <label className="block text-xs text-[var(--text-secondary)] mb-1 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help">Timeframe</label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
            >
              <option value="15m">15m</option>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>
          </div>
          <div title="Start date for historical data. Data is downloaded from Binance. Longer periods = more accurate results but slower.">
            <label className="block text-xs text-[var(--text-secondary)] mb-1 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help">Start</label>
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
            />
          </div>
          <div title="End date for historical data. Use a past date — backtest simulates trading over this historical period.">
            <label className="block text-xs text-[var(--text-secondary)] mb-1 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help">End</label>
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
            />
          </div>
          <div title="Starting portfolio balance in USDT. This is the simulated money you begin trading with.">
            <label className="block text-xs text-[var(--text-secondary)] mb-1 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help">Balance (USDT)</label>
            <input
              value={balance}
              onChange={(e) => setBalance(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
            />
          </div>
        </div>

        <div className="mt-3">
          <label className="block text-xs text-[var(--text-secondary)] mb-2 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help" title="Technical analysis strategies used to generate BUY/SELL/HOLD signals. Multiple strategies are combined — a trade is executed when they agree.">
            Strategies
          </label>
          <div className="flex flex-wrap gap-2">
            {AVAILABLE_STRATEGIES.map((s) => {
              const active = enabledStrategies.has(s.id);
              return (
                <button
                  key={s.id}
                  onClick={() => toggleStrategy(s.id)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer border ${
                    active
                      ? 'bg-[var(--accent-blue)]/15 border-[var(--accent-blue)] text-[var(--accent-blue)]'
                      : 'bg-[var(--bg-secondary)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--text-secondary)]'
                  }`}
                  title={s.description}
                >
                  {active ? '\u2713 ' : ''}{s.label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="mt-3">
          <div className="flex items-center gap-3">
            <label
              className="flex items-center gap-2 cursor-pointer select-none"
              title="Simulated AI filter that detects crash conditions (rapid price drops, high volatility, volume spikes) and adjusts signal confidence. Blocks risky BUY signals during market crashes and boosts SELL signals. Does not call any API — uses mathematical heuristics to approximate what an AI model would decide."
            >
              <input
                type="checkbox"
                checked={aiEnabled}
                onChange={(e) => setAiEnabled(e.target.checked)}
                className="w-4 h-4 rounded accent-[var(--accent-purple,#a855f7)] cursor-pointer"
              />
              <span className="text-sm font-medium text-[var(--accent-purple,#a855f7)] border-b border-dotted border-[var(--accent-purple,#a855f7)]/40 cursor-help">
                AI Crash Filter
              </span>
            </label>
            {aiEnabled && (
              <div className="flex items-center gap-2" title="How aggressively the AI filter modifies signals. 0 = no effect, 1 = maximum filtering. At 0.5 a detected crash reduces BUY confidence by ~50%.">
                <span className="text-xs text-[var(--text-secondary)]">Strength:</span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={aiStrength}
                  onChange={(e) => setAiStrength(Number(e.target.value))}
                  className="w-24 h-1.5 rounded-full appearance-none cursor-pointer accent-[var(--accent-purple,#a855f7)] bg-[var(--bg-secondary)]"
                />
                <span className="text-xs font-mono text-[var(--accent-purple,#a855f7)]">{aiStrength.toFixed(2)}</span>
              </div>
            )}
          </div>
        </div>

        <div className="mt-3">
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
          >
            {showAdvanced ? '\u25BC' : '\u25B6'} Advanced Settings
          </button>
        </div>

        {showAdvanced && (
          <div className="mt-3 space-y-4 border-t border-[var(--border)] pt-4">
            {enabledStrategies.has('rsi') && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent-blue)] mb-2">RSI Parameters</h3>
                <div className="grid grid-cols-3 gap-3">
                  <ParamInput label="Period" value={rsiPeriod} onChange={setRsiPeriod} min={2} max={50} tooltip="Number of candles used to calculate RSI. Lower = more sensitive, higher = smoother. Default: 14" />
                  <ParamInput label="Oversold" value={rsiOversold} onChange={setRsiOversold} min={5} max={45} tooltip="RSI level below which the asset is considered oversold (BUY signal). Typical range: 20–35. Default: 30" />
                  <ParamInput label="Overbought" value={rsiOverbought} onChange={setRsiOverbought} min={55} max={95} tooltip="RSI level above which the asset is considered overbought (SELL signal). Typical range: 65–80. Default: 70" />
                </div>
              </div>
            )}

            {enabledStrategies.has('macd') && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent-blue)] mb-2">MACD Parameters</h3>
                <div className="grid grid-cols-3 gap-3">
                  <ParamInput label="Fast EMA" value={macdFast} onChange={setMacdFast} min={2} max={50} tooltip="Period for the fast Exponential Moving Average. Shorter period reacts faster to price changes. Default: 12" />
                  <ParamInput label="Slow EMA" value={macdSlow} onChange={setMacdSlow} min={10} max={100} tooltip="Period for the slow Exponential Moving Average. Longer period smooths out noise. Must be larger than fast EMA. Default: 26" />
                  <ParamInput label="Signal" value={macdSignal} onChange={setMacdSignal} min={2} max={50} tooltip="Period for the signal line (EMA of MACD line). Used to detect crossovers. Lower = more signals. Default: 9" />
                </div>
              </div>
            )}

            {enabledStrategies.has('bollinger') && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent-blue)] mb-2">Bollinger Bands Parameters</h3>
                <div className="grid grid-cols-2 gap-3">
                  <ParamInput label="Period" value={bollPeriod} onChange={setBollPeriod} min={5} max={50} tooltip="Number of candles for the moving average that forms the middle band. Lower = tighter bands, higher = smoother. Default: 20" />
                  <ParamInput label="Std Dev" value={bollStdDev} onChange={setBollStdDev} min={0.5} max={4} step={0.1} tooltip="Number of standard deviations for the upper/lower bands. Higher = wider bands = fewer signals. Typical range: 1.5–2.5. Default: 2.0" />
                </div>
              </div>
            )}

            {aiEnabled && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent-purple,#a855f7)] mb-2">AI Crash Filter Parameters</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  <ParamInput label="Crash Lookback" value={aiCrashLookback} onChange={setAiCrashLookback} min={3} max={30} tooltip="Number of candles to look back when detecting a price crash. Lower = more sensitive to short-term drops. Default: 10" />
                  <ParamInput label="Crash Threshold %" value={aiCrashThreshold} onChange={setAiCrashThreshold} min={-20} max={-1} tooltip="Price drop percentage that triggers crash detection. E.g. -5 means a 5% drop over the lookback period is flagged as a crash. Default: -5%" />
                  <ParamInput label="Volatility Mult." value={aiVolMultiplier} onChange={setAiVolMultiplier} min={1} max={5} step={0.1} tooltip="How much higher recent volatility must be compared to the long-term average to trigger a warning. 2.0 = recent volatility must be 2x normal. Default: 2.0" />
                  <ParamInput label="Volume Spike Mult." value={aiVolSpikeMultiplier} onChange={setAiVolSpikeMultiplier} min={1} max={5} step={0.1} tooltip="How much higher the current volume must be vs 20-candle average to flag a panic sell. Only triggers when price is also falling. Default: 2.5" />
                  <ParamInput label="Recovery Boost" value={aiRecoveryBoost} onChange={setAiRecoveryBoost} min={1} max={2} step={0.05} tooltip="Confidence multiplier applied to BUY signals during recovery (price bouncing back after a crash). 1.3 = 30% confidence boost. Default: 1.3" />
                </div>
              </div>
            )}

            <div>
              <h3 className="text-xs font-medium text-[var(--accent-yellow,#eab308)] mb-2">Trading Costs (Realism)</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <ParamInput label="Fee Rate %" value={feeRate} onChange={setFeeRate} min={0} max={0.5} step={0.01} tooltip="Exchange fee per trade as percentage. Binance default: 0.1% (maker/taker). Set to 0 for zero-fee simulation. Default: 0.1%" />
                <ParamInput label="Slippage %" value={slippageRate} onChange={setSlippageRate} min={0} max={0.5} step={0.01} tooltip="Estimated price slippage per trade. BUY price is increased, SELL price decreased by this amount. Real markets: 0.01–0.3%. Default: 0.05%" />
                <ParamInput label="Min Confidence %" value={minConfidence} onChange={setMinConfidence} min={0} max={90} tooltip="Minimum aggregated signal confidence required to execute a trade. Filters out weak signals. 0 = no filter, 60 = only strong signals. Default: 0" />
                <ParamInput label="Cooldown (candles)" value={cooldownCandles} onChange={setCooldownCandles} min={0} max={50} tooltip="Minimum number of candles between trades. Prevents rapid-fire trading that racks up fees. 0 = no cooldown. Default: 0" />
              </div>
            </div>

            <div>
              <h3 className="text-xs font-medium text-[var(--accent-yellow,#eab308)] mb-2">Position Management</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="flex items-center gap-2" title="Scale position size by signal confidence. High-confidence signals get larger positions, low-confidence get smaller.">
                  <input type="checkbox" checked={dynamicSizing} onChange={(e) => setDynamicSizing(e.target.checked)} className="w-4 h-4 rounded accent-[var(--accent-yellow,#eab308)] cursor-pointer" />
                  <span className="text-xs text-[var(--text-secondary)] border-b border-dotted border-[var(--text-secondary)]/40 cursor-help">Dynamic Sizing</span>
                </div>
                <div className="flex items-center gap-2" title="Skip mean-reversion signals (RSI, Bollinger) when ADX indicates a strong trend. Prevents buying dips in a crash or selling rallies in a bull run.">
                  <input type="checkbox" checked={regimeFilter} onChange={(e) => setRegimeFilter(e.target.checked)} className="w-4 h-4 rounded accent-[var(--accent-yellow,#eab308)] cursor-pointer" />
                  <span className="text-xs text-[var(--text-secondary)] border-b border-dotted border-[var(--text-secondary)]/40 cursor-help">ADX Regime Filter</span>
                </div>
                {regimeFilter && (
                  <ParamInput label="ADX Threshold" value={adxThreshold} onChange={setAdxThreshold} min={15} max={50} tooltip="ADX value above which the market is considered trending and mean-reversion signals are filtered. 20–25 = moderate trend, 30+ = strong trend. Default: 25" />
                )}
                <ParamInput label="Take Profit %" value={takeProfitPct} onChange={setTakeProfitPct} min={0} max={50} tooltip="Automatically sell a portion of the position when price rises this much above entry. 0 = disabled. Default: 0%" />
                {takeProfitPct > 0 && (
                  <ParamInput label="TP Sell Ratio %" value={takeProfitRatio} onChange={setTakeProfitRatio} min={10} max={100} tooltip="What percentage of the position to sell at take-profit. 50 = sell half, 100 = sell all. Default: 50%" />
                )}
              </div>
            </div>

            <div>
              <h3 className="text-xs font-medium text-[var(--accent-blue)] mb-2">Walk-Forward Validation</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="flex items-center gap-2" title="Split the data into sequential train/test folds to detect overfitting. Shows how the strategy performs on unseen data.">
                  <input type="checkbox" checked={wfEnabled} onChange={(e) => setWfEnabled(e.target.checked)} className="w-4 h-4 rounded accent-[var(--accent-blue)] cursor-pointer" />
                  <span className="text-xs text-[var(--text-secondary)] border-b border-dotted border-[var(--text-secondary)]/40 cursor-help">Enable</span>
                </div>
                {wfEnabled && (
                  <>
                    <ParamInput label="Folds" value={wfFolds} onChange={setWfFolds} min={2} max={10} tooltip="Number of sequential train/test splits. More folds = more robust validation but slower. Default: 3" />
                    <ParamInput label="Train %" value={wfTrainPct} onChange={setWfTrainPct} min={50} max={90} tooltip="Percentage of each fold used for training. The rest is the out-of-sample test set. Default: 70%" />
                    <div title="Rolling: each fold is a separate data chunk. Expanding: training window grows with each fold.">
                      <label className="block text-xs text-[var(--text-secondary)] mb-1 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help">Step Type</label>
                      <select value={wfStepType} onChange={(e) => setWfStepType(e.target.value as 'rolling' | 'expanding')} className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1 text-sm">
                        <option value="rolling">Rolling</option>
                        <option value="expanding">Expanding</option>
                      </select>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div>
              <h3 className="text-xs font-medium text-[var(--accent-red)] mb-2">Risk Management</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <ParamInput label="Max Position %" value={riskMaxPos} onChange={setRiskMaxPos} min={1} max={100} tooltip="Maximum percentage of available balance that can be used for a single position. Lower = more conservative. Default: 10%" />
                <ParamInput label="Stop Loss %" value={riskStopLoss} onChange={setRiskStopLoss} min={0.5} max={20} step={0.5} tooltip="Fixed stop-loss percentage below purchase price. Position is closed if price drops this much. Default: 3%" />
                <ParamInput label="Trailing Stop %" value={riskTrailingStop} onChange={setRiskTrailingStop} min={0.5} max={20} step={0.5} tooltip="Dynamic stop that follows price upward. Locks in profits while allowing upside. Triggers if price drops this % from its peak. Default: 2%" />
                <ParamInput label="Max Order (USDT)" value={riskMaxOrder} onChange={setRiskMaxOrder} min={10} max={100000} step={10} tooltip="Maximum value (in USDT) for a single order. Prevents any one trade from being too large. Default: $1,000" />
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center gap-3 mt-3">
          <button
            onClick={runBacktest}
            disabled={loading}
            className="px-4 py-2 bg-[var(--accent-blue)] text-white rounded text-sm font-medium hover:opacity-90 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
          >
            {loading ? 'Running...' : 'Run Backtest'}
          </button>
          {loading && (
            <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
              <LoadingSpinner />
              <span>Downloading data & running strategies... {(elapsed / 1000).toFixed(1)}s</span>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-[var(--accent-red)]/10 border border-[var(--accent-red)]/30 rounded-lg px-4 py-3 text-sm text-[var(--accent-red)]">
          {error}
        </div>
      )}

      {result && (
        <>
          {/* Stats cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard
              label="Total Return"
              value={`${result.report.total_return_pct >= 0 ? '+' : ''}${result.report.total_return_pct.toFixed(2)}%`}
              color={isUp ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}
              tooltip="Overall profit or loss percentage over the entire backtest period relative to the starting balance."
            />
            <StatCard
              label="Max Drawdown"
              value={`${result.report.max_drawdown_pct.toFixed(2)}%`}
              color="text-[var(--accent-red)]"
              tooltip="Largest peak-to-trough decline in portfolio value. Measures the worst-case scenario during the period. Lower is better."
            />
            <StatCard
              label="Sharpe Ratio"
              value={result.report.sharpe_ratio.toFixed(3)}
              tooltip="Risk-adjusted return metric. Measures excess return per unit of volatility. > 1.0 is good, > 2.0 is very good, > 3.0 is excellent."
            />
            <StatCard
              label="Win Rate"
              value={`${result.report.win_rate.toFixed(1)}%`}
              tooltip="Percentage of trades that were profitable. Note: a high win rate with small wins and large losses can still lose money."
            />
            <StatCard
              label="Total Trades"
              value={String(result.report.total_trades)}
              tooltip="Total number of executed trades (buys and sells). More trades = higher fees but potentially more opportunities captured."
            />
            <StatCard
              label="Avg Trade P&L"
              value={`$${result.report.avg_trade_pnl.toFixed(2)}`}
              color={result.report.avg_trade_pnl >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}
              tooltip="Average profit or loss per trade in USD. Shows the expected value of each trade."
            />
            <StatCard
              label="Best Trade"
              value={`$${result.report.best_trade_pnl.toFixed(2)}`}
              color="text-[var(--accent-green)]"
              tooltip="Most profitable single trade during the backtest period."
            />
            <StatCard
              label="Worst Trade"
              value={`$${result.report.worst_trade_pnl.toFixed(2)}`}
              color="text-[var(--accent-red)]"
              tooltip="Biggest loss from a single trade during the backtest period."
            />
          </div>

          {/* Candlestick chart with trade markers */}
          {result.ohlcv && result.ohlcv.length > 0 && (
            <CandlestickChart
              ohlcv={result.ohlcv}
              trades={tradeMarkers}
              equityCurve={result.equity_curve}
            />
          )}

          {/* Equity curve */}
          <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
            <h2 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
              Equity Curve
            </h2>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={equityChartData}>
                <defs>
                  <linearGradient id="btGradUp" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent-green)" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="var(--accent-green)" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="btGradDown" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent-red)" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="var(--accent-red)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="time"
                  tick={{ fill: 'var(--text-secondary)', fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v: number) => `$${v.toLocaleString()}`}
                  domain={['dataMin', 'dataMax']}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border)',
                    borderRadius: 6,
                    color: 'var(--text-primary)',
                  }}
                  formatter={(value) => [`$${Number(value).toLocaleString()}`, 'Portfolio']}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke={isUp ? 'var(--accent-green)' : 'var(--accent-red)'}
                  fill={isUp ? 'url(#btGradUp)' : 'url(#btGradDown)'}
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Strategy signals breakdown */}
          {result.report.strategy_stats && Object.keys(result.report.strategy_stats).length > 0 && (
            <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
              <h2 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
                Strategy Signals
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {Object.entries(result.report.strategy_stats).map(([name, stats]) => {
                  const total = (stats.BUY ?? 0) + (stats.SELL ?? 0) + (stats.HOLD ?? 0);
                  const buyPct = total > 0 ? ((stats.BUY ?? 0) / total) * 100 : 0;
                  const sellPct = total > 0 ? ((stats.SELL ?? 0) / total) * 100 : 0;
                  const holdPct = total > 0 ? ((stats.HOLD ?? 0) / total) * 100 : 0;

                  return (
                    <div key={name} className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium capitalize">{name}</span>
                        <span className="text-xs text-[var(--text-secondary)]">{total} signals</span>
                      </div>
                      <div className="flex h-2 rounded-full overflow-hidden bg-[var(--bg-secondary)]">
                        <div
                          className="bg-[var(--accent-green)]"
                          style={{ width: `${buyPct}%` }}
                          title={`BUY: ${stats.BUY ?? 0}`}
                        />
                        <div
                          className="bg-[var(--accent-red)]"
                          style={{ width: `${sellPct}%` }}
                          title={`SELL: ${stats.SELL ?? 0}`}
                        />
                        <div
                          className="bg-gray-500"
                          style={{ width: `${holdPct}%` }}
                          title={`HOLD: ${stats.HOLD ?? 0}`}
                        />
                      </div>
                      <div className="flex justify-between text-xs text-[var(--text-secondary)]">
                        <span className="text-[var(--accent-green)]">BUY {stats.BUY ?? 0}</span>
                        <span className="text-[var(--accent-red)]">SELL {stats.SELL ?? 0}</span>
                        <span>HOLD {stats.HOLD ?? 0}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* AI Filter stats */}
          {result.report.ai_filter_stats && result.report.ai_filter_stats.signals_reviewed > 0 && (
            <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--accent-purple,#a855f7)]/30">
              <h2 className="text-sm font-medium text-[var(--accent-purple,#a855f7)] mb-3">
                AI Crash Filter Results
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <AIStatItem
                  label="Signals Reviewed"
                  value={result.report.ai_filter_stats.signals_reviewed}
                  tooltip="Total BUY/SELL signals that the AI filter evaluated."
                />
                <AIStatItem
                  label="Blocked"
                  value={result.report.ai_filter_stats.signals_blocked}
                  color="text-[var(--accent-red)]"
                  tooltip="BUY signals converted to HOLD because confidence dropped below threshold during risky conditions."
                />
                <AIStatItem
                  label="Reduced"
                  value={result.report.ai_filter_stats.signals_reduced}
                  color="text-[var(--accent-yellow,#eab308)]"
                  tooltip="Signals that still executed but with lowered confidence (smaller position size)."
                />
                <AIStatItem
                  label="Boosted"
                  value={result.report.ai_filter_stats.signals_boosted}
                  color="text-[var(--accent-green)]"
                  tooltip="Signals with increased confidence — either recovery BUY opportunities or SELL signals during crashes."
                />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-2">
                <AIStatItem
                  label="Crash Events"
                  value={result.report.ai_filter_stats.crash_detections}
                  tooltip="Times a rapid price drop was detected in the lookback window."
                />
                <AIStatItem
                  label="Volatility Spikes"
                  value={result.report.ai_filter_stats.volatility_detections}
                  tooltip="Times recent volatility exceeded the long-term average by the configured multiplier."
                />
                <AIStatItem
                  label="Volume Spikes"
                  value={result.report.ai_filter_stats.volume_spike_detections}
                  tooltip="Times volume surged above average while price dropped (panic selling)."
                />
                <AIStatItem
                  label="Recoveries"
                  value={result.report.ai_filter_stats.recovery_detections}
                  tooltip="Times a price bounce-back was detected after a recent crash (potential buy opportunity)."
                />
              </div>
            </div>
          )}

          {/* Engine stats */}
          {result.report.engine_stats && (result.report.engine_stats.total_fees > 0 || result.report.engine_stats.stop_loss_exits > 0 || result.report.engine_stats.signals_below_confidence > 0) && (
            <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--accent-yellow,#eab308)]/30">
              <h2 className="text-sm font-medium text-[var(--accent-yellow,#eab308)] mb-3">
                Execution & Risk Stats
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <AIStatItem label="Total Fees" value={Number(result.report.engine_stats.total_fees.toFixed(2))} color="text-[var(--accent-red)]" tooltip="Total exchange fees paid during the backtest." />
                <AIStatItem label="Total Slippage" value={Number(result.report.engine_stats.total_slippage.toFixed(2))} color="text-[var(--accent-red)]" tooltip="Total estimated slippage cost during the backtest." />
                <AIStatItem label="Stop-Loss Exits" value={result.report.engine_stats.stop_loss_exits} tooltip="Positions automatically closed by fixed stop-loss." />
                <AIStatItem label="Trailing Stop Exits" value={result.report.engine_stats.trailing_stop_exits} tooltip="Positions automatically closed by trailing stop." />
                <AIStatItem label="Take-Profit Exits" value={result.report.engine_stats.take_profit_exits} color="text-[var(--accent-green)]" tooltip="Positions where profit was automatically taken." />
                <AIStatItem label="Low Confidence Skips" value={result.report.engine_stats.signals_below_confidence} tooltip="Signals filtered out because confidence was below the minimum threshold." />
                <AIStatItem label="Cooldown Skips" value={result.report.engine_stats.cooldown_skips} tooltip="Signals skipped because the cooldown period between trades hadn't elapsed." />
                <AIStatItem label="Regime Filtered" value={result.report.engine_stats.regime_filtered} tooltip="Candles where signals were skipped because ADX indicated a strong trend (mean-reversion unsafe)." />
              </div>
              {result.report.engine_stats.drawdown_halt_candle !== null && (
                <div className="mt-2 text-xs text-[var(--accent-red)] font-medium">
                  Drawdown circuit breaker triggered at candle #{result.report.engine_stats.drawdown_halt_candle} — trading halted.
                </div>
              )}
            </div>
          )}

          {/* Walk-forward results */}
          {result.walk_forward && result.walk_forward.folds.length > 0 && (
            <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--accent-blue)]/30">
              <h2 className="text-sm font-medium text-[var(--accent-blue)] mb-3">
                Walk-Forward Validation ({result.walk_forward.aggregate_oos.n_folds} folds)
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <StatCard
                  label="Avg OOS Return"
                  value={`${result.walk_forward.aggregate_oos.avg_return_pct >= 0 ? '+' : ''}${result.walk_forward.aggregate_oos.avg_return_pct.toFixed(2)}%`}
                  color={result.walk_forward.aggregate_oos.avg_return_pct >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}
                  tooltip="Average out-of-sample return across all test folds. This is the most realistic performance estimate."
                />
                <StatCard
                  label="Avg OOS Sharpe"
                  value={result.walk_forward.aggregate_oos.avg_sharpe.toFixed(3)}
                  tooltip="Average Sharpe ratio on out-of-sample test data. More reliable than in-sample Sharpe."
                />
                <StatCard
                  label="Avg OOS Drawdown"
                  value={`${result.walk_forward.aggregate_oos.avg_max_drawdown_pct.toFixed(2)}%`}
                  color="text-[var(--accent-red)]"
                  tooltip="Average maximum drawdown on test data across folds."
                />
                <StatCard
                  label="Worst Fold Return"
                  value={`${result.walk_forward.aggregate_oos.worst_return_pct >= 0 ? '+' : ''}${result.walk_forward.aggregate_oos.worst_return_pct.toFixed(2)}%`}
                  color={result.walk_forward.aggregate_oos.worst_return_pct >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}
                  tooltip="Return of the worst-performing test fold. Shows the downside risk of the strategy."
                />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[var(--border)] text-[var(--text-secondary)] text-xs">
                      <th className="text-left px-3 py-2 font-medium">Fold</th>
                      <th className="text-left px-3 py-2 font-medium">Period</th>
                      <th className="text-right px-3 py-2 font-medium">Train Return</th>
                      <th className="text-right px-3 py-2 font-medium">Test Return</th>
                      <th className="text-right px-3 py-2 font-medium">Train Sharpe</th>
                      <th className="text-right px-3 py-2 font-medium">Test Sharpe</th>
                      <th className="text-right px-3 py-2 font-medium">Test Trades</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.walk_forward.folds.map((fold) => {
                      const testIsUp = fold.test_report.total_return_pct >= 0;
                      return (
                        <tr key={fold.fold_index} className="border-b border-[var(--border)]/50 hover:bg-[var(--bg-secondary)]/50">
                          <td className="px-3 py-2 text-[var(--text-secondary)]">#{fold.fold_index}</td>
                          <td className="px-3 py-2 text-xs">
                            {new Date(fold.train_start).toLocaleDateString()} — {new Date(fold.test_end).toLocaleDateString()}
                          </td>
                          <td className="px-3 py-2 text-right font-mono">
                            <span className={fold.train_report.total_return_pct >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}>
                              {fold.train_report.total_return_pct >= 0 ? '+' : ''}{fold.train_report.total_return_pct.toFixed(2)}%
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right font-mono font-bold">
                            <span className={testIsUp ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}>
                              {testIsUp ? '+' : ''}{fold.test_report.total_return_pct.toFixed(2)}%
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right font-mono">{fold.train_report.sharpe_ratio.toFixed(3)}</td>
                          <td className="px-3 py-2 text-right font-mono font-bold">{fold.test_report.sharpe_ratio.toFixed(3)}</td>
                          <td className="px-3 py-2 text-right">{fold.test_report.total_trades}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Trades table */}
          {result.trades.length > 0 && (
            <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)] overflow-hidden">
              <div className="px-4 pt-3 pb-2">
                <h2 className="text-sm font-medium text-[var(--text-secondary)]">
                  Trade History ({result.trades.length} trades)
                </h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-t border-[var(--border)] text-[var(--text-secondary)] text-xs">
                      <th className="text-left px-4 py-2 font-medium">#</th>
                      <th className="text-left px-4 py-2 font-medium">Time</th>
                      <th className="text-left px-4 py-2 font-medium">Side</th>
                      <th className="text-right px-4 py-2 font-medium">Amount</th>
                      <th className="text-right px-4 py-2 font-medium">Price</th>
                      <th className="text-right px-4 py-2 font-medium">Value</th>
                      <th className="text-right px-4 py-2 font-medium">Portfolio</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((t, i) => (
                      <tr
                        key={i}
                        className="border-t border-[var(--border)] hover:bg-[var(--bg-secondary)]/50 transition-colors"
                      >
                        <td className="px-4 py-2 text-[var(--text-secondary)]">{i + 1}</td>
                        <td className="px-4 py-2 text-xs">
                          {t.executed_at ? new Date(t.executed_at).toLocaleString() : '-'}
                        </td>
                        <td className="px-4 py-2">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                              t.side === 'BUY'
                                ? 'bg-[var(--accent-green)]/15 text-[var(--accent-green)]'
                                : 'bg-[var(--accent-red)]/15 text-[var(--accent-red)]'
                            }`}
                          >
                            {t.side === 'BUY' ? '\u25B2' : '\u25BC'} {t.side}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-right font-mono">{t.amount.toFixed(6)}</td>
                        <td className="px-4 py-2 text-right font-mono">
                          ${t.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </td>
                        <td className="px-4 py-2 text-right font-mono">
                          ${(t.amount * t.price).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </td>
                        <td className="px-4 py-2 text-right font-mono">
                          ${t.portfolio_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, color, tooltip }: { label: string; value: string; color?: string; tooltip?: string }) {
  return (
    <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]" title={tooltip}>
      <p className={`text-xs font-medium text-[var(--text-secondary)] mb-1 ${tooltip ? 'border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help' : ''}`}>
        {label}
      </p>
      <p className={`text-lg font-bold ${color ?? ''}`}>{value}</p>
    </div>
  );
}

function ParamInput({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  tooltip,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  tooltip?: string;
}) {
  return (
    <div title={tooltip}>
      <label className="flex items-center justify-between text-xs text-[var(--text-secondary)] mb-1">
        <span className={tooltip ? 'border-b border-dotted border-[var(--text-secondary)]/40 cursor-help' : ''}>
          {label}
        </span>
        <span className="font-mono">{value}</span>
      </label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-[var(--accent-blue)] bg-[var(--bg-secondary)]"
      />
    </div>
  );
}

function AIStatItem({ label, value, color, tooltip }: { label: string; value: number; color?: string; tooltip?: string }) {
  return (
    <div className="flex items-center justify-between py-1" title={tooltip}>
      <span className={`text-xs ${tooltip ? 'border-b border-dotted border-[var(--text-secondary)]/40 cursor-help' : ''} text-[var(--text-secondary)]`}>
        {label}
      </span>
      <span className={`text-sm font-mono font-bold ${color ?? ''}`}>{value}</span>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
