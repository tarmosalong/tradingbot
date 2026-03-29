import type { Trade } from '../api';

interface TradesTableProps {
  trades: Trade[];
}

export function TradesTable({ trades }: TradesTableProps) {
  return (
    <div className="bg-[var(--bg-card)]/80 backdrop-blur-sm rounded-xl border border-[var(--border)] overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--border)]">
        <h2 className="text-sm font-medium text-[var(--text-secondary)]">Recent Trades</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[var(--text-secondary)] text-xs uppercase tracking-wider">
              <th className="px-4 py-2">Time</th>
              <th className="px-4 py-2">Symbol</th>
              <th className="px-4 py-2">Side</th>
              <th className="px-4 py-2 text-right">Amount</th>
              <th className="px-4 py-2 text-right">Price</th>
              <th className="px-4 py-2 text-right">P&L</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center">
                  <p className="text-[var(--text-secondary)] text-sm mb-1">No trades yet</p>
                  <p className="text-[var(--text-secondary)] text-xs">
                    The bot is analysing the market. When it finds a strong signal, it will place a trade automatically.
                  </p>
                </td>
              </tr>
            ) : (
              trades.map((trade) => (
                <tr
                  key={trade.id}
                  className="border-t border-[var(--border)] hover:bg-[var(--bg-secondary)]/50 transition-colors"
                >
                  <td className="px-4 py-2 text-[var(--text-secondary)]">
                    {new Date(trade.executed_at).toLocaleString([], {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </td>
                  <td className="px-4 py-2 font-medium">{trade.symbol}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                        trade.side === 'BUY'
                          ? 'bg-[var(--accent-green)]/20 text-[var(--accent-green)]'
                          : 'bg-[var(--accent-red)]/20 text-[var(--accent-red)]'
                      }`}
                    >
                      {trade.side === 'BUY' ? 'Buy' : 'Sell'}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right font-mono">{trade.amount.toFixed(6)}</td>
                  <td className="px-4 py-2 text-right font-mono">
                    ${trade.price.toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {trade.pnl != null ? (
                      <span
                        className={
                          trade.pnl >= 0
                            ? 'text-[var(--accent-green)]'
                            : 'text-[var(--accent-red)]'
                        }
                      >
                        {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                      </span>
                    ) : (
                      <span className="text-[var(--text-secondary)]">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
