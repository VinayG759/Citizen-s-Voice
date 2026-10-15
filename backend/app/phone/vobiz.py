"""Talking to Vobiz: the answer XML that starts audio streaming, and hanging up a call."""

import logging
from xml.sax.saxutils import escape

import httpx

from app.settings import get_settings

log = logging.getLogger(__name__)
API = "https://api.vobiz.ai/api/v1/Account/{auth_id}"


def stream_xml(ws_url: str, status_url: str) -> str:
    """Tell Vobiz to stream the call's audio both ways over a WebSocket (16 kHz, 16-bit)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f'  <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-l16;rate=16000" '
        f'statusCallbackUrl="{escape(status_url)}">{escape(ws_url)}</Stream>\n'
        "</Response>\n"
    )


def reject_xml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n  <Hangup reason="rejected"/>\n</Response>\n'


def hang_up(call_uuid: str) -> bool:
    s = get_settings()
    if not (s.vobiz_auth_id and s.vobiz_auth_token and call_uuid):
        return False
    try:
        r = httpx.delete(
            f"{API.format(auth_id=s.vobiz_auth_id)}/Call/{call_uuid}/",
            headers={"X-Auth-ID": s.vobiz_auth_id, "X-Auth-Token": s.vobiz_auth_token},
            timeout=10,
        )
    except httpx.HTTPError as e:
        log.warning("hangup failed: %s", e)
        return False
    if r.status_code not in (200, 204, 404):  # 404: the caller already hung up
        log.warning("hangup HTTP %s", r.status_code)
    return r.status_code in (200, 204)
