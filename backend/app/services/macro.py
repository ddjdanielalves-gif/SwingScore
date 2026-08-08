"""Macroeconomic context.

Sources:
- Banco Central do Brasil (SGS API, no key): Selic, IPCA, PIB.
- Yahoo Finance: dólar, IBOVESPA, S&P 500, VIX, petróleo.

The macro score is one of the three pillars (25% weight) of the SwingScore.
"""

from __future__ import annotations

import logging
import threading
import time

import httpx
import pandas as pd

from ..config import settings
from . import market_data

logger = logging.getLogger("swing.macro")

MACRO_CACHE: dict[str, tuple[float, dict]] = {}
MACRO_LOCK = threading.Lock()
MACRO_TTL_SECONDS = 45 * 60

BCB_URLS = {
    "selic": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/12?formato=json",
    "ipca": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/13?formato=json",
    "pib": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4380/dados/ultimos/5?formato=json",
}


def _fetch_bcb() -> dict:
    out: dict = {}
    with httpx.Client(timeout=12) as client:
        for name, url in BCB_URLS.items():
            try:
                resp = client.get(url)
                resp.raise_for_status()
                rows = resp.json()
                values = [float(r["valor"].replace(",", ".")) for r in rows if r.get("valor")]
                if not values:
                    continue
                out[name] = {
                    "value": values[-1],
                    "last": values[-1],
                    "prev": values[-2] if len(values) > 1 else None,
                    "min": min(values),
                    "max": max(values),
                }
            except Exception as exc:
                logger.warning("BCB %s failed: %s", name, exc)
    return out


def _momentums(tickers: list[str]) -> dict[str, dict | None]:
    """Fetch several macro series in a single batch download."""
    out: dict[str, dict | None] = {t: None for t in tickers}
    try:
        df = market_data.batch_candles(tickers, period="6mo")
        if df is None or df.empty:
            return out
        for t in tickers:
            if t not in df.columns:
                continue
            series = df[t].dropna()
            if len(series) < 30:
                continue
            last = float(series.iloc[-1])
            m1 = float(series.iloc[-22]) if len(series) >= 22 else last
            m3 = float(series.iloc[-66]) if len(series) >= 66 else m1
            out[t] = {
                "value": last,
                "mom_1m": (last / m1 - 1) * 100 if m1 else 0.0,
                "mom_3m": (last / m3 - 1) * 100 if m3 else 0.0,
                "trend": "alta" if last > m3 else ("baixa" if last < m3 else "estável"),
            }
    except Exception as exc:
        logger.warning("momentums failed: %s", exc)
    return out


def _mock_bcb() -> dict:
    return {
        "selic": {"value": 10.5, "last": 10.5, "prev": 10.75, "min": 10.5, "max": 13.75},
        "ipca": {"value": 4.2, "last": 4.2, "prev": 4.3, "min": 3.2, "max": 6.0},
        "pib": {"value": 1.8, "last": 1.8, "prev": 1.6, "min": 0.9, "max": 3.0},
    }


def _fetch_all() -> dict:
    bcb = _fetch_bcb() if not settings.mock_mode else _mock_bcb()
    if not bcb:
        bcb = _mock_bcb()

    usd, ibov, spx, vix, oil = _momentums(["USDBRL=X", "^BVSP", "^GSPC", "^VIX", "CL=F"]).values()

    return {
        "selic": bcb.get("selic"),
        "ipca": bcb.get("ipca"),
        "pib": bcb.get("pib"),
        "usd": usd,
        "ibov": ibov,
        "sp500": spx,
        "vix": vix,
        "oil": oil,
        "is_demo": settings.mock_mode,
    }


def collect() -> dict:
    """Macro snapshot with a short TTL (macro data does not change intraday)."""
    with MACRO_LOCK:
        item = MACRO_CACHE.get("macro")
        if item is not None and time.time() - item[0] < MACRO_TTL_SECONDS:
            return item[1]
    data = _fetch_all()
    with MACRO_LOCK:
        MACRO_CACHE["macro"] = (time.time(), data)
    return data


def score(macro: dict, market: str = "B3") -> dict:
    """Turn macro context into a 0-100 score and a human label."""
    pieces: list[float] = []
    notes: list[str] = []

    selic = macro.get("selic") or {}
    if selic:
        s = selic.get("value")
        prev = selic.get("prev")
        if s is not None:
            if s <= 8:
                score_s = 90
            elif s <= 10:
                score_s = 70
            elif s <= 13:
                score_s = 45
            else:
                score_s = 25
            if prev is not None and s < prev:
                score_s = min(95, score_s + 15)
                notes.append("juros em queda favorecem ativos de risco")
            elif prev is not None and s > prev:
                score_s = max(10, score_s - 15)
                notes.append("juros em alta pressionam avaliações")
            pieces.append(score_s)
            notes.append(f"Selic em {s:.2f}% a.a.")

    ipca = macro.get("ipca") or {}
    if ipca.get("value") is not None:
        inf = ipca["value"]
        pieces.append(85 if inf <= 4 else 60 if inf <= 6 else 35)
        notes.append(f"inflação (IPCA) em {inf:.1f}%")

    pib = macro.get("pib") or {}
    if pib.get("value") is not None:
        pieces.append(70 if pib["value"] >= 1 else 45 if pib["value"] >= -1 else 20)
        notes.append(f"PIB crescendo {pib['value']:.1f}%")

    if market == "B3":
        usd = macro.get("usd") or {}
        if usd:
            mom = usd.get("mom_3m", 0.0)
            if -5 <= mom <= 5:
                pieces.append(70)
                notes.append("câmbio estável")
            else:
                pieces.append(40)
                notes.append("câmbio mais volátil que o usual")
        ibov = macro.get("ibov") or {}
        if ibov:
            pieces.append(45 + max(-30, min(30, ibov.get("mom_3m", 0.0))) * 1.2)
            notes.append(f"IBOV em {'alta' if ibov.get('mom_3m', 0) > 0 else 'baixa'} nos últimos 3 meses")
    else:
        spx = macro.get("sp500") or {}
        vix = macro.get("vix") or {}
        if spx:
            pieces.append(45 + max(-30, min(30, spx.get("mom_3m", 0.0))) * 1.2)
        if vix and vix.get("value"):
            v = vix["value"]
            pieces.append(80 if v < 18 else 55 if v < 25 else 30)
            notes.append(f"volatilidade (VIX) em {v:.1f}")

    if not pieces:
        return {"score": 50.0, "label": "contexto econômico neutro", "notes": []}

    total = sum(max(0.0, min(100.0, p)) for p in pieces) / len(pieces)
    if total >= 65:
        label = "contexto favorável a ativos de risco"
    elif total >= 45:
        label = "contexto econômico neutro"
    else:
        label = "contexto de cautela"
    return {"score": round(total, 1), "label": label, "notes": notes[:4]}
