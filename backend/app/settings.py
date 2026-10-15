"""All configuration comes from environment variables (or the repo-root .env file).

Every name used here is listed, without values, in .env.example.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_version: str = "0.1.0"

    # Postgres (Supabase Session pooler). Plain "postgresql://" URLs are accepted.
    database_url: str = ""

    # Gemma 4 — Gemini API is the primary route, OpenRouter the fallback.
    gemini_api_key: str = ""
    openrouter_api_key: str = ""

    # Sarvam — speech to text and text to speech.
    sarvam_api_key: str = ""

    # Vobiz — the phone line.
    vobiz_auth_id: str = ""
    vobiz_auth_token: str = ""
    vobiz_phone_number: str = ""

    @property
    def sqlalchemy_url(self) -> str:
        """SQLAlchemy needs the driver named explicitly (psycopg 3)."""
        url = self.database_url.strip()
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
