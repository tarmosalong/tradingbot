import { useCallback, useEffect, useState } from 'react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { api } from '../api';
import type { SignalEntry } from '../api';

interface SignalsPanelProps {
  refreshTrigger: unknown;
}

interface SymbolCycle {
  symbol: string;
  aggregated: SignalEntry;
  strategies: SignalEntry[];
  history: SignalEntry[];
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
    const aggregators = entries
      .filter((e) => e.strategy_name === 'aggregator')
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

    const latest = aggregators[aggregators.length - 1];
    if (!latest) continue;

    const strategies = entries.filter(
      (e) =>
        e.strategy_name !== 'aggregator' &&
        Math.abs(new Date(e.timestamp).getTime() - new Date(latest.timestamp).getTime()) < 5000,
    );

    result.push({ symbol, aggregated: latest, strategies, history: aggregators });
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

const DIR_COLOR: Record<string, string> = {
  BUY: 'var(--accent-green)',
  SELL: 'var(--accent-red)',
  HOLD: 'var(--text-secondary)',
};

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function fmtShortTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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

interface ChartPoint {
  time: string;
  confidence: number;
  direction: string;
  reason: string;
}

function ConfidenceTimeline({ history }: { history: SignalEntry[] }) {
  if (history.length < 2) {
    return (
      <p className="text-[11px] text-[var(--text-secondary)] py-2 text-center">
        Waiting for more cycles to show chart...
      </p>
    );
  }

  const data: ChartPoint[] = history.map((h) => ({
    time: fmtShortTime(h.timestamp),
    confidence: h.confidence,
    direction: h.direction,
    reason: h.reason,
  }));

  return (
    <div>
      <h3 className="text-[11px] font-medium text-[var(--text-secondary)] uppercase tracking-wide mb-2">
        Aggregated confidence over time
      </h3>
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
          <defs>
            <linearGradient id="confGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent-blue)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--accent-blue)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="time"
            tick={{ fill: 'var(--text-secondary)', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1.0]}
            tick={{ fill: 'var(--text-secondary)', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
          />
          <ReferenceLine y={0.5} stroke="var(--border)" strokeDasharray="4 4" />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              color: 'var(--text-primary)',
              fontSize: 12,
            }}
            formatter={(_value: unknown, _name: unknown, props: unknown) => {
              const p = props as { payload?: ChartPoint };
              const v = Number(_value) || 0;
              const dir = p.payload?.direction ?? '';
              return [`${Math.round(v * 100)}% (${dir})`, 'Confidence'];
            }}
            labelFormatter={(label: unknown) => String(label ?? '')}
          />
          <Area
            type="monotone"
            dataKey="confidence"
            stroke="var(--accent-blue)"
            fill="url(#confGrad)"
            strokeWidth={2}
            dot={(props: unknown) => {
              const p = props as { cx?: number; cy?: number; payload?: ChartPoint; index?: number };
              const cx = p.cx ?? 0;
              const cy = p.cy ?? 0;
              const dir = p.payload?.direction ?? 'HOLD';
              return (
                <circle
                  key={p.index ?? 0}
                  cx={cx}
                  cy={cy}
                  r={4}
                  fill={DIR_COLOR[dir] ?? 'var(--text-secondary)'}
                  stroke="var(--bg-card)"
                  strokeWidth={2}
                />
              );
            }}
            activeDot={{ r: 6, strokeWidth: 2, stroke: 'var(--bg-card)' }}
          />
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex items-center justify-center gap-4 mt-1 text-[10px] text-[var(--text-secondary)]">
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-[var(--accent-green)]" /> BUY
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-[var(--accent-red)]" /> SELL
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: 'var(--text-secondary)' }} /> HOLD
        </span>
      </div>
    </div>
  );
}

function StrategyBarChart({ strategies }: { strategies: SignalEntry[] }) {
  if (strategies.length === 0) return null;

  const data = strategies.map((s) => ({
    name: s.strategy_name.toUpperCase(),
    confidence: s.confidence,
    direction: s.direction,
  }));

  return (
    <div>
      <h3 className="text-[11px] font-medium text-[var(--text-secondary)] uppercase tracking-wide mb-2">
        Strategy confidence comparison
      </h3>
      <ResponsiveContainer width="100%" height={Math.max(80, strategies.length * 36 + 16)}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 4 }}>
          <XAxis
            type="number"
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1.0]}
            tick={{ fill: 'var(--text-secondary)', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fill: 'var(--text-secondary)', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={80}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              color: 'var(--text-primary)',
              fontSize: 12,
            }}
            formatter={(_value: unknown, _name: unknown, props: unknown) => {
              const p = props as { payload?: { direction?: string } };
              const v = Number(_value) || 0;
              return [`${Math.round(v * 100)}% (${p.payload?.direction ?? ''})`, 'Confidence'];
            }}
          />
          <Bar dataKey="confidence" radius={[0, 4, 4, 0]} barSize={20}>
            {data.map((entry, idx) => (
              <Cell key={idx} fill={DIR_COLOR[entry.direction] ?? 'var(--text-secondary)'} fillOpacity={0.8} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SignalsPanel({ refreshTrigger }: SignalsPanelProps) {
  const [signals, setSignals] = useState<SignalEntry[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(true);

  const fetchSignals = useCallback(async () => {
    try {
      const data = await api.signals(200);
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
        <p className="text-sm text-[var(--text-secondary)]">Loading signals...</p>
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
        {cycles.map(({ symbol, aggregated, strategies, history }) => {
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
                <div className="px-4 pb-4 space-y-4">
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="rounded-lg border border-[var(--border)] p-3">
                      <ConfidenceTimeline history={history} />
                    </div>
                    <div className="rounded-lg border border-[var(--border)] p-3">
                      <StrategyBarChart strategies={strategies} />
                    </div>
                  </div>

                  {strategies.length > 0 && (
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
