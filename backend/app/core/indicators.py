"""Technical analysis primitives.

Only a few indicators are exposed to the user (RSI, moving averages,
support/resistance, trend lines) but the module computes everything else
internally so future indicators can be plugged in without touching the API.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

RSI_PERIOD = 14
ATR_PERIOD = 14
SMA_WINDOWS = (21, 72, 200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _last(x: pd.Series) -> float:
    series = x.dropna()
    return float(series.iloc[-1]) if len(series) else float("nan")


def _slope(series: pd.Series, window: int = 20) -> float:
    """Annualized-ish linear slope of the last `window` values, in %/bar."""
    s = series.dropna().tail(window)
    if len(s) < 5:
        return 0.0
    y = s.to_numpy(dtype=float)
    x = np.arange(len(y))
    if np.ptp(y) == 0:
        return 0.0
    coef = np.polyfit(x, y, 1)
    base = float(np.mean(y))
    if base == 0:
        return 0.0
    return float(coef[0]) / base * 100.0


# ---------------------------------------------------------------------------
# Classic indicators
# ---------------------------------------------------------------------------

def rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = ATR_PERIOD) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


# ---------------------------------------------------------------------------
# Pivots / supports & resistances
# ---------------------------------------------------------------------------

def _pivots(df: pd.DataFrame, window: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return pivot highs and pivot lows (each as a DataFrame with
    `price` and the bar index)."""
    highs = df["high"]
    lows = df["low"]
    hi_idx = [
        i
        for i in range(window, len(df) - window)
        if highs.iloc[i] == highs.iloc[i - window : i + window + 1].max()
    ]
    lo_idx = [
        i
        for i in range(window, len(df) - window)
        if lows.iloc[i] == lows.iloc[i - window : i + window + 1].min()
    ]
    piv_hi = pd.DataFrame({"price": highs.iloc[hi_idx].to_numpy(), "pos": hi_idx})
    piv_lo = pd.DataFrame({"price": lows.iloc[lo_idx].to_numpy(), "pos": lo_idx})
    return piv_hi, piv_lo


def support_resistance(
    df: pd.DataFrame,
    tolerance: float = 0.015,
    window: int = 5,
) -> list[dict]:
    """Cluster pivot levels into support / resistance zones.

    Each zone is a price level with a touch count. The more a level is
    respected, the more weight it gets downstream.
    """
    piv_hi, piv_lo = _pivots(df, window=window)
    levels: list[dict] = []

    def add(price: float, pos: int, kind: str) -> None:
        for level in levels:
            if abs(level["price"] - price) / price <= tolerance:
                level["touches"] += 1
                level["last_touch"] = max(level["last_touch"], pos)
                level["strength"] = min(1.0, level["touches"] / 5.0)
                return
        levels.append(
            {
                "price": float(price),
                "touches": 1,
                "kind": kind,
                "last_touch": pos,
                "strength": 0.2,
            }
        )

    for _, row in piv_hi.iterrows():
        add(float(row["price"]), int(row["pos"]), "resistance")
    for _, row in piv_lo.iterrows():
        add(float(row["price"]), int(row["pos"]), "support")

    # Classify by position relative to the last close (a level can act as
    # both; keep the most recent role).
    last_close = float(df["close"].iloc[-1])
    for level in levels:
        if level["price"] < last_close * 0.985:
            level["kind"] = "support"
        elif level["price"] > last_close * 1.015:
            level["kind"] = "resistance"
        else:
            level["kind"] = "pivot"
    levels.sort(key=lambda l: l["touches"], reverse=True)
    return levels


# ---------------------------------------------------------------------------
# Trend lines
# ---------------------------------------------------------------------------

@dataclass
class TrendLine:
    kind: str  # "support" | "resistance"
    start_pos: int
    end_pos: int
    slope_per_bar: float
    touches: int
    strength: str  # "fraca" | "provável" | "forte"
    broken: bool
    start_value: float = 0.0
    end_value: float = 0.0


def _fit_line(points: np.ndarray) -> tuple[float, float] | None:
    if len(points) < 2:
        return None
    x = points[:, 0].astype(float)
    y = points[:, 1].astype(float)
    coef = np.polyfit(x, y, 1)
    return float(coef[0]), float(coef[1])


