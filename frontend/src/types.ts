export interface SearchHit {
  ticker: string;
  name: string;
  market: string;
}

export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MaPoint {
  time: string;
  value: number;
}

export interface Level {
  price: number;
  touches: number;
  kind: string;
  strength: number;
}

export interface TrendLineData {
  kind: string;
  start_pos: number;
  end_pos: number;
  start_value?: number;
  end_value?: number;
  start_time?: string;
  end_time?: string;
  touches: number;
  strength: string;
  broken: boolean;
}

export interface Target {
  faixa: [number, number];
  probabilidade: number;
  label: string;
}

export interface Scenario {
  favoravel: number;
  neutro: number;
  desfavoravel: number;
  horizonte_dias: number;
  retorno_esperado: number;
}

export interface Pillar {
  score: number;
  label: string;
}

export interface Analysis {
  ticker: string;
  name: string;
  currency: string;
  market: string;
  price: number;
  change_pct: number;
  swing_score: number;
  confidence: number;
  label: string;
  pillars: { fundamentals: Pillar; technical: Pillar; macro: Pillar };
  scenarios: Scenario;
  targets: Record<string, Target>;
  dividends: Record<string, unknown>;
  fundamentals: Record<string, unknown>;
  technical: {
    rsi: number;
    rsi_state: string;
    rsi_divergence: { type: string; note: string } | null;
    atr_pct: number;
    ma_status: Record<string, string>;
    ma_distance: Record<string, number>;
    levels: Level[];
    nearest_support: { price: number; touches: number } | null;
    nearest_resistance: { price: number; touches: number } | null;
    trend_lines: TrendLineData[];
    trend_support: { strength: string; touches: number; broken: boolean } | null;
    trend_resistance: { strength: string; touches: number; broken: boolean } | null;
  };
  macro: Record<string, unknown> & { label?: string; score?: number };
  report: string;
  candles: Candle[];
  ma_series: { sma21: MaPoint[]; sma72: MaPoint[]; sma200: MaPoint[] };
  created_at: string;
  is_demo: boolean;
}

export interface HistoryPoint {
  created_at: string;
  price: number;
  swing_score: number;
  confidence: number;
  label: string;
}

export interface HistoryResponse {
  ticker: string;
  points: HistoryPoint[];
  delta_yesterday: number | null;
  delta_week: number | null;
  delta_month: number | null;
}

export interface QuoteItem {
  ticker: string;
  name: string;
  price: number;
  change_pct: number;
}

export interface TickerTape {
  items: QuoteItem[];
  updated_at: string;
  is_demo: boolean;
}
