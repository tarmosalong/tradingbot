import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { BotConfig, BotStatus, BotRunnerState } from '../api';

const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '1d'] as const;

const TIMEFRAME_LABELS: Record<string, string> = {
  '1m': '1 min', '3m': '3 min', '5m': '5 min',
  '15m': '15 min', '30m': '30 min', '1h': '1 hour',
  '2h': '2 hours', '4h': '4 hours', '1d': '1 day',
};

const STRATEGY_LABELS: Record<string, { label: string; desc: string }> = {
  rsi: { label: 'Momentum (RSI)', desc: 'Detects overbought/oversold conditions' },
  macd: { label: 'Trend (MACD)', desc: 'Spots trend changes and momentum shifts' },
  bollinger: { label: 'Volatility (Bollinger)', desc: 'Checks if price is unusually high or low' },
};

const BUILDABLE_STRATEGIES = ['rsi', 'macd', 'bollinger'] as const;

interface PaperTradingPanelProps {
  config: BotConfig | null;
  onConfigRefresh: () => void;
}

export function PaperTradingPanel({ config, onConfigRefresh }: PaperTradingPanelProps) {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [balance, setBalance] = useState('');
  const [pairs, setPairs] = useState('');
  const [timeframe, setTimeframe] = useState('1h');
  const [pollSec, setPollSec] = useState('60');
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
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
        m === 'Not Found' ||
        /\b404\b/.test(m) ||
        m.toLowerCase().includes('not found');
      setStatusError(
        missingBot
          ? 'GET /api/bot/status returned 404. From the repo root, run the FastAPI app (not only python -m backend.main): uvicorn backend.api.app:app --reload --port 8000 — port must match frontend/vite.config.ts proxy.'
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
  }, [config]);

  const state: BotRunnerState | null = status?.state ?? null;
  const canControl = status?.control_enabled !== false;
  const stopped = state === 'stopped' || state === null;
  const running = state === 'running' || state === 'starting';
  const botApiUnavailable = statusError !== null;

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
    const pairList = pairs
      .split(',')
      .map((p) => p.trim())
      .filter(Boolean);
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
            Bot control is disabled (set <code className="bg-[var(--bg-secondary)] px-1 rounded">BOT_CONTROL_ENABLED=true</code> in{' '}
            <code className="bg-[var(--bg-secondary)] px-1 rounded">.env</code>).
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

        <label className="block space-y-1">
          <span className="text-xs text-[var(--text-secondary)]">Starting balance (virtual USDT)</span>
          <input
            type="number"
            min={100}
            step={100}
            value={balance}
            onChange={(e) => setBalance(e.target.value)}
            disabled={!stopped || botApiUnavailable}
            className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-2 text-sm disabled:opacity-50"
          />
          <span className="text-[10px] text-[var(--text-secondary)]">The fake money amount you start with</span>
        </label>

        <label className="block space-y-1">
          <span className="text-xs text-[var(--text-secondary)]">Trading pairs</span>
          <input
            type="text"
            value={pairs}
            onChange={(e) => setPairs(e.target.value)}
            disabled={!stopped || botApiUnavailable}
            placeholder="BTC/USDT, ETH/USDT"
            className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-2 text-sm disabled:opacity-50"
          />
          <span className="text-[10px] text-[var(--text-secondary)]">Which coins to trade, e.g. BTC/USDT, ETH/USDT</span>
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block space-y-1">
            <span className="text-xs text-[var(--text-secondary)]">Chart timeframe</span>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              disabled={!stopped || botApiUnavailable}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-2 text-sm disabled:opacity-50"
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf}>
                  {TIMEFRAME_LABELS[tf] ?? tf}
                </option>
              ))}
            </select>
            <span className="text-[10px] text-[var(--text-secondary)]">Candle period for analysis</span>
          </label>
          <label className="block space-y-1">
            <span className="text-xs text-[var(--text-secondary)]">Check every (seconds)</span>
            <input
              type="number"
              min={10}
              max={86400}
              value={pollSec}
              onChange={(e) => setPollSec(e.target.value)}
              disabled={!stopped || botApiUnavailable}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-2 text-sm disabled:opacity-50"
            />
            <span className="text-[10px] text-[var(--text-secondary)]">How often the bot analyses the market</span>
          </label>
        </div>

        <div>
          <span className="text-xs text-[var(--text-secondary)] block mb-2">Analysis strategies</span>
          <div className="space-y-2">
            {BUILDABLE_STRATEGIES.map((key) => {
              const info = STRATEGY_LABELS[key];
              return (
                <label key={key} className="flex items-start gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selected.has(key)}
                    onChange={() => toggleStrategy(key)}
                    disabled={!stopped || botApiUnavailable}
                    className="rounded border-[var(--border)] mt-0.5"
                  />
                  <div>
                    <span className="text-xs font-medium">{info?.label ?? key.toUpperCase()}</span>
                    {info && <p className="text-[10px] text-[var(--text-secondary)] leading-tight">{info.desc}</p>}
                  </div>
                </label>
              );
            })}
          </div>
        </div>

        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={busy || !stopped || botApiUnavailable}
          className="w-full py-2.5 rounded-md border border-[var(--accent)]/40 bg-[var(--accent)]/10 text-sm font-medium text-[var(--accent)] hover:bg-[var(--accent)]/20 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed transition-colors"
        >
          Save Settings
        </button>
      </div>
    </div>
  );
}
