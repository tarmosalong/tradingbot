import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { SignalEntry } from '../api';

interface SignalsPanelProps {
  refreshTrigger: unknown;
}

interface SymbolCycle {
  symbol: string;
  aggregated: SignalEntry;
  strategies: SignalEntry[];
}

function groupByCycle(signals: SignalEntry[]): SymbolCycle[] {
  const bySymbol = new Map<string, SignalEntry[]>();
  for (const s of signals) {
    const arr = bySymbol.get(s.symbol) ?? [];
    arr.push(s);
    bySymbol.set(s.symbol, arr);
  }

  const result: SymbolCycle[] = [];
  for (const [symbol, entries] of bySymbol) {
    const agg = entries.find((e) => e.strategy_name === 'aggregator');
    if (!agg) continue;
    const strategies = entries.filter(
      (e) =>
        e.strategy_name !== 'aggregator' &&
        Math.abs(new Date(e.timestamp).getTime() - new Date(agg.timestamp).getTime()) < 5000,
    );
    result.push({ symbol, aggregated: agg, strategies });
  }
  return result.sort((a, b) => a.symbol.localeCompare(b.symbol));
}

const DIR_CLASSES: Record<string, string> = {
  BUY: 'text-[var(--accent-green)]',
  SELL: 'text-[var(--accent-red)]',
  HOLD: 'text-[var(--text-secondary)]',
};

const DIR_BG: Record<string, string> = {
  BUY: 'bg-[var(--accent-green)]/15 text-[var(--accent-green)]',
  SELL: 'bg-[var(--accent-red)]/15 text-[var(--accent-red)]',
  HOLD: 'bg-[var(--bg-secondary)] text-[var(--text-secondary)]',
};

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2 min-w-[90px]">
      <div className="flex-1 h-1.5 rounded-full bg-[var(--bg-secondary)] overflow-hidden">
        <div
          className="h-full rounded-full bg-[var(--accent-blue)] transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[11px] tabular-nums w-8 text-right">{pct}%</span>
    </div>
  );
}

function IndicatorPills({ indicators }: { indicators: Record<string, number> }) {
  const keys = Object.keys(indicators);
  if (keys.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mt-1">
      {keys.map((k) => (
        <span
          key={k}
          className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-secondary)] text-[var(--text-secondary)] tabular-nums"
        >
          {k}: {Number.isInteger(indicators[k]) ? indicators[k] : indicators[k].toFixed(2)}
        </span>
      ))}
    </div>
  );
}

export function SignalsPanel({ refreshTrigger }: SignalsPanelProps) {
  const [signals, setSignals] = useState<SignalEntry[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(true);

  const fetchSignals = useCallback(async () => {
    try {
      const data = await api.signals(80);
      setSignals(data);
    } catch {
      /* non-critical */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchSignals();
    const t = setInterval(() => void fetchSignals(), 8000);
    return () => clearInterval(t);
  }, [fetchSignals]);

  useEffect(() => {
    void fetchSignals();
  }, [refreshTrigger, fetchSignals]);

  const cycles = groupByCycle(signals);

  if (loading && cycles.length === 0) {
    return (
      <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
        <p className="text-sm text-[var(--text-secondary)]">Loading signals…</p>
      </div>
    );
  }

  if (cycles.length === 0) {
    return (
      <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)]">
        <div className="px-4 py-3 border-b border-[var(--border)]">
          <h2 className="text-sm font-medium text-[var(--text-secondary)]">Signal Analyses</h2>
        </div>
        <p className="px-4 py-6 text-sm text-[var(--text-secondary)] text-center">
          No signals yet — start the bot to see strategy analyses.
        </p>
      </div>
    );
  }

  function toggle(symbol: string) {
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(symbol)) n.delete(symbol);
      else n.add(symbol);
      return n;
    });
  }

  return (
    <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)]">
      <div className="px-4 py-3 border-b border-[var(--border)]">
        <h2 className="text-sm font-medium text-[var(--text-secondary)]">Signal Analyses</h2>
      </div>

      <div className="divide-y divide-[var(--border)]">
        {cycles.map(({ symbol, aggregated, strategies }) => {
          const open = expanded.has(symbol);
          return (
            <div key={symbol}>
              <button
                type="button"
                onClick={() => toggle(symbol)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[var(--bg-secondary)]/40 transition-colors cursor-pointer"
              >
                <span className="text-sm font-medium min-w-[90px]">{symbol}</span>
                <span
                  className={`text-xs font-semibold px-2 py-0.5 rounded ${DIR_BG[aggregated.direction] ?? ''}`}
                >
                  {aggregated.direction}
                </span>
                <ConfidenceBar value={aggregated.confidence} />
                <span className="flex-1 text-xs text-[var(--text-secondary)] truncate">
                  {aggregated.reason}
                </span>
                <span className="text-[11px] text-[var(--text-secondary)] tabular-nums shrink-0">
                  {fmtTime(aggregated.timestamp)}
                </span>
                <svg
                  className={`w-4 h-4 text-[var(--text-secondary)] transition-transform ${open ? 'rotate-180' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {open && (
                <div className="px-4 pb-3 space-y-2">
                  {strategies.length === 0 ? (
                    <p className="text-xs text-[var(--text-secondary)] pl-2">
                      No per-strategy signals in this cycle.
                    </p>
                  ) : (
                    <div className="rounded-lg border border-[var(--border)] overflow-hidden">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-[var(--bg-secondary)]/60 text-[var(--text-secondary)]">
                            <th className="text-left px-3 py-2 font-medium">Strategy</th>
                            <th className="text-left px-3 py-2 font-medium">Direction</th>
                            <th className="text-left px-3 py-2 font-medium">Confidence</th>
                            <th className="text-left px-3 py-2 font-medium">Reason</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[var(--border)]">
                          {strategies.map((s) => (
                            <tr key={s.id}>
                              <td className="px-3 py-2 font-medium uppercase tracking-wide">
                                {s.strategy_name}
                              </td>
                              <td className={`px-3 py-2 font-semibold ${DIR_CLASSES[s.direction] ?? ''}`}>
                                {s.direction}
                              </td>
                              <td className="px-3 py-2">
                                <ConfidenceBar value={s.confidence} />
                              </td>
                              <td className="px-3 py-2 text-[var(--text-secondary)]">
                                {s.reason}
                                <IndicatorPills indicators={s.indicators} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
