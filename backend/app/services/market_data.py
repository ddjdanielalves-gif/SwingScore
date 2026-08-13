"""Market data layer.

Primary source: Yahoo Finance (yfinance). It covers both B3 (PETR4.SA,
VALE3.SA, ...) and international markets (AAPL, MSFT, ...).

A synthetic local provider backs the platform when there is no internet
access or the provider is blocked, so the product is always demonstrable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import yfinance as yf

from ..config import settings

logger = logging.getLogger("swing.market")

CACHE: dict[str, tuple[float, dict]] = {}
CACHE_LOCK = threading.Lock()

CURATED: list[dict] = [
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


def _no_accent(value: str) -> str:
    norm = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in norm if not unicodedata.combining(ch)).upper()


def _load_b3_index() -> list[dict]:
    """Load the local B3 ticker catalog (brapi-derived, no FIIs)."""
    try:
        path = Path(__file__).resolve().parents[1] / "data" / "b3_tickers.json"
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        logger.warning("could not load B3 index: %s", exc)
        return []
    kept = []
    for item in data:
        name = item.get("name") or ""
        nn = _no_accent(name)
        if "FUNDO DE INVESTIMENTO" in nn:
            continue
        if "FIC " in nn or " FIC" in nn or "FIC " in name:
            continue
        if "FUNDOS INCENTIVADOS" in nn:
            continue
        tk = (item.get("ticker") or "").strip().upper()
        if tk.endswith(".SA"):
            tk = tk[:-3]
        if tk.endswith("F") or tk.startswith("$"):
            continue
        kept.append(item)
    return kept


B3_INDEX: list[dict] = _load_b3_index()


def _base_code(ticker: str) -> str:
    tk = ticker.upper()
    if tk.endswith(".SA"):
        tk = tk[:-3]
    return tk


def _rank_key(ticker: str) -> tuple:
    """Liquidity-ish order: PN(4) > ON(3) > Units(11) > 5/6 > BDR(34) > rest."""
    tk = _base_code(ticker)
    if len(tk) in (6, 7) and tk.endswith("34"):
        return (6, tk)
    suffix = tk[-2:] if tk[-2:] == "11" else tk[-1]
    order = {"4": 0, "3": 1, "11": 2, "5": 3, "6": 4}
    return (order.get(suffix, 5), tk)


def _match_priority(q: str, ticker: str, name: str) -> int | None:
    """Lower = better. Ticker intent beats name intent; exact beats substring."""
    code = _base_code(ticker).upper()
    nn = _no_accent(name)
    if code == q:
        return 0
    if q.startswith(code):
        return 1
    if len(q) >= 3 and code.startswith(q):
        return 2
    tokens = nn.split()
    if tokens and tokens[0] == q:
        return 3
    if nn.startswith(q):
        return 4
    if q in nn:
        return 5
    # Allow "SANTANDER BR" to match "BANCO SANTANDER (BRASIL)".
    nn_clean = nn.replace("(", " ").replace(")", " ").replace("-", " ")
    q_clean = q.replace("-", " ")
    if q_clean in " ".join(nn_clean.split()):
        return 5
    return None


# ---------------------------------------------------------------------------
# Ticker normalization
# ---------------------------------------------------------------------------

def _b3_like(t: str) -> bool:
    """Looks like a B3 code: PETR4, VALE3, BBAS3, TAEE11, SANB11, MELI34..."""
    return (
        len(t) <= 7
        and t.isalnum()
        and not t.isdigit()
        and t.endswith(BR_SUFFIX)
    )


def _known_b3_code(code: str) -> bool:
    """True when <code>.SA is in the local B3 catalog (PETR4, TAEE11, ...)."""
    target = f"{code}.SA"
    return any(c["ticker"] == target for c in B3_INDEX + CURATED)


def _b3_resolve(code: str) -> str:
    """Resolve a B3-looking code, checking the local catalog first."""
    candidate = f"{code}.SA"
    if _known_b3_code(code):
        return candidate
    # Unknown code: try smart resolution (catches typos like MELI3 -> MELI34).
    try:
        for h in search(code, limit=5):
            if h["ticker"].endswith(".SA"):
                return h["ticker"]
    except Exception as exc:  # pragma: no cover
        logger.warning("B3 resolution failed for %r: %s", code, exc)
    return candidate


def resolve_ticker(raw: str) -> str:
    t = raw.strip().upper().replace(" ", "")
    if "." in t:
        # Some Yahoo BR artifacts use BBAS3.F; treat as the B3 code.
        if t.endswith(".F") and _b3_like(t[:-2]):
            return _b3_resolve(t[:-2])
        return t
    if t.startswith("^"):
        return t
    # Strip trailing "F" sometimes seen on B3 codes (BBAS3F -> BBAS3).
    base = t[:-1] if len(t) > 1 and t.endswith("F") else t
    if base != t and _b3_like(base):
        return _b3_resolve(base)
    # B3 codes look like PETR4, VALE3, BBAS3, TAEE11, SANB11...
    if _b3_like(t):
        return _b3_resolve(t)
    # Not a code: try company-name resolution ("banco do brasil", "vale", ...).
    name_query = raw.strip().upper()
    try:
        hits = search(name_query, limit=1)
        if hits:
            return hits[0]["ticker"]
    except Exception as exc:  # pragma: no cover
        logger.warning("Name resolution failed for %r: %s", raw, exc)
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
    try:
        meta = _fetch_meta(ticker)
        if float(meta.get("price") or 0.0) <= 0.0:
            raise MarketDataUnavailable(f"Meta vazia para {ticker}")
    except MarketDataUnavailable:
        if _b3_like(_base_code(ticker)):
            meta = _brapi_meta(ticker)
        else:
            raise
    _cache_set(key, meta)
    return meta


def asset_info(ticker: str) -> dict:
    """Raw fundamental/quote info (quoteSummary equivalent via Ticker.info)."""
    key = f"info|{ticker}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    info = _fetch_info(ticker)
    if not info and _b3_like(_base_code(ticker)):
        info = _brapi_info(ticker)
        logger.warning("info %s: Yahoo falhou, usando dados reais da brapi", ticker)
    if info:
        # Never cache a failed/empty fetch: a transient Yahoo blip must not
        # poison the cache for the whole TTL.
        _cache_set(key, info)
    return info


def dividends_history(ticker: str) -> pd.Series:
    key = f"divs|{ticker}"
    cached = _cache_get(key)
    if cached is not None:
        return pd.Series(cached)
    series = _fetch_dividends(ticker)
    if len(series):
        _cache_set(key, series.to_dict())
    return series


def search(query: str, limit: int = 8) -> list[dict]:
    q = query.strip()
    if not q:
        return []
    nq = _no_accent(q)
    hits: list[dict] = []

    def add(ticker: str, name: str) -> None:
        if any(h["ticker"] == ticker for h in hits):
            return
        hits.append(
            {
                "ticker": ticker,
                "name": name,
                "market": "B3" if ticker.endswith(".SA") else "Internacional",
            }
        )

    def sort_hits(items: list[dict], match_q: str | None = None) -> list[dict]:
        mq = match_q or nq
        dedup: dict[str, dict] = {}
        for c in items:
            name = c["name"]
            key = _no_accent(name)
            existing = dedup.get(key)
            if existing is None or _rank_key(c["ticker"]) < _rank_key(existing["ticker"]):
                dedup[key] = c
        ranked = sorted(
            dedup.values(),
            key=lambda c: (
                _match_priority(mq, c["ticker"], c["name"]) or 9,
                _rank_key(c["ticker"]),
            ),
        )
        return ranked

    # 1) Exact ticker match.
    exact = [
        c
        for c in B3_INDEX + CURATED
        if _base_code(c["ticker"]).upper() == nq or c["ticker"].upper() == nq
    ]
    for c in sort_hits(exact):
        add(c["ticker"], c["name"])
    if hits:
        return hits[:limit]

    # 2) Local B3 catalog by ticker prefix or company name (accent-insensitive).
    local = [
        c
        for c in B3_INDEX
        if _match_priority(nq, c["ticker"], c["name"]) is not None
    ]
    for c in sort_hits(local):
        add(c["ticker"], c["name"])
        if len(hits) >= limit:
            break
    if len(hits) >= limit:
        return hits[:limit]

    # 3) Curated list (indexes + international anchors).
    curated = [
        c
        for c in CURATED
        if _match_priority(nq, c["ticker"], c["name"]) is not None
    ]
    for c in sort_hits(curated):
        add(c["ticker"], c["name"])
    if hits or settings.mock_mode:
        return hits[:limit]

    # 3b) Typo tolerance: drop trailing characters ("ambeve" -> "ambev").
    for probe in (nq[:-1], nq[:-2]):
        if len(probe) < 3:
            break
        fuzzy = [
            c
            for c in B3_INDEX + CURATED
            if _match_priority(probe, c["ticker"], c["name"]) is not None
        ]
        for c in sort_hits(fuzzy, match_q=probe):
            add(c["ticker"], c["name"])
            if len(hits) >= limit:
                break
        if hits:
            return hits[:limit]

    # 4) Yahoo fallback (international symbols / long names).
    try:
        results = yf.Search(q, max_results=limit)
        for quote in results.quotes or []:
            sym = quote.get("symbol", "")
            if not sym:
                continue
            add(sym, quote.get("longname") or quote.get("shortname") or sym)
    except Exception as exc:  # pragma: no cover
        logger.warning("Search failed for %r: %s", q, exc)
    return hits[:limit]


# ---------------------------------------------------------------------------
# Yahoo Finance / mock fetching
#
# Policy: synthetic data is ONLY produced when SWING_MOCK_MODE is enabled.
# In production a Yahoo failure surfaces as MarketDataUnavailable so the app
# never presents fabricated prices or fundamentals as real data.
# ---------------------------------------------------------------------------

class MarketDataUnavailable(Exception):
    """Raised when live Yahoo data cannot be obtained (no synthetic fallback)."""


def _yf_call(fn, attempts: int = 3, base_delay: float = 0.7):
    """Run a Yahoo call with retries/backoff; raise MarketDataUnavailable."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - any Yahoo error is retriable
            last = exc
            if i < attempts - 1:
                time.sleep(base_delay * (i + 1))
    raise MarketDataUnavailable(f"Yahoo Finance indisponível: {last}") from last


