import { useState } from 'react';
import type { Trade, OpenPosition, ExitRule } from '../api';

interface PositionsPanelProps {
  trades: Trade[];
  positions: OpenPosition[];
  exitRules: ExitRule[];
  loading: boolean;
}

export function PositionsPanel({
  trades,
  positions,
  exitRules,
  loading,
}: PositionsPanelProps) {
  const [showAllTrades, setShowAllTrades] = useState(false);

  const visibleTrades = showAllTrades ? trades : trades.slice(0, 10);
  const hasPositions = positions.length > 0;
  const hasTrades = trades.length > 0;

  return (
    <div className="bg-[var(--bg-card)]/80 backdrop-blur-sm rounded-xl border border-[var(--border)] overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--border)] flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium text-[var(--text-primary)]">Trading Activity</h2>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5">
            Open positions and trade history
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasPositions && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--accent-green)]/15 text-[var(--accent-green)] font-medium">
              {positions.length} open
            </span>
          )}
          {hasTrades && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--bg-secondary)] text-[var(--text-secondary)] font-medium">
              {trades.length} trades
            </span>
          )}
        </div>
      </div>

      {loading ? (
        <div className="px-4 py-8 text-center text-sm text-[var(--text-secondary)]">
          Loading...
        </div>
      ) : (
        <>
          {/* Open positions */}
          {hasPositions && (
            <div className="divide-y divide-[var(--border)]">
              {positions.map((pos) => (
                <PositionRow
                  key={pos.symbol}
                  position={pos}
                  fills={trades.filter(
                    (t) => t.symbol === pos.symbol && t.side === 'BUY',
                  )}
                />
              ))}
            </div>
          )}

          {/* Exit rules */}
          {exitRules.length > 0 && (
            <div className="px-4 py-3 border-t border-[var(--border)]">
              <ExitRulesBox rules={exitRules} />
            </div>
          )}

          {/* Trade history */}
          <div className="border-t border-[var(--border)]">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[var(--text-secondary)] text-xs uppercase tracking-wider">
                    <th className="px-4 py-2.5">Time</th>
                    <th className="px-4 py-2.5">Symbol</th>
                    <th className="px-4 py-2.5">Side</th>
                    <th className="px-4 py-2.5 text-right">Amount</th>
                    <th className="px-4 py-2.5 text-right">Price</th>
                    <th className="px-4 py-2.5 text-right">P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {!hasTrades ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center">
                        <p className="text-[var(--text-secondary)] text-sm mb-1">
                          No trades yet
                        </p>
                        <p className="text-[var(--text-secondary)] text-xs">
                          The bot is analysing the market. When it finds a strong
                          signal, it will place a trade automatically.
                        </p>
                      </td>
                    </tr>
                  ) : (
                    visibleTrades.map((trade) => (
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
                        <td className="px-4 py-2 text-right font-mono">
                          {trade.amount.toFixed(6)}
                        </td>
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
                            <span className="text-[var(--text-secondary)]">
                              —
                            </span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {trades.length > 10 && (
              <div className="px-4 py-2 border-t border-[var(--border)]">
                <button
                  type="button"
                  onClick={() => setShowAllTrades((p) => !p)}
                  className="text-xs text-[var(--accent)] hover:underline cursor-pointer"
                >
                  {showAllTrades
                    ? `Show less`
                    : `Show all ${trades.length} trades`}
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function PositionRow({
  position: pos,
  fills,
}: {
  position: OpenPosition;
  fills: Trade[];
}) {
  const pnlColor =
    pos.pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
  const priceDropToSl =
    ((pos.current_price - pos.stop_loss_price) / pos.current_price) * 100;
  const priceDropToTs =
    ((pos.current_price - pos.trailing_stop_price) / pos.current_price) * 100;
  const nearestExit = Math.min(priceDropToSl, priceDropToTs);
  const totalCost = pos.amount * pos.entry_price;

  return (
    <div className="px-4 py-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-medium text-[var(--text-primary)]">
            {pos.symbol}
          </span>
          <span className="text-xs text-[var(--text-secondary)]">
            {pos.amount.toFixed(6)} @ $
            {pos.entry_price.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
          {fills.length > 1 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-[var(--bg-secondary)] text-[var(--text-secondary)]">
              avg of {fills.length} buys
            </span>
          )}
        </div>
        <div className="text-right">
          <span className="font-mono text-sm" style={{ color: pnlColor }}>
            {pos.pnl >= 0 ? '+' : ''}
            {pos.pnl_pct.toFixed(2)}%
          </span>
          <span className="text-xs text-[var(--text-secondary)] ml-2">
            ({pos.pnl >= 0 ? '+' : ''}${pos.pnl.toFixed(2)})
          </span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 text-xs">
        <PriceInfo
          label={fills.length > 1 ? 'Avg Entry' : 'Entry'}
          value={pos.entry_price}
          sub={`$${totalCost.toLocaleString(undefined, { maximumFractionDigits: 2 })} total`}
        />
        <PriceInfo label="Current" value={pos.current_price} />
        <PriceInfo label="Peak" value={pos.peak_price} highlight />
      </div>

      {fills.length > 1 && (
        <div className="rounded-lg bg-[var(--bg-secondary)]/40 px-3 py-2">
          <p className="text-[10px] font-medium text-[var(--text-secondary)] uppercase tracking-wider mb-1.5">
            Buy fills
          </p>
          <div className="space-y-1">
            {fills.map((f, i) => (
              <div
                key={f.id ?? i}
                className="flex items-center justify-between text-xs"
              >
                <span className="text-[var(--text-secondary)]">
                  {new Date(f.executed_at).toLocaleString([], {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
                <span className="font-mono text-[var(--text-primary)]">
                  {f.amount.toFixed(6)} @ $
                  {f.price.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <p className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
          Exit conditions
        </p>
        <ExitCondition
          icon={'\u{1F6D1}'}
          label="Stop-loss"
          price={pos.stop_loss_price}
          distance={priceDropToSl}
          description={`Sells if price drops to $${pos.stop_loss_price.toLocaleString(undefined, { minimumFractionDigits: 2 })} (${priceDropToSl.toFixed(1)}% below current)`}
        />
        <ExitCondition
          icon={'\u{1F4C9}'}
          label="Trailing stop"
          price={pos.trailing_stop_price}
          distance={priceDropToTs}
          description={`Sells if price drops to $${pos.trailing_stop_price.toLocaleString(undefined, { minimumFractionDigits: 2 })} (${priceDropToTs.toFixed(1)}% below current, tracks peak $${pos.peak_price.toLocaleString(undefined, { minimumFractionDigits: 2 })})`}
        />
        <ExitCondition
          icon={'\u{1F4CA}'}
          label="Strategy signal"
          description="Sells when RSI \u2265 70 (overbought), bearish MACD crossover, or price above Bollinger upper band"
        />
      </div>

      {nearestExit < 3 && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--accent-red)]/10 border border-[var(--accent-red)]/20">
          <span className="text-xs text-[var(--accent-red)]">
            {'\u26A0'} Price is {nearestExit.toFixed(1)}% from nearest exit
            trigger
          </span>
        </div>
      )}
    </div>
  );
}

function PriceInfo({
  label,
  value,
  highlight,
  sub,
}: {
  label: string;
  value: number;
  highlight?: boolean;
  sub?: string;
}) {
  return (
    <div className="rounded-lg bg-[var(--bg-secondary)] px-2.5 py-1.5">
      <p className="text-[var(--text-secondary)] text-[10px] uppercase tracking-wider">
        {label}
      </p>
      <p
        className={`font-mono text-sm ${highlight ? 'text-[var(--accent-green)]' : 'text-[var(--text-primary)]'}`}
      >
        $
        {value.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}
      </p>
      {sub && (
        <p className="text-[10px] text-[var(--text-secondary)] mt-0.5">
          {sub}
        </p>
      )}
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
          <span className="text-xs font-medium text-[var(--text-primary)]">
            {label}
          </span>
          {price != null && distance != null && (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                distance < 3
                  ? 'bg-[var(--accent-red)]/15 text-[var(--accent-red)]'
                  : 'bg-[var(--bg-card)] text-[var(--text-secondary)]'
              }`}
            >
              {distance.toFixed(1)}% away
            </span>
          )}
        </div>
        <p className="text-[11px] text-[var(--text-secondary)] mt-0.5 leading-relaxed">
          {description}
        </p>
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
          <span
            className={`w-1.5 h-1.5 rounded-full ${rule.active ? 'bg-[var(--accent-green)]' : 'bg-[var(--text-secondary)]/30'}`}
          />
          <span className="text-[var(--text-secondary)]">
            <span className="text-[var(--text-primary)] font-medium">
              {rule.name}
            </span>
            {' \u2014 '}
            {rule.description}
          </span>
        </div>
      ))}
    </div>
  );
}
