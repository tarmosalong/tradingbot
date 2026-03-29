import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { PortfolioSnapshot } from '../api';

interface PortfolioChartProps {
  data: PortfolioSnapshot[];
}

export function PortfolioChart({ data }: PortfolioChartProps) {
  const chartData = [...data]
    .reverse()
    .map((s) => ({
      time: new Date(s.timestamp).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      }),
      value: s.total_value_usdt,
    }));

  if (chartData.length === 0) {
    return (
      <div className="bg-[var(--bg-card)]/80 backdrop-blur-sm rounded-xl border border-[var(--border)] overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border)]">
          <h2 className="text-sm font-medium text-[var(--text-primary)]">Portfolio Value</h2>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5">Equity curve over time</p>
        </div>
        <div className="px-4 py-12 text-center">
          <p className="text-sm text-[var(--text-secondary)]">No portfolio data yet</p>
          <p className="text-xs text-[var(--text-secondary)] mt-1">
            Start the bot to begin tracking
          </p>
        </div>
      </div>
    );
  }

  const values = chartData.map((d) => d.value);
  const min = Math.min(...values) * 0.998;
  const max = Math.max(...values) * 1.002;
  const isUp =
    values.length > 1 && values[values.length - 1] >= values[0];

  return (
    <div className="bg-[var(--bg-card)]/80 backdrop-blur-sm rounded-xl border border-[var(--border)] overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--border)]">
        <h2 className="text-sm font-medium text-[var(--text-primary)]">Portfolio Value</h2>
        <p className="text-xs text-[var(--text-secondary)] mt-0.5">Equity curve over time</p>
      </div>
      <div className="p-4">
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="0%"
                  stopColor={
                    isUp ? 'var(--accent-green)' : 'var(--accent-red)'
                  }
                  stopOpacity={0.15}
                />
                <stop
                  offset="100%"
                  stopColor={
                    isUp ? 'var(--accent-green)' : 'var(--accent-red)'
                  }
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="time"
              tick={{ fill: 'var(--text-secondary)', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[min, max]}
              tick={{ fill: 'var(--text-secondary)', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `$${v.toLocaleString()}`}
              width={70}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                color: 'var(--text-primary)',
                fontSize: 12,
                padding: '8px 12px',
              }}
              formatter={(value) => [
                `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
                'Value',
              ]}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={
                isUp ? 'var(--accent-green)' : 'var(--accent-red)'
              }
              fill="url(#areaGrad)"
              strokeWidth={1.5}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
