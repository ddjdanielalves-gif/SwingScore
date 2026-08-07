import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Analysis, HistoryResponse } from "./types";
import SearchBar from "./components/SearchBar";
import ScoreGauge from "./components/ScoreGauge";
import PriceChart from "./components/PriceChart";
import Pillars from "./components/Pillars";
import Scenarios from "./components/Scenarios";
import Targets from "./components/Targets";
import HistoryChart from "./components/HistoryChart";
import Learn from "./components/Learn";
import TickerTape from "./components/TickerTape";

type Tab = "overview" | "advanced" | "learn" | "history";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "overview", label: "Visão Geral" },
  { id: "advanced", label: "Avançado" },
  { id: "learn", label: "Aprenda" },
  { id: "history", label: "Histórico" },
];

function formatPrice(v: number, currency: string): string {
  const sym = currency === "BRL" ? "R$" : "US$";
  return `${sym} ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function App() {
  const [ticker, setTicker] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [isDemo, setIsDemo] = useState(false);
  const requestSeq = useRef(0);

  const load = useCallback(async (t: string) => {
    const seq = ++requestSeq.current;
    setTicker(t);
    setLoading(true);
    setError(null);
    setAnalysis(null);
    setHistory(null);
    try {
      const [a, h] = await Promise.all([api.analysis(t), api.history(t)]);
      if (seq !== requestSeq.current) return;
      setAnalysis(a);
      setHistory(h);
      setIsDemo(a.is_demo);
    } catch (e) {
      if (seq !== requestSeq.current) return;
      let msg = e instanceof Error ? e.message : "Erro ao carregar análise.";
      try {
        const parsed = JSON.parse(msg);
        if (parsed?.detail) msg = String(parsed.detail);
      } catch {
        /* keep raw message */
      }
      if (/abort/i.test(msg)) msg = "A análise demorou demais. Tente novamente.";
      setError(msg);
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ticker) load(ticker);
  }, [ticker, load]);

  const selectTicker = (t: string) => setTicker(t);

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <BrandLogo />
          <div>
            <div className="brand-name">SwingScore</div>
            <div className="brand-sub">Análise probabilística de swing trade</div>
          </div>
        </div>
        <SearchBar onSelect={selectTicker} />
        <div className="header-note">B3 · Nasdaq · NYSE</div>
      </header>

      <TickerTape />

      <main className="app-main">
        {!ticker && (
          <section className="empty">
            <h1>Escolha um ativo para começar</h1>
            <p>
              Digite um ticker ou o nome da empresa e pressione Enter. Exemplos:{" "}
              <b>BBDC4</b>, <b>ITUB3</b>, <b>VALE3</b>, <b>AAPL</b>, <b>Itaú</b>,{" "}
              <b>Petrobras</b>.
            </p>
          </section>
        )}

        {ticker && loading && (
          <div className="loading">
            Calculando SwingScore…
            <div className="loading-note">
              Primeira análise pode levar até 30s (buscando dados do Yahoo).
            </div>
          </div>
        )}

        {ticker && error && !loading && (
          <section className="error-box">
            <div className="error-title">Não foi possível analisar {ticker}</div>
            <p>{error}</p>
          </section>
        )}

        {analysis && !loading && (
          <>
            {isDemo && (
              <div className="demo-banner">
                Dados de demonstração — servidor sem conexão com dados reais.
              </div>
            )}
            <section className="tabs">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  className={`tab ${tab === t.id ? "active" : ""}`}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </section>

            {tab === "overview" && (
              <>
                <section className="hero-card">
                  <div className="hero-left">
                    <h1 className="asset-name">
                      {analysis.ticker}
                      <span className="asset-region">{analysis.market}</span>
                    </h1>
                    <div className="asset-name-sub">{analysis.name}</div>
                    <div className="price-line">
                      <span className="price">
                        {formatPrice(analysis.price, analysis.currency)}
                      </span>
                      <span
                        className={`chg ${analysis.change_pct >= 0 ? "pos" : "neg"}`}
                      >
                        {analysis.change_pct >= 0 ? "+" : ""}
                        {analysis.change_pct.toFixed(2)}%
                      </span>
                    </div>
                    <div className="confidence">
                      Grau de confiança: {analysis.confidence.toFixed(0)}%
                    </div>
                    <div className={`label-chip ${analysis.label.toLowerCase()}`}>
                      {analysis.label}
                    </div>
                  </div>
                  <div className="hero-right">
                    <ScoreGauge value={analysis.swing_score} label="SwingScore" />
                  </div>
                </section>

                <section className="card">
                  <div className="card-title">Gráfico · 2 anos</div>
                  <PriceChart data={analysis} />
                </section>

                <section className="grid-2">
                  <div className="card">
                    <div className="card-title">Pilares do score</div>
                    <Pillars data={analysis} />
                  </div>
                  <div className="card">
                    <div className="card-title">Cenários · {analysis.scenarios.horizonte_dias} pregões</div>
                    <Scenarios data={analysis} />
                  </div>
                </section>

                <section className="card">
                  <div className="card-title">Faixas-alvo (recálculo diário)</div>
                  <Targets data={analysis} />
                </section>

                {analysis.report && (
                  <section className="card">
                    <div className="card-title">Relatório</div>
                    <div className="report">{analysis.report}</div>
                  </section>
                )}
              </>
            )}

            {tab === "advanced" && (
              <>
                <section className="card">
                  <div className="card-title">Gráfico avançado</div>
                  <PriceChart data={analysis} advanced />
                </section>
                <section className="grid-2">
                  <div className="card">
                    <div className="card-title">Técnica</div>
                    <AdvancedTechnical data={analysis} />
                  </div>
                  <div className="card">
                    <div className="card-title">Fundamentos</div>
                    <FundamentalTable data={analysis} />
                  </div>
                </section>
              </>
            )}

            {tab === "learn" && (
              <section className="card">
                <div className="card-title">Aprenda como funciona</div>
                <Learn />
              </section>
            )}

            {tab === "history" && (
              <section className="card">
                <div className="card-title">Histórico de scores</div>
                {history && history.points.length > 0 ? (
                  <>
                    <div className="deltas">
                      <Delta label="Ontem" v={history.delta_yesterday} />
                      <Delta label="Semana" v={history.delta_week} />
                      <Delta label="Mês" v={history.delta_month} />
                    </div>
                    <HistoryChart points={history.points} ticker={analysis.ticker} />
                  </>
                ) : (
                  <p className="muted">Sem histórico ainda. O score diário é salvo automaticamente.</p>
                )}
              </section>
            )}

            <footer className="disclaimer">
              <b>Disclaimer:</b> o SwingScore é uma ferramenta educacional e estatística.
              Nada aqui é recomendação de investimento, nem projeção de resultados. Nunca
              afirmamos que um ativo "vai subir" ou "é hora de comprar". Toda informação é
              apresentada como probabilidade. Decisões de investimento envolvem risco.
            </footer>
          </>
        )}
      </main>
    </div>
  );
}

function BrandLogo() {
  const [failed, setFailed] = useState(false);
  if (failed) return <span className="logo">SS</span>;
  return <img className="logo-img" src="/logo.png" alt="SwingScore" onError={() => setFailed(true)} />;
}

function Delta({ label, v }: { label: string; v: number | null }) {  if (v === null) return <div className="delta"><span>{label}</span><em>—</em></div>;
  return (
    <div className="delta">
      <span>{label}</span>
      <em className={v >= 0 ? "pos" : "neg"}>
        {v >= 0 ? "+" : ""}
        {v.toFixed(1)}
      </em>
    </div>
  );
}

function AdvancedTechnical({ data }: { data: Analysis }) {
  const t = data.technical;
  const rows: Array<[string, string]> = [
    ["RSI (14)", `${t.rsi.toFixed(1)} — ${t.rsi_state}`],
    ["ATR %", `${t.atr_pct.toFixed(2)}%`],
    ["Preço vs MM21", t.ma_distance.sma21 ? `${(t.ma_distance.sma21 * 100).toFixed(1)}%` : "—"],
    ["Preço vs MM72", t.ma_distance.sma72 ? `${(t.ma_distance.sma72 * 100).toFixed(1)}%` : "—"],
    ["Preço vs MM200", t.ma_distance.sma200 ? `${(t.ma_distance.sma200 * 100).toFixed(1)}%` : "—"],
  ];
  return (
    <div>
      <table className="kv">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <td>{k}</td>
              <td>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h4>Médias móveis</h4>
      {Object.entries(t.ma_status).map(([k, v]) => (
        <div className="kv-line" key={k}>
          <span>{k.toUpperCase()}</span>
          <span className={v === "acima" ? "pos" : v === "abaixo" ? "neg" : ""}>{v}</span>
        </div>
      ))}
      <h4>Linhas de tendência</h4>
      <table className="kv">
        <tbody>
          {t.trend_lines.map((tl, i) => (
            <tr key={i}>
              <td>{tl.kind}</td>
              <td>{tl.strength} · {tl.touches} toques{tl.broken ? " · rompida" : ""}</td>
            </tr>
          ))}
          {t.trend_lines.length === 0 && <tr><td colSpan={2} className="muted">—</td></tr>}
        </tbody>
      </table>
      {t.rsi_divergence && (
        <div className="note">
          Divergência {t.rsi_divergence.type}: {t.rsi_divergence.note}
        </div>
      )}
    </div>
  );
}

interface FundData {
  sector?: string;
  pe?: number;
  pvp?: number;
  roe?: number;
  profit_margin?: number;
  revenue_growth?: number;
  dividend_yield?: number;
  payout?: number;
  debt_to_equity?: number;
  avg_volume?: number;
  free_cashflow?: number;
  currency?: string;
  history?: {
    years?: number;
    roe_5y?: number;
    margin_5y?: number;
    pe_5y?: number;
    pvp_5y?: number;
    revenue_growth_5y?: number;
    dy_5y?: number;
  };
}

function FundamentalTable({ data }: { data: Analysis }) {
  const raw = data.fundamentals as { data?: FundData };
  const f: FundData = raw.data ?? {};
  const h = f.history;
  const sym = f.currency === "BRL" ? "R$" : "US$";

  const pct = (v?: number): string =>
    typeof v === "number" ? `${(v * 100).toFixed(1)}%` : "—";
  const num = (v?: number, d = 2): string =>
    typeof v === "number"
      ? v.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d })
      : "—";
  const money = (v?: number): string =>
    typeof v === "number" ? `${sym} ${Math.round(v).toLocaleString("pt-BR")}` : "—";

  const rows: Array<[string, string, string]> = [
    ["Setor", f.sector ?? "—", "—"],
    ["P/L", num(f.pe), num(h?.pe_5y)],
    ["P/VPA", num(f.pvp), num(h?.pvp_5y)],
    ["ROE", pct(f.roe), pct(h?.roe_5y)],
    ["Margem líquida", pct(f.profit_margin), pct(h?.margin_5y)],
    ["Crescimento de receita", pct(f.revenue_growth), pct(h?.revenue_growth_5y)],
    ["Dividend yield", typeof f.dividend_yield === "number" ? `${num(f.dividend_yield)}%` : "—", pct(h?.dy_5y)],
    ["Payout", pct(f.payout), "—"],
    ["Dívida/PL", typeof f.debt_to_equity === "number" ? `${num(f.debt_to_equity)} %` : "—", "—"],
    ["Fluxo de caixa livre", money(f.free_cashflow ?? undefined), "—"],
  ];

  return (
    <div>
      <table className="kv fund-table">
        <thead>
          <tr>
            <th>Indicador</th>
            <th>Atual</th>
            <th>Média 5 anos</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, cur, hist]) => (
            <tr key={label}>
              <td>{label}</td>
              <td className={cur === "—" ? "muted" : ""}>{cur}</td>
              <td className={hist === "—" ? "muted" : ""}>{hist}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted fund-note">
        Médias calculadas sobre demonstrações anuais dos últimos ~5 anos no Yahoo Finance.
      </p>
    </div>
  );
}

export default App;
