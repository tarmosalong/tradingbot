import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  HistogramSeries,
} from 'lightweight-charts';
import type { IChartApi, CandlestickData, HistogramData, Time } from 'lightweight-charts';
import { api } from '../api';
import type { OhlcvCandle } from '../api';

interface MiniPriceChartProps {
  symbol: string;
  timeframe?: string;
}

const COLORS = {
  bg: 'transparent',
  text: '#888888',
  grid: '#1a1a1a',
  border: '#2a2a2a',
  upCandle: '#22c55e',
  downCandle: '#ef4444',
  volumeUp: 'rgba(34, 197, 94, 0.12)',
  volumeDown: 'rgba(239, 68, 68, 0.12)',
};

export function MiniPriceChart({ symbol, timeframe = '1h' }: MiniPriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [candles, setCandles] = useState<OhlcvCandle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const data = await api.ohlcv(symbol, timeframe, 80);
      setCandles(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return;

    const el = containerRef.current;

    const chart = createChart(el, {
      width: el.clientWidth,
      height: 260,
      layout: {
        background: { type: ColorType.Solid, color: COLORS.bg },
        textColor: COLORS.text,
        fontFamily: "'Inter', system-ui, sans-serif",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: COLORS.grid },
        horzLines: { color: COLORS.grid },
      },
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: {
        borderColor: COLORS.border,
        scaleMargins: { top: 0.05, bottom: 0.2 },
      },
      timeScale: {
        borderColor: COLORS.border,
        timeVisible: true,
        secondsVisible: false,
      },
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.upCandle,
      downColor: COLORS.downCandle,
      wickUpColor: COLORS.upCandle,
      wickDownColor: COLORS.downCandle,
      borderVisible: false,
    });

    const candleData: CandlestickData<Time>[] = candles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candleSeries.setData(candleData);

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    const volumeData: HistogramData<Time>[] = candles.map((c) => ({
      time: c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? COLORS.volumeUp : COLORS.volumeDown,
    }));
    volumeSeries.setData(volumeData);

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [candles]);

  const lastCandle = candles.length > 0 ? candles[candles.length - 1] : null;
  const prevCandle = candles.length > 1 ? candles[candles.length - 2] : null;
  const priceChange = lastCandle && prevCandle
    ? ((lastCandle.close - prevCandle.close) / prevCandle.close) * 100
    : null;

  if (loading) {
    return (
      <div className="rounded-lg border border-[var(--border)] p-3 bg-[var(--bg-primary)]/30 flex items-center justify-center h-[300px]">
        <span className="text-xs text-[var(--text-secondary)]">Loading price chart...</span>
      </div>
    );
  }

  if (error || candles.length === 0) {
    return (
      <div className="rounded-lg border border-[var(--border)] p-3 bg-[var(--bg-primary)]/30 flex items-center justify-center h-[300px]">
        <span className="text-xs text-[var(--text-secondary)]">{error ?? 'No price data available'}</span>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-primary)]/30 overflow-hidden">
      <div className="flex items-center justify-between px-3 pt-2.5 pb-1">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-medium text-[var(--text-secondary)]">
            Price chart
          </span>
          <span className="text-[10px] text-[var(--text-secondary)] px-1.5 py-0.5 rounded bg-[var(--bg-secondary)]">
            {timeframe}
          </span>
        </div>
        {lastCandle && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-[var(--text-primary)]">
              ${lastCandle.close.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            {priceChange !== null && (
              <span className={`text-[10px] font-medium ${priceChange >= 0 ? 'text-[var(--accent-green)]' : 'text-[var(--accent-red)]'}`}>
                {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
              </span>
            )}
          </div>
        )}
      </div>
      <div ref={containerRef} />
    </div>
  );
}
