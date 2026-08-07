import { useState } from "react";
import type { ReactNode } from "react";

const SECTIONS: Array<{ id: string; title: string; body: ReactNode }> = [
  {
    id: "score",
    title: "O que é o SwingScore?",
    body: "O SwingScore é uma nota de 0 a 100 que resume a atratividade de um ativo para operações de swing trade (dias a semanas). Não é uma previsão de direção: é uma medida probabilística de favorabilidade. 65+ indica cenário estatisticamente favorável, 45–65 neutro e abaixo de 45 desfavorável.",
  },
  {
    id: "pesos",
    title: "Como o score é calculado?",
    body: "A nota combina três pilares: Fundamentos (40%), Técnica (35%) e Macroeconomia (25%). Cada pilar recebe uma nota parcial; a composição gera o score final junto com um grau de confiança baseado na quantidade e qualidade dos dados disponíveis.",
  },
  {
    id: "cenarios",
    title: "Cenários e probabilidades",
    body: "Usamos simulação estatística (bootstrap sobre os retornos históricos do ativo, com horizonte de 63 pregões) para estimar a probabilidade de cenários favorável, neutro e desfavorável. Alvos são sempre faixas de preço — nunca valores únicos — acompanhadas de sua probabilidade de alcance.",
  },
  {
    id: "tecnica",
    title: "Análise técnica usada",
    body: "Os indicadores incluem RSI (momentum), médias móveis de 21, 72 e 200 períodos (tendência de curto, médio e longo prazo), ATR (volatilidade), suportes/resistências por toques e linhas de tendência. Uma linha com 2 toques é provável; com 3 ou mais, é considerada forte. Linha rompida perde força.",
  },
  {
    id: "probabilistico",
    title: "Por que nunca dizemos 'vai subir' ou 'compre'?",
    body: "O mercado é incerto. Toda conclusão é apresentada como probabilidade ou faixa, nunca como certeza. Isso evita excesso de confiança e ajuda a dimensionar risco antes de qualquer decisão.",
  },
  {
    id: "fundamentals",
    title: "Fundamentos: o que cada indicador significa?",
    body: (
      <div className="fund-list">
        <div className="fund-item">
          <b>P/L (preço/lucro)</b>
          <p>Quantos anos de lucro são necessários para pagar o preço da ação. P/L baixo pode indicar ação barata; P/L alto costuma refletir expectativa de crescimento. Setores têm faixas típicas diferentes (bancos, por exemplo, têm P/L baixo por natureza).</p>
        </div>
        <div className="fund-item">
          <b>P/VPA (preço/valor patrimonial)</b>
          <p>Quanto o mercado paga em relação ao patrimônio líquido da empresa. Abaixo de 1, o mercado precifica a ação abaixo do valor contábil; acima de 1, paga prêmio — comum em empresas que geram valor além do patrimônio.</p>
        </div>
        <div className="fund-item">
          <b>ROE (retorno sobre patrimônio)</b>
          <p>Lucro gerado sobre o patrimônio da empresa, em percentual. ROE alto e estável indica gestão eficiente. Acima de 15% ao ano já é considerado bom na maioria dos setores.</p>
        </div>
        <div className="fund-item">
          <b>Dividend yield (DY)</b>
          <p>Rendimento anual em dividendos sobre o preço da ação. DY alto pode sinalizar ação barata ou distribuição generosa; DY muito alto também pode esconder problemas (preço caindo ou payout insustentável).</p>
        </div>
        <div className="fund-item">
          <b>Payout</b>
          <p>Percentual do lucro distribuído como dividendos. Acima de 100% indica que a empresa está pagando mais do que ganha — risco de corte futuro.</p>
        </div>
        <div className="fund-item">
          <b>Dívida/PL (endividamento)</b>
          <p>Relação entre dívida total e patrimônio. Acima de ~3x sugere alavancagem alta e maior sensibilidade a juros e crises; valores baixos indicam estrutura mais conservadora.</p>
        </div>
        <div className="fund-item">
          <b>Liquidez diária</b>
          <p>Volume médio negociado por dia. Alta liquidez facilita entrar e sair sem impacto no preço — importante para swing trade.</p>
        </div>
      </div>
    ),
  },
];

export default function Learn() {
  const [open, setOpen] = useState<string | null>("score");
  return (
    <div>
      {SECTIONS.map((s) => (
        <div className={`learn-item ${open === s.id ? "open" : ""}`} key={s.id}>
          <button
            className="learn-head"
            onClick={() => setOpen(open === s.id ? null : s.id)}
          >
            {s.title}
            <span className="chevron">{open === s.id ? "▾" : "▸"}</span>
          </button>
          {open === s.id && <div className="learn-body">{s.body}</div>}
        </div>
      ))}
    </div>
  );
}
