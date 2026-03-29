import { useEffect, useMemo, useState } from 'react';
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
  partial_tp_exits: number;
  drawdown_halt_candle: number | null;
  daily_loss_skips: number;
  signals_below_confidence: number;
  cooldown_skips: number;
  regime_filtered: number;
  volume_filtered: number;
  ema_filtered: number;
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
  {
    id: 'ema',
    label: 'EMA Crossover',
    description: 'Trend-following strategy using fast/slow EMA crossovers. BUY when fast crosses above slow, SELL when below. Complements mean-reversion strategies.',
  },
] as const;

const POPULAR_SYMBOLS = [
  'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT',
  'XRP/USDT', 'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT',
];

interface BacktestProfile {
  label: string;
  desc: string;
  icon: string;
  rsi: { period: number; oversold: number; overbought: number };
  macd: { fast: number; slow: number; signal: number };
  bollinger: { period: number; std_dev: number };
  ema: { fastPeriod: number; slowPeriod: number };
  signal: { minAgreement: number; holdOpposition: number };
  risk: {
    maxPos: number;
    stopLoss: number;
    trailingStop: number;
    maxDrawdown: number;
    dailyLoss: number;
    maxOrder: number;
    minConfidence: number;
    atrStop: number;
    atrTp: number;
    atrTrailing: number;
    volumeMin: number;
    emaPeriod: number;
    emaEnabled: boolean;
    riskPerTrade: number;
    partialTp: number;
  };
  engine: {
    fee: number;
    slippage: number;
    cooldown: number;
    dynamicSizing: boolean;
    regimeFilter: boolean;
  };
}

const PROFILES: Record<string, BacktestProfile> = {
  conservative: {
    label: 'Conservative',
    desc: 'Low risk, wide ATR stops, strong filters. Best for beginners or volatile markets.',
    icon: '\u{1F6E1}',
    rsi: { period: 14, oversold: 25, overbought: 75 },
    macd: { fast: 12, slow: 26, signal: 9 },
    bollinger: { period: 20, std_dev: 2.5 },
    ema: { fastPeriod: 9, slowPeriod: 21 },
    signal: { minAgreement: 3, holdOpposition: 0.15 },
    risk: {
      maxPos: 5, stopLoss: 5, trailingStop: 3, maxDrawdown: 10,
      dailyLoss: 3, maxOrder: 500, minConfidence: 60,
      atrStop: 2.5, atrTp: 4.0, atrTrailing: 2.0,
      volumeMin: 1.5, emaPeriod: 50, emaEnabled: true,
      riskPerTrade: 0.5, partialTp: 50,
    },
    engine: { fee: 0.1, slippage: 0.05, cooldown: 3, dynamicSizing: false, regimeFilter: true },
  },
  balanced: {
    label: 'Balanced',
    desc: 'Standard settings. Good balance of risk and reward for most conditions.',
    icon: '\u2696',
    rsi: { period: 14, oversold: 30, overbought: 70 },
    macd: { fast: 12, slow: 26, signal: 9 },
    bollinger: { period: 20, std_dev: 2.0 },
    ema: { fastPeriod: 9, slowPeriod: 21 },
    signal: { minAgreement: 2, holdOpposition: 0.1 },
    risk: {
      maxPos: 10, stopLoss: 3, trailingStop: 2, maxDrawdown: 15,
      dailyLoss: 5, maxOrder: 1000, minConfidence: 40,
      atrStop: 2.0, atrTp: 3.0, atrTrailing: 1.5,
      volumeMin: 1.2, emaPeriod: 50, emaEnabled: true,
      riskPerTrade: 1.0, partialTp: 50,
    },
    engine: { fee: 0.1, slippage: 0.05, cooldown: 0, dynamicSizing: false, regimeFilter: false },
  },
  aggressive: {
    label: 'Aggressive',
    desc: 'Higher risk, tighter stops, larger positions. More trades, more potential reward.',
    icon: '\u{1F525}',
    rsi: { period: 10, oversold: 35, overbought: 65 },
    macd: { fast: 8, slow: 21, signal: 5 },
    bollinger: { period: 15, std_dev: 1.5 },
    ema: { fastPeriod: 5, slowPeriod: 15 },
    signal: { minAgreement: 1, holdOpposition: 0.0 },
    risk: {
      maxPos: 20, stopLoss: 2, trailingStop: 1, maxDrawdown: 30,
      dailyLoss: 10, maxOrder: 3000, minConfidence: 25,
      atrStop: 1.5, atrTp: 2.5, atrTrailing: 1.0,
      volumeMin: 0.8, emaPeriod: 30, emaEnabled: false,
      riskPerTrade: 2.0, partialTp: 40,
    },
    engine: { fee: 0.1, slippage: 0.05, cooldown: 0, dynamicSizing: true, regimeFilter: false },
  },
  scalper: {
    label: 'Scalper',
    desc: 'Very short-term, fast signals, tight ATR stops. For high-frequency backtesting.',
    icon: '\u26A1',
    rsi: { period: 7, oversold: 35, overbought: 65 },
    macd: { fast: 5, slow: 13, signal: 4 },
    bollinger: { period: 10, std_dev: 1.5 },
    ema: { fastPeriod: 5, slowPeriod: 12 },
    signal: { minAgreement: 1, holdOpposition: 0.0 },
    risk: {
      maxPos: 15, stopLoss: 1, trailingStop: 1, maxDrawdown: 15,
      dailyLoss: 5, maxOrder: 2000, minConfidence: 20,
      atrStop: 1.0, atrTp: 2.0, atrTrailing: 0.8,
      volumeMin: 1.0, emaPeriod: 20, emaEnabled: false,
      riskPerTrade: 1.5, partialTp: 60,
    },
    engine: { fee: 0.1, slippage: 0.1, cooldown: 0, dynamicSizing: true, regimeFilter: false },
  },
  hodl: {
    label: 'HODL',
    desc: 'Long-term signals only. Wide filters, large ATR stops, fewer trades. Ride the trend.',
    icon: '\u{1F4C8}',
    rsi: { period: 21, oversold: 20, overbought: 80 },
    macd: { fast: 16, slow: 36, signal: 12 },
    bollinger: { period: 30, std_dev: 2.5 },
    ema: { fastPeriod: 12, slowPeriod: 50 },
    signal: { minAgreement: 3, holdOpposition: 0.2 },
    risk: {
      maxPos: 10, stopLoss: 8, trailingStop: 5, maxDrawdown: 25,
      dailyLoss: 8, maxOrder: 2000, minConfidence: 50,
      atrStop: 3.0, atrTp: 5.0, atrTrailing: 2.5,
      volumeMin: 1.5, emaPeriod: 100, emaEnabled: true,
      riskPerTrade: 0.5, partialTp: 30,
    },
    engine: { fee: 0.1, slippage: 0.05, cooldown: 5, dynamicSizing: false, regimeFilter: true },
  },
};

