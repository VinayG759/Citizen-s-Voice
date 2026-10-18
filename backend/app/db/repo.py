"""Database reads and writes the features need. Plain functions; one short transaction each."""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import Call, ClerkEvent, Complaint, Photo, StatusChange, Turn
from app.db.session import get_engine

log = logging.getLogger(__name__)


@dataclass
class FiledComplaint:
    id: int  # the row this conversation created (for a linked report: the report, not the original)
    tracking_number: int  # the problem's tracking number (for a linked report: the original's)

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
    # For "what happened to my complaint?": the office, and what officers (and the citizen) did so far.
    department: str = "unrouted"
    is_emergency: bool = False
    updates: list[dict] = field(default_factory=list)  # timeline entries: status, by, note, at


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

    def file_complaint(self, forget_call: int | None = None, **fields) -> FiledComplaint:
        """forget_call: a sensitive report — the call it came from stops recording who called, too."""
        with Session(get_engine()) as s, s.begin():
            _forget_caller(s, forget_call)
            c = Complaint(**fields)
            s.add(c)
            s.flush()
            s.add(StatusChange(complaint_id=c.id, status="open", changed_by="system", note="filed"))
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

    def add_report(self, parent_tracking_number: int, forget_call: int | None = None,
                   **fields) -> tuple[FiledComplaint, int, bool]:
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
            _forget_caller(s, forget_call)
            report = Complaint(duplicate_of=parent.id, **fields)
            s.add(report)
            parent.report_count += 1
            raised = parent.report_count % 3 == 0 and parent.urgency < 5
            if raised:
                parent.urgency += 1
            s.flush()
            # The conversation links to the report itself, so the complaint page can show each
            # person's own words (tester's report, 17 Oct: a Telegram report showed the first caller's call).
            return FiledComplaint(report.id, parent.tracking_number), parent.report_count, raised

    def set_contact(self, complaint_id: int, contact_enc: str, last4: str) -> bool:
        """A browser citizen leaves a number for the call-back after filing. Never on a sensitive report."""
        with Session(get_engine()) as s, s.begin():
            c = s.get(Complaint, complaint_id)
            if c is None or c.sensitive:
                return False
            c.contact_enc, c.caller_last4 = contact_enc, last4
            return True

    def latest_for_caller(self, caller_hash: str) -> ComplaintStatus | None:
        """The caller's most recent complaint (the original, if theirs was a linked report)."""
        with Session(get_engine()) as s:
            c = s.scalar(select(Complaint).where(Complaint.caller_hash == caller_hash)
                         .order_by(desc(Complaint.created_at)).limit(1))
            if c is None:
                return None
            if c.duplicate_of:
                c = s.get(Complaint, c.duplicate_of)
            return _status(s, c)

    def complaint_status(self, tracking_number: int) -> ComplaintStatus | None:
        with Session(get_engine()) as s:
            c = s.scalar(select(Complaint).where(Complaint.tracking_number == tracking_number))
            if not c:
                return None
            return _status(s, c)


def _status(s: Session, c: Complaint) -> ComplaintStatus:
    return ComplaintStatus(c.tracking_id, c.status, c.category, c.summary_en, c.place_name, c.created_at,
                           c.department, c.is_emergency, timeline(s, c.id))


def _forget_caller(s: Session, call_id: int | None) -> None:
    if call_id is not None and (call := s.get(Call, call_id)) is not None:
        call.caller_hash = None


def _metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


SENSITIVE_SUMMARY = "A sensitive report — details are visible to officers only."


def public_complaint(c: Complaint, officer: bool = False) -> dict:
    """What the dashboard may show. Never a phone number, caller hash or contact — only the last 4 digits.
    Sensitive reports (harassment, violence, corruption) show their details to officers only."""
    hide = c.sensitive and not officer
    return {
        "tracking_id": c.tracking_id, "status": c.status, "category": c.category,
        "department": c.department, "sensitive": c.sensitive,
        "summary_en": SENSITIVE_SUMMARY if hide else c.summary_en,
        "summary_local": None if hide else c.summary_local, "language": c.language,
        "urgency": c.urgency, "is_emergency": c.is_emergency, "is_incomplete": c.is_incomplete,
        "place_name": c.place_name, "landmark": c.landmark, "lat": c.lat, "lon": c.lon,
        "since_when": c.since_when, "report_count": c.report_count, "channel": c.channel,
        "caller_last4": c.caller_last4, "created_at": c.created_at.isoformat(),
    }


def list_complaints(limit: int = 200, officer: bool = False, department: str | None = None) -> list[dict]:
    with Session(get_engine()) as s:
        q = select(Complaint).where(Complaint.duplicate_of.is_(None))
        if department:
            q = q.where(Complaint.department == department)
        rows = s.scalars(q.order_by(desc(Complaint.created_at)).limit(limit)).all()
        return [public_complaint(c, officer) for c in rows]


