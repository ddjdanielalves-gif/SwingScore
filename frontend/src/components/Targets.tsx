import type { Analysis } from "../types";

interface Props {
  data: Analysis;
}

function fmt(v: number): string {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function Targets({ data }: Props) {
  const targets = data.targets;
  const currency = data.currency === "BRL" ? "R$" : "US$";
  const order: Array<[string, string]> = [
    ["estatistico", "Faixa estatística"],
    ["valor_justo", "Valor justo"],
    ["primeiro_objetivo", "1º objetivo"],
    ["objetivo_otimista", "Objetivo otimista"],
  ];

  return (
    <div>
      {order.map(([key, label]) => {
        const t = targets[key];
        if (!t || !t.faixa) return null;
        return (
          <div className="target-row" key={key}>
            <div className="target-label">{t.label || label}</div>
            <div className="target-range">
              {currency}
              {fmt(t.faixa[0])} – {currency}
              {fmt(t.faixa[1])}
            </div>
            <div className="target-prob">
              <div className="p">
                {Number.isFinite(t.probabilidade) ? Math.round(t.probabilidade) : "—"}%
              </div>
              <div className="t">probabilidade</div>
            </div>
          </div>
        );
      })}
      <p style={{ fontSize: 11.5, color: "var(--text-faint)", margin: "10px 0 0" }}>
        Faixas, nunca preços únicos. Probabilidade de o preço alcançar a faixa no horizonte de{" "}
        {data.scenarios.horizonte_dias} pregões.
      </p>
    </div>
  );
}
