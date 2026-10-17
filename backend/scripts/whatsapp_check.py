"""Check the WhatsApp access token and phone number id work, without sending anything.

One read-only request: Meta returns the number's details if both are right.
Needs WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID in .env.

Run:  python -m scripts.whatsapp_check
"""

import sys

import httpx

from app.channels.whatsapp import GRAPH
from app.settings import get_settings


def main() -> int:
    s = get_settings()
    missing = [name for name, value in (("WHATSAPP_ACCESS_TOKEN", s.whatsapp_access_token),
                                        ("WHATSAPP_PHONE_NUMBER_ID", s.whatsapp_phone_number_id)) if not value]
    if missing:
        print("Missing in .env:", ", ".join(missing))
        return 1
    for name in ("WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET"):
        if not getattr(s, name.lower()):
            print(f"Note: {name} is empty, so the webhook will refuse Meta until it is set.")
    r = httpx.get(f"{GRAPH}/{s.whatsapp_phone_number_id}", timeout=20,
                  params={"fields": "display_phone_number,verified_name,quality_rating"},
                  headers={"Authorization": f"Bearer {s.whatsapp_access_token}"})
    body = r.json()
    if r.status_code != 200:
        print("failed -", body.get("error", {}).get("message", r.status_code))
        return 1
    print("ok - number:", body.get("display_phone_number"), "- name:", body.get("verified_name"),
          "- quality:", body.get("quality_rating"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except httpx.HTTPError as e:
        print("Could not reach Meta:", type(e).__name__)  # not the error itself: it may hold the request
        sys.exit(1)
