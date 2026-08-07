import type { Analysis } from "../types";

interface Props {
  data: Analysis;
}

export default function Scenarios({ data }: Props) {
  const s = data.scenarios;
  const rows = [
    { key: "favoravel", name: "Cenário favorável", cls: "favoravel" },
    { key: "neutro", name: "Cenário neutro", cls: "neutro" },
    { key: "desfavoravel", name: "Cenário desfavorável", cls: "desfavoravel" },
  ] as const;

  return (
    <div>
      {rows.map((r) => {
        const v = s[r.key];
        const color = r.cls === "favoravel" ? "var(--up)" : r.cls === "neutro" ? "var(--accent)" : "var(--down)";
        return (
          <div className="scenario-row" key={r.key}>
            <span className="name">{r.name}</span>
            <div className="scenario-track">
              <div style={{ width: `${Math.max(2, v)}%`, background: color }} />
            </div>
            <span className={`pct ${r.cls}`}>{v.toFixed(1)}%</span>
          </div>
        );
      })}
      <p style={{ fontSize: 11.5, color: "var(--text-faint)", margin: "10px 0 0" }}>
        Probabilidades calculadas por simulação estatística para os próximos {s.horizonte_dias} pregões.
        Retorno esperado no período: {s.retorno_esperado > 0 ? "+" : ""}
        {s.retorno_esperado.toFixed(1)}%.
      </p>
    </div>
  );
}
