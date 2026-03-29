import type { Trade, PortfolioSnapshot, OpenPosition } from '../api';

interface StatsPanelProps {
  portfolio: PortfolioSnapshot[];
  trades: Trade[];
  positions: OpenPosition[];
  initialBalance: number;
}

export function StatsPanel({ portfolio, trades, positions, initialBalance }: StatsPanelProps) {
  const unrealizedPnl = positions.reduce((sum, p) => sum + p.pnl, 0);
  const realizedPnl = trades.reduce(
    (sum, t) => sum + (t.pnl ?? 0),
    0,
  );
  const pnl = unrealizedPnl + realizedPnl;
  const currentValue = initialBalance + pnl;
  const pnlPct = initialBalance > 0 ? (pnl / initialBalance) * 100 : 0;

  const totalTrades = trades.length;
  const buys = trades.filter((t) => t.side === 'BUY').length;
  const sells = trades.filter((t) => t.side === 'SELL').length;
  const winTrades = trades.filter((t) => t.pnl != null && t.pnl > 0).length;
  const lossTrades = trades.filter((t) => t.pnl != null && t.pnl < 0).length;
  const winRate =
    winTrades + lossTrades > 0
      ? ((winTrades / (winTrades + lossTrades)) * 100).toFixed(0)
      : '\u2014';

  const isUp = pnl >= 0;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
        <p className="text-xs text-[var(--text-secondary)] mb-1">Portfolio</p>
        <p className="text-xl font-bold font-mono tracking-tight">
          $
          {currentValue.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}
        </p>
        <p className="text-[10px] text-[var(--text-secondary)] mt-0.5">
          Started at ${initialBalance.toLocaleString()}
        </p>
      </div>

      <div
        className={`rounded-lg p-4 border ${
          isUp
            ? 'bg-[var(--accent-green)]/5 border-[var(--accent-green)]/15'
            : 'bg-[var(--accent-red)]/5 border-[var(--accent-red)]/15'
        }`}
      >
        <p className="text-xs text-[var(--text-secondary)] mb-1">P&L</p>
        <p
          className={`text-xl font-bold font-mono tracking-tight ${
            isUp ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'
          }`}
        >
          {isUp ? '+' : ''}
          {pnlPct.toFixed(2)}%
        </p>
        <p
          className={`text-xs font-mono mt-0.5 ${
            isUp ? 'text-[var(--accent-green)]/70' : 'text-[var(--accent-red)]/70'
          }`}
        >
          {isUp ? '+' : ''}${pnl.toFixed(2)}
        </p>
      </div>

      <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
        <p className="text-xs text-[var(--text-secondary)] mb-1">Trades</p>
        <p className="text-xl font-bold font-mono tracking-tight">{totalTrades}</p>
        <p className="text-xs text-[var(--text-secondary)] mt-0.5">
          <span className="text-[var(--accent-green)]">{buys} buy</span>
          {' \u00B7 '}
          <span className="text-[var(--accent-red)]">{sells} sell</span>
        </p>
      </div>

      <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
        <p className="text-xs text-[var(--text-secondary)] mb-1">Win Rate</p>
        <p className="text-xl font-bold font-mono tracking-tight">
          {winRate}
          {typeof winRate === 'string' && winRate !== '\u2014' ? '%' : ''}
        </p>
        <p className="text-xs text-[var(--text-secondary)] mt-0.5">
          {winTrades}W \u00B7 {lossTrades}L
        </p>
      </div>
    </div>
  );
}
