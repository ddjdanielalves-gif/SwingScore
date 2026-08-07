from __future__ import annotations

from pydantic import BaseModel


class SearchHit(BaseModel):
    ticker: str
    name: str
    market: str


class AssetResponse(BaseModel):
    ticker: str
    name: str
    currency: str
    market: str
    price: float
    change_pct: float
    swing_score: float
    confidence: float
    label: str
    pillars: dict
    scenarios: dict
    targets: dict
    dividends: dict
    fundamentals: dict
    technical: dict
    macro: dict
    report: str
    candles: list[dict]
    ma_series: dict
    created_at: str
    is_demo: bool


class HistoryPoint(BaseModel):
    created_at: str
    price: float
    swing_score: float
    confidence: float
    label: str


class HistoryResponse(BaseModel):
    ticker: str
    points: list[HistoryPoint]
    delta_yesterday: float | None
    delta_week: float | None
    delta_month: float | None


class MacroResponse(BaseModel):
    macro: dict


class QuoteItem(BaseModel):
    ticker: str
    name: str
    price: float
    change_pct: float


class TickerTapeResponse(BaseModel):
    items: list[QuoteItem]
    updated_at: str
    is_demo: bool
