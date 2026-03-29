import { useEffect, useRef, useState, useCallback } from 'react';
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
  CandlestickData,
  HistogramData,
  LineData,
  Time,
  SeriesMarker,
} from 'lightweight-charts';
import { api } from '../api';
import type { OhlcvCandle } from '../api';

export interface SignalPoint {
  timestamp: string;
  confidence: number;
  direction: string;
}

interface MiniPriceChartProps {
  symbol: string;
  sinceTimestamp?: string;
  signalHistory?: SignalPoint[];
}

type Timeframe = '1m' | '5m' | '15m' | '1h' | '4h' | '1d';
type Overlay = 'bb' | 'ema' | 'rsi' | 'signals';

const TIMEFRAMES: { value: Timeframe; label: string }[] = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1H' },
  { value: '4h', label: '4H' },
  { value: '1d', label: '1D' },
];

const TF_LIMITS: Record<Timeframe, number> = {
  '1m': 120, '5m': 100, '15m': 80, '1h': 80, '4h': 60, '1d': 60,
};

function pickDefaultTf(sinceTs?: string): Timeframe {
  if (!sinceTs) return '1h';
  const spanMin = (Date.now() - new Date(sinceTs).getTime()) / 60_000;
  if (spanMin < 120) return '1m';
  if (spanMin < 720) return '5m';
  if (spanMin < 2880) return '15m';
  return '1h';
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
  bbUpper: 'rgba(100, 181, 246, 0.5)',
  bbLower: 'rgba(100, 181, 246, 0.5)',
  bbMid: 'rgba(100, 181, 246, 0.25)',
  ema20: 'rgba(255, 183, 77, 0.7)',
  ema50: 'rgba(186, 104, 200, 0.7)',
  rsiLine: '#a0a0a0',
  rsiOverbought: 'rgba(239, 68, 68, 0.3)',
  rsiOversold: 'rgba(34, 197, 94, 0.3)',
  signalLine: 'rgba(160, 160, 160, 0.6)',
};

function computeEMA(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  const k = 2 / (period + 1);
  let ema: number | null = null;
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else if (ema === null) {
      ema = data.slice(0, period).reduce((a, b) => a + b, 0) / period;
      result.push(ema);
    } else {
      ema = data[i] * k + ema * (1 - k);
      result.push(ema);
    }
  }
  return result;
}

function computeRSI(closes: number[], period = 14): (number | null)[] {
  const result: (number | null)[] = [];
  if (closes.length < period + 1) return closes.map(() => null);
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) avgGain += diff;
    else avgLoss -= diff;
  }
  avgGain /= period;
  avgLoss /= period;
  for (let i = 0; i < period; i++) result.push(null);
  result.push(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss));
  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    avgGain = (avgGain * (period - 1) + (diff > 0 ? diff : 0)) / period;
    avgLoss = (avgLoss * (period - 1) + (diff < 0 ? -diff : 0)) / period;
    result.push(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss));
  }
  return result;
}

function computeBB(closes: number[], period = 20, mult = 2): { upper: (number | null)[]; mid: (number | null)[]; lower: (number | null)[] } {
  const upper: (number | null)[] = [];
  const mid: (number | null)[] = [];
  const lower: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) {
      upper.push(null); mid.push(null); lower.push(null);
    } else {
      const slice = closes.slice(i - period + 1, i + 1);
      const mean = slice.reduce((a, b) => a + b, 0) / period;
      const std = Math.sqrt(slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period);
      mid.push(mean);
      upper.push(mean + mult * std);
      lower.push(mean - mult * std);
    }
  }
  return { upper, mid, lower };
}

function dedupeSignalMarkers(signals: SignalPoint[]): SignalPoint[] {
  const result: SignalPoint[] = [];
  let lastDir = '';
  for (const s of signals) {
    if (s.direction !== 'HOLD' && s.confidence >= 0.5 && s.direction !== lastDir) {
      result.push(s);
      lastDir = s.direction;
    } else if (s.direction === 'HOLD') {
      lastDir = '';
    }
  }
  return result;
}