def trend_lines(df: pd.DataFrame, window: int = 5) -> list[TrendLine]:
    """Auto-detect support/resistance trend lines from pivot clusters.

    Connects pairs of monotonic pivots (ascending lows for support,
    descending highs for resistance), then counts how many pivots sit near
    each line. 2 touches -> "provável", 3 or more -> "forte". A broken line
    happens when price closes beyond it.
    """
    piv_hi, piv_lo = _pivots(df, window=window)
    last_pos = len(df) - 1
    last_close = float(df["close"].iloc[-1])
    lines: list[TrendLine] = []

    def build(pivots: pd.DataFrame, kind: str, tolerance: float = 0.01) -> None:
        pts = pivots.to_numpy()[:, [1, 0]]  # (bar_index, price)
        n = len(pts)
        for i in range(n):
            for j in range(i + 1, n):
                gap = pts[j, 0] - pts[i, 0]
                if gap < 20:  # too close: fragile line
                    continue
                fit = _fit_line(pts[[i, j]])
                if fit is None:
                    continue
                slope, intercept = fit
                # Monotonicity: support lows rise, resistance highs fall.
                if kind == "support" and slope < -1e-9:
                    continue
                if kind == "resistance" and slope > 1e-9:
                    continue
                # Count pivots sitting near the line (touches).
                touched = [i]
                for k in range(i + 1, n):
                    line_val = slope * pts[k, 0] + intercept
                    if line_val and abs((pts[k, 1] - line_val) / line_val) < tolerance:
                        touched.append(k)
                if len(touched) < 2:
                    continue
                touch_count = len(touched)
                end_idx = int(pts[touched[-1], 0])
                start_val = float(slope * pts[touched[0], 0] + intercept)
                end_val = float(slope * end_idx + intercept)
                projected = slope * last_pos + intercept
                broken = last_close < projected if kind == "support" else last_close > projected
                strength = "forte" if touch_count >= 3 else "provável"
                lines.append(
                    TrendLine(
                        kind=kind,
                        start_pos=int(pts[touched[0], 0]),
                        end_pos=end_idx,
                        slope_per_bar=slope,
                        touches=touch_count,
                        strength=strength,
                        broken=broken,
                        start_value=start_val,
                        end_value=end_val,
                    )
                )

    build(piv_hi, "resistance")
    build(piv_lo, "support")

    # Keep the most relevant lines: recent, high-touch, not near-duplicates.
    def keep_relevant(kind: str, max_lines: int = 2) -> list[TrendLine]:
        cand = sorted(
            (l for l in lines if l.kind == kind),
            key=lambda l: (-l.touches, l.end_pos),
        )
        kept: list[TrendLine] = []
        for l in cand:
            if any(abs(l.start_pos - k.start_pos) < 12 for k in kept):
                continue
            kept.append(l)
            if len(kept) >= max_lines:
                break
        return kept

    return keep_relevant("support") + keep_relevant("resistance")


# ---------------------------------------------------------------------------
# Master computation
# ---------------------------------------------------------------------------

