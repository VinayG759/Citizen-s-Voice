"""After an officer marks a complaint fixed: ask the citizen whether it really is.

For now this records the request in the timeline. The call-back (phone) and the message (chat) that
actually ask the citizen are priority 7 — until then the citizen confirms on the tracking page or by
calling the helpline ("what happened to my complaint?").
"""

import logging

from app import events

log = logging.getLogger(__name__)


def ask_citizen(tracking_number: int) -> None:
    log.info("follow-up requested for CV-%s", tracking_number)
    events.publish("followup_requested", tracking_id=f"CV-{tracking_number}")
