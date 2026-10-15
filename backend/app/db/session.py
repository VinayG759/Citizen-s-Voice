"""Database connection: one engine for the whole app, created on first use."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from app.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,  # drop connections the pooler has closed
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 5},
    )


def database_is_up() -> bool:
    """True if a trivial query succeeds. Never raises — /health must always answer."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("select 1"))
        return True
    except Exception:
        return False
