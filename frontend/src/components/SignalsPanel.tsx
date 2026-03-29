import { useCallback, useEffect, useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { api } from '../api';
import type { SignalEntry } from '../api';

/* ── Friendly labels ── */

const STRATEGY_INFO: Record<string, { label: string; desc: string }> = {
  rsi: { label: 'Momentum', desc: 'Checks if the price moved too far, too fast (RSI indicator)' },
  macd: { label: 'Trend', desc: 'Detects when a new upward or downward trend is forming (MACD indicator)' },
  bollinger: { label: 'Volatility', desc: 'Checks if the price is unusually high or low compared to recent range' },
  ai_filter: { label: 'AI Analysis', desc: 'Claude AI reviews the market and decides if conditions are favourable' },
  sentiment: { label: 'News Sentiment', desc: 'Analyses recent crypto news to gauge market mood' },
  aggregator: { label: 'Combined', desc: 'Final decision combining all strategy opinions' },
};

function strategyLabel(name: string) {
  return STRATEGY_INFO[name]?.label ?? name.toUpperCase();
}

function directionLabel(dir: string): string {
  if (dir === 'BUY') return 'Bullish';
  if (dir === 'SELL') return 'Bearish';
  return 'Neutral';
}

function moodEmoji(dir: string): string {
  if (dir === 'BUY') return '\u2191';   // ↑
  if (dir === 'SELL') return '\u2193';  // ↓
  return '\u2194';                       // ↔
}

function moodSummary(dir: string, confidence: number): string {
  if (dir === 'HOLD') return 'Market is quiet — no strong signal from any strategy. The bot is watching and will act when conditions change.';
  const strength = confidence >= 0.7 ? 'Strong' : confidence >= 0.4 ? 'Moderate' : 'Weak';
  if (dir === 'BUY') return `${strength} bullish signal — strategies see a potential buying opportunity.`;
  return `${strength} bearish signal — strategies see a potential selling opportunity.`;
}

function indicatorExplain(key: string, value: number): string {
  const k = key.toLowerCase();
  if (k === 'rsi') {
    if (value <= 30) return `RSI ${value.toFixed(0)} — Oversold (potential bounce)`;
    if (value >= 70) return `RSI ${value.toFixed(0)} — Overbought (may drop)`;
    return `RSI ${value.toFixed(0)} — Neutral zone`;
  }
  if (k === 'macd_histogram' || k === 'macd_hist') {
    if (value > 0) return `MACD +${value.toFixed(2)} — Upward momentum`;
    if (value < 0) return `MACD ${value.toFixed(2)} — Downward momentum`;
    return 'MACD flat — No clear momentum';
  }
  if (k === 'macd') return `MACD line: ${value.toFixed(2)}`;
  if (k === 'macd_signal') return `Signal line: ${value.toFixed(2)}`;
  if (k === 'bb_upper') return `Upper band: $${value.toFixed(2)}`;
  if (k === 'bb_lower') return `Lower band: $${value.toFixed(2)}`;
  if (k === 'bb_mid') return `Middle band: $${value.toFixed(2)}`;
  if (k === 'bb_width') return `Band width: ${value.toFixed(2)}`;
  if (k === 'close') return `Current price: $${value.toLocaleString()}`;
  if (k === 'sentiment') {
    if (value > 0.3) return `Sentiment +${value.toFixed(2)} — Positive mood`;
    if (value < -0.3) return `Sentiment ${value.toFixed(2)} — Negative mood`;
    return `Sentiment ${value.toFixed(2)} — Mixed mood`;
  }
  if (k === 'sentiment_confidence') return `News confidence: ${(value * 100).toFixed(0)}%`;
  return `${key}: ${Number.isInteger(value) ? value : value.toFixed(2)}`;
}

/* ── Helpers ── */

interface SignalsPanelProps { refreshTrigger: unknown }

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

const DIR_COLOR: Record<string, string> = {
  BUY: 'var(--accent-green)',
  SELL: 'var(--accent-red)',
  HOLD: 'var(--text-secondary)',
};

const DIR_BG: Record<string, string> = {
  BUY: 'bg-[var(--accent-green)]/15 border-[var(--accent-green)]/30 text-[var(--accent-green)]',
  SELL: 'bg-[var(--accent-red)]/15 border-[var(--accent-red)]/30 text-[var(--accent-red)]',
  HOLD: 'bg-[var(--bg-secondary)] border-[var(--border)] text-[var(--text-secondary)]',
};

const DIR_BG_SM: Record<string, string> = {
  BUY: 'bg-[var(--accent-green)]/15 text-[var(--accent-green)]',
  SELL: 'bg-[var(--accent-red)]/15 text-[var(--accent-red)]',
  HOLD: 'bg-[var(--bg-secondary)] text-[var(--text-secondary)]',
};

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function fmtShortTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/* ── Small components ── */

function ConfidenceGauge({ value, size = 'md' }: { value: number; size?: 'sm' | 'md' }) {
  const pct = Math.round(value * 100);
  const h = size === 'sm' ? 'h-1.5' : 'h-2.5';
  return (
    <div className="flex items-center gap-2">
      <div className={`flex-1 ${h} rounded-full bg-[var(--bg-primary)] overflow-hidden min-w-[60px]`}>
        <div
          className={`${h} rounded-full transition-all duration-500`}
          style={{
            width: `${Math.max(pct, 2)}%`,
            backgroundColor: pct >= 60 ? 'var(--accent-green)' : pct >= 30 ? 'var(--accent)' : 'var(--text-secondary)',
          }}
        />
      </div>
      <span className="text-xs tabular-nums font-medium w-9 text-right">{pct}%</span>
    </div>
  );
}

function InfoTooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  return (
    <span className="relative inline-flex ml-1">
      <button
        type="button"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onClick={() => setShow((p) => !p)}
        className="w-4 h-4 rounded-full bg-[var(--bg-secondary)] text-[var(--text-secondary)] text-[10px] font-bold leading-none flex items-center justify-center cursor-help hover:text-[var(--text-primary)] transition-colors"
      >
        ?
      </button>
      {show && (
        <span className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-52 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-xs text-[var(--text-primary)] leading-relaxed shadow-lg pointer-events-none">
          {text}
        </span>
      )}
    </span>
  );
}