def complaint_detail(tracking_number: int, officer: bool = False, show_conversation: bool = True) -> dict | None:
    """The complaint, its timeline and photos, plus the conversation that produced it and every step
    Gemma took (conversation hidden for sensitive reports unless an officer is asking)."""
    with Session(get_engine()) as s:
        c = s.scalar(select(Complaint).where(Complaint.tracking_number == tracking_number))
        if c is None:
            return None
        out = public_complaint(c, officer)
        out["timeline"] = timeline(s, c.id)
        out["photos"] = photos_meta(s, c.id)
        # The first conversation is the original report's (before 17 Oct, linked reports' calls
        # pointed here too: the earliest is still the original).
        call = s.scalar(select(Call).where(Call.complaint_id == c.id).order_by(Call.id).limit(1))
        talk = officer or (show_conversation and not c.sensitive)
        out["transcript"], out["steps"] = [], []
        if call is not None and talk:
            out["transcript"] = _transcript(s, call.id)
            out["steps"] = [e.payload for e in s.scalars(
                select(ClerkEvent).where(ClerkEvent.call_id == call.id).order_by(ClerkEvent.id))]
        # Everyone else who reported the same problem, each with their own details and words.
        # (Sensitive reports are never merged, so nothing private appears here.)
        out["linked_reports"] = []
        for r in s.scalars(select(Complaint).where(Complaint.duplicate_of == c.id).order_by(Complaint.created_at)):
            r_call = s.scalar(select(Call).where(Call.complaint_id == r.id).order_by(Call.id).limit(1))
            out["linked_reports"].append({
                "channel": r.channel, "language": r.language, "caller_last4": r.caller_last4,
                "summary_en": r.summary_en, "summary_local": r.summary_local, "place_name": r.place_name,
                "landmark": r.landmark, "since_when": r.since_when, "created_at": r.created_at.isoformat(),
                "transcript": _transcript(s, r_call.id) if r_call is not None and talk else [],
            })
        return out


def _transcript(s: Session, call_id: int) -> list[dict]:
    return [{"speaker": t.speaker, "text": t.text_local, "language": t.language, "at": t.created_at.isoformat()}
            for t in s.scalars(select(Turn).where(Turn.call_id == call_id).order_by(Turn.id))]


# ---- after filing: what happens next ---------------------------------------------------------

def change_status(tracking_number: int, status: str, changed_by: str, note: str | None = None) -> dict | None:
    """Move a complaint along (open → in_progress → fixed → reopened …) and record it in the timeline.
    When a citizen confirms the fix, the encrypted contact is deleted: it is no longer needed."""
    with Session(get_engine()) as s, s.begin():
        c = s.scalar(select(Complaint).where(Complaint.tracking_number == tracking_number).with_for_update())
        if c is None:
            return None
        c.status = status
        if status == "reopened":
            c.urgency = min(5, c.urgency + 1)
        if status == "fixed" and changed_by == "citizen":
            c.contact_enc = None
        s.add(StatusChange(complaint_id=c.id, status=status, changed_by=changed_by, note=(note or "")[:500] or None))
        s.flush()
        return public_complaint(c, officer=True)


def reroute(tracking_number: int, department: str, note: str | None = None) -> dict | None:
    """An officer sends a complaint to a different office (the AI picked the wrong one)."""
    with Session(get_engine()) as s, s.begin():
        c = s.scalar(select(Complaint).where(Complaint.tracking_number == tracking_number).with_for_update())
        if c is None:
            return None
        old, c.department = c.department, department
        s.add(StatusChange(complaint_id=c.id, status=c.status, changed_by="officer",
                           note=f"re-routed from {old} to {department}" + (f": {note}" if note else "")))
        s.flush()
        return public_complaint(c, officer=True)


def add_note(tracking_number: int, note: str) -> bool:
    """A line in the timeline that keeps the current status (e.g. "call-back: no answer")."""
    with Session(get_engine()) as s, s.begin():
        c = s.scalar(select(Complaint).where(Complaint.tracking_number == tracking_number))
        if c is None:
            return False
        s.add(StatusChange(complaint_id=c.id, status=c.status, changed_by="system", note=note[:500]))
        return True


