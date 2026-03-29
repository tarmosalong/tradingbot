import { useState } from 'react';

interface TrialResult {
  number: number;
  params: Record<string, number | boolean>;
  score: number;
  metrics: {
    sharpe: number;
    return_pct: number;
    max_drawdown_pct: number;
    win_rate: number;
    total_trades: number;
    sortino: number;
  };
}

interface WalkForwardOOS {
  avg_return_pct: number;
  avg_sharpe: number;
  avg_max_drawdown_pct: number;
  avg_win_rate: number;
  worst_return_pct: number;
  best_return_pct: number;
  n_folds: number;
}

interface OptimizationResult {
  trials: TrialResult[];
  best_params: Record<string, number | boolean>;
  best_metrics: Record<string, number>;
  best_score: number;
  validation: { aggregate_oos: WalkForwardOOS } | null;
  error?: string;
}

const POPULAR_SYMBOLS = [
  'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT',
  'XRP/USDT', 'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT',
];

const TUNE_GROUPS = [
  { id: 'strategy', label: 'Strategy (RSI, MACD, Bollinger)', desc: 'Indicator periods, thresholds' },
  { id: 'risk', label: 'Risk Management', desc: 'Stop-loss, position size, confidence' },
  { id: 'atr', label: 'ATR Stops', desc: 'ATR multipliers, partial TP' },
  { id: 'guards', label: 'Trading Guards', desc: 'Volume filter, EMA trend' },
  { id: 'engine', label: 'Engine', desc: 'Cooldown, dynamic sizing' },
] as const;

const SCORING_OPTIONS = [
  { id: 'sharpe', label: 'Sharpe Ratio', desc: 'Risk-adjusted return (recommended)' },
  { id: 'return', label: 'Total Return %', desc: 'Raw profit percentage' },
  { id: 'calmar', label: 'Calmar Ratio', desc: 'Return / Max Drawdown' },
] as const;

const AVAILABLE_STRATEGIES = [
  { id: 'rsi', label: 'RSI' },
  { id: 'macd', label: 'MACD' },
  { id: 'bollinger', label: 'Bollinger' },
] as const;

const PARAM_LABELS: Record<string, string> = {
  rsi_period: 'RSI Period',
  rsi_oversold: 'RSI Oversold',
  rsi_overbought: 'RSI Overbought',
  macd_fast: 'MACD Fast',
  macd_slow: 'MACD Slow',
  macd_signal: 'MACD Signal',
  boll_period: 'Boll Period',
  boll_std_dev: 'Boll Std Dev',
  stop_loss_pct: 'Stop Loss %',
  trailing_stop_pct: 'Trailing Stop %',
  max_position_pct: 'Max Position %',
  min_confidence: 'Min Confidence',
  risk_per_trade_pct: 'Risk/Trade %',
  atr_stop_multiplier: 'ATR Stop',
  atr_tp_multiplier: 'ATR TP',
  atr_trailing_multiplier: 'ATR Trailing',
  partial_tp_ratio: 'Partial TP %',
  volume_min_multiplier: 'Volume Mult',
  ema_trend_period: 'EMA Period',
  ema_trend_enabled: 'EMA Filter',
  cooldown_candles: 'Cooldown',
  use_dynamic_sizing: 'Dyn. Sizing',
};

function formatParamValue(key: string, val: number | boolean): string {
  if (typeof val === 'boolean') return val ? 'On' : 'Off';
  if (key.endsWith('_pct') || key === 'partial_tp_ratio') {
    return `${(val * 100).toFixed(1)}%`;
  }
  if (key.endsWith('_multiplier')) return val.toFixed(2);
  if (key === 'boll_std_dev') return val.toFixed(1);
  return String(val);
}

interface OptimizerPanelProps {
  onApplyParams?: (params: Record<string, number | boolean>) => void;
}

