import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { BotConfig, BotStatus, BotRunnerState } from '../api';

const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '1d'] as const;

const TIMEFRAME_LABELS: Record<string, string> = {
  '1m': '1 min', '3m': '3 min', '5m': '5 min',
  '15m': '15 min', '30m': '30 min', '1h': '1 hour',
  '2h': '2 hours', '4h': '4 hours', '1d': '1 day',
};

const STRATEGY_INFO: Record<string, { label: string; desc: string }> = {
  rsi: {
    label: 'RSI',
    desc: 'Relative Strength Index — momentum oscillator (0–100) that identifies overbought/oversold conditions.',
  },
  macd: {
    label: 'MACD',
    desc: 'Moving Average Convergence Divergence — trend-following indicator using two moving averages.',
  },
  bollinger: {
    label: 'Bollinger',
    desc: 'Bollinger Bands — volatility bands around a moving average. BUY below lower, SELL above upper.',
  },
};

const BUILDABLE_STRATEGIES = ['rsi', 'macd', 'bollinger'] as const;

const POPULAR_SYMBOLS = [
  'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT',
  'XRP/USDT', 'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT',
];

interface PaperTradingPanelProps {
  config: BotConfig | null;
  onConfigRefresh: () => void;
}

export function PaperTradingPanel({ config, onConfigRefresh }: PaperTradingPanelProps) {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [balance, setBalance] = useState('10000');
  const [pairs, setPairs] = useState('BTC/USDT, ETH/USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [pollSec, setPollSec] = useState('60');
  const [selected, setSelected] = useState<Set<string>>(() => new Set(['rsi', 'macd', 'bollinger']));
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
  const [riskMaxDrawdown, setRiskMaxDrawdown] = useState(20);
  const [riskDailyLoss, setRiskDailyLoss] = useState(5);
  const [riskMaxOrder, setRiskMaxOrder] = useState(1000);

  const [msg, setMsg] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const s = await api.botStatus();
      setStatus(s);
      setStatusError(null);
    } catch (e) {
      setStatus(null);
      const m = e instanceof Error ? e.message : String(e);
      const missingBot =
        m === 'Not Found' || /\b404\b/.test(m) || m.toLowerCase().includes('not found');
      setStatusError(
        missingBot
          ? 'GET /api/bot/status returned 404. Start the FastAPI backend: uvicorn backend.api.app:app --reload --port 8000'
          : m,
      );
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
    const t = setInterval(() => void fetchStatus(), 3000);
    return () => clearInterval(t);
  }, [fetchStatus]);

  useEffect(() => {
    if (!config) return;
    setBalance(String(config.paper_trading?.initial_balance_usdt ?? 10_000));
    setPairs(config.pairs.join(', '));
    setTimeframe(config.timeframe);
    setPollSec(String(config.poll_interval));

    const next = new Set<string>();
    for (const s of config.strategies) {
      if ((BUILDABLE_STRATEGIES as readonly string[]).includes(s)) next.add(s);
    }
    if (next.size === 0) next.add('rsi');
    setSelected(next);

    if (config.strategy_params) {
      const { rsi, macd, bollinger } = config.strategy_params;
      setRsiPeriod(rsi.period);
      setRsiOversold(rsi.oversold);
      setRsiOverbought(rsi.overbought);
      setMacdFast(macd.fast);
      setMacdSlow(macd.slow);
      setMacdSignal(macd.signal);
      setBollPeriod(bollinger.period);
      setBollStdDev(bollinger.std_dev);
    }

    const r = config.risk;
    setRiskMaxPos(Math.round(r.max_position_pct * 100));
    setRiskStopLoss(Math.round(r.stop_loss_pct * 100));
    setRiskTrailingStop(Math.round(r.trailing_stop_pct * 100));
    setRiskMaxDrawdown(Math.round(r.max_drawdown_pct * 100));
    setRiskDailyLoss(Math.round(r.daily_loss_limit_pct * 100));
    setRiskMaxOrder(r.max_single_order_usdt);
  }, [config]);

  const state: BotRunnerState | null = status?.state ?? null;
  const canControl = status?.control_enabled !== false;
  const stopped = state === 'stopped' || state === null;
  const running = state === 'running' || state === 'starting';
  const botApiUnavailable = statusError !== null;
  const editable = stopped && !botApiUnavailable;

  async function handleStart() {
    setBusy(true);
    setMsg(null);
    try {
      await api.botStart();
      await fetchStatus();
      onConfigRefresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Start failed');
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    setBusy(true);
    setMsg(null);
    try {
      await api.botStop();
      await fetchStatus();
      onConfigRefresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Stop failed');
    } finally {
      setBusy(false);
    }
  }

  async function handleSave() {
    if (!config) return;
    setBusy(true);
    setMsg(null);
    const pairList = pairs.split(',').map((p) => p.trim()).filter(Boolean);
    const buildableOn = BUILDABLE_STRATEGIES.filter((k) => selected.has(k));
    const passthrough = (config.strategies ?? []).filter(
      (s) => !(BUILDABLE_STRATEGIES as readonly string[]).includes(s),
    );
    const strategies = [...passthrough, ...buildableOn];
    const poll = parseInt(pollSec, 10);
    const bal = parseFloat(balance);
    try {
      await api.botPatchSettings({
        initial_balance_usdt: bal,
        pairs: pairList,
        timeframe,
        poll_interval_seconds: poll,
        strategies,
        rsi: { period: rsiPeriod, oversold: rsiOversold, overbought: rsiOverbought },
        macd: { fast: macdFast, slow: macdSlow, signal: macdSignal },
        bollinger: { period: bollPeriod, std_dev: bollStdDev },
        risk: {
          max_position_pct: riskMaxPos / 100,
          stop_loss_pct: riskStopLoss / 100,
          trailing_stop_pct: riskTrailingStop / 100,
          max_drawdown_pct: riskMaxDrawdown / 100,
          daily_loss_limit_pct: riskDailyLoss / 100,
          max_single_order_usdt: riskMaxOrder,
        },
      });
      setMsg('Settings saved to config.yaml.');
      onConfigRefresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  function toggleStrategy(key: string) {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(key)) {
        if (n.size <= 1) return prev;
        n.delete(key);
      } else {
        n.add(key);
      }
      return n;
    });
  }

  if (!config) {
    return (
      <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)] mb-4">
        <p className="text-sm text-[var(--text-secondary)]">Loading…</p>
      </div>
    );
  }

  return (
    <div className="bg-[var(--bg-card)]/80 backdrop-blur-sm rounded-xl border border-[var(--border)] mb-4 overflow-hidden">
      {/* Header with status & controls */}
      <div className="px-4 py-3 border-b border-[var(--border)] flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium">Paper Trading</h2>
          <p className="text-[11px] text-[var(--text-secondary)]">Simulated trading — no real money is used</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded flex items-center gap-1.5 ${
              running
                ? 'bg-[var(--accent-green)]/15 text-[var(--accent-green)]'
                : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)]'
            }`}
          >
            {running && <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-green)] animate-pulse" />}
            {state === 'running' ? 'Analysing...' : state === 'starting' ? 'Starting...' : state === 'stopped' ? 'Stopped' : state ?? '…'}
          </span>
          <button
            type="button"
            onClick={() => void handleStart()}
            disabled={busy || botApiUnavailable || !canControl || running}
            className="text-xs px-3 py-1.5 rounded-md bg-[var(--accent-green)] text-white disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
          >
            Start
          </button>
          <button
            type="button"
            onClick={() => void handleStop()}
            disabled={busy || botApiUnavailable || !running}
            className="text-xs px-3 py-1.5 rounded-md bg-[var(--accent-red)]/90 text-white disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
          >
            Stop
          </button>
        </div>
      </div>

      <div className="p-4 space-y-3 text-sm">
        {statusError && (
          <p className="text-xs text-[var(--accent-red)] border border-[var(--accent-red)]/25 rounded px-2 py-1.5 leading-relaxed">
            {statusError}
          </p>
        )}
        {!canControl && (
          <p className="text-xs text-[var(--accent-red)]">
            Bot control is disabled (set <code className="bg-[var(--bg-secondary)] px-1 rounded">BOT_CONTROL_ENABLED=true</code> in .env).
          </p>
        )}
        {status?.last_error && (
          <p className="text-xs text-[var(--accent-red)] border border-[var(--accent-red)]/25 rounded px-2 py-1.5">
            Last error: {status.last_error}
          </p>
        )}
        {msg && (
          <p className={`text-xs ${msg.includes('saved') ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>{msg}</p>
        )}

        <p className="text-xs text-[var(--text-secondary)] leading-relaxed bg-[var(--accent)]/5 border border-[var(--accent)]/20 rounded-lg px-3 py-2">
          <strong className="text-[var(--text-primary)]">How it works:</strong> Press Start to begin simulated trading.
          The bot will analyse the market using your chosen strategies and make virtual trades.
          Settings can only be changed when the bot is stopped.
        </p>

        {/* Basic settings */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <div title="Crypto trading pair(s) to trade.">
            <label className="block text-xs text-[var(--text-secondary)] mb-1 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help">Symbol(s)</label>
            <input
              type="text"
              value={pairs}
              onChange={(e) => setPairs(e.target.value)}
              disabled={!editable}
              placeholder="BTC/USDT, ETH/USDT"
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm disabled:opacity-50"
            />
          </div>
          <div title="Candle interval for price data. 1h is a good starting point.">
            <label className="block text-xs text-[var(--text-secondary)] mb-1 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help">Timeframe</label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              disabled={!editable}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm disabled:opacity-50"
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf}>{TIMEFRAME_LABELS[tf] ?? tf}</option>
              ))}
            </select>
          </div>
          <div title="How often the bot checks the market.">
            <label className="block text-xs text-[var(--text-secondary)] mb-1 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help">Check every (sec)</label>
            <input
              type="number"
              min={10}
              max={86400}
              value={pollSec}
              onChange={(e) => setPollSec(e.target.value)}
              disabled={!editable}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm disabled:opacity-50"
            />
          </div>
          <div title="Starting portfolio balance in USDT. This is the simulated money you begin trading with.">
            <label className="block text-xs text-[var(--text-secondary)] mb-1 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help">Balance (USDT)</label>
            <input
              type="number"
              min={100}
              step={100}
              value={balance}
              onChange={(e) => setBalance(e.target.value)}
              disabled={!editable}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm disabled:opacity-50"
            />
          </div>
        </div>

        {/* Strategies */}
        <div className="mt-2">
          <label className="block text-xs text-[var(--text-secondary)] mb-2 border-b border-dotted border-[var(--text-secondary)]/40 w-fit cursor-help" title="Technical analysis strategies used to generate BUY/SELL/HOLD signals. Multiple strategies are combined — a trade is executed when they agree.">
            Strategies
          </label>
          <div className="flex flex-wrap gap-2">
            {BUILDABLE_STRATEGIES.map((id) => {
              const info = STRATEGY_INFO[id];
              const active = selected.has(id);
              return (
                <button
                  key={id}
                  onClick={() => toggleStrategy(id)}
                  disabled={!editable}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer border disabled:opacity-50 disabled:cursor-not-allowed ${
                    active
                      ? 'bg-[var(--accent)]/15 border-[var(--accent)] text-[var(--accent)]'
                      : 'bg-[var(--bg-secondary)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--text-secondary)]'
                  }`}
                  title={info?.desc}
                >
                  {active ? '\u2713 ' : ''}{info?.label ?? id.toUpperCase()}
                </button>
              );
            })}
          </div>
        </div>

        {/* Advanced settings toggle */}
        <div className="mt-1">
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
          >
            {showAdvanced ? '\u25BC' : '\u25B6'} Advanced Settings
          </button>
        </div>

        {showAdvanced && (
          <div className="space-y-4 border-t border-[var(--border)] pt-4">
            {/* RSI Parameters */}
            {selected.has('rsi') && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent)] mb-2">RSI Parameters</h3>
                <div className="grid grid-cols-3 gap-3">
                  <ParamSlider label="Period" value={rsiPeriod} onChange={setRsiPeriod} min={2} max={50} disabled={!editable} tooltip="Number of candles used to calculate RSI. Lower = more sensitive, higher = smoother. Default: 14" />
                  <ParamSlider label="Oversold" value={rsiOversold} onChange={setRsiOversold} min={5} max={45} disabled={!editable} tooltip="RSI level below which the asset is considered oversold (BUY signal). Default: 30" />
                  <ParamSlider label="Overbought" value={rsiOverbought} onChange={setRsiOverbought} min={55} max={95} disabled={!editable} tooltip="RSI level above which the asset is considered overbought (SELL signal). Default: 70" />
                </div>
              </div>
            )}

            {/* MACD Parameters */}
            {selected.has('macd') && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent)] mb-2">MACD Parameters</h3>
                <div className="grid grid-cols-3 gap-3">
                  <ParamSlider label="Fast EMA" value={macdFast} onChange={setMacdFast} min={2} max={50} disabled={!editable} tooltip="Period for the fast Exponential Moving Average. Default: 12" />
                  <ParamSlider label="Slow EMA" value={macdSlow} onChange={setMacdSlow} min={10} max={100} disabled={!editable} tooltip="Period for the slow Exponential Moving Average. Must be larger than fast. Default: 26" />
                  <ParamSlider label="Signal" value={macdSignal} onChange={setMacdSignal} min={2} max={50} disabled={!editable} tooltip="Period for the signal line (EMA of MACD). Default: 9" />
                </div>
              </div>
            )}

            {/* Bollinger Parameters */}
            {selected.has('bollinger') && (
              <div>
                <h3 className="text-xs font-medium text-[var(--accent)] mb-2">Bollinger Bands Parameters</h3>
                <div className="grid grid-cols-2 gap-3">
                  <ParamSlider label="Period" value={bollPeriod} onChange={setBollPeriod} min={5} max={50} disabled={!editable} tooltip="Number of candles for the middle band moving average. Default: 20" />
                  <ParamSlider label="Std Dev" value={bollStdDev} onChange={setBollStdDev} min={0.5} max={4} step={0.1} disabled={!editable} tooltip="Standard deviations for upper/lower bands. Higher = wider bands = fewer signals. Default: 2.0" />
                </div>
              </div>
            )}

            {/* Risk Management */}
            <div>
              <h3 className="text-xs font-medium text-[var(--accent-red)] mb-2">Risk Management</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <ParamSlider label="Max Position %" value={riskMaxPos} onChange={setRiskMaxPos} min={1} max={100} disabled={!editable} tooltip="Maximum percentage of balance for a single position. Lower = more conservative. Default: 10%" />
                <ParamSlider label="Stop Loss %" value={riskStopLoss} onChange={setRiskStopLoss} min={0} max={20} step={0.5} disabled={!editable} tooltip="Fixed stop-loss percentage below entry price. Default: 3%" />
                <ParamSlider label="Trailing Stop %" value={riskTrailingStop} onChange={setRiskTrailingStop} min={0} max={20} step={0.5} disabled={!editable} tooltip="Dynamic stop that follows price upward. Triggers when price drops this % from peak. Default: 2%" />
                <ParamSlider label="Max Drawdown %" value={riskMaxDrawdown} onChange={setRiskMaxDrawdown} min={1} max={50} disabled={!editable} tooltip="If total portfolio drops this % from highest point, trading halts. Default: 20%" />
                <ParamSlider label="Daily Loss Limit %" value={riskDailyLoss} onChange={setRiskDailyLoss} min={1} max={50} disabled={!editable} tooltip="Maximum loss allowed in a single day. Default: 5%" />
                <ParamSlider label="Max Order (USDT)" value={riskMaxOrder} onChange={setRiskMaxOrder} min={10} max={100000} step={10} disabled={!editable} tooltip="Maximum value (USDT) for a single order. Default: $1,000" />
              </div>
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={busy || !editable}
          className="w-full py-2.5 rounded-md border border-[var(--accent)]/40 bg-[var(--accent)]/10 text-sm font-medium text-[var(--accent)] hover:bg-[var(--accent)]/20 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed transition-colors"
        >
          Save Settings
        </button>
      </div>
    </div>
  );
}

function ParamSlider({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  tooltip,
  disabled = false,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  tooltip?: string;
  disabled?: boolean;
}) {
  return (
    <div title={tooltip} className={disabled ? 'opacity-50' : ''}>
      <label className="flex items-center justify-between text-xs text-[var(--text-secondary)] mb-1">
        <span className={tooltip ? 'border-b border-dotted border-[var(--text-secondary)]/40 cursor-help' : ''}>
          {label}
        </span>
        <span className="font-mono">{typeof value === 'number' && step < 1 ? value.toFixed(1) : value}</span>
      </label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-[var(--accent)] bg-[var(--bg-secondary)] disabled:cursor-not-allowed"
      />
    </div>
  );
}
