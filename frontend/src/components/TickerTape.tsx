import { useEffect, useState } from "react";
import { api } from "../api";
import type { QuoteItem } from "../types";

function shortName(t: string): string {
  if (t === "^BVSP") return "IBOV";
  if (t === "^GSPC") return "S&P 500";
  if (t === "USDBRL=X") return "Dólar";
  if (t.endsWith(".SA")) return t.replace(".SA", "");
  return t;
}

function Item({ q }: { q: QuoteItem }) {
  const pos = q.change_pct >= 0;
  return (
    <div className="tape-item">
      <span className="tape-sym">{shortName(q.ticker)}</span>
      <span className="tape-price">{q.price.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
      <span className={`tape-chg ${pos ? "pos" : "neg"}`}>
        {pos ? "▲" : "▼"} {pos ? "+" : ""}
        {q.change_pct.toFixed(2)}%
      </span>
    </div>
  );
}

export default function TickerTape() {
  const [items, setItems] = useState<QuoteItem[]>([]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const tape = await api.ticker();
        if (alive && tape.items.length > 0) setItems(tape.items);
      } catch {
        // keep last known quotes
      }
    };
    load();
    const id = setInterval(load, 45000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (items.length === 0) return null;
  const doubled = [...items, ...items];

  return (
    <div className="tape-wrap">
      <span className="tape-label">MERCADO</span>
      <div className="tape-viewport">
        <div className="tape-track">
          {doubled.map((q, i) => (
            <Item key={`${q.ticker}-${i}`} q={q} />
          ))}
        </div>
      </div>
    </div>
  );
}
