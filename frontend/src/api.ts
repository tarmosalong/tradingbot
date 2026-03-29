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
  strategy_params?: {
    rsi: { period: number; oversold: number; overbought: number };
    macd: { fast: number; slow: number; signal: number };
    bollinger: { period: number; std_dev: number };
  };
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  const text = await res.text();
  if (!res.ok) {
    const detail = parseErrorDetail(text);
    throw new Error(detail || `API error: ${res.status}`);
  }
  return (text ? JSON.parse(text) : {}) as T;
}

function parseErrorDetail(text: string): string {
  try {
    const j = JSON.parse(text) as { detail?: unknown };
    const d = j.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
      return d
        .map((e) => (typeof e === 'object' && e && 'msg' in e ? String((e as { msg: string }).msg) : String(e)))
        .join('; ');
    }
  } catch {
    /* use raw */
  }
  return text || 'Request failed';
}

async function fetchJsonRequest<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers as Record<string, string>),
    },
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(parseErrorDetail(text));
  }
  return text ? (JSON.parse(text) as T) : ({} as T);
}

export interface SignalEntry {
  id: number;
  symbol: string;
  direction: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  strategy_name: string;
  reason: string;
  indicators: Record<string, number>;
  timestamp: string;
}

export type BotRunnerState = 'stopped' | 'starting' | 'running' | 'stopping';

export interface BotStatus {
  state: BotRunnerState;
  mode: string;
  control_enabled: boolean;
  last_error: string | null;
}

export interface RSIParams {
  period?: number;
  oversold?: number;
  overbought?: number;
}

export interface MACDParams {
  fast?: number;
  slow?: number;
  signal?: number;
}

export interface BollingerParams {
  period?: number;
  std_dev?: number;
}

export interface RiskParams {
  max_position_pct?: number;
  stop_loss_pct?: number;
  trailing_stop_pct?: number;
  max_drawdown_pct?: number;
  daily_loss_limit_pct?: number;
  max_single_order_usdt?: number;
}

export interface PaperBotSettingsBody {
  initial_balance_usdt?: number;
  pairs?: string[];
  timeframe?: string;
  poll_interval_seconds?: number;
  strategies?: string[];
  rsi?: RSIParams;
  macd?: MACDParams;
  bollinger?: BollingerParams;
  risk?: RiskParams;
}

export interface OpenPosition {
  symbol: string;
  amount: number;
  entry_price: number;
  current_price: number;
  peak_price: number;
  pnl: number;
  pnl_pct: number;
  stop_loss_price: number;
  trailing_stop_price: number;
  opened_at: string;
  exit_conditions: string[];
}

export interface ExitRule {
  name: string;
  description: string;
  active: boolean;
}

export interface PositionsResponse {
  positions: OpenPosition[];
  risk_config: {
    stop_loss_pct: number;
    trailing_stop_pct: number;
  };
  exit_rules: ExitRule[];
}

export interface OhlcvCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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
  signals: (limit = 50) => fetchJson<SignalEntry[]>(`/signals?limit=${limit}`),
  ohlcv: (symbol = 'BTC/USDT', timeframe = '1h', limit = 100) =>
    fetchJson<OhlcvCandle[]>(`/ohlcv?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`),
  botStatus: () => fetchJson<BotStatus>('/bot/status'),
  botStart: () =>
    fetchJsonRequest<{ ok: boolean } & BotStatus>('/bot/start', { method: 'POST' }),
  botStop: () =>
    fetchJsonRequest<{ ok: boolean } & BotStatus>('/bot/stop', { method: 'POST' }),
  botPositions: () => fetchJson<PositionsResponse>('/bot/positions'),
  botPatchSettings: (body: PaperBotSettingsBody) =>
    fetchJsonRequest<{
      ok: boolean;
      mode: string;
      pairs: string[];
      timeframe: string;
      poll_interval: number;
      strategies: string[];
      paper_trading: { initial_balance_usdt: number };
    }>('/bot/settings', { method: 'PATCH', body: JSON.stringify(body) }),
};
