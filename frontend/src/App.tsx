import { useEffect, useState, useCallback } from 'react';
import { api } from './api';
import type { Trade, PortfolioSnapshot, BotConfig } from './api';
import { useWebSocket } from './hooks/useWebSocket';
import { Header } from './components/Header';
import { StatsPanel } from './components/StatsPanel';
import { PortfolioChart } from './components/PortfolioChart';
import { TradesTable } from './components/TradesTable';
import { ConfigPanel } from './components/ConfigPanel';
import { PaperTradingPanel } from './components/PaperTradingPanel';
import { SignalsPanel } from './components/SignalsPanel';
import { BacktestPanel } from './components/BacktestPanel';
import { PositionsPanel } from './components/PositionsPanel';

type Tab = 'dashboard' | 'backtest';

function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [trades, setTrades] = useState<Trade[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot[]>([]);
  const [config, setConfig] = useState<BotConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  const wsUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;
  const { lastMessage, connected } = useWebSocket(wsUrl);

  const fetchData = useCallback(async () => {
    try {
      const [t, p, c] = await Promise.all([
        api.trades(),
        api.portfolio(),
        api.config(),
      ]);
      setTrades(t);
      setPortfolio(p);
      setConfig(c);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch data');
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    if (lastMessage?.type === 'trade' || lastMessage?.type === 'portfolio') {
      fetchData();
    }
  }, [lastMessage, fetchData]);

  const signalTrigger = lastMessage?.type === 'signal' ? lastMessage : null;

  return (
    <div className="min-h-screen flex flex-col bg-[var(--bg-primary)]">
      <Header mode={config?.mode ?? '...'} connected={connected} />

      <nav className="flex gap-1 px-6 pt-4 pb-2">
        <TabButton active={tab === 'dashboard'} onClick={() => setTab('dashboard')}>
          Dashboard
        </TabButton>
        <TabButton active={tab === 'backtest'} onClick={() => setTab('backtest')}>
          Backtest
        </TabButton>
      </nav>

      <main className="flex-1 p-6 pt-2 max-w-7xl mx-auto w-full space-y-6">
        {error && tab === 'dashboard' && (
          <div className="bg-[var(--accent-red)]/10 border border-[var(--accent-red)]/30 rounded-xl px-4 py-3 text-sm text-[var(--accent-red)]">
            {error}
          </div>
        )}

        {tab === 'dashboard' && (
          <>
            <StatsPanel portfolio={portfolio} trades={trades} />
            {config?.mode === 'paper' && (
              <PaperTradingPanel config={config} onConfigRefresh={fetchData} />
            )}
            <PositionsPanel refreshTrigger={signalTrigger} />
            <SignalsPanel refreshTrigger={signalTrigger} />
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <PortfolioChart data={portfolio} />
              </div>
              <div>
                <ConfigPanel config={config} />
              </div>
            </div>
            <TradesTable trades={trades} />
          </>
        )}

        {tab === 'backtest' && <BacktestPanel />}
      </main>

      <footer className="px-6 py-3 border-t border-[var(--border)] text-center text-xs text-[var(--text-secondary)]">
        Trading Bot Dashboard &middot; {config?.pairs?.join(' · ') ?? '...'} &middot; {config?.timeframe ?? '...'}
      </footer>
    </div>
  );
}

function TabButton({
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
      className={`px-4 py-2 text-sm font-medium rounded-lg transition-all cursor-pointer ${
        active
          ? 'bg-[var(--bg-card)] text-[var(--accent)] shadow-sm shadow-[var(--accent)]/10 border border-[var(--border)]'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]'
      }`}
    >
      {children}
    </button>
  );
}

export default App;
