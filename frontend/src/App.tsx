import { useEffect, useState, useCallback } from 'react';
import { api } from './api';
import type { Trade, PortfolioSnapshot, BotConfig } from './api';
import { useWebSocket } from './hooks/useWebSocket';
import { Header } from './components/Header';
import { StatsPanel } from './components/StatsPanel';
import { PortfolioChart } from './components/PortfolioChart';
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

  const currentValue = portfolio.length > 0 ? portfolio[0].total_value_usdt : null;

  return (
    <div className="min-h-screen flex flex-col bg-[var(--bg-primary)]">
      <Header
        mode={config?.mode ?? '...'}
        connected={connected}
        portfolioValue={currentValue}
        tab={tab}
        onTabChange={setTab}
      />

      <main className="flex-1 px-4 sm:px-6 lg:px-8 py-5 max-w-[1400px] mx-auto w-full space-y-5">
        {error && tab === 'dashboard' && (
          <div className="bg-[var(--accent-red)]/8 border border-[var(--accent-red)]/20 rounded-lg px-4 py-3 text-sm text-[var(--accent-red)]">
            {error}
          </div>
        )}

        {tab === 'dashboard' && (
          <>
            <StatsPanel portfolio={portfolio} trades={trades} />

            {config?.mode === 'paper' && (
              <PaperTradingPanel config={config} onConfigRefresh={fetchData} />
            )}

            <PositionsPanel trades={trades} refreshTrigger={signalTrigger} />

            <PortfolioChart data={portfolio} />

            <SignalsPanel refreshTrigger={signalTrigger} />
          </>
        )}

        {tab === 'backtest' && <BacktestPanel />}
      </main>

      <footer className="px-6 py-4 border-t border-[var(--border-subtle)] text-center text-xs text-[var(--text-secondary)]">
        {config?.pairs?.join(' \u00B7 ') ?? '...'} \u00B7 {config?.timeframe ?? '...'}
      </footer>
    </div>
  );
}

export default App;
