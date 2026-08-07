import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { SearchHit } from "../types";

interface Props {
  onSelect: (ticker: string) => void;
}

export default function SearchBar({ onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    const t = setTimeout(async () => {
      try {
        setResults(await api.search(query.trim()));
      } catch {
        setResults([]);
      }
    }, 220);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <div className="searchbox" ref={boxRef}>
      <input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="Buscar ativo — PETR4, VALE3, BBAS3, AAPL, MSFT..."
      />
      {open && query.trim() && (
        <div className="search-results">
          {results.map((r) => (
            <button
              key={r.ticker}
              onClick={() => {
                onSelect(r.ticker);
                setOpen(false);
                setQuery("");
              }}
            >
              <span className="sym">{r.ticker}</span>
              <span className="meta">
                {r.name} · {r.market}
              </span>
            </button>
          ))}
          {!results.some((r) => r.ticker.toUpperCase() === query.trim().toUpperCase()) && (
            <button
              className="free"
              onClick={() => {
                onSelect(query.trim().toUpperCase());
                setOpen(false);
                setQuery("");
              }}
            >
              <span className="sym">Analisar {query.trim().toUpperCase()}</span>
              <span className="meta">direto no Yahoo (qualquer ticker)</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
