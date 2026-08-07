from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..core import indicators
from ..database import get_db
from ..schemas import AssetResponse, SearchHit, TickerTapeResponse
from ..services import analysis as analysis_service
from ..services import market_data

logger = logging.getLogger("swing.router")

router = APIRouter(prefix="/api", tags=["assets"])


@router.get("/assets/search", response_model=list[SearchHit])
def search(q: str = Query(..., min_length=1, max_length=32)):
    return market_data.search(q)


@router.get("/market/ticker", response_model=TickerTapeResponse)
def ticker_tape():
    return TickerTapeResponse(
        items=market_data.quotes(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        is_demo=settings.mock_mode,
    )


@router.get("/assets/{ticker}/analysis", response_model=AssetResponse)
async def get_analysis(
    ticker: str,
    refresh: bool = Query(False, description="Ignora o snapshot de hoje e recalcula"),
    db: Session = Depends(get_db),
):
    resolved = market_data.resolve_ticker(ticker)
    try:
        snapshot = await analysis_service.run(resolved, db, force_refresh=refresh)
    except Exception as exc:
        logger.exception("Analysis failed for %s", resolved)
        raise HTTPException(status_code=502, detail=f"Não foi possível analisar {resolved}: {exc}")

    df = market_data.candles(resolved)
    ma_series = {}
    for w in indicators.SMA_WINDOWS:
        series = indicators.sma(df["close"], w).dropna().tail(300)
        ma_series[f"sma{w}"] = [
            {"time": idx.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
            for idx, v in series.items()
        ]

    technical = dict(snapshot.technical)
    if technical.get("trend_lines"):
        index = list(df.index)
        for tl in technical["trend_lines"]:
            tl["start_time"] = index[tl["start_pos"]].strftime("%Y-%m-%d")
            tl["end_time"] = index[tl["end_pos"]].strftime("%Y-%m-%d")

    return AssetResponse(
        ticker=snapshot.ticker,
        name=snapshot.name,
        currency=snapshot.currency,
        market=snapshot.market,
        price=snapshot.price,
        change_pct=snapshot.change_pct,
        swing_score=snapshot.swing_score,
        confidence=snapshot.confidence,
        label=(
            "cenário favorável"
            if snapshot.swing_score >= 65
            else "cenário neutro" if snapshot.swing_score >= 45 else "cenário desfavorável"
        ),
        pillars=snapshot.pillars,
        scenarios=snapshot.scenarios,
        targets=snapshot.targets,
        dividends=snapshot.dividends,
        fundamentals=snapshot.fundamentals,
        technical=technical,
        macro=snapshot.macro,
        report=snapshot.report,
        candles=analysis_service.candle_payload(df.tail(520)),
        ma_series=ma_series,
        created_at=snapshot.created_at.isoformat(),
        is_demo=snapshot.is_demo,
    )
