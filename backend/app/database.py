from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

logger = logging.getLogger("swing.db")


class Base(DeclarativeBase):
    pass


def _build_engine():
    url = settings.database_url.strip()
    if url:
        logger.info("Using DATABASE_URL from config.")
        return create_engine(url, pool_pre_ping=True)

    postgres_url = "postgresql+psycopg2://postgres:postgres@localhost:5432/swingscore"
    try:
        engine = create_engine(
            postgres_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )
        with engine.connect():
            pass
        logger.info("Connected to PostgreSQL (localhost:5432/swingscore).")
        return engine
    except Exception as exc:  # pragma: no cover - depends on local infra
        logger.warning(
            "PostgreSQL unavailable (%s). Falling back to SQLite (swing.db). "
            "Set SWING_DATABASE_URL to use PostgreSQL.",
            exc.__class__.__name__,
        )
        return create_engine(
            "sqlite:///./swing.db",
            connect_args={"check_same_thread": False},
        )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
