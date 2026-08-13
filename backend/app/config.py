from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="SWING_",
    )

    app_name: str = "SwingScore API"
    version: str = "0.1.0"

    # DATABASE_URL is optional. When empty the app tries PostgreSQL on
    # localhost and falls back to a local SQLite file so the platform can
    # run even without a database server installed.
    database_url: str = ""

    # Local OpenAI-compatible endpoint (9router proxy). Used only for the
    # natural-language report. Falls back to a template when unreachable or
    # when llm_enabled is false.
    llm_enabled: bool = True
    llm_base_url: str = "http://localhost:20128/v1"
    llm_api_key: str = "sk_9router"
    llm_model: str = "nvidia/deepseek-ai/deepseek-v4-pro"
    llm_timeout: float = 30.0

    # In-memory cache TTL for raw market data (seconds).
    cache_ttl_seconds: int = 3600

    # When true, all data comes from a synthetic local provider so the
    # platform works fully offline. Every response is flagged as demo data.
    mock_mode: bool = False

    # brapi.dev token (https://brapi.dev). Used as a real-data fallback for
    # B3 quotes/fundamentals when Yahoo Finance is unavailable or rate-limited.
    brapi_token: str = ""

    # CORS origins for the web frontend.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
settings.mock_mode = settings.mock_mode or os.environ.get("SWING_MOCK", "") == "1"