export function OptimizerPanel({ onApplyParams }: OptimizerPanelProps) {
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [start, setStart] = useState('2025-01-01');
  const [end, setEnd] = useState('2025-06-30');
  const [balance, setBalance] = useState('10000');
  const [strategies, setStrategies] = useState<Set<string>>(
    new Set(['rsi', 'macd', 'bollinger']),
  );
  const [nTrials, setNTrials] = useState(50);
  const [scoring, setScoring] = useState('sharpe');
  const [tuneGroups, setTuneGroups] = useState<Set<string>>(
    new Set(['strategy', 'risk', 'atr']),
  );
  const [validateBest, setValidateBest] = useState(true);

  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState<'score' | 'return_pct' | 'max_drawdown_pct' | 'win_rate'>('score');
  const [sortAsc, setSortAsc] = useState(false);

  const toggleStrategy = (id: string) => {
    setStrategies((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { if (next.size > 1) next.delete(id); }
      else next.add(id);
      return next;
    });
  };

  const toggleGroup = (id: string) => {
    setTuneGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { if (next.size > 1) next.delete(id); }
      else next.add(id);
      return next;
    });
  };

  const handleSort = (col: typeof sortCol) => {
    if (col === sortCol) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(false); }
  };

  const runOptimize = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setElapsed(0);
    const t0 = Date.now();
    const timer = setInterval(() => setElapsed(Date.now() - t0), 200);

    try {
      const res = await fetch('/api/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          timeframe,
          start,
          end,
          balance: parseFloat(balance),
          strategies: Array.from(strategies),
          n_trials: nTrials,
          scoring,
          tune_groups: Array.from(tuneGroups),
          validate_best: validateBest,
          fee_rate: 0.001,
          slippage_rate: 0.0005,
        }),
      });
      if (!res.ok) {
        setError(`Server error (${res.status}): ${(await res.text()).slice(0, 200)}`);
        return;
      }
      const data: OptimizationResult = await res.json();
      if (data.error) setError(data.error);
      else setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Optimization failed');
    } finally {
      clearInterval(timer);
      setLoading(false);
    }
  };

  const sortedTrials = result
    ? [...result.trials].sort((a, b) => {
        const av = sortCol === 'score' ? a.score : (a.metrics[sortCol] ?? 0);
        const bv = sortCol === 'score' ? b.score : (b.metrics[sortCol] ?? 0);
        return sortAsc ? av - bv : bv - av;
      })
    : [];

  const bestParamKeys = result ? Object.keys(result.best_params) : [];

  return (
    <div className="space-y-4">
      <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)] p-4">
        <h2 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
          Parameter Optimizer
        </h2>
        <p className="text-xs text-[var(--text-secondary)] mb-4">
          Uses Bayesian optimization (Optuna) to find the best-performing parameter
          combination across the selected groups. Each trial runs a full backtest.
        </p>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">Symbol</label>
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm">
              {POPULAR_SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">Timeframe</label>
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm">
              <option value="15m">15m</option>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">Start</label>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">End</label>
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">Balance (USDT)</label>
            <input value={balance} onChange={(e) => setBalance(e.target.value)} className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm" />
          </div>
        </div>

        {/* Strategies */}
        <div className="mb-4">
          <label className="block text-xs text-[var(--text-secondary)] mb-2">Strategies</label>
          <div className="flex flex-wrap gap-2">
            {AVAILABLE_STRATEGIES.map((s) => {
              const active = strategies.has(s.id);
              return (
                <button key={s.id} onClick={() => toggleStrategy(s.id)} className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer border ${active ? 'bg-[var(--accent)]/15 border-[var(--accent)] text-[var(--accent)]' : 'bg-[var(--bg-secondary)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--text-secondary)]'}`}>
                  {active ? '\u2713 ' : ''}{s.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Tune groups */}
        <div className="mb-4">
          <label className="block text-xs text-[var(--text-secondary)] mb-2">Parameter Groups to Optimize</label>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
            {TUNE_GROUPS.map((g) => {
              const active = tuneGroups.has(g.id);
              return (
                <button key={g.id} onClick={() => toggleGroup(g.id)} title={g.desc} className={`px-3 py-2 rounded-lg text-left border transition-all cursor-pointer ${active ? 'bg-[var(--accent)]/10 border-[var(--accent)] ring-1 ring-[var(--accent)]/30' : 'bg-[var(--bg-secondary)] border-[var(--border)] hover:border-[var(--text-secondary)]'}`}>
                  <span className={`text-xs font-medium ${active ? 'text-[var(--accent)]' : ''}`}>
                    {active ? '\u2713 ' : ''}{g.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Controls */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div>
            <label className="flex items-center justify-between text-xs text-[var(--text-secondary)] mb-1">
              <span>Trials</span>
              <span className="font-mono">{nTrials}</span>
            </label>
            <input type="range" min={5} max={200} step={5} value={nTrials} onChange={(e) => setNTrials(Number(e.target.value))} className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-[var(--accent)] bg-[var(--bg-secondary)]" />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">Scoring</label>
            <select value={scoring} onChange={(e) => setScoring(e.target.value)} className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm">
              {SCORING_OPTIONS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
          </div>
          <div className="flex items-end pb-1">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input type="checkbox" checked={validateBest} onChange={(e) => setValidateBest(e.target.checked)} className="w-4 h-4 rounded accent-[var(--accent)] cursor-pointer" />
              <span className="text-xs text-[var(--text-secondary)]">Walk-Forward Validation</span>
            </label>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button onClick={runOptimize} disabled={loading} className="px-4 py-2 bg-[var(--accent)] text-white rounded text-sm font-medium hover:opacity-90 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed">
            {loading ? 'Optimizing...' : 'Run Optimization'}
          </button>
          {loading && (
            <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
              <Spinner />
              <span>Running {nTrials} trials... {(elapsed / 1000).toFixed(1)}s</span>
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
          {/* Best result */}
          <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--accent)]/30 p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-medium text-[var(--accent)]">
                Best Result (Trial #{result.trials[0]?.number})
              </h2>
              {onApplyParams && (
                <button
                  onClick={() => onApplyParams(result.best_params)}
                  className="px-3 py-1.5 bg-[var(--accent)] text-white rounded text-xs font-medium hover:opacity-90 cursor-pointer"
                >
                  Apply to Backtest
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <MetricCard label="Score" value={result.best_score.toFixed(3)} />
              <MetricCard
                label="Return"
                value={`${result.best_metrics.return_pct >= 0 ? '+' : ''}${result.best_metrics.return_pct?.toFixed(2)}%`}
                color={result.best_metrics.return_pct >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}
              />
              <MetricCard label="Max Drawdown" value={`${result.best_metrics.max_drawdown_pct?.toFixed(2)}%`} color="text-[var(--accent-red)]" />
              <MetricCard label="Win Rate" value={`${result.best_metrics.win_rate?.toFixed(1)}%`} />
            </div>

            <div>
              <h3 className="text-xs font-medium text-[var(--text-secondary)] mb-2">Best Parameters</h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(result.best_params).map(([k, v]) => (
                  <span key={k} className="inline-flex items-center gap-1 px-2 py-1 rounded bg-[var(--bg-secondary)] text-xs">
                    <span className="text-[var(--text-secondary)]">{PARAM_LABELS[k] ?? k}:</span>
                    <span className="font-mono font-medium">{formatParamValue(k, v)}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Walk-Forward Validation */}
          {result.validation?.aggregate_oos && (
            <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--accent-yellow,#eab308)]/30 p-4">
              <h2 className="text-sm font-medium text-[var(--accent-yellow,#eab308)] mb-3">
                Walk-Forward Validation ({result.validation.aggregate_oos.n_folds} folds)
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricCard
                  label="Avg OOS Return"
                  value={`${result.validation.aggregate_oos.avg_return_pct >= 0 ? '+' : ''}${result.validation.aggregate_oos.avg_return_pct.toFixed(2)}%`}
                  color={result.validation.aggregate_oos.avg_return_pct >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}
                />
                <MetricCard label="Avg OOS Sharpe" value={result.validation.aggregate_oos.avg_sharpe.toFixed(3)} />
                <MetricCard label="Avg OOS Drawdown" value={`${result.validation.aggregate_oos.avg_max_drawdown_pct.toFixed(2)}%`} color="text-[var(--accent-red)]" />
                <MetricCard
                  label="Worst Fold"
                  value={`${result.validation.aggregate_oos.worst_return_pct >= 0 ? '+' : ''}${result.validation.aggregate_oos.worst_return_pct.toFixed(2)}%`}
                  color={result.validation.aggregate_oos.worst_return_pct >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}
                />
              </div>
              {result.validation.aggregate_oos.avg_return_pct < 0 && result.best_metrics.return_pct > 0 && (
                <p className="mt-2 text-xs text-[var(--accent-yellow,#eab308)] font-medium">
                  In-sample profit but out-of-sample loss may indicate overfitting.
                </p>
              )}
            </div>
          )}

          {/* Trials table */}
          <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)] overflow-hidden">
            <div className="px-4 pt-3 pb-2">
              <h2 className="text-sm font-medium text-[var(--text-secondary)]">
                All Trials ({result.trials.length})
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-t border-[var(--border)] text-[var(--text-secondary)] text-xs">
                    <th className="text-left px-3 py-2 font-medium">#</th>
                    <SortHeader label="Score" col="score" active={sortCol} asc={sortAsc} onSort={handleSort} />
                    <SortHeader label="Return %" col="return_pct" active={sortCol} asc={sortAsc} onSort={handleSort} />
                    <SortHeader label="Drawdown %" col="max_drawdown_pct" active={sortCol} asc={sortAsc} onSort={handleSort} />
                    <SortHeader label="Win Rate" col="win_rate" active={sortCol} asc={sortAsc} onSort={handleSort} />
                    <th className="text-right px-3 py-2 font-medium">Trades</th>
                    {bestParamKeys.slice(0, 5).map((k) => (
                      <th key={k} className="text-right px-3 py-2 font-medium">{PARAM_LABELS[k] ?? k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedTrials.map((t, i) => (
                    <tr key={t.number} className={`border-t border-[var(--border)]/50 hover:bg-[var(--bg-secondary)]/50 ${i === 0 && sortCol === 'score' && !sortAsc ? 'bg-[var(--accent)]/5' : ''}`}>
                      <td className="px-3 py-2 text-[var(--text-secondary)]">{t.number}</td>
                      <td className="px-3 py-2 text-right font-mono font-bold">{t.score.toFixed(3)}</td>
                      <td className={`px-3 py-2 text-right font-mono ${t.metrics.return_pct >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>
                        {t.metrics.return_pct >= 0 ? '+' : ''}{t.metrics.return_pct.toFixed(2)}%
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-[var(--accent-red)]">{t.metrics.max_drawdown_pct.toFixed(2)}%</td>
                      <td className="px-3 py-2 text-right font-mono">{t.metrics.win_rate.toFixed(1)}%</td>
                      <td className="px-3 py-2 text-right">{t.metrics.total_trades}</td>
                      {bestParamKeys.slice(0, 5).map((k) => (
                        <td key={k} className="px-3 py-2 text-right font-mono text-xs">
                          {formatParamValue(k, t.params[k])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function MetricCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-[var(--bg-secondary)] rounded-lg p-3">
      <p className="text-xs text-[var(--text-secondary)] mb-1">{label}</p>
      <p className={`text-lg font-bold ${color ?? ''}`}>{value}</p>
    </div>
  );
}

function SortHeader({ label, col, active, asc, onSort }: {
  label: string;
  col: string;
  active: string;
  asc: boolean;
  onSort: (col: never) => void;
}) {
  const isActive = active === col;
  return (
    <th
      className="text-right px-3 py-2 font-medium cursor-pointer hover:text-[var(--text-primary)] select-none"
      onClick={() => onSort(col as never)}
    >
      {label} {isActive ? (asc ? '\u25B2' : '\u25BC') : ''}
    </th>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}
