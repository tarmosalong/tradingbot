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

  return (
    <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)]">
      <div className="px-4 py-3 border-b border-[var(--border)]">
        <h2 className="text-sm font-medium text-[var(--text-secondary)]">Bot Configuration</h2>
      </div>
      <div className="p-4 grid grid-cols-2 gap-3 text-sm">
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
