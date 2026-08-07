import type { Analysis } from "../types";

interface Props {
  data: Analysis;
}

const WEIGHTS: Record<string, string> = {
  fundamentals: "Fundamentos · 40%",
  technical: "Técnica · 35%",
  macro: "Macroeconomia · 25%",
};

function colorFor(v: number): string {
  if (v >= 65) return "var(--up)";
  if (v >= 45) return "var(--accent)";
  return "var(--down)";
}

export default function Pillars({ data }: Props) {
  const pillars = data.pillars;
  return (
    <div>
      {(["fundamentals", "technical", "macro"] as const).map((k) => {
        const p = pillars[k];
        return (
          <div className="pillar-row" key={k}>
            <div className="pillar-top">
              <span className="label">{WEIGHTS[k]}</span>
              <span className="val">{p ? Math.round(p.score) : "—"}</span>
            </div>
            <div className="pillar-track">
              <div style={{ width: `${p ? Math.max(2, p.score) : 0}%`, background: colorFor(p?.score ?? 0) }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
