import { useEffect, useRef } from 'react';
import {
  createChart,
  createSeriesMarkers,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
} from 'lightweight-charts';
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

const COLORS = {
  bg: '#0f1117',
  text: '#8b8fa3',
  grid: '#1a1d2e',
  border: '#262a3a',
  upCandle: '#22c55e',
  downCandle: '#ef4444',
  volumeUp: 'rgba(34, 197, 94, 0.15)',
  volumeDown: 'rgba(239, 68, 68, 0.15)',
  equityLine: '#e5a243',
};

export function CandlestickChart({ ohlcv, trades, equityCurve }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);

  useEffect(() => {
    if (!containerRef.current || ohlcv.length === 0) return;

    const el = containerRef.current;

    const chart = createChart(el, {
      width: el.clientWidth,
      height: 420,
      layout: {
        background: { type: ColorType.Solid, color: COLORS.bg },
        textColor: COLORS.text,
        fontFamily: "'Inter', system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: COLORS.grid },
        horzLines: { color: COLORS.grid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: COLORS.border,
        scaleMargins: { top: 0.05, bottom: 0.25 },
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
    candleRef.current = candleSeries;

    const candleData: CandlestickData<Time>[] = ohlcv.map((c) => ({
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
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const volumeData: HistogramData<Time>[] = ohlcv.map((c) => ({
      time: c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? COLORS.volumeUp : COLORS.volumeDown,
    }));
    volumeSeries.setData(volumeData);

    if (equityCurve && equityCurve.length > 0) {
      const equitySeries = chart.addSeries(LineSeries, {
        color: COLORS.equityLine,
        lineWidth: 2,
        priceScaleId: 'equity',
        lastValueVisible: true,
        priceLineVisible: false,
      });
      chart.priceScale('equity').applyOptions({
        scaleMargins: { top: 0.05, bottom: 0.25 },
        visible: false,
      });

      const eqData = equityCurve
        .slice(0, ohlcv.length)
        .map((value, i) => ({
          time: ohlcv[i].time as Time,
          value,
        }));
      equitySeries.setData(eqData);
    }

    if (trades.length > 0) {
      const timeSet = new Set(ohlcv.map((c) => c.time));

      const markers: SeriesMarker<Time>[] = trades
        .filter((t) => timeSet.has(t.time))
        .map((t) => ({
          time: t.time as Time,
          position: t.side === 'BUY' ? ('belowBar' as const) : ('aboveBar' as const),
          color: t.side === 'BUY' ? '#22c55e' : '#ef4444',
          shape: t.side === 'BUY' ? ('arrowUp' as const) : ('arrowDown' as const),
          text: `${t.side} ${t.amount.toFixed(4)} @ $${t.price.toLocaleString()}`,
        }))
        .sort((a, b) => (a.time as number) - (b.time as number));

      createSeriesMarkers(candleSeries, markers);
    }

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
    };
  }, [ohlcv, trades, equityCurve]);

  return (
    <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)] overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <h2 className="text-sm font-medium text-[var(--text-secondary)]">Price Chart</h2>
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
              <span className="w-3 h-0.5 bg-[#e5a243] inline-block rounded" />
              Equity
            </span>
          )}
        </div>
      </div>
      <div ref={containerRef} />
    </div>
  );
}
