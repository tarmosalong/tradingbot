import type { Trade, PortfolioSnapshot } from '../api';

interface StatsPanelProps {
  portfolio: PortfolioSnapshot[];
  trades: Trade[];
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
      <p className="text-xs font-medium text-[var(--text-secondary)] mb-1">{label}</p>
      <p className={`text-lg font-bold ${color ?? ''}`}>{value}</p>
    </div>
  );
}

export function StatsPanel({ portfolio, trades }: StatsPanelProps) {
  const currentValue = portfolio.length > 0 ? portfolio[0].total_value_usdt : 0;
  const initialValue = portfolio.length > 0 ? portfolio[portfolio.length - 1].total_value_usdt : 0;
  const pnl = currentValue - initialValue;
  const pnlPct = initialValue > 0 ? (pnl / initialValue) * 100 : 0;

  const totalTrades = trades.length;
  const buys = trades.filter((t) => t.side === 'BUY').length;
  const sells = trades.filter((t) => t.side === 'SELL').length;

  const pnlColor = pnl >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]';

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <StatCard label="Portfolio Value" value={`$${currentValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}`} />
      <StatCard label="Total P&L" value={`${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (${pnlPct.toFixed(2)}%)`} color={pnlColor} />
      <StatCard label="Total Trades" value={String(totalTrades)} />
      <StatCard label="Buy / Sell" value={`${buys} / ${sells}`} />
    </div>
  );
}
