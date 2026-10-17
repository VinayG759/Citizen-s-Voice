"""Tell Telegram where to send the bot's messages: PUBLIC_BASE_URL + /webhooks/telegram.

Needs TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET and PUBLIC_BASE_URL in .env. Telegram then sends
every message with the secret in a header, and the server refuses anything without it.
Run again whenever PUBLIC_BASE_URL changes (a new tunnel, a new deploy address).

Run:  python -m scripts.telegram_webhook          (register)
      python -m scripts.telegram_webhook --check  (show what Telegram has now)
"""

import sys

import httpx

from app.settings import get_settings

API = "https://api.telegram.org"


def main() -> int:
    s = get_settings()
    missing = [name for name, value in (("TELEGRAM_BOT_TOKEN", s.telegram_bot_token),
                                        ("TELEGRAM_WEBHOOK_SECRET", s.telegram_webhook_secret),
                                        ("PUBLIC_BASE_URL", s.public_base_url)) if not value]
    if missing:
        print("Missing in .env:", ", ".join(missing))
        return 1
    base = f"{API}/bot{s.telegram_bot_token}"  # never printed: the token is in it

    if "--check" in sys.argv:
        info = httpx.get(f"{base}/getWebhookInfo", timeout=20).json().get("result", {})
        print("url:", info.get("url") or "(none)")
        print("waiting messages:", info.get("pending_update_count"))
        print("last error:", info.get("last_error_message") or "(none)")
        return 0

    url = s.public_base_url.rstrip("/") + "/webhooks/telegram"
    if not url.startswith("https://"):
        print("Telegram only sends to https addresses:", url)
        return 1
    r = httpx.post(f"{base}/setWebhook", timeout=20, json={
        "url": url,
        "secret_token": s.telegram_webhook_secret,
        "allowed_updates": ["message"],  # new messages only: no edits, no group joins
    }).json()
    print("ok" if r.get("ok") else "failed", "-", r.get("description", ""), "-", url)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except httpx.HTTPError as e:
        print("Could not reach Telegram:", type(e).__name__)  # not the error itself: it may hold the token
        sys.exit(1)
