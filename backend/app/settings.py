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
    # Google's normal live reply takes ~2 s; slower than this is handed to OpenRouter (real call, 16 Oct:
    # waiting 4 s for a timeout cost the caller 4 s of silence).
    llm_primary_timeout_s: float = 2.5

    # Sarvam — speech to text and text to speech.
    sarvam_api_key: str = ""
    sarvam_stt_model: str = "saaras:v3"  # codemix mode keeps English words in English letters
    sarvam_tts_model: str = "bulbul:v3"
    # The clerk's voice: chosen by Vinay from ten samples (16 Oct) — the default sounded curt.
    sarvam_tts_speaker: str = "roopa"
    sarvam_tts_pace: float = 0.95  # a touch slower than normal: easier on a phone line
    sarvam_tts_temperature: float = 0.7  # a little more expressive than the default 0.6

    # Keyed hash for caller phone numbers / web sessions. Set a long random value in production.
    caller_hash_key: str = "dev-only-not-secret"
    # Encrypts how to reach a citizen for the follow-up call/message. Empty: no contact is stored.
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    contact_encryption_key: str = ""

    # Officers sign in with this passcode to change a complaint's status (single shared passcode:
    # enough for a pilot; stated in the README). Empty: officer actions are disabled.
    officer_passcode: str = ""

    # Switches, so a feature that misbehaves on stage can be turned off without a deploy of new code.
    feature_photo_check: bool = True
    feature_callback: bool = True

    # Telegram (bot token from @BotFather; a secret we choose for the webhook).
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # WhatsApp Cloud API (Meta app).
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    # Vobiz — the phone line.
    vobiz_auth_id: str = ""
    vobiz_auth_token: str = ""
    vobiz_phone_number: str = ""
    # The app's public address, e.g. https://citizens-voice-production.up.railway.app — used to tell
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
