import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
} from "lightweight-charts";
import type { Analysis } from "../types";

interface Props {
  data: Analysis;
  advanced?: boolean;
}

function computeRsi(closes: number[], period: number): number[] {
  const out: number[] = new Array(closes.length).fill(50);
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1];
    const gain = Math.max(change, 0);
    const loss = Math.max(-change, 0);
    if (i <= period) {
      avgGain += gain / period;
      avgLoss += loss / period;
      if (i === period) out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
    } else {
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
      out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
    }
  }
  return out;
}

export default function PriceChart({ data, advanced = false }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 440,
      layout: {
        background: { type: ColorType.Solid, color: "#181d29" },
        textColor: "#8b92a3",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#1d2333" },
        horzLines: { color: "#1d2333" },
      },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: "#3b4252" }, horzLine: { color: "#3b4252" } },
      rightPriceScale: { borderColor: "#2a2e39" },
      timeScale: { borderColor: "#2a2e39", timeVisible: false },
      localization: { priceFormatter: (p: number) => p.toFixed(2) },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderUpColor: "#26a69a",
      borderDownColor: "#ef5350",
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });
    candles.setData(
      data.candles.map((c) => ({
        time: c.time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(
      data.candles.map((c) => ({
        time: c.time,
        value: c.volume,
        color: c.close >= c.open ? "rgba(38,166,154,0.45)" : "rgba(239,83,80,0.45)",
      })),
    );

    const maSeries: Record<string, ReturnType<typeof chart.addSeries>> = {};
    const maDefs: Array<[string, string, number]> = [
      ["sma21", "#f0b90b", 2],
      ["sma72", "#2962ff", 2],
      ["sma200", "#ab47bc", 2],
    ];
    for (const [key, color, width] of maDefs) {
      const pts = data.ma_series[key as keyof typeof data.ma_series];
      if (!pts || pts.length === 0) continue;
      const s = chart.addSeries(LineSeries, {
        color,
        lineWidth: width as 1 | 2 | 3 | 4,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(pts.map((p) => ({ time: p.time, value: p.value })));
      maSeries[key] = s;
    }

    if (advanced) {
      // Support / resistance horizontal lines
      const activeLevels = (data.technical.levels ?? []).slice(0, 8);
      for (const level of activeLevels) {
        candles.createPriceLine({
          price: level.price,
          color: level.kind === "resistance" ? "rgba(239,83,80,0.6)" : "rgba(38,166,154,0.6)",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `${level.touches}x`,
        });
      }

      // Auto-detected trend lines
      for (const tl of data.technical.trend_lines ?? []) {
        if (!tl.start_time || !tl.end_time || tl.start_value == null || tl.end_value == null) continue;
        const s = chart.addSeries(LineSeries, {
          color: tl.kind === "resistance" ? "#ef5350" : "#26a69a",
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        s.setData([
          { time: tl.start_time, value: tl.start_value },
          { time: tl.end_time, value: tl.end_value },
        ]);
      }

      // RSI sub-chart
      const rsiSeries = chart.addSeries(LineSeries, {
        color: "#7e57c2",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        priceScaleId: "rsi",
      });
      chart.priceScale("rsi").applyOptions({ scaleMargins: { top: 0.75, bottom: 0.12 } });
      const closes = data.candles.map((c) => c.close);
      const rsi = computeRsi(closes, 14);
      rsiSeries.setData(data.candles.map((c, i) => ({ time: c.time, value: rsi[i] })));
      rsiSeries.applyOptions({
        autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) as never,
      });
    }

    chart.timeScale().fitContent();

    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) chart.applyOptions({ width: w });
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.ticker, advanced]);

  return (
    <div className="chart-wrap">
      <div className="chart-head">
        <span>
          {advanced ? "Gráfico avançado" : "Visão geral"} · 2 anos · candles diários
        </span>
        <span>MM21 · MM72 · MM200 {advanced && "· Suportes/Resistências · Linhas de tendência · RSI"}</span>
      </div>
      <div ref={containerRef} style={{ width: "100%" }} />
      <img className="chart-watermark" src="/logo.png" alt="" draggable={false} onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />
    </div>
  );
}
