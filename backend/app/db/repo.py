"""Database reads and writes the features need. Plain functions; one short transaction each."""

import math
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

    def nearby_open(self, lat: float, lon: float, category: str, radius_m: float = 150) -> list[dict]:
        """Open complaints of this category within `radius_m` (originals only, not linked reports)."""
        d = radius_m / 111_000 * 1.5  # a generous box first, exact distance below
        with Session(get_engine()) as s:
            rows = s.scalars(select(Complaint).where(
                Complaint.category == category, Complaint.duplicate_of.is_(None),
                Complaint.status.in_(("open", "in_progress", "reopened")),
                Complaint.lat.between(lat - d, lat + d), Complaint.lon.between(lon - d, lon + d),
            )).all()
            out = []
            for c in rows:
                m = _metres(lat, lon, c.lat, c.lon)
                if m <= radius_m:
                    out.append({"tracking_id": c.tracking_id, "tracking_number": c.tracking_number,
                                "summary": c.summary_en, "place": c.place_name, "report_count": c.report_count,
                                "metres_away": round(m), "filed_on": c.created_at.date().isoformat()})
            return sorted(out, key=lambda x: x["metres_away"])

    def add_report(self, parent_tracking_number: int, **fields) -> tuple[FiledComplaint, int, bool]:
        """Record another person's report of an existing problem.

        Stores the new report linked to the original, bumps the original's report count, and
        raises its urgency by one for every third report (max 5). Returns the ORIGINAL complaint
        (one problem, one tracking ID), the new report count, and whether urgency went up.
        """
        with Session(get_engine()) as s, s.begin():
            parent = s.scalar(select(Complaint).where(Complaint.tracking_number == parent_tracking_number)
                              .with_for_update())
            if parent is None:
                raise LookupError(parent_tracking_number)
            s.add(Complaint(duplicate_of=parent.id, **fields))
            parent.report_count += 1
            raised = parent.report_count % 3 == 0 and parent.urgency < 5
            if raised:
                parent.urgency += 1
            s.flush()
            return FiledComplaint(parent.id, parent.tracking_number), parent.report_count, raised

    def latest_for_caller(self, caller_hash: str) -> ComplaintStatus | None:
        """The caller's most recent complaint (the original, if theirs was a linked report)."""
        with Session(get_engine()) as s:
            c = s.scalar(select(Complaint).where(Complaint.caller_hash == caller_hash)
                         .order_by(desc(Complaint.created_at)).limit(1))
            if c is None:
                return None
            if c.duplicate_of:
                c = s.get(Complaint, c.duplicate_of)
            return ComplaintStatus(c.tracking_id, c.status, c.category, c.summary_en, c.place_name, c.created_at)

    def complaint_status(self, tracking_number: int) -> ComplaintStatus | None:
        with Session(get_engine()) as s:
            c = s.scalar(select(Complaint).where(Complaint.tracking_number == tracking_number))
            if not c:
                return None
            return ComplaintStatus(c.tracking_id, c.status, c.category, c.summary_en, c.place_name, c.created_at)


def _metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


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
        rows = s.scalars(select(Complaint).where(Complaint.duplicate_of.is_(None))
                         .order_by(desc(Complaint.created_at)).limit(limit)).all()
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
