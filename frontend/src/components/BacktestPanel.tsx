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
}

interface BacktestTrade {
  symbol: string;
  side: string;
  amount: number;
  price: number;
  executed_at: string;
  portfolio_value: number;
}

interface BacktestResult {
  report: BacktestReport;
  equity_curve: number[];
  timestamps: string[];
  ohlcv: OhlcvCandle[];
  trades: BacktestTrade[];
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
  const [elapsed, setElapsed] = useState(0);

  const runBacktest = async () => {
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
            />
            <StatCard
              label="Max Drawdown"
              value={`${result.report.max_drawdown_pct.toFixed(2)}%`}
              color="text-[var(--accent-red)]"
            />
            <StatCard label="Sharpe Ratio" value={result.report.sharpe_ratio.toFixed(3)} />
            <StatCard label="Win Rate" value={`${result.report.win_rate.toFixed(1)}%`} />
            <StatCard label="Total Trades" value={String(result.report.total_trades)} />
            <StatCard
              label="Avg Trade P&L"
              value={`$${result.report.avg_trade_pnl.toFixed(2)}`}
              color={result.report.avg_trade_pnl >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}
            />
            <StatCard
              label="Best Trade"
              value={`$${result.report.best_trade_pnl.toFixed(2)}`}
              color="text-[var(--accent-green)]"
            />
            <StatCard
              label="Worst Trade"
              value={`$${result.report.worst_trade_pnl.toFixed(2)}`}
              color="text-[var(--accent-red)]"
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

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
      <p className="text-xs font-medium text-[var(--text-secondary)] mb-1">{label}</p>
      <p className={`text-lg font-bold ${color ?? ''}`}>{value}</p>
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
