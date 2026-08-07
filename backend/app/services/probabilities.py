"""Probabilities, targets and scenario distribution.

Everything is expressed as ranges with probabilities derived from a Monte
Carlo simulation of the asset over a 3-month (63 sessions) horizon, using
historical daily volatility and a drift influenced by the SwingScore.

No single price is ever presented to the user — only ranges.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HORIZON_DAYS = 63
SIMULATIONS = 3000
RNG_SEED = 42


def _returns(df: pd.DataFrame) -> np.ndarray:
    close = df["close"].dropna()
    rets = close.pct_change().dropna().to_numpy(dtype=float)
    rets = rets[np.isfinite(rets)]
    if len(rets) < 30:
        rets = np.concatenate([rets, np.random.default_rng(7).normal(0, 0.02, 60)])
    return rets


def simulate(df: pd.DataFrame, swing_score: float) -> np.ndarray:
    """Simulated prices at the end of the horizon. Returns (n,) array.

    Bootstraps H daily returns (preserves fat tails) and rescales the total
    return so its mean matches the expected horizon drift: historical drift
    plus a SwingScore tilt.
    """
    rets = _returns(df)
    last = float(df["close"].iloc[-1])
    sigma_h = float(np.std(rets)) * np.sqrt(HORIZON_DAYS)
    hist_mean_h = float(np.mean(rets)) * HORIZON_DAYS
    drift_adj = (swing_score - 50.0) / 100.0 * sigma_h
    mu_h = hist_mean_h + drift_adj

    rng = np.random.default_rng(RNG_SEED)
    sample = rng.choice(rets, size=(SIMULATIONS, HORIZON_DAYS), replace=True)
    total = sample.sum(axis=1)
    total = total - float(np.mean(total)) + mu_h
    return last * np.exp(total)


def scenario_probabilities(swing_score: float, final_prices: np.ndarray, current: float) -> dict:
    """Split the distribution into Favorável / Neutro / Desfavorável.

    Thresholds scale with volatility so the split stays informative even in
    low-vol assets.
    """
    rets = np.log(final_prices / current)
    sigma = float(np.std(rets))
    threshold = max(0.02, 0.35 * sigma)

    favorable = float(np.mean(rets > threshold))
    unfavorable = float(np.mean(rets < -threshold))
    neutral = 1.0 - favorable - unfavorable

    return {
        "favoravel": round(favorable * 100, 1),
        "neutro": round(neutral * 100, 1),
        "desfavoravel": round(unfavorable * 100, 1),
        "horizonte_dias": HORIZON_DAYS,
        "threshold_pct": round(threshold * 100, 1),
        "retorno_esperado": round((np.mean(rets)) * 100, 1),
    }


def targets(
    tech: dict,
    final_prices: np.ndarray,
    current: float,
    fair_value_low: float,
    fair_value_high: float,
) -> dict:
    """Build the price-range targets with reaching probabilities."""
    p10, p25, p50, p75, p90 = np.percentile(final_prices, [10, 25, 50, 75, 90])

    atr = tech.get("atr") or current * 0.02
    nearest_res = tech.get("nearest_resistance") or {}
    res_price = nearest_res.get("price") or current + 1.5 * atr

    # First probable target: nearest resistance (a range around it).
    first_low = min(res_price, float(p50)) if res_price else float(p50)
    first_high = max(res_price, float(p50))
    first_prob = _reach_prob(final_prices, (first_low + first_high) / 2)

    # Optimistic target: upper statistical band or +3 ATR.
    opt_low = max(float(p75), res_price + atr)
    opt_high = max(float(p90), res_price + 3 * atr)
    opt_prob = _reach_prob(final_prices, (opt_low + opt_high) / 2)

    def _fmt(lo: float, hi: float) -> tuple[float, float]:
        return round(min(lo, hi), 2), round(max(lo, hi), 2)

    stat_low, stat_high = _fmt(p25, p75)
    fair_lo, fair_hi = _fmt(fair_value_low, fair_value_high)
    first_lo, first_hi = _fmt(first_low, first_high)
    opt_lo, opt_hi = _fmt(opt_low, opt_high)

    return {
        "estatistico": {
            "faixa": [stat_low, stat_high],
            "probabilidade": round((p75 - p25) / np.ptp(final_prices) * 100, 0) if np.ptp(final_prices) else 50,
            "label": "Faixa estatística (25–75%)",
        },
        "valor_justo": {
            "faixa": [fair_lo, fair_hi],
            "probabilidade": _reach_prob(final_prices, (fair_lo + fair_hi) / 2),
            "label": "Faixa de valor justo estimado",
        },
        "primeiro_objetivo": {
            "faixa": [first_lo, first_hi],
            "probabilidade": round(first_prob * 100, 0),
            "label": "Primeiro objetivo provável",
        },
        "objetivo_otimista": {
            "faixa": [opt_lo, opt_hi],
            "probabilidade": round(opt_prob * 100, 0),
            "label": "Objetivo otimista",
        },
        "horizonte_dias": HORIZON_DAYS,
    }


def _reach_prob(prices: np.ndarray, level: float) -> float:
    if level <= 0:
        return 1.0
    return float(np.mean(prices >= level))


def fair_value(fund: dict, price: float) -> tuple[float, float]:
    """Statistical fair-value band from fundamentals (EPS x fair P/E).

    Graham-style fair P/E = 8.5 + 2 * growth(%). Capped at 25, floored at 5.
    """
    eps = fund.get("eps")
    pe = fund.get("pe")
    growth = fund.get("earnings_growth")
    if not eps and pe and price:
        eps = price / pe
    if not eps or eps <= 0:
        base = price
    else:
        g = (growth if growth is not None else 0.0) * 100
        fair_pe = max(5.0, min(25.0, 8.5 + 2 * g))
        base = eps * fair_pe
    band = base * 0.12
    return base - band, base + band
