"""Dividends.

Historical dividend yield (last 5 years) plus a statistical estimate of
future dividends based on profit, payout and history.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute(div_series: pd.Series, info: dict, price: float) -> dict:
    if div_series is None or len(div_series) == 0:
        return {
            "available": False,
            "message": "sem histórico de dividendos no provedor de dados",
        }

    series = div_series.copy()
    series.index = pd.to_datetime(series.index)
    if series.index.tz is not None:
        series.index = series.index.tz_localize(None)
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=6)
    series = series[series.index >= cutoff]
    if len(series) == 0:
        return {"available": False, "message": "sem dividendos recentes registrados"}

    yearly = series.resample("YE").sum()
    yearly = yearly[yearly > 0]
    if len(yearly) == 0:
        return {"available": False, "message": "sem dividendos recentes registrados"}

    years = list(yearly.index.year)
    amounts = yearly.to_numpy(dtype=float)
    # DY relative to price today (as the user would experience it).
    yields_per_year = amounts / price

    last_yield = float(yields_per_year[-1])
    avg_yield = float(np.mean(yields_per_year))
    payout_ratio = info.get("payout")
    eps = info.get("eps")
    net_income = info.get("net_income")
    historical_payouts = amounts / eps if eps and eps > 0 else None

    # Statistical estimate: avg payout applied to current earnings power.
    expected_div = None
    if eps and eps > 0:
        if payout_ratio is None and historical_payouts is not None and len(historical_payouts):
            payout_ratio = float(np.mean(historical_payouts[pd.notna(historical_payouts)]))
        if payout_ratio is None and net_income:
            payout_ratio = 0.35
        if payout_ratio:
            payout_ratio = min(max(payout_ratio, 0.0), 1.2)
            expected_div = eps * payout_ratio

    if expected_div and expected_div > 0:
        est_yield = expected_div / price
        low, high = est_yield * 0.85, est_yield * 1.15
    else:
        low, high = avg_yield * 0.7, avg_yield * 1.3

    return {
        "available": True,
        "last_12m_yield": round(last_yield * 100, 2),
        "avg_5y_yield": round(avg_yield * 100, 2),
        "years": [int(y) for y in years],
        "yields": [round(float(v) * 100, 2) for v in yields_per_year],
        "payout": round(payout_ratio * 100, 1) if payout_ratio is not None else None,
        "estimate_range_yield": [round(low * 100, 2), round(high * 100, 2)],
        "estimate_range_value": [round(low * price, 2), round(high * price, 2)],
    }
