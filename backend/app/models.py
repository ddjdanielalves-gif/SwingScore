from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisSnapshot(Base):
    """A daily snapshot of the full analysis for one asset.

    Storing snapshots over time is what lets the platform compare the
    SwingScore between yesterday, last week and last month, and show how
    it evolved.
    """

    __tablename__ = "analysis_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    currency: Mapped[str] = mapped_column(String(8), default="BRL")
    market: Mapped[str] = mapped_column(String(12), default="B3")
    price: Mapped[float] = mapped_column(Float, nullable=False)
    change_pct: Mapped[float] = mapped_column(Float, default=0.0)
    swing_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    pillars: Mapped[dict] = mapped_column(JSON, default=dict)
    scenarios: Mapped[dict] = mapped_column(JSON, default=dict)
    targets: Mapped[dict] = mapped_column(JSON, default=dict)
    dividends: Mapped[dict] = mapped_column(JSON, default=dict)
    fundamentals: Mapped[dict] = mapped_column(JSON, default=dict)
    technical: Mapped[dict] = mapped_column(JSON, default=dict)
    macro: Mapped[dict] = mapped_column(JSON, default=dict)
    report: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
