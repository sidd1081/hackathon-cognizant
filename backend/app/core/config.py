"""Application configuration via Pydantic Settings.

Settings are loaded from environment variables and an optional `.env` file.
Every field has a default so the app can start without any configuration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Values resolve in this order: environment variable -> `.env` file -> default.
    Field names are case-insensitive (e.g. `APP_NAME` maps to `app_name`).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    app_name: str = "AI-Powered Incident RCA Assistant"
    api_prefix: str = "/api"
    debug: bool = False
    log_level: str = "INFO"

    # Browser origins allowed to call the API directly (cross-origin). Defaults
    # to the Vite dev/preview ports. In production set CORS_ORIGINS to your
    # frontend URL(s) — comma-separated, e.g.
    #   CORS_ORIGINS=https://my-app.vercel.app,https://www.example.com
    # or "*" to allow any origin (fine here: auth is via bearer token, not
    # cookies, so credentials are not sent cross-site).
    # NoDecode: don't let pydantic-settings JSON-decode this from the env; the
    # validator below parses a comma-separated string instead.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string for CORS_ORIGINS (env-friendly)."""
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    # ---- LLM: Groq ----
    groq_api_key: str | None = None
    # Override via GROQ_MODEL. Must be a chat model your key can access
    # (e.g. openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.6-27b).
    groq_model: str = "openai/gpt-oss-20b"
    llm_temperature: float = 0.0
    # Keep retries low — on the free tier each 429 retry waits the full
    # Retry-After window (up to 60 s), so 6 retries = potential 6-minute hang.
    groq_max_retries: int = 2

    # ---- Embeddings (reserved for a later RAG stage; not used yet) ----
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ---- Auth (JWT) ----
    # Secret used to sign JWTs. MUST be overridden in production via JWT_SECRET.
    # (>=32 bytes to satisfy HS256 key-length guidance even in dev.)
    jwt_secret: str = "dev-insecure-change-me-set-JWT_SECRET-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720  # 12 hours

    # ---- Database (user auth store) ----
    # SQLAlchemy URL for the user store. Leave unset to use a local SQLite file
    # (data/auth.db) for dev/demo. In production set DATABASE_URL to Postgres,
    # e.g. postgresql://user:pass@host:5432/dbname (any postgres:// or
    # postgresql:// URL is normalized to the psycopg3 driver automatically).
    database_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return a cached, singleton `Settings` instance."""
    return Settings()


# Convenience singleton for direct imports: `from app.core.config import settings`.
settings: Settings = get_settings()