BRAPI_BASE = "https://brapi.dev/api"
BRAPI_TIMEOUT = 15.0


def _brapi_quote(code: str) -> dict | None:
    """Real B3 quote from brapi.dev. Best-effort; returns None when the
    provider is not configured or the call fails."""
    token = settings.brapi_token
    if not token:
        return None
    try:
        resp = httpx.get(
            f"{BRAPI_BASE}/quote/{code}",
            params={"token": token, "fundamentals": "true"},
            timeout=BRAPI_TIMEOUT,
        )
        resp.raise_for_status()
        results = (resp.json() or {}).get("results") or []
        if not results:
            logger.warning("brapi sem resultado para %s", code)
            return None
        return results[0]
    except Exception as exc:  # noqa: BLE001 - brapi is best-effort fallback
        logger.warning("brapi quote %s falhou: %s", code, exc)
        return None


def _brapi_meta(ticker: str) -> dict:
    """Meta real da brapi quando o Yahoo falha (somente B3)."""
    code = _base_code(ticker)
    r = _brapi_quote(code)
    if not r:
        raise MarketDataUnavailable(f"Sem dados para {ticker} (Yahoo e brapi indisponíveis)")
    price = float(r.get("regularMarketPrice") or 0.0)
    name = r.get("longName") or r.get("shortName") or code
    if name == code:
        name = next(
            (c["name"] for c in B3_INDEX + CURATED if c["ticker"] == ticker), ticker
        )
    return {
        "ticker": ticker,
        "name": name,
        "currency": r.get("currency") or "BRL",
        "market": "B3",
        "price": price,
        "previous_close": float(r.get("regularMarketPreviousClose") or price),
    }


