interface HeaderProps {
  mode: string;
  connected: boolean;
  portfolioValue: number | null;
  tab: string;
  onTabChange: (tab: 'dashboard' | 'backtest') => void;
}

const MODE_LABEL: Record<string, string> = {
  paper: 'Paper',
  live: 'Live',
};

export function Header({ mode, connected, portfolioValue, tab, onTabChange }: HeaderProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--border)] bg-[var(--bg-primary)]/80 backdrop-blur-md">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          {/* Left: logo + nav */}
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2.5">
              <span className="text-base font-semibold tracking-tight">TradingBot</span>
              <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded uppercase tracking-wider ${
                mode === 'live'
                  ? 'bg-[var(--accent-red)]/15 text-[var(--accent-red)]'
                  : 'bg-[var(--accent-green)]/10 text-[var(--accent-green)]'
              }`}>
                {MODE_LABEL[mode] ?? mode}
              </span>
            </div>

            <nav className="flex items-center gap-1">
              <NavTab active={tab === 'dashboard'} onClick={() => onTabChange('dashboard')}>
                Dashboard
              </NavTab>
              <NavTab active={tab === 'backtest'} onClick={() => onTabChange('backtest')}>
                Backtest
              </NavTab>
            </nav>
          </div>

          {/* Right: portfolio + status */}
          <div className="flex items-center gap-4">
            {portfolioValue != null && (
              <span className="text-sm font-mono font-medium text-[var(--text-primary)]">
                ${portfolioValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            )}
            <div className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${
                connected ? 'bg-[var(--accent-green)]' : 'bg-[var(--accent-red)]'
              }`} />
              <span className="text-xs text-[var(--text-secondary)]">
                {connected ? 'Live' : 'Offline'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

function NavTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors cursor-pointer ${
        active
          ? 'text-[var(--text-primary)] bg-[var(--bg-secondary)]'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
      }`}
    >
      {children}
    </button>
  );
}
