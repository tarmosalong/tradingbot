import { useEffect, useRef } from 'react';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
  HistogramData,
  Time,
  SeriesMarker,
} from 'lightweight-charts';

export interface OhlcvCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface TradeMarker {
  time: number;
  side: string;
  price: number;
  amount: number;
}

interface CandlestickChartProps {
  ohlcv: OhlcvCandle[];
  trades: TradeMarker[];
  equityCurve?: number[];
}

const CHART_COLORS = {
  bg: '#0f1117',
  text: '#8b8fa3',
  grid: '#1a1d2e',
  border: '#262a3a',
  upCandle: '#22c55e',
  downCandle: '#ef4444',
  upWick: '#22c55e',
  downWick: '#ef4444',
  volumeUp: 'rgba(34, 197, 94, 0.15)',
  volumeDown: 'rgba(239, 68, 68, 0.15)',
  equityLine: '#3b82f6',
};

export function CandlestickChart({ ohlcv, trades, equityCurve }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);

  useEffect(() => {
    if (!containerRef.current || ohlcv.length === 0) return;

    const container = containerRef.current;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 420,
      layout: {
        background: { type: ColorType.Solid, color: CHART_COLORS.bg },
        textColor: CHART_COLORS.text,
        fontFamily: "'Inter', system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: CHART_COLORS.grid },
        horzLines: { color: CHART_COLORS.grid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: CHART_COLORS.border,
        scaleMargins: { top: 0.05, bottom: 0.25 },
      },
      timeScale: {
        borderColor: CHART_COLORS.border,
        timeVisible: true,
        secondsVisible: false,
      },
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: CHART_COLORS.upCandle,
      downColor: CHART_COLORS.downCandle,
      wickUpColor: CHART_COLORS.upWick,
      wickDownColor: CHART_COLORS.downWick,
      borderVisible: false,
    });
    candleSeriesRef.current = candleSeries;

    const candleData: CandlestickData<Time>[] = ohlcv.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candleSeries.setData(candleData);

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });

    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const volumeData: HistogramData<Time>[] = ohlcv.map((c) => ({
      time: c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? CHART_COLORS.volumeUp : CHART_COLORS.volumeDown,
    }));
    volumeSeries.setData(volumeData);

    if (equityCurve && equityCurve.length > 0 && equityCurve.length <= ohlcv.length) {
      const equitySeries = chart.addLineSeries({
        color: CHART_COLORS.equityLine,
        lineWidth: 2,
        priceScaleId: 'equity',
        lastValueVisible: true,
        priceLineVisible: false,
      });

      chart.priceScale('equity').applyOptions({
        scaleMargins: { top: 0.05, bottom: 0.25 },
        visible: false,
      });

      const equityData = equityCurve.map((value, i) => ({
        time: ohlcv[Math.min(i, ohlcv.length - 1)].time as Time,
        value,
      }));
      equitySeries.setData(equityData);
    }

    if (trades.length > 0) {
      const ohlcvTimeSet = new Set(ohlcv.map((c) => c.time));

      const markers: SeriesMarker<Time>[] = trades
        .filter((t) => ohlcvTimeSet.has(t.time))
        .map((t) => ({
          time: t.time as Time,
          position: t.side === 'BUY' ? 'belowBar' as const : 'aboveBar' as const,
          color: t.side === 'BUY' ? '#22c55e' : '#ef4444',
          shape: t.side === 'BUY' ? 'arrowUp' as const : 'arrowDown' as const,
          text: `${t.side} ${t.amount.toFixed(4)} @ $${t.price.toLocaleString()}`,
        }))
        .sort((a, b) => (a.time as number) - (b.time as number));

      candleSeries.setMarkers(markers);
    }

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (container) {
        chart.applyOptions({ width: container.clientWidth });
      }
    };
    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
    };
  }, [ohlcv, trades, equityCurve]);

  return (
    <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)] overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <h2 className="text-sm font-medium text-[var(--text-secondary)]">
          Price Chart
        </h2>
        <div className="flex items-center gap-3 text-xs text-[var(--text-secondary)]">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-[#22c55e] inline-block" />
            BUY
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-[#ef4444] inline-block" />
            SELL
          </span>
          {equityCurve && (
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-[#3b82f6] inline-block rounded" />
              Equity
            </span>
          )}
        </div>
      </div>
      <div ref={containerRef} />
    </div>
  );
}
