"""Database reads and writes the features need. Plain functions; one short transaction each."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import Call, ClerkEvent, Complaint, Turn
from app.db.session import get_engine


@dataclass
class FiledComplaint:
    id: int
    tracking_number: int

    @property
    def tracking_id(self) -> str:
        return f"CV-{self.tracking_number}"


@dataclass
class ComplaintStatus:
    tracking_id: str
    status: str
    category: str
    summary_en: str
    place_name: str | None
    created_at: datetime


class Repo:
    """The real database. Tests use a fake with the same methods."""

    def start_call(self, channel: str, caller_hash: str | None = None, vobiz_call_id: str | None = None) -> int:
        with Session(get_engine()) as s, s.begin():
            call = Call(channel=channel, caller_hash=caller_hash, vobiz_call_id=vobiz_call_id)
            s.add(call)
            s.flush()
            return call.id

    def end_call(self, call_id: int, outcome: str | None, complaint_id: int | None = None) -> None:
        with Session(get_engine()) as s, s.begin():
            call = s.get(Call, call_id)
            if call:
                call.ended_at = datetime.now().astimezone()
                call.outcome = outcome
                call.complaint_id = complaint_id or call.complaint_id

    def add_turn(self, call_id: int, speaker: str, text_local: str | None, language: str | None,
                 stt_ms: int | None = None, llm_ms: int | None = None, tts_ms: int | None = None) -> None:
        with Session(get_engine()) as s, s.begin():
            s.add(Turn(call_id=call_id, speaker=speaker, text_local=text_local, language=language,
                       stt_ms=stt_ms, llm_ms=llm_ms, tts_ms=tts_ms))

    def add_events(self, call_id: int, events: list[dict]) -> None:
        if not events:
            return
        with Session(get_engine()) as s, s.begin():
            s.add_all(ClerkEvent(call_id=call_id, kind=e["kind"], payload=e) for e in events)

    def file_complaint(self, **fields) -> FiledComplaint:
        with Session(get_engine()) as s, s.begin():
            c = Complaint(**fields)
            s.add(c)
            s.flush()
            s.refresh(c)
            return FiledComplaint(c.id, c.tracking_number)

    def complaint_status(self, tracking_number: int) -> ComplaintStatus | None:
        with Session(get_engine()) as s:
            c = s.scalar(select(Complaint).where(Complaint.tracking_number == tracking_number))
            if not c:
                return None
            return ComplaintStatus(c.tracking_id, c.status, c.category, c.summary_en, c.place_name, c.created_at)


def public_complaint(c: Complaint) -> dict:
    """What the public dashboard may show. Never a phone number or caller hash — only the last 4 digits."""
    return {
        "tracking_id": c.tracking_id, "status": c.status, "category": c.category,
        "summary_en": c.summary_en, "summary_local": c.summary_local, "language": c.language,
        "urgency": c.urgency, "is_emergency": c.is_emergency, "is_incomplete": c.is_incomplete,
        "place_name": c.place_name, "landmark": c.landmark, "lat": c.lat, "lon": c.lon,
        "since_when": c.since_when, "report_count": c.report_count, "channel": c.channel,
        "caller_last4": c.caller_last4, "created_at": c.created_at.isoformat(),
    }


def list_complaints(limit: int = 200) -> list[dict]:
    with Session(get_engine()) as s:
        rows = s.scalars(select(Complaint).order_by(desc(Complaint.created_at)).limit(limit)).all()
        return [public_complaint(c) for c in rows]


def complaint_detail(tracking_number: int) -> dict | None:
    """The complaint, plus the conversation that produced it and every step Gemma took."""
    with Session(get_engine()) as s:
        c = s.scalar(select(Complaint).where(Complaint.tracking_number == tracking_number))
        if c is None:
            return None
        out = public_complaint(c)
        call = s.scalar(select(Call).where(Call.complaint_id == c.id))
        out["transcript"], out["steps"] = [], []
        if call is not None:
            out["transcript"] = [
                {"speaker": t.speaker, "text": t.text_local, "language": t.language, "at": t.created_at.isoformat()}
                for t in s.scalars(select(Turn).where(Turn.call_id == call.id).order_by(Turn.id))
            ]
            out["steps"] = [e.payload for e in s.scalars(
                select(ClerkEvent).where(ClerkEvent.call_id == call.id).order_by(ClerkEvent.id))]
        return out
