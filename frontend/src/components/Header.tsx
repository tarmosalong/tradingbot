import { useState } from 'react';

interface HeaderProps {
  mode: string;
  connected: boolean;
}

const MODE_TIPS: Record<string, string> = {
  paper: 'Paper mode — simulated trading with fake money. No real funds are used.',
  live: 'Live mode — real money trading on Binance. Be careful!',
};

export function Header({ mode, connected }: HeaderProps) {
  const [tipOpen, setTipOpen] = useState(false);
  const tip = MODE_TIPS[mode] ?? `Mode: ${mode}`;

  return (
    <header className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold tracking-tight">Trading Bot</h1>
        <span
          className="relative px-2 py-0.5 text-xs font-medium rounded bg-[var(--accent-blue)]/20 text-[var(--accent-blue)] uppercase cursor-help"
          onMouseEnter={() => setTipOpen(true)}
          onMouseLeave={() => setTipOpen(false)}
        >
          {mode}
          {tipOpen && (
            <span className="absolute z-50 top-full left-0 mt-2 w-56 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-[11px] text-[var(--text-primary)] leading-relaxed shadow-lg pointer-events-none normal-case font-normal">
              {tip}
            </span>
          )}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${
            connected ? 'bg-[var(--accent-green)] animate-pulse' : 'bg-[var(--accent-red)]'
          }`}
        />
        <span className="text-sm text-[var(--text-secondary)]">
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>
    </header>
  );
}