/* ── Charts ── */

interface ChartPoint { time: string; confidence: number; direction: string; reason: string }

function ConfidenceTimeline({ history }: { history: SignalEntry[] }) {
  if (history.length < 2) {
    return (
      <div className="flex items-center justify-center h-full text-xs text-[var(--text-secondary)] py-4">
        Collecting data — chart appears after 2+ analysis cycles
      </div>
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
      <h3 className="text-[11px] font-medium text-[var(--text-secondary)] mb-2">
        Signal strength over time
        <InfoTooltip text="Shows how confident the bot has been over recent analysis cycles. Higher means a stronger trading signal was detected." />
      </h3>
      <ResponsiveContainer width="100%" height={130}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
          <defs>
            <linearGradient id="confGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="time" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis domain={[0, 1]} ticks={[0, 0.5, 1.0]} tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} />
          <ReferenceLine y={0.5} stroke="var(--border)" strokeDasharray="4 4" />
          <Tooltip
            contentStyle={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text-primary)', fontSize: 12 }}
            formatter={(_v: unknown, _n: unknown, props: unknown) => {
              const p = props as { payload?: ChartPoint };
              const v = Number(_v) || 0;
              return [`${Math.round(v * 100)}% — ${directionLabel(p.payload?.direction ?? '')}`, 'Strength'];
            }}
            labelFormatter={(l: unknown) => String(l ?? '')}
          />
          <Area
            type="monotone" dataKey="confidence" stroke="var(--accent)" fill="url(#confGrad)" strokeWidth={2}
            dot={(props: unknown) => {
              const p = props as { cx?: number; cy?: number; payload?: ChartPoint; index?: number };
              return (
                <circle key={p.index ?? 0} cx={p.cx ?? 0} cy={p.cy ?? 0} r={4}
                  fill={DIR_COLOR[p.payload?.direction ?? 'HOLD'] ?? 'var(--text-secondary)'}
                  stroke="var(--bg-card)" strokeWidth={2} />
              );
            }}
            activeDot={{ r: 6, strokeWidth: 2, stroke: 'var(--bg-card)' }}
          />
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex items-center justify-center gap-5 mt-1 text-[10px] text-[var(--text-secondary)]">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[var(--accent-green)] inline-block" /> Bullish</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[var(--accent-red)] inline-block" /> Bearish</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: 'var(--text-secondary)' }} /> Neutral</span>
      </div>
    </div>
  );
}

function verdictText(dir: string, confidence: number): string {
  if (dir === 'HOLD' || confidence < 0.05) return 'No signal detected';
  const pct = Math.round(confidence * 100);
  const strength = pct >= 70 ? 'Strong' : pct >= 40 ? 'Moderate' : 'Weak';
  return `${strength} ${dir === 'BUY' ? 'buy' : 'sell'} signal (${pct}%)`;
}

function StrategyVerdicts({ strategies }: { strategies: SignalEntry[] }) {
  if (strategies.length === 0) return null;
  return (
    <div>
      <h3 className="text-[11px] font-medium text-[var(--text-secondary)] mb-2">
        Strategy opinions
        <InfoTooltip text="Each strategy independently analyses the market and gives its verdict. A filled bar means a stronger signal." />
      </h3>
      <div className="space-y-2.5">
        {strategies.map((s) => {
          const pct = Math.round(s.confidence * 100);
          const noSignal = s.direction === 'HOLD' || pct < 1;
          const color = DIR_COLOR[s.direction] ?? 'var(--text-secondary)';
          return (
            <div key={s.id}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium">{strategyLabel(s.strategy_name)}</span>
                <span className={`text-[11px] ${noSignal ? 'text-[var(--text-secondary)]' : ''}`} style={noSignal ? undefined : { color }}>
                  {verdictText(s.direction, s.confidence)}
                </span>
              </div>
              <div className="h-2 rounded-full bg-[var(--bg-primary)] overflow-hidden">
                {noSignal ? (
                  <div className="h-full rounded-full bg-[var(--border)]" style={{ width: '100%', opacity: 0.3 }} />
                ) : (
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${Math.max(pct, 3)}%`, backgroundColor: color }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Strategy detail cards ── */

function StrategyCard({ s }: { s: SignalEntry }) {
  const [open, setOpen] = useState(true);
  const info = STRATEGY_INFO[s.strategy_name];
  const indicators = Object.entries(s.indicators);

  return (
    <div className="rounded-lg border border-[var(--border)] overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-[var(--bg-secondary)]/40 transition-colors cursor-pointer"
      >
        <span className="text-sm font-medium w-24">{strategyLabel(s.strategy_name)}</span>
        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded ${DIR_BG_SM[s.direction] ?? ''}`}>
          {directionLabel(s.direction)}
        </span>
        <div className="flex-1"><ConfidenceGauge value={s.confidence} size="sm" /></div>
        <svg className={`w-3.5 h-3.5 text-[var(--text-secondary)] transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 border-t border-[var(--border)] space-y-2">
          {info && <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">{info.desc}</p>}
          <p className="text-xs">{s.reason}</p>
          {indicators.length > 0 && (
            <div className="space-y-1">
              {indicators.map(([k, v]) => (
                <div key={k} className="text-[11px] text-[var(--text-secondary)] flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] shrink-0" />
                  {indicatorExplain(k, v)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Main panel ── */

export function SignalsPanel({ refreshTrigger }: SignalsPanelProps) {
  const [signals, setSignals] = useState<SignalEntry[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(true);

  const fetchSignals = useCallback(async () => {
    try { setSignals(await api.signals(200)); } catch { /* non-critical */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { void fetchSignals(); const t = setInterval(() => void fetchSignals(), 8000); return () => clearInterval(t); }, [fetchSignals]);
  useEffect(() => { void fetchSignals(); }, [refreshTrigger, fetchSignals]);

  const cycles = groupByCycle(signals);

  useEffect(() => {
    if (cycles.length === 0) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      for (const c of cycles) next.add(c.symbol);
      if (next.size === prev.size) return prev;
      return next;
    });
  }, [cycles]);

  if (loading && cycles.length === 0) {
    return (
      <div className="bg-[var(--bg-card)] rounded-lg p-6 border border-[var(--border)] text-center">
        <p className="text-sm text-[var(--text-secondary)]">Loading market analysis...</p>
      </div>
    );
  }

  if (cycles.length === 0) {
    return (
      <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)]">
        <div className="px-4 py-3 border-b border-[var(--border)] flex items-center gap-2">
          <h2 className="text-sm font-medium">Market Analysis</h2>
          <InfoTooltip text="The bot runs multiple strategies that independently analyse the market. Their combined opinion determines whether to buy, sell, or wait." />
        </div>
        <div className="px-4 py-8 text-center space-y-2">
          <p className="text-3xl">&#128269;</p>
          <p className="text-sm font-medium">No analyses yet</p>
          <p className="text-xs text-[var(--text-secondary)]">Press <strong>Start</strong> in the Paper Trading panel above to begin market analysis.</p>
        </div>
      </div>
    );
  }

  function toggle(symbol: string) {
    setExpanded((prev) => { const n = new Set(prev); if (n.has(symbol)) n.delete(symbol); else n.add(symbol); return n; });
  }

  return (
    <div className="bg-[var(--bg-card)]/80 backdrop-blur-sm rounded-xl border border-[var(--border)]">
      <div className="px-4 py-3 border-b border-[var(--border)] flex items-center gap-2">
        <h2 className="text-sm font-medium">Market Analysis</h2>
        <InfoTooltip text="Each trading pair is analysed every cycle by multiple strategies (Momentum, Trend, Volatility). Click a pair to see detailed breakdowns and charts." />
      </div>

      <div className="divide-y divide-[var(--border)]">
        {cycles.map(({ symbol, aggregated, strategies, history }) => {
          const open = expanded.has(symbol);
          const coin = symbol.split('/')[0];
          return (
            <div key={symbol}>
              {/* Summary row */}
              <button
                type="button"
                onClick={() => toggle(symbol)}
                className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-[var(--bg-secondary)]/40 transition-colors cursor-pointer"
              >
                <div className="flex items-center gap-2 min-w-[100px]">
                  <span className="text-lg leading-none">{moodEmoji(aggregated.direction)}</span>
                  <div>
                    <span className="text-sm font-semibold">{coin}</span>
                    <span className="text-xs text-[var(--text-secondary)] ml-1 hidden sm:inline">/USDT</span>
                  </div>
                </div>

                <span className={`text-xs font-semibold px-2.5 py-1 rounded-md border ${DIR_BG[aggregated.direction] ?? ''}`}>
                  {directionLabel(aggregated.direction)}
                </span>

                <div className="flex-1 min-w-[80px] max-w-[140px]">
                  <ConfidenceGauge value={aggregated.confidence} />
                </div>

                <span className="flex-1 text-xs text-[var(--text-secondary)] truncate hidden md:block">
                  {moodSummary(aggregated.direction, aggregated.confidence).split('—')[0]}
                </span>

                <span className="text-[11px] text-[var(--text-secondary)] tabular-nums shrink-0">
                  {fmtTime(aggregated.timestamp)}
                </span>

                <svg className={`w-4 h-4 text-[var(--text-secondary)] transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* Expanded detail */}
              {open && (
                <div className="px-4 pb-4 space-y-4">
                  {/* Mood banner */}
                  <div className={`rounded-lg px-4 py-3 border ${DIR_BG[aggregated.direction] ?? ''}`}>
                    <p className="text-sm leading-relaxed">
                      {moodSummary(aggregated.direction, aggregated.confidence)}
                    </p>
                  </div>

                  {/* Charts */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="rounded-lg border border-[var(--border)] p-3 bg-[var(--bg-primary)]/30">
                      <ConfidenceTimeline history={history} />
                    </div>
                    <div className="rounded-lg border border-[var(--border)] p-3 bg-[var(--bg-primary)]/30">
                      <StrategyVerdicts strategies={strategies} />
                    </div>
                  </div>

                  {/* Strategy cards */}
                  {strategies.length > 0 && (
                    <div>
                      <h3 className="text-xs font-medium text-[var(--text-secondary)] mb-2">
                        Strategy details — click to expand
                      </h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                        {strategies.map((s) => <StrategyCard key={s.id} s={s} />)}
                      </div>
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
