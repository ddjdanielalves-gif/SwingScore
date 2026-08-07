"""Market data layer.

Primary source: Yahoo Finance (yfinance). It covers both B3 (PETR4.SA,
VALE3.SA, ...) and international markets (AAPL, MSFT, ...).

A synthetic local provider backs the platform when there is no internet
access or the provider is blocked, so the product is always demonstrable.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import yfinance as yf

from ..config import settings

logger = logging.getLogger("swing.market")

CACHE: dict[str, tuple[float, dict]] = {}
CACHE_LOCK = threading.Lock()

CURATED: list[dict] = [
    {"ticker": "PETR4", "name": "Petrobras PN", "market": "B3"},
    {"ticker": "VALE3", "name": "Vale ON", "market": "B3"},
    {"ticker": "BBAS3", "name": "Banco do Brasil ON", "market": "B3"},
    {"ticker": "ITUB4", "name": "Itaú Unibanco PN", "market": "B3"},
    {"ticker": "BBDC4", "name": "Bradesco PN", "market": "B3"},
    {"ticker": "ABEV3", "name": "Ambev ON", "market": "B3"},
    {"ticker": "WEGE3", "name": "WEG ON", "market": "B3"},
    {"ticker": "MGLU3", "name": "Magazine Luiza ON", "market": "B3"},
    {"ticker": "B3SA3", "name": "B3 ON", "market": "B3"},
    {"ticker": "PRIO3", "name": "PetroRio ON", "market": "B3"},
    {"ticker": "SUZB3", "name": "Suzano ON", "market": "B3"},
    {"ticker": "GGBR4", "name": "Gerdau PN", "market": "B3"},
    {"ticker": "PETR3", "name": "Petrobras ON", "market": "B3"},
    {"ticker": "EQTL3", "name": "Equatorial ON", "market": "B3"},
    {"ticker": "TAEE11", "name": "Taesa Units", "market": "B3"},
    {"ticker": "ITSA4", "name": "Itaúsa PN", "market": "B3"},
    {"ticker": "CMIG4", "name": "Cemig PN", "market": "B3"},
    {"ticker": "RENT3", "name": "Localiza ON", "market": "B3"},
    {"ticker": "LREN3", "name": "Lojas Renner ON", "market": "B3"},
    {"ticker": "SANB11", "name": "Santander Units", "market": "B3"},
    {"ticker": "BRFS3", "name": "BRF ON", "market": "B3"},
    {"ticker": "JBSS3", "name": "JBS ON", "market": "B3"},
    {"ticker": "ASAI3", "name": "Assaí ON", "market": "B3"},
    {"ticker": "PETR4.SA", "name": "Petrobras PN", "market": "B3"},
    {"ticker": "VALE3.SA", "name": "Vale ON", "market": "B3"},
    {"ticker": "BBAS3.SA", "name": "Banco do Brasil ON", "market": "B3"},
    {"ticker": "AAPL", "name": "Apple Inc.", "market": "NASDAQ"},
    {"ticker": "MSFT", "name": "Microsoft Corp.", "market": "NASDAQ"},
    {"ticker": "GOOGL", "name": "Alphabet Inc.", "market": "NASDAQ"},
    {"ticker": "AMZN", "name": "Amazon.com Inc.", "market": "NASDAQ"},
    {"ticker": "NVDA", "name": "NVIDIA Corp.", "market": "NASDAQ"},
    {"ticker": "TSLA", "name": "Tesla Inc.", "market": "NASDAQ"},
    {"ticker": "META", "name": "Meta Platforms", "market": "NASDAQ"},
    {"ticker": "KO", "name": "Coca-Cola Co.", "market": "NYSE"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "market": "NYSE"},
    {"ticker": "PG", "name": "Procter & Gamble", "market": "NYSE"},
    {"ticker": "XOM", "name": "Exxon Mobil", "market": "NYSE"},
    {"ticker": "BABA", "name": "Alibaba Group", "market": "NYSE"},
    {"ticker": "TSM", "name": "TSMC ADR", "market": "NYSE"},
    {"ticker": "^BVSP", "name": "IBOVESPA", "market": "B3"},
    {"ticker": "^GSPC", "name": "S&P 500", "market": "NYSE"},
]

BR_SUFFIX = ("3", "4", "5", "6", "11")


# ---------------------------------------------------------------------------
# Ticker normalization
# ---------------------------------------------------------------------------

def resolve_ticker(raw: str) -> str:
    t = raw.strip().upper().replace(" ", "")
    if "." in t:
        return t
    if t.startswith("^"):
        return t
    # B3 codes look like PETR4, VALE3, BBAS3, TAEE11, SANB11...
    if len(t) <= 7 and t.isalnum() and not t.isdigit() and t.endswith(("3", "4", "5", "6", "11")):
        return f"{t}.SA"
    return t


def market_of(ticker: str) -> str:
    return "B3" if ticker.endswith(".SA") else "Internacional"


def currency_of(ticker: str) -> str:
    return "BRL" if ticker.endswith(".SA") else "USD"


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_get(key: str) -> dict | None:
    with CACHE_LOCK:
        item = CACHE.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts > settings.cache_ttl_seconds:
        return None
    return value


def _cache_set(key: str, value: dict) -> None:
    with CACHE_LOCK:
        CACHE[key] = (time.time(), value)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def candles(ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """OHLCV history. Returns a DataFrame indexed by date."""
    key = f"candles|{ticker}|{period}|{interval}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    df = _fetch_candles(ticker, period, interval)
    _cache_set(key, df)
    return df


def asset_meta(ticker: str) -> dict:
    key = f"meta|{ticker}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    meta = _fetch_meta(ticker)
    _cache_set(key, meta)
    return meta


def asset_info(ticker: str) -> dict:
    """Raw fundamental/quote info (quoteSummary equivalent via Ticker.info)."""
    key = f"info|{ticker}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    info = _fetch_info(ticker)
    _cache_set(key, info)
    return info


def dividends_history(ticker: str) -> pd.Series:
    key = f"divs|{ticker}"
    cached = _cache_get(key)
    if cached is not None:
        return pd.Series(cached)
    series = _fetch_dividends(ticker)
    _cache_set(key, series.to_dict())
    return series


def search(query: str, limit: int = 8) -> list[dict]:
    q = query.strip().upper()
    if not q:
        return []
    hits = [
        {
            "ticker": c["ticker"],
            "name": c["name"],
            "market": c["market"],
        }
        for c in CURATED
        if q in c["ticker"].upper() or q in c["name"].upper()
    ]
    hits = hits[:limit]
    if hits or settings.mock_mode:
        return hits

    try:
        results = yf.Search(q, max_results=limit)
        for quote in results.quotes or []:
            sym = quote.get("symbol", "")
            if not sym:
                continue
            hits.append(
                {
                    "ticker": sym,
                    "name": quote.get("longname") or quote.get("shortname") or sym,
                    "market": "B3" if sym.endswith(".SA") else "Internacional",
                }
            )
        return hits
    except Exception as exc:  # pragma: no cover
        logger.warning("Search failed for %r: %s", q, exc)
        return hits


# ---------------------------------------------------------------------------
# Yahoo Finance / mock fetching
# ---------------------------------------------------------------------------

def _fetch_candles(ticker: str, period: str, interval: str) -> pd.DataFrame:
    if settings.mock_mode:
        return _mock_candles(ticker)
    try:
        hist = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
        if hist is not None and len(hist):
            df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.columns = ["open", "high", "low", "close", "volume"]
            df.index = pd.to_datetime(df.index)
            df = df[~df.index.duplicated(keep="last")].sort_index()
            return df
    except Exception as exc:
        logger.warning("yfinance candles failed for %s: %s", ticker, exc)
    return _mock_candles(ticker)


def _fetch_meta(ticker: str) -> dict:
    if settings.mock_mode:
        return _mock_meta(ticker)
    try:
        info = yf.Ticker(ticker).fast_info
        return {
            "ticker": ticker,
            "name": info.get("shortName") or ticker,
            "currency": info.get("currency") or currency_of(ticker),
            "market": market_of(ticker),
            "price": float(info.get("last_price") or 0.0),
            "previous_close": float(info.get("previous_close") or 0.0),
        }
    except Exception as exc:
        logger.warning("yfinance meta failed for %s: %s", ticker, exc)
    meta = _mock_meta(ticker)
    return meta


def _fetch_info(ticker: str) -> dict:
    if settings.mock_mode:
        return _mock_info(ticker)
    try:
        info = yf.Ticker(ticker).info or {}
        return {k: v for k, v in info.items() if not isinstance(v, (dict, list))}
    except Exception as exc:
        logger.warning("yfinance info failed for %s: %s", ticker, exc)
    return _mock_info(ticker)


def _fetch_dividends(ticker: str) -> pd.Series:
    if settings.mock_mode:
        return _mock_dividends(ticker)
    try:
        divs = yf.Ticker(ticker).dividends
        if divs is not None and len(divs):
            return divs
    except Exception as exc:
        logger.warning("yfinance dividends failed for %s: %s", ticker, exc)
    return _mock_dividends(ticker)


# ---------------------------------------------------------------------------
# Synthetic provider (offline / demo)
# ---------------------------------------------------------------------------

def _seed(ticker: str) -> int:
    return int(hashlib.md5(ticker.encode()).hexdigest()[:8], 16)


def _mock_candles(ticker: str) -> pd.DataFrame:
    rng = np.random.default_rng(_seed(ticker))
    n = 520
    base = 10.0 + (_seed(ticker) % 400) / 10.0
    drift = ((_seed(ticker) % 7) - 2) / 1000.0
    vol = 0.02 + (_seed(ticker) % 10) / 1000.0
    rets = rng.normal(drift, vol, n)
    price = base * np.exp(np.cumsum(rets))
    idx = pd.date_range(end=datetime.now(timezone.utc).date(), periods=n, freq="B")
    high = price * (1 + rng.normal(0.006, 0.004, n))
    low = price * (1 - rng.normal(0.006, 0.004, n))
    open_ = price * (1 + rng.normal(0.001, 0.005, n))
    close = price
    volume = rng.integers(1_000_000, 30_000_000, n).astype(float)
    df = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum.reduce([open_, high, close]),
            "low": np.minimum.reduce([open_, low, close]),
            "close": close,
            "volume": volume,
        },
        index=idx,
    )
    df.attrs["is_mock"] = True
    return df


def _mock_meta(ticker: str) -> dict:
    df = _mock_candles(ticker)
    price = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    return {
        "ticker": ticker,
        "name": f"Demonstração {ticker}",
        "currency": currency_of(ticker),
        "market": market_of(ticker),
        "price": price,
        "previous_close": prev,
    }


def _mock_info(ticker: str) -> dict:
    s = _seed(ticker)
    return {
        "shortName": f"Demonstração {ticker}",
        "longName": f"Empresa de Demonstração {ticker}",
        "sector": "Demonstração",
        "industry": "Demonstração",
        "trailingPE": 6.0 + (s % 150) / 10.0,
        "forwardPE": 5.0 + (s % 120) / 10.0,
        "priceToBook": 0.6 + (s % 300) / 100.0,
        "returnOnEquity": 0.08 + (s % 3000) / 10000.0,
        "profitMargins": 0.05 + (s % 2000) / 10000.0,
        "freeCashflow": 1e9 + s % 3 * 1e8,
        "operatingCashflow": 2e9 + s % 4 * 1e8,
        "netIncome": 1.5e9 + s % 3 * 5e8,
        "totalRevenue": 8e9 + s % 5 * 1e9,
        "revenueGrowth": 0.02 + (s % 2000) / 10000.0,
        "earningsGrowth": 0.03 + (s % 2500) / 10000.0,
        "dividendYield": 0.02 + (s % 600) / 10000.0,
        "payoutRatio": 0.2 + (s % 4000) / 10000.0,
        "debtToEquity": 20.0 + s % 120,
        "totalDebt": 4e9 + s % 4 * 1e9,
        "totalCash": 2e9 + s % 3 * 1e9,
        "ebitda": 3e9 + s % 5 * 1e8,
        "bookValue": 15.0 + s % 500 / 10.0,
        "currentPrice": float(_mock_candles(ticker)["close"].iloc[-1]),
        "targetMeanPrice": 0.0,
    }


def _mock_dividends(ticker: str) -> pd.Series:
    rng = np.random.default_rng(_seed(ticker) + 7)
    price = float(_mock_candles(ticker)["close"].iloc[-1])
    dy = 0.02 + (_seed(ticker) % 500) / 10000.0
    yearly = price * dy
    dates = pd.date_range(end=datetime.now(timezone.utc).date(), periods=20, freq="QE")
    amounts = np.abs(rng.normal(yearly / 4, yearly / 12, 20))
    return pd.Series(amounts, index=dates)


# ---------------------------------------------------------------------------
# Batch helpers (macro)
# ---------------------------------------------------------------------------

def batch_candles(tickers: list[str], period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """Download multiple tickers at once and return Close-only frame."""
    if settings.mock_mode:
        closes = {}
        idx = None
        for t in tickers:
            df = _mock_candles(t)
            closes[t] = df["close"]
            idx = df.index
        out = pd.DataFrame(closes, index=idx)
        return out
    try:
        data = yf.download(tickers, period=period, interval=interval, auto_adjust=True, progress=False)
        if isinstance(data, pd.DataFrame) and "Close" in data.columns:
            if isinstance(data["Close"], pd.DataFrame):
                return data["Close"]
            return data[["Close"]].rename(columns={"Close": tickers[0]})
    except Exception as exc:
        logger.warning("batch download failed: %s", exc)
    closes = {}
    for t in tickers:
        try:
            closes[t] = _mock_candles(t)["close"]
        except Exception:
            continue
    return pd.DataFrame(closes)


# ---------------------------------------------------------------------------
# Ticker tape (near real-time quotes)
# ---------------------------------------------------------------------------

TAPE_TICKERS = [
    "^BVSP", "^GSPC", "USDBRL=X",
    "PETR4.SA", "VALE3.SA", "BBAS3.SA", "ITUB4.SA", "BBDC4.SA",
    "ABEV3.SA", "WEGE3.SA", "B3SA3.SA", "PRIO3.SA", "SUZB3.SA",
    "GGBR4.SA", "TAEE11.SA", "CMIG4.SA", "RENT3.SA", "LREN3.SA",
    "SANB11.SA", "BRFS3.SA", "JBSS3.SA", "EQTL3.SA", "ITSA4.SA",
    "MGLU3.SA", "AAPL", "NVDA", "MSFT",
]

TAPE_CACHE: dict[str, tuple[float, list[dict]]] = {}
TAPE_TTL_SECONDS = 45


def _quote_item(ticker: str, price: float, prev: float) -> dict:
    name = next((c["name"] for c in CURATED if c["ticker"] == ticker), ticker)
    return {
        "ticker": ticker,
        "name": name,
        "price": round(float(price), 2),
        "change_pct": round((price / prev - 1) * 100, 2) if prev else 0.0,
    }


def _fetch_quotes(tickers: list[str]) -> list[dict]:
    if settings.mock_mode:
        out = []
        for t in tickers:
            df = _mock_candles(t)
            closes = df["close"].tolist()
            price = closes[-1]
            prev = closes[-2] if len(closes) > 1 else price
            out.append(_quote_item(t, price, prev))
        return out
    try:
        data = yf.download(tickers, period="5d", interval="1d", auto_adjust=True, progress=False)
        if data is None or len(data) == 0:
            raise ValueError("empty download")
        if isinstance(data.columns, pd.MultiIndex):
            closes = data["Close"]
        else:
            closes = data[["Close"]].rename(columns={"Close": tickers[0]})
        out = []
        for t in tickers:
            if t not in closes.columns:
                continue
            s = closes[t].dropna()
            if len(s) == 0:
                continue
            price = float(s.iloc[-1])
            prev = float(s.iloc[-2]) if len(s) > 1 else price
            out.append(_quote_item(t, price, prev))
        if out:
            return out
    except Exception as exc:
        logger.warning("quotes download failed: %s", exc)
    # Fallback: mock quotes so the tape is never empty.
    return [_quote_item(t, float(_mock_candles(t)["close"].iloc[-1]), float(_mock_candles(t)["close"].iloc[-2])) for t in tickers]


def quotes(tickers: list[str] | None = None) -> list[dict]:
    """Near-real-time quotes for the header tape, cached for ~45s."""
    tickers = tickers or TAPE_TICKERS
    key = "|".join(tickers)
    now = time.time()
    cached = TAPE_CACHE.get(key)
    if cached and now - cached[0] < TAPE_TTL_SECONDS:
        return cached[1]
    out = _fetch_quotes(tickers)
    TAPE_CACHE[key] = (now, out)
    return out
