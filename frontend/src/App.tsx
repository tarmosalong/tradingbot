import { useEffect, useState, useCallback } from 'react';
import { api } from './api';
import type { Trade, PortfolioSnapshot, BotConfig, OpenPosition, ExitRule } from './api';
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
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [exitRules, setExitRules] = useState<ExitRule[]>([]);
  const [positionsLoading, setPositionsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const wsUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;
  const { lastMessage, connected } = useWebSocket(wsUrl);

  const fetchData = useCallback(async () => {
    try {
      const [t, p, c, posData] = await Promise.all([
        api.trades(),
        api.portfolio(),
        api.config(),
        api.botPositions().catch(() => ({ positions: [], risk_config: { stop_loss_pct: 0, trailing_stop_pct: 0 }, exit_rules: [] })),
      ]);
      setTrades(t);
      setPortfolio(p);
      setConfig(c);
      setPositions(posData.positions);
      setExitRules(posData.exit_rules);
      setPositionsLoading(false);
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

  const initialBalance = config?.paper_trading?.initial_balance_usdt ?? 10_000;
  const unrealizedPnl = positions.reduce((sum, p) => sum + p.pnl, 0);
  const realizedPnl = trades.reduce((sum, t) => sum + (t.pnl ?? 0), 0);
  const currentValue = initialBalance + unrealizedPnl + realizedPnl;

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
            <StatsPanel
              portfolio={portfolio}
              trades={trades}
              positions={positions}
              initialBalance={initialBalance}
            />

            {config?.mode === 'paper' && (
              <PaperTradingPanel config={config} onConfigRefresh={fetchData} />
            )}

            <PortfolioChart data={portfolio} />

            <PositionsPanel
              trades={trades}
              positions={positions}
              exitRules={exitRules}
              loading={positionsLoading}
            />

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
