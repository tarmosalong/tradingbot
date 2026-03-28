interface HeaderProps {
  mode: string;
  connected: boolean;
}

export function Header({ mode, connected }: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold tracking-tight">Trading Bot</h1>
        <span className="px-2 py-0.5 text-xs font-medium rounded bg-[var(--accent-blue)]/20 text-[var(--accent-blue)] uppercase">
          {mode}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${
            connected ? 'bg-[var(--accent-green)]' : 'bg-[var(--accent-red)]'
          }`}
        />
        <span className="text-sm text-[var(--text-secondary)]">
          {connected ? 'Live' : 'Disconnected'}
        </span>
      </div>
    </header>
  );
}
