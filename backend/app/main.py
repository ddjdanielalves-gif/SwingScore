from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine
from .routers import assets, history, macro

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("swing")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Database ready. Mock mode=%s", settings.mock_mode)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class _CacheControlMiddleware(BaseHTTPMiddleware):
    """Cache policy: index.html revalidates always; hashed assets are immutable."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        path = request.url.path
        if path.endswith("/index.html") or path in ("/", ""):
            response.headers["Cache-Control"] = "no-cache"
        elif path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app.add_middleware(_CacheControlMiddleware)

app.include_router(assets.router)
app.include_router(history.router)
app.include_router(macro.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


# Serve the built frontend (frontend/dist) when available so the whole app
# runs from a single service. API routes are registered first and take
# precedence over this catch-all mount.
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
    logger.info("Serving frontend from %s", _frontend_dist)
else:
    logger.warning("Frontend build not found at %s", _frontend_dist)