def _brapi_info(ticker: str) -> dict:
    """Info fundamental mínima da brapi (P/L real) quando o Yahoo falha."""
    code = _base_code(ticker)
    r = _brapi_quote(code)
    if not r:
        return {}
    return {
        "shortName": r.get("shortName") or code,
        "longName": r.get("longName") or code,
        "trailingPE": r.get("priceEarnings"),
        "earningsPerShare": r.get("earningsPerShare"),
        "currentPrice": r.get("regularMarketPrice"),
        "regularMarketPrice": r.get("regularMarketPrice"),
        "marketCap": r.get("marketCap"),
        "currency": r.get("currency") or "BRL",
        "fiftyTwoWeekLow": r.get("fiftyTwoWeekLow"),
        "fiftyTwoWeekHigh": r.get("fiftyTwoWeekHigh"),
    }


def _fetch_candles(ticker: str, period: str, interval: str) -> pd.DataFrame:
    if settings.mock_mode:
        return _mock_candles(ticker)
    hist = _yf_call(
        lambda: yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
    )
    if hist is not None and len(hist):
        df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]
        df.index = pd.to_datetime(df.index)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df.dropna(subset=["open", "high", "low", "close"])
        if len(df):
            return df
    raise MarketDataUnavailable(f"Sem histórico de preços para {ticker}")


