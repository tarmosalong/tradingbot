import { useEffect, useState, useCallback } from 'react';
import { api } from './api';
import type { Trade, PortfolioSnapshot, BotConfig } from './api';
import { useWebSocket } from './hooks/useWebSocket';
import { Header } from './components/Header';
import { StatsPanel } from './components/StatsPanel';
import { PortfolioChart } from './components/PortfolioChart';
import { TradesTable } from './components/TradesTable';
import { ConfigPanel } from './components/ConfigPanel';

function App() {
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

  return (
    <div className="min-h-screen flex flex-col">
      <Header mode={config?.mode ?? '...'} connected={connected} />

      <main className="flex-1 p-6 max-w-7xl mx-auto w-full space-y-6">
        {error && (
          <div className="bg-[var(--accent-red)]/10 border border-[var(--accent-red)]/30 rounded-lg px-4 py-3 text-sm text-[var(--accent-red)]">
            {error}
          </div>
        )}

        <StatsPanel portfolio={portfolio} trades={trades} />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <PortfolioChart data={portfolio} />
          </div>
          <div>
            <ConfigPanel config={config} />
          </div>
        </div>

        <TradesTable trades={trades} />
      </main>

      <footer className="px-6 py-3 border-t border-[var(--border)] text-center text-xs text-[var(--text-secondary)]">
        Trading Bot Dashboard &middot; {config?.pairs?.join(' · ') ?? '...'} &middot; {config?.timeframe ?? '...'}
      </footer>
    </div>
  );
}

export default App;
