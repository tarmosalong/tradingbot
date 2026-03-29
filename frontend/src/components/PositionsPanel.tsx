import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import type { OpenPosition, ExitRule } from '../api';

interface PositionsPanelProps {
  refreshTrigger?: unknown;
}

export function PositionsPanel({ refreshTrigger }: PositionsPanelProps) {
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [exitRules, setExitRules] = useState<ExitRule[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchPositions = useCallback(async () => {
    try {
      const data = await api.botPositions();
      setPositions(data.positions);
      setExitRules(data.exit_rules);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPositions();
    const interval = setInterval(fetchPositions, 5000);
    return () => clearInterval(interval);
  }, [fetchPositions]);

  useEffect(() => {
    fetchPositions();
  }, [refreshTrigger, fetchPositions]);

  return (
    <div className="bg-[var(--bg-card)]/80 backdrop-blur-sm rounded-xl border border-[var(--border)] overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--border)] flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium text-[var(--text-primary)]">Open Positions</h2>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5">
            Holdings the bot has bought and hasn't sold yet
          </p>
        </div>
        {positions.length > 0 && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--accent-green)]/15 text-[var(--accent-green)] font-medium">
            {positions.length} active
          </span>
        )}
      </div>

      {loading ? (
        <div className="px-4 py-8 text-center text-sm text-[var(--text-secondary)]">Loading...</div>
      ) : positions.length === 0 ? (
        <div className="px-4 py-6">
          <p className="text-center text-sm text-[var(--text-secondary)] mb-4">No open positions</p>
          <ExitRulesBox rules={exitRules} />
        </div>
      ) : (
        <div className="divide-y divide-[var(--border)]">
          {positions.map((pos) => (
            <PositionRow key={pos.symbol} position={pos} />
          ))}
          <div className="px-4 py-3">
            <ExitRulesBox rules={exitRules} />
          </div>
        </div>
      )}
    </div>
  );
}

function PositionRow({ position: pos }: { position: OpenPosition }) {
  const pnlColor = pos.pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
  const priceDropToSl = ((pos.current_price - pos.stop_loss_price) / pos.current_price) * 100;
  const priceDropToTs = ((pos.current_price - pos.trailing_stop_price) / pos.current_price) * 100;
  const nearestExit = Math.min(priceDropToSl, priceDropToTs);

  return (
    <div className="px-4 py-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-medium text-[var(--text-primary)]">{pos.symbol}</span>
          <span className="text-xs text-[var(--text-secondary)]">
            {pos.amount.toFixed(6)} @ ${pos.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>
        <div className="text-right">
          <span className="font-mono text-sm" style={{ color: pnlColor }}>
            {pos.pnl >= 0 ? '+' : ''}{pos.pnl_pct.toFixed(2)}%
          </span>
          <span className="text-xs text-[var(--text-secondary)] ml-2">
            ({pos.pnl >= 0 ? '+' : ''}${pos.pnl.toFixed(2)})
          </span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 text-xs">
        <PriceInfo label="Entry" value={pos.entry_price} />
        <PriceInfo label="Current" value={pos.current_price} />
        <PriceInfo label="Peak" value={pos.peak_price} highlight />
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
          Exit conditions
        </p>

        <ExitCondition
          icon="🛑"
          label="Stop-loss"
          price={pos.stop_loss_price}
          distance={priceDropToSl}
          description={`Sells if price drops to $${pos.stop_loss_price.toLocaleString(undefined, { minimumFractionDigits: 2 })} (${priceDropToSl.toFixed(1)}% below current)`}
        />
        <ExitCondition
          icon="📉"
          label="Trailing stop"
          price={pos.trailing_stop_price}
          distance={priceDropToTs}
          description={`Sells if price drops to $${pos.trailing_stop_price.toLocaleString(undefined, { minimumFractionDigits: 2 })} (${priceDropToTs.toFixed(1)}% below current, tracks peak $${pos.peak_price.toLocaleString(undefined, { minimumFractionDigits: 2 })})`}
        />
        <ExitCondition
          icon="📊"
          label="Strategy signal"
          description="Sells when RSI ≥ 70 (overbought), bearish MACD crossover, or price above Bollinger upper band"
        />
      </div>

      {nearestExit < 3 && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--accent-red)]/10 border border-[var(--accent-red)]/20">
          <span className="text-xs text-[var(--accent-red)]">
            ⚠ Price is {nearestExit.toFixed(1)}% from nearest exit trigger
          </span>
        </div>
      )}
    </div>
  );
}

function PriceInfo({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className="rounded-lg bg-[var(--bg-secondary)] px-2.5 py-1.5">
      <p className="text-[var(--text-secondary)] text-[10px] uppercase tracking-wider">{label}</p>
      <p className={`font-mono text-sm ${highlight ? 'text-[var(--accent-green)]' : 'text-[var(--text-primary)]'}`}>
        ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </p>
    </div>
  );
}

function ExitCondition({
  icon,
  label,
  price,
  distance,
  description,
}: {
  icon: string;
  label: string;
  price?: number;
  distance?: number;
  description: string;
}) {
  return (
    <div className="flex items-start gap-2 rounded-lg bg-[var(--bg-secondary)]/60 px-3 py-2">
      <span className="text-sm mt-0.5">{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-[var(--text-primary)]">{label}</span>
          {price != null && distance != null && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
              distance < 3
                ? 'bg-[var(--accent-red)]/15 text-[var(--accent-red)]'
                : 'bg-[var(--bg-card)] text-[var(--text-secondary)]'
            }`}>
              {distance.toFixed(1)}% away
            </span>
          )}
        </div>
        <p className="text-[11px] text-[var(--text-secondary)] mt-0.5 leading-relaxed">{description}</p>
      </div>
    </div>
  );
}

function ExitRulesBox({ rules }: { rules: ExitRule[] }) {
  if (!rules.length) return null;
  return (
    <div className="rounded-lg bg-[var(--bg-secondary)]/40 px-3 py-2.5 space-y-1.5">
      <p className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
        When will the bot sell?
      </p>
      {rules.map((rule) => (
        <div key={rule.name} className="flex items-center gap-2 text-xs">
          <span className={`w-1.5 h-1.5 rounded-full ${rule.active ? 'bg-[var(--accent-green)]' : 'bg-[var(--text-secondary)]/30'}`} />
          <span className="text-[var(--text-secondary)]">
            <span className="text-[var(--text-primary)] font-medium">{rule.name}</span>
            {' — '}
            {rule.description}
          </span>
        </div>
      ))}
    </div>
  );
}
