"""Analysis orchestrator.

Puts every service together and persists a snapshot to the database so the
history endpoints can compare yesterday / last week / last month.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..core import indicators
from ..models import AnalysisSnapshot
from . import dividends as dividends_service
from . import fundamentals as fundamentals_service
from . import macro as macro_service
from . import market_data
from . import probabilities as probability_service
from . import report as report_service
from . import scoring as scoring_service

logger = logging.getLogger("swing.analysis")


async def run(ticker: str, db: Session, force_refresh: bool = False) -> AnalysisSnapshot:
    """Compute the full analysis for an asset and persist a snapshot."""
    if not force_refresh:
        today = _today_snapshot(db, ticker)
        if today is not None:
            return today

    # Fetch all external data concurrently (yfinance calls are blocking).
    meta, df, info, fund_history = await asyncio.gather(
        asyncio.to_thread(market_data.asset_meta, ticker),
        asyncio.to_thread(market_data.candles, ticker),
        asyncio.to_thread(market_data.asset_info, ticker),
        asyncio.to_thread(fundamentals_service.history, ticker),
    )

    fund_raw = fundamentals_service.collect(info, meta.get("currency", "USD"))
    fund_raw["history"] = fund_history
    fund = fundamentals_service.score(fund_raw)
    tech = indicators.compute(df)
    macro_data = await asyncio.to_thread(macro_service.collect)
    macro_scored = macro_service.score(macro_data, market=meta.get("market", "B3"))
    macro_result = {**macro_data, "score": macro_scored["score"], "label": macro_scored["label"], "notes": macro_scored["notes"]}

    scoring = scoring_service.compute(fund, tech, macro_data, market=meta.get("market", "B3"))

    price = float(df["close"].iloc[-1])
    if price != price or price <= 0:  # NaN / zero guard
        price = float(df["close"].dropna().iloc[-1])
    if price != price or price <= 0:
        price = 1.0
    final_prices = probability_service.simulate(df, scoring["swing_score"])
    scenarios = probability_service.scenario_probabilities(scoring["swing_score"], final_prices, price)
    fair_lo, fair_hi = probability_service.fair_value(fund_raw, price)
    targets = probability_service.targets(tech, final_prices, price, fair_lo, fair_hi)

    div_series = await asyncio.to_thread(market_data.dividends_history, ticker)
    dividends = dividends_service.compute(div_series, fund_raw, price)

    report_text = await report_service.generate(
        scoring, tech, fund, macro_result, scenarios, targets, meta
    )

    used_mock = settings.mock_mode or bool(df.attrs.get("is_mock", False))

    snapshot = AnalysisSnapshot(
        ticker=meta.get("ticker") or ticker,
        name=meta.get("name") or ticker,
        currency=meta.get("currency") or "USD",
        market=meta.get("market") or "Internacional",
        price=price,
        change_pct=round((price / (meta.get("previous_close") or price) - 1) * 100, 2),
        swing_score=scoring["swing_score"],
        confidence=scoring["confidence"],
        pillars=scoring["pillars"],
        scenarios=scenarios,
        targets=targets,
        dividends=dividends,
        fundamentals=fund,
        technical=_public_technical(tech),
        macro=macro_result,
        report=report_text,
        is_demo=used_mock,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    logger.info("Analysis persisted for %s (score %.1f)", ticker, snapshot.swing_score)
    return snapshot


def _public_technical(tech: dict) -> dict:
    return {
        k: tech[k]
        for k in (
            "price", "rsi", "rsi_prev", "rsi_state", "rsi_divergence", "atr",
            "atr_pct", "ma_status", "ma_values", "ma_slopes", "ma_distance",
            "levels", "nearest_support", "nearest_resistance",
            "trend_lines", "trend_support", "trend_resistance",
        )
    }


def _today_snapshot(db: Session, ticker: str) -> AnalysisSnapshot | None:
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc) - timedelta(hours=20)
    stmt = (
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.ticker == ticker, AnalysisSnapshot.created_at >= since)
        .order_by(AnalysisSnapshot.created_at.desc())
    )
    return db.execute(stmt).scalars().first()


def history(db: Session, ticker: str, limit: int = 90) -> list[AnalysisSnapshot]:
    stmt = (
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.ticker == ticker)
        .order_by(AnalysisSnapshot.created_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


def candle_payload(df) -> list[dict]:
    rows = []
    for idx, row in df.iterrows():
        rows.append(
            {
                "time": idx.strftime("%Y-%m-%d"),
                "open": round(float(row["open"]), 4),
                "high": round(float(row["high"]), 4),
                "low": round(float(row["low"]), 4),
                "close": round(float(row["close"]), 4),
                "volume": int(row["volume"]),
            }
        )
    return rows