def reports_since(since: datetime) -> list[dict]:
    """Every report filed since `since` (linked reports too: each is one more person), sensitive
    reports left out. `tracking_id` is the ORIGINAL complaint's, so evidence points at real complaints."""
    with Session(get_engine()) as s:
        rows = s.scalars(select(Complaint).where(Complaint.created_at >= since, Complaint.sensitive.is_(False))).all()
        parents = {c.id: c.tracking_id for c in rows}
        missing = {c.duplicate_of for c in rows if c.duplicate_of and c.duplicate_of not in parents}
        if missing:
            parents.update({c.id: c.tracking_id for c in s.scalars(select(Complaint).where(Complaint.id.in_(missing)))})
        return [{"tracking_id": parents.get(c.duplicate_of, c.tracking_id) if c.duplicate_of else c.tracking_id,
                 "category": c.category, "lat": c.lat, "lon": c.lon, "place_name": c.place_name,
                 "created_at": c.created_at} for c in rows]


def add_photo(tracking_number: int, kind: str, mime: str, data: bytes, verdict: dict | None) -> int | None:
    with Session(get_engine()) as s, s.begin():
        c = s.scalar(select(Complaint).where(Complaint.tracking_number == tracking_number))
        if c is None:
            return None
        p = Photo(complaint_id=c.id, kind=kind, mime=mime, data=data, gemma_verdict=verdict)
        s.add(p)
        s.flush()
        return p.id


def get_photo(tracking_number: int, photo_id: int) -> tuple[str, bytes] | None:
    with Session(get_engine()) as s:
        p = s.scalar(select(Photo).join(Complaint, Photo.complaint_id == Complaint.id).where(
            Complaint.tracking_number == tracking_number, Photo.id == photo_id))
        return (p.mime, p.data) if p else None


def citizen_photo(tracking_number: int) -> tuple[str, bytes] | None:
    """The citizen's own photo of the problem, if they sent one — compared with the fix photo."""
    with Session(get_engine()) as s:
        p = s.scalar(select(Photo).join(Complaint, Photo.complaint_id == Complaint.id).where(
            Complaint.tracking_number == tracking_number, Photo.kind == "citizen").order_by(Photo.id).limit(1))
        return (p.mime, p.data) if p else None


def contact_for(tracking_number: int) -> tuple[str | None, dict | None]:
    """The encrypted contact (for the follow-up) and the complaint, for the follow-up call/message."""
    with Session(get_engine()) as s:
        c = s.scalar(select(Complaint).where(Complaint.tracking_number == tracking_number))
        return (c.contact_enc, public_complaint(c, officer=True)) if c else (None, None)


def reporter_contacts(tracking_number: int) -> list[tuple[str, bool, str | None]]:
    """Everyone who reported this problem and can be reached: (encrypted contact, is the original
    reporter, their language). Sensitive reports keep no contact, so they never appear here."""
    with Session(get_engine()) as s:
        c = s.scalar(select(Complaint).where(Complaint.tracking_number == tracking_number))
        if c is None:
            return []
        linked = s.scalars(select(Complaint).where(Complaint.duplicate_of == c.id).order_by(Complaint.id)).all()
        return [(r.contact_enc, r.id == c.id, r.language) for r in [c, *linked] if r.contact_enc]


def timeline(s: Session, complaint_id: int) -> list[dict]:
    return [{"status": t.status, "by": t.changed_by, "note": t.note, "at": t.created_at.isoformat()}
            for t in s.scalars(select(StatusChange).where(StatusChange.complaint_id == complaint_id)
                               .order_by(StatusChange.id))]


def photos_meta(s: Session, complaint_id: int) -> list[dict]:
    return [{"id": p.id, "kind": p.kind, "verdict": p.gemma_verdict, "at": p.created_at.isoformat()}
            for p in s.scalars(select(Photo).where(Photo.complaint_id == complaint_id).order_by(Photo.id))]


def all_for_scorecard() -> list[dict]:
    """Every original complaint with its timeline, for the per-office scorecard."""
    with Session(get_engine()) as s:
        out = []
        for c in s.scalars(select(Complaint).where(Complaint.duplicate_of.is_(None))):
            d = public_complaint(c)
            fixed_at = s.scalar(select(StatusChange.created_at).where(
                StatusChange.complaint_id == c.id, StatusChange.status == "fixed").order_by(StatusChange.id).limit(1))
            d["fixed_at"] = fixed_at.isoformat() if fixed_at else None
            out.append(d)
        return out


def save_turn(conv, caller_text: str, stt_ms: int, result) -> None:
    """One turn of a conversation, saved after the reply has gone (try-it page and chat apps)."""
    try:  # saving history must never cost the visitor their reply
        conv.repo.add_turn(conv.call_id, "caller", caller_text, result.language, stt_ms=stt_ms or None)
        conv.repo.add_turn(conv.call_id, "clerk", result.reply, result.language, llm_ms=result.llm_ms)
        conv.repo.add_events(conv.call_id, result.events)
        if result.complaint:
            conv.repo.end_call(conv.call_id, "filed", conv.state.filed.id)
    except Exception:
        log.exception("could not save turn")
