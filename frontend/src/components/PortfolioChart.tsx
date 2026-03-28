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

  const values = chartData.map((d) => d.value);
  const min = Math.min(...values) * 0.995;
  const max = Math.max(...values) * 1.005;
  const isUp = values.length > 1 && values[values.length - 1] >= values[0];

  return (
    <div className="bg-[var(--bg-card)] rounded-lg p-4 border border-[var(--border)]">
      <h2 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
        Portfolio Value
      </h2>
      {chartData.length === 0 ? (
        <div className="flex items-center justify-center h-48 text-[var(--text-secondary)] text-sm">
          No portfolio data yet
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="gradUp" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent-green)" stopOpacity={0.3} />
                <stop offset="100%" stopColor="var(--accent-green)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gradDown" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent-red)" stopOpacity={0.3} />
                <stop offset="100%" stopColor="var(--accent-red)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="time"
              tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={[min, max]}
              tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `$${v.toLocaleString()}`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                color: 'var(--text-primary)',
              }}
              formatter={(value) => [`$${Number(value).toLocaleString()}`, 'Value']}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={isUp ? 'var(--accent-green)' : 'var(--accent-red)'}
              fill={isUp ? 'url(#gradUp)' : 'url(#gradDown)'}
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
