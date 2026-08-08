import type { Analysis, HistoryResponse, SearchHit, TickerTape } from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";
const TIMEOUT_MS = 180000;

interface HttpError extends Error {
  status?: number;
}

async function fetchOnce<T>(path: string): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, { signal: controller.signal });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      const err = new Error(detail || `Erro ${res.status}`) as HttpError;
      err.status = res.status;
      throw err;
    }
    return res.json() as Promise<T>;
  } finally {
    clearTimeout(timer);
  }
}

async function get<T>(path: string, retries = 0): Promise<T> {
  let last: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fetchOnce(path);
    } catch (err) {
      last = err;
      const status = (err as HttpError).status;
      const aborted = (err as Error).name === "AbortError";
      const retriable = aborted || status === undefined || status >= 500;
      if (!retriable || attempt === retries) throw last;
      await new Promise((r) => setTimeout(r, 1500));
    }
  }
  throw last;
}

export const api = {
  search: (q: string) => get<SearchHit[]>(`/api/assets/search?q=${encodeURIComponent(q)}`),
  analysis: (ticker: string) => get<Analysis>(`/api/assets/${encodeURIComponent(ticker)}/analysis`, 1),
  history: (ticker: string) => get<HistoryResponse>(`/api/assets/${encodeURIComponent(ticker)}/history`, 1),
  ticker: () => get<TickerTape>(`/api/market/ticker`),
  health: () => get<{ status: string }>(`/health`, 0),
};
