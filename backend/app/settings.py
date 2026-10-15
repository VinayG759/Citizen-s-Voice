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

    # Which Gemma does which job (Gemini API names; OpenRouter adds "google/").
    llm_live_model: str = "gemma-4-26b-a4b-it"  # a caller is waiting: lightweight, thinking off
    llm_background_model: str = "gemma-4-31b-it"  # nobody waiting: bigger, thinking on
    # After this long, a live turn gives up on Google and asks OpenRouter instead.
    llm_primary_timeout_s: float = 4.0

    # Sarvam — speech to text and text to speech.
    sarvam_api_key: str = ""
    sarvam_stt_model: str = "saaras:v3"  # codemix mode keeps English words in English letters
    sarvam_tts_model: str = "bulbul:v3"

    # Keyed hash for caller phone numbers / web sessions. Set a long random value in production.
    caller_hash_key: str = "dev-only-not-secret"

    # Vobiz — the phone line.
    vobiz_auth_id: str = ""
    vobiz_auth_token: str = ""
    vobiz_phone_number: str = ""
    # The app's public address, e.g. https://citizens-voice-xxxx.ondigitalocean.app — used to tell
    # Vobiz where to stream call audio. Empty: taken from the request's Host header.
    public_base_url: str = ""

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