def compute(df: pd.DataFrame) -> dict:
    """Compute every technical component for a full OHLCV frame.

    Expects a frame with columns open/high/low/close/volume indexed by date.
    """
    close = df["close"]
    volume = df["volume"]

    mas = {f"sma{w}": sma(close, w) for w in SMA_WINDOWS}
    r = rsi(close)
    atr_series = atr(df["high"], df["low"], close)

    levels = support_resistance(df)
    below = [l for l in levels if l["price"] <= close.iloc[-1]]
    above = [l for l in levels if l["price"] >= close.iloc[-1]]
    nearest_support = max(below, key=lambda l: l["price"]) if below else None
    nearest_resistance = min(above, key=lambda l: l["price"]) if above else None

    t_lines = trend_lines(df)
    support_line = next((l for l in t_lines if l.kind == "support"), None)
    resistance_line = next((l for l in t_lines if l.kind == "resistance"), None)

    price = float(close.iloc[-1])
    rsi_value = _last(r)
    rsi_prev = _last(r.shift(1))

    ma_status: dict[str, str] = {}
    for key, series in mas.items():
        v = _last(series)
        if np.isnan(v):
            ma_status[key] = "n/a"
        else:
            ma_status[key] = "acima" if price > v else "abaixo"

    ma_data: dict[str, float | None] = {}
    for key, series in mas.items():
        v = _last(series)
        ma_data[key] = None if np.isnan(v) else round(float(v), 4)

    distance_mas = {
        key: round((price / float(_last(s)) - 1) * 100, 2)
        for key, s in mas.items()
        if not np.isnan(_last(s))
    }

    rsi_state = "neutro"
    if rsi_value >= 70:
        rsi_state = "sobrecompra"
    elif rsi_value <= 30:
        rsi_state = "sobrevenda"
    elif rsi_value >= 55 and rsi_value < 70:
        rsi_state = "viés comprador"
    elif rsi_value > 30 and rsi_value < 45:
        rsi_state = "viés vendedor"

    return {
        "price": price,
        "rsi": round(rsi_value, 1),
        "rsi_prev": round(rsi_prev, 1) if not np.isnan(rsi_prev) else None,
        "rsi_state": rsi_state,
        "rsi_divergence": _detect_divergence(close, r),
        "atr": round(float(_last(atr_series)), 4),
        "atr_pct": round(float(_last(atr_series)) / price * 100, 2) if price else 0.0,
        "ma_status": ma_status,
        "ma_values": ma_data,
        "ma_slopes": {k: round(_slope(s), 3) for k, s in mas.items()},
        "ma_distance": distance_mas,
        "levels": levels,
        "nearest_support": (
            {"price": round(nearest_support["price"], 4), "touches": nearest_support["touches"]}
            if nearest_support
            else None
        ),
        "nearest_resistance": (
            {
                "price": round(nearest_resistance["price"], 4),
                "touches": nearest_resistance["touches"],
            }
            if nearest_resistance
            else None
        ),
        "trend_lines": [
            {
                "kind": l.kind,
                "start_pos": l.start_pos,
                "end_pos": l.end_pos,
                "start_value": round(l.start_value, 4),
                "end_value": round(l.end_value, 4),
                "slope_per_bar": round(l.slope_per_bar, 6),
                "touches": l.touches,
                "strength": l.strength,
                "broken": l.broken,
            }
            for l in t_lines
        ],
        "trend_support": (
            {
                "strength": support_line.strength,
                "touches": support_line.touches,
                "broken": support_line.broken,
                "slope_per_bar": round(support_line.slope_per_bar, 6),
            }
            if support_line
            else None
        ),
        "trend_resistance": (
            {
                "strength": resistance_line.strength,
                "touches": resistance_line.touches,
                "broken": resistance_line.broken,
                "slope_per_bar": round(resistance_line.slope_per_bar, 6),
            }
            if resistance_line
            else None
        ),
        "ma_data": ma_data,
    }


def _detect_divergence(close: pd.Series, r: pd.Series, lookback: int = 40) -> dict | None:
    """Look for a recent bullish/bearish RSI divergence at a price extreme."""
    r_tail = r.dropna().tail(lookback)
    c_tail = close.reindex(r_tail.index)
    if len(r_tail) < lookback // 2:
        return None
    min_idx = r_tail.values.argmin()
    max_idx = r_tail.values.argmax()
    price_at_rmin = float(c_tail.iloc[min_idx])
    price_at_rmax = float(c_tail.iloc[max_idx])
    r_min = float(r_tail.iloc[min_idx])
    r_max = float(r_tail.iloc[max_idx])
    last = float(r_tail.iloc[-1])
    if r_max > 70 and last < r_max and price_at_rmax > float(c_tail.iloc[-1]):
        return {"type": "bearish", "note": "preço faz topo mais alto, RSI não acompanha"}
    if r_min < 30 and last > r_min and price_at_rmin < float(c_tail.iloc[-1]):
        return {"type": "bullish", "note": "preço faz fundo mais baixo, RSI não acompanha"}
    return None
