import type { Analysis, HistoryResponse, SearchHit, TickerTape } from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";
const TIMEOUT_MS = 150000;

async function get<T>(path: string): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, { signal: controller.signal });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(detail || `Erro ${res.status}`);
    }
    return res.json() as Promise<T>;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  search: (q: string) => get<SearchHit[]>(`/api/assets/search?q=${encodeURIComponent(q)}`),
  analysis: (ticker: string) => get<Analysis>(`/api/assets/${encodeURIComponent(ticker)}/analysis`),
  history: (ticker: string) => get<HistoryResponse>(`/api/assets/${encodeURIComponent(ticker)}/history`),
  ticker: () => get<TickerTape>(`/api/market/ticker`),
};
