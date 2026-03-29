import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { BotConfig, BotStatus, BotRunnerState } from '../api';

const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '1d'] as const;

/** Matches backend STRATEGY_REGISTRY keys (dashboard patch only persists these). */
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
  const [busy, setBusy] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const s = await api.botStatus();
      setStatus(s);
    } catch {
      setStatus(null);
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
    setBusy(true);
    setMsg(null);
    const pairList = pairs
      .split(',')
      .map((p) => p.trim())
      .filter(Boolean);
    const strategies = BUILDABLE_STRATEGIES.filter((k) => selected.has(k));
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
    <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)] mb-4 overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--border)] flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium text-[var(--text-secondary)]">Paper trading (in-process)</h2>
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded ${
              running
                ? 'bg-[var(--accent-green)]/15 text-[var(--accent-green)]'
                : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)]'
            }`}
          >
            {state ?? '…'}
          </span>
          <button
            type="button"
            onClick={() => void handleStart()}
            disabled={busy || !canControl || running}
            className="text-xs px-3 py-1.5 rounded-md bg-[var(--accent-green)] text-white disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
          >
            Start
          </button>
          <button
            type="button"
            onClick={() => void handleStop()}
            disabled={busy || !running}
            className="text-xs px-3 py-1.5 rounded-md bg-[var(--accent-red)]/90 text-white disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
          >
            Stop
          </button>
        </div>
      </div>

      <div className="p-4 space-y-3 text-sm">
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

        <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
          Start/stop runs the strategy loop inside the API server. Save writes{' '}
          <code className="text-[var(--text-primary)] bg-[var(--bg-secondary)] px-1 rounded text-[11px]">config.yaml</code> — stop the bot
          first. Changing starting balance applies on the next run (not to an already-running simulated book).
        </p>

        <label className="block space-y-1">
          <span className="text-xs text-[var(--text-secondary)]">Starting balance (USDT)</span>
          <input
            type="number"
            min={100}
            step={100}
            value={balance}
            onChange={(e) => setBalance(e.target.value)}
            disabled={!stopped}
            className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-2 text-sm disabled:opacity-50"
          />
        </label>

        <label className="block space-y-1">
          <span className="text-xs text-[var(--text-secondary)]">Pairs (comma-separated)</span>
          <input
            type="text"
            value={pairs}
            onChange={(e) => setPairs(e.target.value)}
            disabled={!stopped}
            placeholder="BTC/USDT, ETH/USDT"
            className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-2 text-sm disabled:opacity-50"
          />
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block space-y-1">
            <span className="text-xs text-[var(--text-secondary)]">Timeframe</span>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              disabled={!stopped}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-2 text-sm disabled:opacity-50"
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1">
            <span className="text-xs text-[var(--text-secondary)]">Poll interval (s)</span>
            <input
              type="number"
              min={10}
              max={86400}
              value={pollSec}
              onChange={(e) => setPollSec(e.target.value)}
              disabled={!stopped}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] px-3 py-2 text-sm disabled:opacity-50"
            />
          </label>
        </div>

        <div>
          <span className="text-xs text-[var(--text-secondary)] block mb-2">Strategies (technical only)</span>
          <div className="flex flex-wrap gap-3">
            {BUILDABLE_STRATEGIES.map((key) => (
              <label key={key} className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected.has(key)}
                  onChange={() => toggleStrategy(key)}
                  disabled={!stopped}
                  className="rounded border-[var(--border)]"
                />
                <span className="uppercase text-xs tracking-wide">{key}</span>
              </label>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={busy || !stopped}
          className="w-full py-2 rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] text-sm font-medium hover:bg-[var(--border)]/40 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
        >
          Save settings to config.yaml
        </button>
      </div>
    </div>
  );
}