def _fetch_meta(ticker: str) -> dict:
    if settings.mock_mode:
        return _mock_meta(ticker)
    info = _yf_call(lambda: yf.Ticker(ticker).fast_info)
    name = info.get("shortName") or ticker
    if name == ticker:
        name = next(
            (c["name"] for c in B3_INDEX + CURATED if c["ticker"] == ticker), ticker
        )
    return {
        "ticker": ticker,
        "name": name,
        "currency": info.get("currency") or currency_of(ticker),
        "market": market_of(ticker),
        "price": float(info.get("last_price") or 0.0),
        "previous_close": float(info.get("previous_close") or 0.0),
    }


def _fetch_info(ticker: str) -> dict:
    if settings.mock_mode:
        return _mock_info(ticker)
    try:
        info = _yf_call(lambda: yf.Ticker(ticker).info or {})
    except MarketDataUnavailable as exc:
        logger.warning("yfinance info failed for %s: %s", ticker, exc)
        return {}
    clean = {k: v for k, v in info.items() if not isinstance(v, (dict, list))}
    if not any(v is not None for v in clean.values()):
        logger.warning("yfinance info returned no data for %s", ticker)
        return {}
    return clean


def _fetch_dividends(ticker: str) -> pd.Series:
    if settings.mock_mode:
        return _mock_dividends(ticker)
    try:
        divs = _yf_call(lambda: yf.Ticker(ticker).dividends)
        if divs is not None and len(divs):
            return divs
    except MarketDataUnavailable as exc:
        logger.warning("yfinance dividends failed for %s: %s", ticker, exc)
    return pd.Series(dtype=float)


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
        data = _yf_call(
            lambda: yf.download(tickers, period=period, interval=interval, auto_adjust=True, progress=False),
            attempts=2,
            base_delay=0.5,
        )
        if isinstance(data, pd.DataFrame) and "Close" in data.columns:
            if isinstance(data["Close"], pd.DataFrame):
                return data["Close"]
            return data[["Close"]].rename(columns={"Close": tickers[0]})
    except Exception as exc:
        logger.warning("batch download failed: %s", exc)
    raise MarketDataUnavailable(f"Sem cotações para {tickers}")


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
    name = next(
        (c["name"] for c in B3_INDEX + CURATED if c["ticker"] == ticker), ticker
    )
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
        data = _yf_call(
            lambda: yf.download(tickers, period="5d", interval="1d", auto_adjust=True, progress=False),
            attempts=2,
            base_delay=0.5,
        )
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
    # Production: never fabricate quotes; the tape stays empty until Yahoo recovers.
    return []


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