interface BacktestPanelProps {
  optimizedParams?: Record<string, number | boolean> | null;
  onParamsApplied?: () => void;
}

export function BacktestPanel({ optimizedParams, onParamsApplied }: BacktestPanelProps = {}) {
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

  const [emaFastPeriod, setEmaFastPeriod] = useState(9);
  const [emaSlowPeriod, setEmaSlowPeriod] = useState(21);

  const [minAgreement, setMinAgreement] = useState(1);
  const [holdOpposition, setHoldOpposition] = useState(0.0);

  const [riskMaxPos, setRiskMaxPos] = useState(10);
  const [riskStopLoss, setRiskStopLoss] = useState(3);
  const [riskTrailingStop, setRiskTrailingStop] = useState(2);
  const [riskMaxOrder, setRiskMaxOrder] = useState(1000);
  const [riskMaxDrawdown, setRiskMaxDrawdown] = useState(15);
  const [riskDailyLoss, setRiskDailyLoss] = useState(5);
  const [riskMinConfidence, setRiskMinConfidence] = useState(40);
  const [atrStopMult, setAtrStopMult] = useState(2.0);
  const [atrTpMult, setAtrTpMult] = useState(3.0);
  const [atrTrailingMult, setAtrTrailingMult] = useState(1.5);
  const [volumeMinMult, setVolumeMinMult] = useState(1.2);
  const [emaTrendPeriod, setEmaTrendPeriod] = useState(50);
  const [emaTrendEnabled, setEmaTrendEnabled] = useState(true);
  const [riskPerTrade, setRiskPerTrade] = useState(1.0);
  const [partialTpRatio, setPartialTpRatio] = useState(50);

  const [feeRate, setFeeRate] = useState(0.1);
  const [slippageRate, setSlippageRate] = useState(0.05);
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

  useEffect(() => {
    if (!optimizedParams) return;
    const p = optimizedParams;
    if (p.rsi_period != null) setRsiPeriod(p.rsi_period as number);
    if (p.rsi_oversold != null) setRsiOversold(p.rsi_oversold as number);
    if (p.rsi_overbought != null) setRsiOverbought(p.rsi_overbought as number);
    if (p.macd_fast != null) setMacdFast(p.macd_fast as number);
    if (p.macd_slow != null) setMacdSlow(p.macd_slow as number);
    if (p.macd_signal != null) setMacdSignal(p.macd_signal as number);
    if (p.boll_period != null) setBollPeriod(p.boll_period as number);
    if (p.boll_std_dev != null) setBollStdDev(p.boll_std_dev as number);
    if (p.max_position_pct != null) setRiskMaxPos(Math.round((p.max_position_pct as number) * 100));
    if (p.stop_loss_pct != null) setRiskStopLoss(Math.round((p.stop_loss_pct as number) * 100));
    if (p.trailing_stop_pct != null) setRiskTrailingStop(Math.round((p.trailing_stop_pct as number) * 100));
    if (p.min_confidence != null) setRiskMinConfidence(Math.round((p.min_confidence as number) * 100));
    if (p.risk_per_trade_pct != null) setRiskPerTrade((p.risk_per_trade_pct as number) * 100);
    if (p.atr_stop_multiplier != null) setAtrStopMult(p.atr_stop_multiplier as number);
    if (p.atr_tp_multiplier != null) setAtrTpMult(p.atr_tp_multiplier as number);
    if (p.atr_trailing_multiplier != null) setAtrTrailingMult(p.atr_trailing_multiplier as number);
    if (p.partial_tp_ratio != null) setPartialTpRatio(Math.round((p.partial_tp_ratio as number) * 100));
    if (p.volume_min_multiplier != null) setVolumeMinMult(p.volume_min_multiplier as number);
    if (p.ema_trend_period != null) setEmaTrendPeriod(p.ema_trend_period as number);
    if (p.ema_trend_enabled != null) setEmaTrendEnabled(p.ema_trend_enabled as boolean);
    if (p.cooldown_candles != null) setCooldownCandles(p.cooldown_candles as number);
    if (p.use_dynamic_sizing != null) setDynamicSizing(p.use_dynamic_sizing as boolean);
    if (p.ema_fast_period != null) setEmaFastPeriod(p.ema_fast_period as number);
    if (p.ema_slow_period != null) setEmaSlowPeriod(p.ema_slow_period as number);
    if (p.min_agreement != null) setMinAgreement(p.min_agreement as number);
    if (p.hold_opposition != null) setHoldOpposition(p.hold_opposition as number);
    setShowAdvanced(true);
    onParamsApplied?.();
  }, [optimizedParams, onParamsApplied]);

  const activeProfile = useMemo(() => {
    for (const [id, p] of Object.entries(PROFILES)) {
      if (
        rsiPeriod === p.rsi.period &&
        rsiOversold === p.rsi.oversold &&
        rsiOverbought === p.rsi.overbought &&
        macdFast === p.macd.fast &&
        macdSlow === p.macd.slow &&
        macdSignal === p.macd.signal &&
        bollPeriod === p.bollinger.period &&
        bollStdDev === p.bollinger.std_dev &&
        riskMaxPos === p.risk.maxPos &&
        riskStopLoss === p.risk.stopLoss &&
        riskTrailingStop === p.risk.trailingStop &&
        riskMaxDrawdown === p.risk.maxDrawdown &&
        riskDailyLoss === p.risk.dailyLoss &&
        riskMaxOrder === p.risk.maxOrder &&
        riskMinConfidence === p.risk.minConfidence &&
        atrStopMult === p.risk.atrStop &&
        atrTpMult === p.risk.atrTp &&
        atrTrailingMult === p.risk.atrTrailing &&
        volumeMinMult === p.risk.volumeMin &&
        emaTrendPeriod === p.risk.emaPeriod &&
        emaTrendEnabled === p.risk.emaEnabled &&
        riskPerTrade === p.risk.riskPerTrade &&
        partialTpRatio === p.risk.partialTp &&
        feeRate === p.engine.fee &&
        slippageRate === p.engine.slippage &&
        cooldownCandles === p.engine.cooldown &&
        dynamicSizing === p.engine.dynamicSizing &&
        regimeFilter === p.engine.regimeFilter &&
        emaFastPeriod === p.ema.fastPeriod &&
        emaSlowPeriod === p.ema.slowPeriod &&
        minAgreement === p.signal.minAgreement &&
        holdOpposition === p.signal.holdOpposition
      ) {
        return id;
      }
    }
    return null;
  }, [
    rsiPeriod, rsiOversold, rsiOverbought,
    macdFast, macdSlow, macdSignal,
    bollPeriod, bollStdDev,
    emaFastPeriod, emaSlowPeriod,
    minAgreement, holdOpposition,
    riskMaxPos, riskStopLoss, riskTrailingStop,
    riskMaxDrawdown, riskDailyLoss, riskMaxOrder, riskMinConfidence,
    atrStopMult, atrTpMult, atrTrailingMult,
    volumeMinMult, emaTrendPeriod, emaTrendEnabled,
    riskPerTrade, partialTpRatio,
    feeRate, slippageRate, cooldownCandles,
    dynamicSizing, regimeFilter,
  ]);

  function applyProfile(id: string) {
    const p = PROFILES[id];
    if (!p) return;
    setRsiPeriod(p.rsi.period);
    setRsiOversold(p.rsi.oversold);
    setRsiOverbought(p.rsi.overbought);
    setMacdFast(p.macd.fast);
    setMacdSlow(p.macd.slow);
    setMacdSignal(p.macd.signal);
    setBollPeriod(p.bollinger.period);
    setBollStdDev(p.bollinger.std_dev);
    setRiskMaxPos(p.risk.maxPos);
    setRiskStopLoss(p.risk.stopLoss);
    setRiskTrailingStop(p.risk.trailingStop);
    setRiskMaxDrawdown(p.risk.maxDrawdown);
    setRiskDailyLoss(p.risk.dailyLoss);
    setRiskMaxOrder(p.risk.maxOrder);
    setRiskMinConfidence(p.risk.minConfidence);
    setAtrStopMult(p.risk.atrStop);
    setAtrTpMult(p.risk.atrTp);
    setAtrTrailingMult(p.risk.atrTrailing);
    setVolumeMinMult(p.risk.volumeMin);
    setEmaTrendPeriod(p.risk.emaPeriod);
    setEmaTrendEnabled(p.risk.emaEnabled);
    setRiskPerTrade(p.risk.riskPerTrade);
    setPartialTpRatio(p.risk.partialTp);
    setFeeRate(p.engine.fee);
    setSlippageRate(p.engine.slippage);
    setCooldownCandles(p.engine.cooldown);
    setDynamicSizing(p.engine.dynamicSizing);
    setRegimeFilter(p.engine.regimeFilter);
    setEmaFastPeriod(p.ema.fastPeriod);
    setEmaSlowPeriod(p.ema.slowPeriod);
    setMinAgreement(p.signal.minAgreement);
    setHoldOpposition(p.signal.holdOpposition);
  }

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
          ema: { fast_period: emaFastPeriod, slow_period: emaSlowPeriod },
          min_agreement: minAgreement,
          hold_opposition: holdOpposition,
          risk: {
            max_position_pct: riskMaxPos / 100,
            stop_loss_pct: riskStopLoss / 100,
            trailing_stop_pct: riskTrailingStop / 100,
            max_single_order_usdt: riskMaxOrder,
            max_drawdown_pct: riskMaxDrawdown / 100,
            daily_loss_limit_pct: riskDailyLoss / 100,
            min_confidence: riskMinConfidence / 100,
            atr_stop_multiplier: atrStopMult,
            atr_tp_multiplier: atrTpMult,
            atr_trailing_multiplier: atrTrailingMult,
            volume_min_multiplier: volumeMinMult,
            ema_trend_period: emaTrendPeriod,
            ema_trend_enabled: emaTrendEnabled,
            risk_per_trade_pct: riskPerTrade / 100,
            partial_tp_ratio: partialTpRatio / 100,
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
            min_confidence: 0,
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
                      ? 'bg-[var(--accent)]/15 border-[var(--accent)] text-[var(--accent)]'
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
                className="w-4 h-4 rounded accent-[var(--accent-warm)] cursor-pointer"
              />
              <span className="text-sm font-medium text-[var(--accent-warm)] border-b border-dotted border-[var(--accent-warm)]/40 cursor-help">
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
                  className="w-24 h-1.5 rounded-full appearance-none cursor-pointer accent-[var(--accent-warm)] bg-[var(--bg-secondary)]"
                />
                <span className="text-xs font-mono text-[var(--accent-warm)]">{aiStrength.toFixed(2)}</span>
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
            {/* Profiles */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-medium text-[var(--text-secondary)]">Profiles</h3>
                <button
                  type="button"
                  onClick={() => applyProfile('balanced')}
                  className="text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer transition-colors"
                >
                  Reset to Defaults
                </button>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
                {Object.entries(PROFILES).map(([id, p]) => {
                  const isActive = activeProfile === id;
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => applyProfile(id)}
                      title={p.desc}
                      className={`relative px-3 py-2 rounded-lg text-left border transition-all cursor-pointer ${
                        isActive
                          ? 'bg-[var(--accent)]/10 border-[var(--accent)] ring-1 ring-[var(--accent)]/30'
                          : 'bg-[var(--bg-secondary)] border-[var(--border)] hover:border-[var(--text-secondary)]'
                      }`}
                    >
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span className="text-sm">{p.icon}</span>
                        <span className={`text-xs font-medium ${isActive ? 'text-[var(--accent)]' : ''}`}>
                          {p.label}
                        </span>
                      </div>
                      <p className="text-[10px] text-[var(--text-secondary)] leading-tight line-clamp-2">{p.desc}</p>
                      {isActive && (
                        <span className="absolute top-1 right-1.5 text-[var(--accent)] text-[10px] font-bold">{'\u2713'}</span>
                      )}
                    </button>
                  );
                })}
              </div>
              {activeProfile === null && (
                <p className="text-[10px] text-[var(--text-secondary)] mt-1.5 italic">
                  Custom settings — does not match any profile
                </p>
              )}
            </div>

            {enabledStrategies.has('rsi') && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent)] mb-2">RSI Parameters</h3>
                <div className="grid grid-cols-3 gap-3">
                  <ParamInput label="Period" value={rsiPeriod} onChange={setRsiPeriod} min={2} max={50} tooltip="Number of candles used to calculate RSI. Lower = more sensitive, higher = smoother. Default: 14" />
                  <ParamInput label="Oversold" value={rsiOversold} onChange={setRsiOversold} min={5} max={45} tooltip="RSI level below which the asset is considered oversold (BUY signal). Typical range: 20–35. Default: 30" />
                  <ParamInput label="Overbought" value={rsiOverbought} onChange={setRsiOverbought} min={55} max={95} tooltip="RSI level above which the asset is considered overbought (SELL signal). Typical range: 65–80. Default: 70" />
                </div>
              </div>
            )}

            {enabledStrategies.has('macd') && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent)] mb-2">MACD Parameters</h3>
                <div className="grid grid-cols-3 gap-3">
                  <ParamInput label="Fast EMA" value={macdFast} onChange={setMacdFast} min={2} max={50} tooltip="Period for the fast Exponential Moving Average. Shorter period reacts faster to price changes. Default: 12" />
                  <ParamInput label="Slow EMA" value={macdSlow} onChange={setMacdSlow} min={10} max={100} tooltip="Period for the slow Exponential Moving Average. Longer period smooths out noise. Must be larger than fast EMA. Default: 26" />
                  <ParamInput label="Signal" value={macdSignal} onChange={setMacdSignal} min={2} max={50} tooltip="Period for the signal line (EMA of MACD line). Used to detect crossovers. Lower = more signals. Default: 9" />
                </div>
              </div>
            )}

            {enabledStrategies.has('bollinger') && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent)] mb-2">Bollinger Bands Parameters</h3>
                <div className="grid grid-cols-2 gap-3">
                  <ParamInput label="Period" value={bollPeriod} onChange={setBollPeriod} min={5} max={50} tooltip="Number of candles for the moving average that forms the middle band. Lower = tighter bands, higher = smoother. Default: 20" />
                  <ParamInput label="Std Dev" value={bollStdDev} onChange={setBollStdDev} min={0.5} max={4} step={0.1} tooltip="Number of standard deviations for the upper/lower bands. Higher = wider bands = fewer signals. Typical range: 1.5–2.5. Default: 2.0" />
                </div>
              </div>
            )}

            {enabledStrategies.has('ema') && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent)] mb-2">EMA Crossover Parameters</h3>
                <div className="grid grid-cols-2 gap-3">
                  <ParamInput label="Fast Period" value={emaFastPeriod} onChange={setEmaFastPeriod} min={3} max={20} tooltip="Period for the fast EMA. Lower = more responsive to recent price. Default: 9" />
                  <ParamInput label="Slow Period" value={emaSlowPeriod} onChange={setEmaSlowPeriod} min={10} max={100} tooltip="Period for the slow EMA. Higher = smoother trend signal. Default: 21" />
                </div>
              </div>
            )}

            <div>
              <h3 className="text-xs font-medium text-[var(--accent)] mb-2">Signal Quality</h3>
              <div className="grid grid-cols-2 gap-3">
                <ParamInput label="Min Agreement" value={minAgreement} onChange={setMinAgreement} min={1} max={enabledStrategies.size} tooltip="Minimum number of strategies that must agree on a direction (BUY/SELL) before a trade is executed. Higher = fewer but higher-quality trades. Default: 1" />
                <ParamInput label="HOLD Opposition" value={holdOpposition} onChange={setHoldOpposition} min={0} max={0.5} step={0.05} tooltip="Penalty weight applied by each HOLD signal against directional signals. Higher = harder for a lone signal to trigger a trade. 0 = disabled (old behavior). Default: 0.0" />
              </div>
            </div>

            {aiEnabled && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent-warm)] mb-2">AI Crash Filter Parameters</h3>
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
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <ParamInput label="Fee Rate %" value={feeRate} onChange={setFeeRate} min={0} max={0.5} step={0.01} tooltip="Exchange fee per trade as percentage. Binance default: 0.1% (maker/taker). Set to 0 for zero-fee simulation. Default: 0.1%" />
                <ParamInput label="Slippage %" value={slippageRate} onChange={setSlippageRate} min={0} max={0.5} step={0.01} tooltip="Estimated price slippage per trade. BUY price is increased, SELL price decreased by this amount. Real markets: 0.01–0.3%. Default: 0.05%" />
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
              <h3 className="text-xs font-medium text-[var(--accent)] mb-2">Walk-Forward Validation</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="flex items-center gap-2" title="Split the data into sequential train/test folds to detect overfitting. Shows how the strategy performs on unseen data.">
                  <input type="checkbox" checked={wfEnabled} onChange={(e) => setWfEnabled(e.target.checked)} className="w-4 h-4 rounded accent-[var(--accent)] cursor-pointer" />
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
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <ParamInput label="Max Position %" value={riskMaxPos} onChange={setRiskMaxPos} min={1} max={100} tooltip="Maximum percentage of available balance that can be used for a single position. Lower = more conservative. Default: 10%" />
                <ParamInput label="Stop Loss %" value={riskStopLoss} onChange={setRiskStopLoss} min={0} max={20} step={0.5} tooltip="Fixed stop-loss percentage below purchase price (fallback when ATR unavailable). Default: 3%" />
                <ParamInput label="Trailing Stop %" value={riskTrailingStop} onChange={setRiskTrailingStop} min={0} max={20} step={0.5} tooltip="Percentage trailing stop from peak price (fallback when ATR unavailable). Default: 2%" />
                <ParamInput label="Max Drawdown %" value={riskMaxDrawdown} onChange={setRiskMaxDrawdown} min={1} max={50} tooltip="If portfolio drops this % from highest point, trading halts permanently. Default: 15%" />
                <ParamInput label="Daily Loss Limit %" value={riskDailyLoss} onChange={setRiskDailyLoss} min={1} max={50} tooltip="Maximum loss allowed in a single day before trading pauses. Resets at midnight. Default: 5%" />
                <ParamInput label="Max Order (USDT)" value={riskMaxOrder} onChange={setRiskMaxOrder} min={10} max={100000} step={10} tooltip="Maximum value (in USDT) for a single order. Default: $1,000" />
                <ParamInput label="Min Confidence %" value={riskMinConfidence} onChange={setRiskMinConfidence} min={0} max={100} tooltip="Minimum aggregated signal confidence required to execute a trade. Default: 40%" />
                <ParamInput label="Risk Per Trade %" value={riskPerTrade} onChange={setRiskPerTrade} min={0.1} max={10} step={0.1} tooltip="Portfolio percentage risked per trade for ATR position sizing. Lower = smaller positions. Default: 1%" />
                <ParamInput label="Partial TP Ratio %" value={partialTpRatio} onChange={setPartialTpRatio} min={10} max={100} tooltip="Fraction of position sold at the first ATR take-profit target. Remainder has stop moved to breakeven. Default: 50%" />
              </div>
            </div>

            <div>
              <h3 className="text-xs font-medium text-[var(--accent-yellow,#eab308)] mb-2">ATR Dynamic Stops</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <ParamInput label="ATR Stop Mult." value={atrStopMult} onChange={setAtrStopMult} min={0.5} max={5} step={0.1} tooltip="ATR multiplier for stop-loss distance from entry. Higher = wider stop. Default: 2.0" />
                <ParamInput label="ATR TP Mult." value={atrTpMult} onChange={setAtrTpMult} min={0.5} max={10} step={0.1} tooltip="ATR multiplier for take-profit target above entry. Higher = farther target. Default: 3.0" />
                <ParamInput label="ATR Trailing Mult." value={atrTrailingMult} onChange={setAtrTrailingMult} min={0.5} max={5} step={0.1} tooltip="ATR multiplier for trailing stop distance from peak. Lower = tighter trailing. Default: 1.5" />
              </div>
            </div>

            <div>
              <h3 className="text-xs font-medium text-[var(--text-primary)] mb-2">Trading Guards</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <ParamInput label="Volume Min Mult." value={volumeMinMult} onChange={setVolumeMinMult} min={0} max={5} step={0.1} tooltip="Minimum volume/SMA-20 ratio to confirm signals. 0 = disabled. 1.2 = volume must be 20% above average. Default: 1.2" />
                <div>
                  <div className="flex items-center gap-2 mb-1" title="Only BUY when price is above EMA, only SELL when below. Prevents counter-trend trades.">
                    <input type="checkbox" checked={emaTrendEnabled} onChange={(e) => setEmaTrendEnabled(e.target.checked)} className="w-4 h-4 rounded accent-[var(--accent)] cursor-pointer" />
                    <span className="text-xs text-[var(--text-secondary)] border-b border-dotted border-[var(--text-secondary)]/40 cursor-help">EMA Trend Filter</span>
                  </div>
                  {emaTrendEnabled && (
                    <ParamInput label="EMA Period" value={emaTrendPeriod} onChange={setEmaTrendPeriod} min={10} max={200} tooltip="EMA period for trend filter. 50 is a common medium-term trend indicator. Default: 50" />
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center gap-3 mt-3">
          <button
            onClick={runBacktest}
            disabled={loading}
            className="px-4 py-2 bg-[var(--accent)] text-white rounded text-sm font-medium hover:opacity-90 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
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
            <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--accent-warm)]/30">
              <h2 className="text-sm font-medium text-[var(--accent-warm)] mb-3">
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
                <AIStatItem label="Take-Profit Exits" value={result.report.engine_stats.take_profit_exits} color="text-[var(--accent-green)]" tooltip="Positions closed at ATR take-profit target." />
                <AIStatItem label="Partial TP Exits" value={result.report.engine_stats.partial_tp_exits} color="text-[var(--accent-green)]" tooltip="Partial position sales at first take-profit target." />
                <AIStatItem label="Low Confidence Skips" value={result.report.engine_stats.signals_below_confidence} tooltip="Signals filtered out because confidence was below the minimum threshold." />
                <AIStatItem label="Cooldown Skips" value={result.report.engine_stats.cooldown_skips} tooltip="Signals skipped because the cooldown period between trades hadn't elapsed." />
                <AIStatItem label="Daily Loss Skips" value={result.report.engine_stats.daily_loss_skips} tooltip="Signals skipped because daily loss limit was already hit." />
                <AIStatItem label="Regime Filtered" value={result.report.engine_stats.regime_filtered} tooltip="Candles where signals were skipped because ADX indicated a strong trend." />
                <AIStatItem label="Volume Filtered" value={result.report.engine_stats.volume_filtered} tooltip="Signals blocked by volume confirmation filter (volume too low vs SMA-20)." />
                <AIStatItem label="EMA Filtered" value={result.report.engine_stats.ema_filtered} tooltip="Signals blocked by EMA trend filter (counter-trend trade)." />
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
            <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--accent)]/30">
              <h2 className="text-sm font-medium text-[var(--accent)] mb-3">
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
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-[var(--accent)] bg-[var(--bg-secondary)]"
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
