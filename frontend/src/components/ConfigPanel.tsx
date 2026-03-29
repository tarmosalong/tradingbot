import type { BotConfig } from '../api';

interface ConfigPanelProps {
  config: BotConfig | null;
}

export function ConfigPanel({ config }: ConfigPanelProps) {
  if (!config) {
    return (
      <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
        <p className="text-sm text-[var(--text-secondary)]">Loading config...</p>
      </div>
    );
  }

  const isPaper = config.mode === 'paper';

  return (
    <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)] space-y-4">
      <div className="px-4 py-3 border-b border-[var(--border)]">
        <h2 className="text-sm font-medium text-[var(--text-secondary)]">Bot Configuration</h2>
      </div>

      {isPaper && (
        <div className="mx-4 -mt-2 rounded-lg border border-[var(--accent-blue)]/35 bg-[var(--accent-blue)]/5 px-3 py-3 text-sm">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--accent-blue)] mb-2">
            Paper trading
          </h3>
          <p className="text-[var(--text-secondary)] text-xs leading-relaxed mb-2">
            Use the <strong className="text-[var(--text-primary)] font-medium">Paper trading</strong> panel above for
            start/stop and editing <code className="text-[var(--text-primary)] bg-[var(--bg-secondary)] px-1 rounded">config.yaml</code>{' '}
            (or run <code className="text-[var(--accent-green)] bg-[var(--bg-secondary)] px-1 rounded text-[11px]">python -m backend.main</code>{' '}
            for a separate process).
          </p>
          <InfoRow
            label="Starting balance (config)"
            value={
              config.paper_trading != null
                ? `$${config.paper_trading.initial_balance_usdt.toLocaleString()}`
                : '—'
            }
          />
        </div>
      )}

      <div className="p-4 pt-0 grid grid-cols-2 gap-3 text-sm">
        <InfoRow label="Pairs" value={config.pairs.join(', ')} />
        <InfoRow label="Timeframe" value={config.timeframe} />
        <InfoRow label="Poll Interval" value={`${config.poll_interval}s`} />
        <InfoRow label="Strategies" value={config.strategies.join(', ')} />
        <InfoRow label="Max Position" value={`${(config.risk.max_position_pct * 100).toFixed(0)}%`} />
        <InfoRow label="Stop Loss" value={`${(config.risk.stop_loss_pct * 100).toFixed(1)}%`} />
        <InfoRow label="Trailing Stop" value={`${(config.risk.trailing_stop_pct * 100).toFixed(1)}%`} />
        <InfoRow label="Max Drawdown" value={`${(config.risk.max_drawdown_pct * 100).toFixed(0)}%`} />
        <InfoRow label="Daily Loss Limit" value={`${(config.risk.daily_loss_limit_pct * 100).toFixed(0)}%`} />
        <InfoRow label="Max Order" value={`$${config.risk.max_single_order_usdt}`} />
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-[var(--text-secondary)]">{label}:</span>{' '}
      <span className="font-medium">{value}</span>
    </div>
  );
}
