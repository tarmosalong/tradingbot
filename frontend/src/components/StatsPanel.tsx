import { useState } from 'react';
import type { Trade, PortfolioSnapshot } from '../api';

interface StatsPanelProps {
  portfolio: PortfolioSnapshot[];
  trades: Trade[];
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
        className="w-3.5 h-3.5 rounded-full bg-[var(--bg-secondary)] text-[var(--text-secondary)] text-[9px] font-bold leading-none flex items-center justify-center cursor-help hover:text-[var(--text-primary)] transition-colors"
      >
        ?
      </button>
      {show && (
        <span className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-[11px] text-[var(--text-primary)] leading-relaxed shadow-lg pointer-events-none">
          {text}
        </span>
      )}
    </span>
  );
}

function StatCard({
  label,
  value,
  color,
  tip,
}: {
  label: string;
  value: string;
  color?: string;
  tip: string;
}) {
  return (
    <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
      <p className="text-xs font-medium text-[var(--text-secondary)] mb-1 flex items-center">
        {label}
        <InfoTooltip text={tip} />
      </p>
      <p className={`text-lg font-bold ${color ?? ''}`}>{value}</p>
    </div>
  );
}

export function StatsPanel({ portfolio, trades }: StatsPanelProps) {
  const currentValue = portfolio.length > 0 ? portfolio[0].total_value_usdt : 0;
  const initialValue =
    portfolio.length > 0 ? portfolio[portfolio.length - 1].total_value_usdt : 0;
  const pnl = currentValue - initialValue;
  const pnlPct = initialValue > 0 ? (pnl / initialValue) * 100 : 0;

  const totalTrades = trades.length;
  const buys = trades.filter((t) => t.side === 'BUY').length;
  const sells = trades.filter((t) => t.side === 'SELL').length;

  const pnlColor = pnl >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]';

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <StatCard
        label="Portfolio Value"
        value={`$${currentValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
        tip="Total value of all your holdings converted to USDT. Starts at the configured paper trading balance."
      />
      <StatCard
        label="Total P&L"
        value={`${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (${pnlPct.toFixed(2)}%)`}
        color={pnlColor}
        tip="Profit and Loss — the difference between your current value and starting balance. Green means profit, red means loss."
      />
      <StatCard
        label="Total Trades"
        value={String(totalTrades)}
        tip="How many trades the bot has executed. In paper mode these are simulated, not real money."
      />
      <StatCard
        label="Buy / Sell"
        value={`${buys} / ${sells}`}
        tip="Number of buy orders vs sell orders. The bot buys when it detects opportunity and sells when it thinks the price will drop."
      />
    </div>
  );
}
