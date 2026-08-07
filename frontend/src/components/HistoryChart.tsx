import { useEffect, useRef } from "react";
import { ColorType, LineSeries, LineStyle, LineType, createChart } from "lightweight-charts";
import type { HistoryPoint } from "../types";

interface Props {
  points: HistoryPoint[];
  ticker: string;
}

export default function HistoryChart({ points, ticker }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || points.length === 0) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 300,
      layout: {
        background: { type: ColorType.Solid, color: "#181d29" },
        textColor: "#8b92a3",
        fontSize: 11,
      },
      grid: { vertLines: { color: "#1d2333" }, horzLines: { color: "#1d2333" } },
      rightPriceScale: { borderColor: "#2a2e39" },
      timeScale: { borderColor: "#2a2e39", timeVisible: true },
    });

    const lineSeries = chart.addSeries(LineSeries, {
      color: "#f0b90b",
      lineWidth: 2,
      lineType: LineType.Simple,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    lineSeries.setData(
      points.map((p) => ({
        time: p.created_at.slice(0, 10),
        value: p.swing_score,
      })),
    );
    lineSeries.applyOptions({
      autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) as never,
    });

    lineSeries.createPriceLine({
      price: 65,
      color: "rgba(38,166,154,0.4)",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: false,
    });
    lineSeries.createPriceLine({
      price: 45,
      color: "rgba(239,83,80,0.4)",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: false,
    });

    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) chart.applyOptions({ width: w });
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [points, ticker]);

  return (
    <div className="chart-wrap">
      <div className="chart-head">
        <span>Evolução do SwingScore — {ticker}</span>
        <span>65+ favorável · 45–65 neutro · &lt;45 desfavorável</span>
      </div>
      <div ref={containerRef} style={{ width: "100%" }} />
    </div>
  );
}
