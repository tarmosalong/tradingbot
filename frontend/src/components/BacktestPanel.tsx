import { useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

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
}

interface BacktestResult {
  report: BacktestReport;
  equity_curve: number[];
  timestamps: string[];
  trades: Array<{
    symbol: string;
    side: string;
    amount: number;
    price: number;
    executed_at: string;
    portfolio_value: number;
  }>;
}

export function BacktestPanel() {
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState('1h');
  const [start, setStart] = useState('2025-01-01');
  const [end, setEnd] = useState('2025-06-30');
  const [balance, setBalance] = useState('10000');
  const [strategies, setStrategies] = useState('rsi,macd,bollinger');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runBacktest = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

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
          strategies: strategies.split(',').map((s) => s.trim()),
        }),
      });
      const data = await res.json();
      if (data.error) {
        setError(data.error);
      } else {
        setResult(data);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Backtest failed');
    } finally {
      setLoading(false);
    }
  };

  const chartData =
    result?.equity_curve.map((value, i) => ({
      time: result.timestamps[i]
        ? new Date(result.timestamps[i]).toLocaleDateString()
        : String(i),
      value,
    })) ?? [];

  const isUp = result ? result.report.total_return_pct >= 0 : true;

  return (
    <div className="space-y-4">
      <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)] p-4">
        <h2 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
          Run Backtest
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">Symbol</label>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">Timeframe</label>
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
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">Start</label>
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">End</label>
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">Balance</label>
            <input
              value={balance}
              onChange={(e) => setBalance(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--text-secondary)] mb-1">Strategies</label>
            <input
              value={strategies}
              onChange={(e) => setStrategies(e.target.value)}
              className="w-full bg-[var(--bg-secondary)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
            />
          </div>
        </div>
        <button
          onClick={runBacktest}
          disabled={loading}
          className="mt-3 px-4 py-2 bg-[var(--accent-blue)] text-white rounded text-sm font-medium hover:opacity-90 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
        >
          {loading ? 'Running...' : 'Run Backtest'}
        </button>
      </div>

      {error && (
        <div className="bg-[var(--accent-red)]/10 border border-[var(--accent-red)]/30 rounded-lg px-4 py-3 text-sm text-[var(--accent-red)]">
          {error}
        </div>
      )}

      {result && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Total Return" value={`${result.report.total_return_pct >= 0 ? '+' : ''}${result.report.total_return_pct.toFixed(2)}%`} color={isUp ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'} />
            <StatCard label="Max Drawdown" value={`${result.report.max_drawdown_pct.toFixed(2)}%`} color="text-[var(--accent-red)]" />
            <StatCard label="Sharpe Ratio" value={result.report.sharpe_ratio.toFixed(3)} />
            <StatCard label="Win Rate" value={`${result.report.win_rate.toFixed(1)}%`} />
            <StatCard label="Total Trades" value={String(result.report.total_trades)} />
            <StatCard label="Avg Trade P&L" value={`$${result.report.avg_trade_pnl.toFixed(2)}`} color={result.report.avg_trade_pnl >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'} />
            <StatCard label="Best Trade" value={`$${result.report.best_trade_pnl.toFixed(2)}`} color="text-[var(--accent-green)]" />
            <StatCard label="Worst Trade" value={`$${result.report.worst_trade_pnl.toFixed(2)}`} color="text-[var(--accent-red)]" />
          </div>

          <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
            <h2 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
              Equity Curve
            </h2>
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={chartData}>
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
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
      <p className="text-xs font-medium text-[var(--text-secondary)] mb-1">{label}</p>
      <p className={`text-lg font-bold ${color ?? ''}`}>{value}</p>
    </div>
  );
}
