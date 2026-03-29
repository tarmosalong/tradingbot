import { useState } from 'react';
import type { BotConfig } from '../api';

interface ConfigPanelProps {
  config: BotConfig | null;
}

const RISK_TIPS: Record<string, string> = {
  max_position: 'Maximum percentage of your balance the bot can put into a single trade.',
  stop_loss: 'If the price drops by this percentage, the bot sells automatically to limit loss.',
  trailing_stop: 'A dynamic stop that rises with the price. If the price drops by this % from its peak, the bot sells.',
  max_drawdown: 'If total portfolio drops by this % from its highest point, the bot stops trading to protect funds.',
  daily_loss: 'Maximum allowed loss in a single day. If hit, the bot pauses until the next day.',
  max_order: 'The largest single trade the bot can make, in USDT.',
};

function InfoTooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  return (
    <span className="relative inline-flex ml-1">
      <button
        type="button"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onClick={() => setShow((p) => !p)}
        className="w-3.5 h-3.5 rounded-full bg-[var(--bg-primary)] text-[var(--text-secondary)] text-[9px] font-bold leading-none flex items-center justify-center cursor-help hover:text-[var(--text-primary)] transition-colors"
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
        <h2 className="text-sm font-medium">Bot Configuration</h2>
        <p className="text-[11px] text-[var(--text-secondary)]">Current settings and risk limits</p>
      </div>

      {isPaper && (
        <div className="mx-4 -mt-2 rounded-lg border border-[var(--accent-blue)]/35 bg-[var(--accent-blue)]/5 px-3 py-3 text-sm">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--accent-blue)] mb-1">
            Paper mode active
          </h3>
          <p className="text-[var(--text-secondary)] text-xs leading-relaxed">
            Use the <strong className="text-[var(--text-primary)] font-medium">Paper Trading</strong> panel above to control the bot.
          </p>
          <InfoRow
            label="Starting balance"
            value={
              config.paper_trading != null
                ? `$${config.paper_trading.initial_balance_usdt.toLocaleString()}`
                : '—'
            }
          />
        </div>
      )}

      <div className="p-4 pt-0 space-y-3 text-sm">
        <div className="grid grid-cols-2 gap-3">
          <InfoRow label="Trading pairs" value={config.pairs.join(', ')} />
          <InfoRow label="Timeframe" value={config.timeframe} />
          <InfoRow label="Check interval" value={`every ${config.poll_interval}s`} />
          <InfoRow label="Strategies" value={config.strategies.join(', ')} />
        </div>

        <div className="border-t border-[var(--border)] pt-3 mt-3">
          <h3 className="text-xs font-medium text-[var(--text-secondary)] mb-2">Risk Protection</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <InfoRowTip label="Max position" value={`${(config.risk.max_position_pct * 100).toFixed(0)}%`} tip={RISK_TIPS.max_position} />
            <InfoRowTip label="Stop loss" value={`${(config.risk.stop_loss_pct * 100).toFixed(1)}%`} tip={RISK_TIPS.stop_loss} />
            <InfoRowTip label="Trailing stop" value={`${(config.risk.trailing_stop_pct * 100).toFixed(1)}%`} tip={RISK_TIPS.trailing_stop} />
            <InfoRowTip label="Max drawdown" value={`${(config.risk.max_drawdown_pct * 100).toFixed(0)}%`} tip={RISK_TIPS.max_drawdown} />
            <InfoRowTip label="Daily loss limit" value={`${(config.risk.daily_loss_limit_pct * 100).toFixed(0)}%`} tip={RISK_TIPS.daily_loss} />
            <InfoRowTip label="Max order size" value={`$${config.risk.max_single_order_usdt}`} tip={RISK_TIPS.max_order} />
          </div>
        </div>
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

function InfoRowTip({ label, value, tip }: { label: string; value: string; tip: string }) {
  return (
    <div className="flex items-center gap-0.5">
      <span className="text-[var(--text-secondary)]">{label}:</span>{' '}
      <span className="font-medium">{value}</span>
      <InfoTooltip text={tip} />
    </div>
  );
}
