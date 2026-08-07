from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import HistoryPoint, HistoryResponse
from ..services import analysis as analysis_service
from ..services import market_data

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/assets/{ticker}/history", response_model=HistoryResponse)
def get_history(
    ticker: str,
    limit: int = Query(90, ge=2, le=365),
    db: Session = Depends(get_db),
):
    resolved = market_data.resolve_ticker(ticker)
    snapshots = analysis_service.history(db, resolved, limit=limit)
    if not snapshots:
        raise HTTPException(status_code=404, detail=f"Sem histórico salvo para {resolved}")

    snapshots = sorted(snapshots, key=lambda s: s.created_at)
    points = [
        HistoryPoint(
            created_at=s.created_at.isoformat(),
            price=s.price,
            swing_score=s.swing_score,
            confidence=s.confidence,
            label=(
                "cenário favorável"
                if s.swing_score >= 65
                else "cenário neutro" if s.swing_score >= 45 else "cenário desfavorável"
            ),
        )
        for s in snapshots
    ]

    def delta(snap) -> float | None:
        if snap is None:
            return None
        return round(snap.swing_score - points[-1].swing_score, 1) * -1 if False else round(
            snap.swing_score - snapshots[-1].swing_score, 1
        )

    yesterday = snapshots[-2] if len(snapshots) >= 2 else None
    week = next((s for s in reversed(snapshots) if (snapshots[-1].created_at - s.created_at).days >= 7), None)
    month = next((s for s in reversed(snapshots) if (snapshots[-1].created_at - s.created_at).days >= 30), None)

    return HistoryResponse(
        ticker=resolved,
        points=points,
        delta_yesterday=round(snapshots[-1].swing_score - yesterday.swing_score, 1) if yesterday else None,
        delta_week=round(snapshots[-1].swing_score - week.swing_score, 1) if week else None,
        delta_month=round(snapshots[-1].swing_score - month.swing_score, 1) if month else None,
    )
