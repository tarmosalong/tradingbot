const BASE = '/api';

export interface Trade {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  amount: number;
  price: number;
  fee: number;
  pnl: number | null;
  executed_at: string;
}

export interface Order {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  order_type: string;
  amount: number;
  price: number | null;
  status: string;
  filled_amount: number;
  filled_price: number | null;
  created_at: string;
}

export interface PortfolioSnapshot {
  total_value_usdt: number;
  balances: Record<string, number>;
  timestamp: string;
}

export interface BotConfig {
  mode: string;
  pairs: string[];
  timeframe: string;
  poll_interval: number;
  strategies: string[];
  paper_trading?: {
    initial_balance_usdt: number;
  };
  risk: {
    max_position_pct: number;
    stop_loss_pct: number;
    trailing_stop_pct: number;
    max_drawdown_pct: number;
    daily_loss_limit_pct: number;
    max_single_order_usdt: number;
  };
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  health: () => fetchJson<{ status: string }>('/health'),
  config: () => fetchJson<BotConfig>('/config'),
  trades: (symbol?: string) =>
    fetchJson<Trade[]>(`/trades${symbol ? `?symbol=${symbol}` : ''}`),
  orders: (symbol?: string) =>
    fetchJson<Order[]>(`/orders${symbol ? `?symbol=${symbol}` : ''}`),
  portfolio: (limit = 100) =>
    fetchJson<PortfolioSnapshot[]>(`/portfolio?limit=${limit}`),
};
