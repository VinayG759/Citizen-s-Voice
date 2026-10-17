"""After an officer marks a complaint fixed: ask the citizen whether it really is.

The citizen's answer decides, not the officer's word: "yes" → the timeline records that the citizen
confirmed (and their contact is deleted, no longer needed); "no" → the complaint is reopened, which
raises its priority. Couldn't tell, no answer, or the call failed → noted, and tried once more later
at most. Only the contact that filed, only between 9 AM and 8 PM, and only if FEATURE_CALLBACK is on.

Phone: we ring them (app/phone/outbound.py) and Gemma (live: a person is on the line) reads their
answer. Chat channels (Telegram, …) plug in with register_chat(): their code sends the question and,
when the citizen replies, calls record_answer(n, classify(text, lang), text, channel=...).
"""

import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

from app import events
from app.contact import unseal
from app.db import repo
from app.llm import router
from app.llm.types import LLMError, Msg
from app.phone import outbound
from app.settings import get_settings

log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
CALL_HOURS = (9, 20)  # 9 AM to 8 PM, Bengaluru time
MAX_ATTEMPTS = 2  # the first ask, and one more if we couldn't tell
RETRY_AFTER_S = 15 * 60

CLASSIFY_PROMPT = """A city helpline asked a citizen whether their complaint is really fixed now.
Their answer is below (it may be Kannada, Hindi, English or a mix). Reply with JSON only:
{"answer": "yes" | "no" | "unclear"}
yes = they say it is fixed. no = they say it is not fixed, only partly fixed, or the problem came back.
unclear = anything else: a question, unrelated talk, or you cannot tell."""

# channel → send(address, tracking_number, complaint) -> bool (True: the question was sent)
_chat_senders: dict[str, Callable[[str, int, dict], bool]] = {}
_in_flight: set[int] = set()  # one call-back at a time per complaint
_lock = threading.Lock()


def register_chat(channel: str, send: Callable[[str, int, dict], bool]) -> None:
    """For chat channels: how to send the "is it really fixed?" question to a chat address."""
    _chat_senders[channel] = send


def within_calling_hours(now: datetime | None = None) -> bool:
    hour = (now or datetime.now(IST)).astimezone(IST).hour
    return CALL_HOURS[0] <= hour < CALL_HOURS[1]


def _publish(tracking_number: int, state: str, **data) -> None:
    """Dashboard: "Calling citizen…" and then the result. Never the number."""
    events.publish("callback", tracking_id=f"CV-{tracking_number}", state=state, **data)


def classify(text: str, language: str) -> str:
    """yes / no / unclear. Anything Gemma can't settle is "unclear": status never changes on a guess."""
    if not text.strip():
        return "unclear"
    try:
        reply = router.generate(system=CLASSIFY_PROMPT, messages=[Msg("user", text[:500])], tools=[],
                                mode="live", caller_language=language, max_tokens=40)
    except LLMError as e:
        log.warning("call-back answer not classified: %s", e)
        return "unclear"
    m = re.search(r"\{.*\}", reply.text, re.S)
    try:
        answer = json.loads(m.group(0)).get("answer") if m else None
    except (json.JSONDecodeError, AttributeError):
        answer = None
    return answer if answer in ("yes", "no", "unclear") else "unclear"


def ask_citizen(tracking_number: int, attempt: int = 1) -> None:
    """Called in the background when an officer marks a complaint fixed (and once more for a retry)."""
    if not get_settings().feature_callback:
        return
    sealed, complaint = repo.contact_for(tracking_number)
    if complaint is None or complaint["status"] != "fixed":  # reopened meanwhile: nothing to confirm
        return
    contact = None if complaint.get("sensitive") else unseal(sealed)
    if contact is None:
        repo.add_note(tracking_number, "call-back: no way to reach the citizen — they can confirm by calling the helpline")
        return _publish(tracking_number, "skipped", reason="no_contact")
    if not within_calling_hours():
        repo.add_note(tracking_number, "call-back: outside calling hours (9 AM–8 PM), not called")
        return _publish(tracking_number, "skipped", reason="outside_hours")
    with _lock:
        if tracking_number in _in_flight:
            return
        _in_flight.add(tracking_number)

    channel, address = contact
    _publish(tracking_number, "calling", channel=channel, attempt=attempt)
    if channel == "phone":
        sess = outbound.Session(
            tracking_number, complaint, outbound.call_language(complaint), classify,
            on_result=lambda answer, heard: record_answer(tracking_number, answer, heard, attempt, "phone"))
        sent = outbound.place_call(address, sess) is not None
    else:
        send = _chat_senders.get(channel)
        try:
            sent = bool(send and send(address, tracking_number, complaint))
        except Exception:
            log.exception("call-back message for CV-%s not sent", tracking_number)
            sent = False
        if sent:  # the reply comes later, through record_answer
            with _lock:
                _in_flight.discard(tracking_number)
    if not sent:
        record_answer(tracking_number, "failed", "", attempt, channel)


def record_answer(tracking_number: int, answer: str, heard: str = "", attempt: int = 1,
                  channel: str = "phone") -> None:
    """What the citizen said → the complaint's timeline (and its status, for a clear yes or no).
    answer: yes / no / unclear / no_answer / failed."""
    with _lock:
        _in_flight.discard(tracking_number)
    _, complaint = repo.contact_for(tracking_number)
    if complaint is None:
        return
    quote = f': "{heard[:200]}"' if heard else ""
    tid = f"CV-{tracking_number}"
    if answer in ("yes", "no") and complaint["status"] != "fixed":
        # An officer changed it while we were asking: keep their status, note what the citizen said.
        repo.add_note(tracking_number, f"call-back: citizen said {answer}{quote} (status was already {complaint['status']})")
        return _publish(tracking_number, "answered", answer=answer, channel=channel)
    if answer == "yes":
        repo.change_status(tracking_number, "fixed", "citizen", f"citizen confirmed it is fixed ({channel} call-back){quote}")
        _publish(tracking_number, "confirmed", channel=channel)
        return events.publish("complaint_updated", tracking_id=tid, status="fixed")
    if answer == "no":
        updated = repo.change_status(tracking_number, "reopened", "citizen",
                                     f"citizen says it is NOT fixed ({channel} call-back){quote}")
        _publish(tracking_number, "reopened", channel=channel)
        return events.publish("complaint_updated", tracking_id=tid, status="reopened",
                              urgency=(updated or {}).get("urgency"))

    state = answer if answer in ("unclear", "no_answer") else "failed"
    what = {"unclear": "couldn't tell the citizen's answer", "no_answer": "the citizen didn't answer",
            "failed": "the call-back could not be made"}[state]
    again = attempt < MAX_ATTEMPTS
    repo.add_note(tracking_number, f"call-back: {what}{quote}" + (" — will try once more later" if again else ""))
    _publish(tracking_number, state, channel=channel, attempt=attempt, retry=again)
    if again:
        _schedule_retry(tracking_number, attempt + 1)


def _schedule_retry(tracking_number: int, attempt: int) -> None:
    t = threading.Timer(RETRY_AFTER_S, ask_citizen, (tracking_number, attempt))
    t.daemon = True  # in memory: a restart forgets it (the citizen can still confirm by calling)
    t.start()
