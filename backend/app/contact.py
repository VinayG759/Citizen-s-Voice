"""Encrypting how to reach a citizen (phone number, chat id) for the "is it really fixed?" follow-up.

Stored only encrypted (Fernet: AES with an integrity check), used for the follow-up, deleted when the
complaint closes. Without CONTACT_ENCRYPTION_KEY nothing that can reach a citizen is stored at all.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.settings import get_settings


def _fernet() -> Fernet | None:
    key = get_settings().contact_encryption_key
    return Fernet(key.encode()) if key else None


def seal(channel: str, address: str) -> str | None:
    """'phone', '+9189…' → an encrypted token, or None if encryption isn't configured."""
    f = _fernet()
    return f.encrypt(f"{channel}:{address}".encode()).decode() if f and address else None


def unseal(token: str | None) -> tuple[str, str] | None:
    f = _fernet()
    if not (f and token):
        return None
    try:
        channel, _, address = f.decrypt(token.encode()).decode().partition(":")
        return channel, address
    except InvalidToken:
        return None