export function MiniPriceChart({ symbol, sinceTimestamp, signalHistory }: MiniPriceChartProps) {
  const mainRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const mainChartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const [candles, setCandles] = useState<OhlcvCandle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tf, setTf] = useState<Timeframe>(() => pickDefaultTf(sinceTimestamp));
  const [overlays, setOverlays] = useState<Set<Overlay>>(() => new Set(['signals']));

  const toggleOverlay = (o: Overlay) => {
    setOverlays((prev) => {
      const next = new Set(prev);
      if (next.has(o)) next.delete(o); else next.add(o);
      return next;
    });
  };

  const fetchData = useCallback(async () => {
    try {
      const data = await api.ohlcv(symbol, tf, TF_LIMITS[tf]);
      setCandles(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [symbol, tf]);

  useEffect(() => {
    setLoading(true);
    fetchData();
    const interval = setInterval(fetchData, tf === '1m' ? 15000 : 60000);
    return () => clearInterval(interval);
  }, [fetchData, tf]);

  useEffect(() => {
    if (!mainRef.current || candles.length === 0) return;

    const el = mainRef.current;
    const showRsi = overlays.has('rsi');
    const chartHeight = showRsi ? 220 : 280;

    const chart = createChart(el, {
      width: el.clientWidth,
      height: chartHeight,
      layout: {
        background: { type: ColorType.Solid, color: COLORS.bg },
        textColor: COLORS.text,
        fontFamily: "'Inter', system-ui, sans-serif",
        fontSize: 10,
      },
      grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: { borderColor: COLORS.border, scaleMargins: { top: 0.05, bottom: 0.2 } },
      timeScale: { borderColor: COLORS.border, timeVisible: true, secondsVisible: false },
    });
    mainChartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.upCandle,
      downColor: COLORS.downCandle,
      wickUpColor: COLORS.upCandle,
      wickDownColor: COLORS.downCandle,
      borderVisible: false,
    });
    candleSeries.setData(candles.map((c): CandlestickData<Time> => ({
      time: c.time as Time, open: c.open, high: c.high, low: c.low, close: c.close,
    })));

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' }, priceScaleId: 'volume',
    });
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
    volumeSeries.setData(candles.map((c): HistogramData<Time> => ({
      time: c.time as Time, value: c.volume,
      color: c.close >= c.open ? COLORS.volumeUp : COLORS.volumeDown,
    })));

    const closes = candles.map((c) => c.close);

    if (overlays.has('bb')) {
      const bb = computeBB(closes);
      const addBBLine = (data: (number | null)[], color: string, width: number) => {
        const s = chart.addSeries(LineSeries, {
          color, lineWidth: width, priceScaleId: 'right',
          lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
        });
        const ld: LineData<Time>[] = [];
        data.forEach((v, i) => { if (v != null) ld.push({ time: candles[i].time as Time, value: v }); });
        s.setData(ld);
      };
      addBBLine(bb.upper, COLORS.bbUpper, 1);
      addBBLine(bb.mid, COLORS.bbMid, 1);
      addBBLine(bb.lower, COLORS.bbLower, 1);
    }

    if (overlays.has('ema')) {
      const addEma = (period: number, color: string) => {
        const emaData = computeEMA(closes, period);
        const s = chart.addSeries(LineSeries, {
          color, lineWidth: 1, priceScaleId: 'right',
          lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
        });
        const ld: LineData<Time>[] = [];
        emaData.forEach((v, i) => { if (v != null) ld.push({ time: candles[i].time as Time, value: v }); });
        s.setData(ld);
      };
      addEma(20, COLORS.ema20);
      addEma(50, COLORS.ema50);
    }

    if (overlays.has('signals') && signalHistory && signalHistory.length > 0) {
      const sigSeries = chart.addSeries(LineSeries, {
        color: COLORS.signalLine, lineWidth: 2, priceScaleId: 'signal',
        lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: true, crosshairMarkerRadius: 4,
      });
      chart.priceScale('signal').applyOptions({ scaleMargins: { top: 0.05, bottom: 0.2 }, visible: false });
      sigSeries.setData(signalHistory.map((s): LineData<Time> => ({
        time: Math.floor(new Date(s.timestamp).getTime() / 1000) as Time,
        value: s.confidence * 100,
      })));

      const unique = dedupeSignalMarkers(signalHistory);
      const markers: SeriesMarker<Time>[] = unique
        .map((s) => ({
          time: Math.floor(new Date(s.timestamp).getTime() / 1000) as Time,
          position: s.direction === 'BUY' ? ('belowBar' as const) : ('aboveBar' as const),
          color: s.direction === 'BUY' ? '#22c55e' : '#ef4444',
          shape: s.direction === 'BUY' ? ('arrowUp' as const) : ('arrowDown' as const),
          text: s.direction === 'BUY' ? 'BUY' : 'SELL',
        }))
        .sort((a, b) => (a.time as number) - (b.time as number));
      if (markers.length > 0) createSeriesMarkers(candleSeries, markers);
    }

    chart.timeScale().fitContent();

    let rsiChart: IChartApi | null = null;
    if (showRsi && rsiRef.current) {
      const rsiEl = rsiRef.current;
      rsiChart = createChart(rsiEl, {
        width: rsiEl.clientWidth,
        height: 80,
        layout: {
          background: { type: ColorType.Solid, color: COLORS.bg },
          textColor: COLORS.text,
          fontFamily: "'Inter', system-ui, sans-serif",
          fontSize: 9,
        },
        grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
        crosshair: { mode: CrosshairMode.Magnet },
        rightPriceScale: { borderColor: COLORS.border, scaleMargins: { top: 0.05, bottom: 0.05 } },
        timeScale: { borderColor: COLORS.border, timeVisible: true, secondsVisible: false, visible: false },
      });
      rsiChartRef.current = rsiChart;

      const overbought = rsiChart.addSeries(LineSeries, {
        color: COLORS.rsiOverbought, lineWidth: 1, lineStyle: 2,
        lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
      });
      const oversold = rsiChart.addSeries(LineSeries, {
        color: COLORS.rsiOversold, lineWidth: 1, lineStyle: 2,
        lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
      });
      const rsiLine = rsiChart.addSeries(LineSeries, {
        color: COLORS.rsiLine, lineWidth: 2,
        lastValueVisible: true, priceLineVisible: false,
      });

      const rsiData = computeRSI(closes);
      const rsiLineData: LineData<Time>[] = [];
      const ob: LineData<Time>[] = [];
      const os: LineData<Time>[] = [];
      rsiData.forEach((v, i) => {
        if (v != null) {
          const t = candles[i].time as Time;
          rsiLineData.push({ time: t, value: v });
          ob.push({ time: t, value: 70 });
          os.push({ time: t, value: 30 });
        }
      });
      rsiLine.setData(rsiLineData);
      overbought.setData(ob);
      oversold.setData(os);

      rsiChart.timeScale().fitContent();

      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) rsiChart!.timeScale().setVisibleLogicalRange(range);
      });
    }

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
      if (rsiChart && rsiRef.current) rsiChart.applyOptions({ width: rsiRef.current.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      mainChartRef.current = null;
      if (rsiChart) { rsiChart.remove(); rsiChartRef.current = null; }
    };
  }, [candles, signalHistory, overlays]);

  const lastCandle = candles.length > 0 ? candles[candles.length - 1] : null;
  const firstCandle = candles.length > 0 ? candles[0] : null;
  const priceChange = lastCandle && firstCandle
    ? ((lastCandle.close - firstCandle.open) / firstCandle.open) * 100
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
      {/* Header */}
      <div className="flex items-center justify-between px-3 pt-2.5 pb-1.5 flex-wrap gap-2">
        <div className="flex items-center gap-1">
          {TIMEFRAMES.map((t) => (
            <button
              key={t.value}
              onClick={() => setTf(t.value)}
              className={`px-2 py-0.5 text-[10px] font-medium rounded transition-colors cursor-pointer ${
                tf === t.value
                  ? 'bg-[var(--text-primary)] text-[var(--bg-primary)]'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]'
              }`}
            >
              {t.label}
            </button>
          ))}
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

      {/* Overlay toggles */}
      <div className="flex items-center gap-1 px-3 pb-1.5 flex-wrap">
        <OverlayToggle label="BB" color="#64b5f6" active={overlays.has('bb')} onClick={() => toggleOverlay('bb')} />
        <OverlayToggle label="EMA" color="#ffb74d" active={overlays.has('ema')} onClick={() => toggleOverlay('ema')} />
        <OverlayToggle label="RSI" color="#a0a0a0" active={overlays.has('rsi')} onClick={() => toggleOverlay('rsi')} />
        <OverlayToggle label="Signals" color="#888" active={overlays.has('signals')} onClick={() => toggleOverlay('signals')} />
        {overlays.has('ema') && (
          <span className="text-[9px] text-[var(--text-secondary)] ml-1">
            <span style={{ color: COLORS.ema20 }}>EMA20</span>
            {' / '}
            <span style={{ color: COLORS.ema50 }}>EMA50</span>
          </span>
        )}
      </div>

      {/* Main chart */}
      <div ref={mainRef} />

      {/* RSI subplot */}
      {overlays.has('rsi') && (
        <div className="border-t border-[var(--border)]">
          <div className="flex items-center gap-2 px-3 py-1">
            <span className="text-[9px] font-medium text-[var(--text-secondary)]">RSI(14)</span>
            <span className="text-[9px] text-[var(--accent-red)]/50">70</span>
            <span className="text-[9px] text-[var(--accent-green)]/50">30</span>
          </div>
          <div ref={rsiRef} />
        </div>
      )}
    </div>
  );
}

function OverlayToggle({ label, color, active, onClick }: {
  label: string; color: string; active: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded transition-all cursor-pointer ${
        active
          ? 'bg-[var(--bg-secondary)] text-[var(--text-primary)]'
          : 'text-[var(--text-secondary)]/50 hover:text-[var(--text-secondary)]'
      }`}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color, opacity: active ? 1 : 0.3 }} />
      {label}
    </button>
  );
}
