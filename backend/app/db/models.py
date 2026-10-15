"""The tables. These are the contracts between features — change them only via a migration.

Phase 6 adds `fix_reports`; everything else the plan needs exists from Phase 0.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Sequence,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Tracking IDs are "CV-" + this number, starting at 1001 (easy to say on a phone).
tracking_seq = Sequence("complaint_tracking_seq", start=1001)

STATUSES = ("open", "in_progress", "fixed", "reopened")
CATEGORIES = ("road", "water", "electricity", "garbage", "drainage", "streetlight", "other")
CHANNELS = ("phone", "web", "whatsapp")
CALL_OUTCOMES = ("filed", "status_check", "abandoned", "emergency")
SPEAKERS = ("caller", "clerk")
EVENT_KINDS = ("thought", "tool_call", "tool_result", "decision")


def _one_of(table: str, column: str, values: tuple[str, ...]) -> CheckConstraint:
    allowed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} in ({allowed})", name=f"ck_{table}_{column}")


class Base(DeclarativeBase):
    pass


class Complaint(Base):
    __tablename__ = "complaints"
    __table_args__ = (
        _one_of("complaints", "status", STATUSES),
        _one_of("complaints", "category", CATEGORIES),
        _one_of("complaints", "channel", CHANNELS),
        CheckConstraint("urgency between 1 and 5", name="ck_complaints_urgency"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tracking_number: Mapped[int] = mapped_column(
        Integer, tracking_seq, server_default=tracking_seq.next_value(), unique=True
    )
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")
    category: Mapped[str] = mapped_column(String(16))
    summary_en: Mapped[str] = mapped_column(Text)
    summary_local: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(8))  # e.g. kn-IN, hi-IN, en-IN
    urgency: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_incomplete: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Location — coordinates always come from place data, never from the model.
    place_name: Mapped[str | None] = mapped_column(Text)
    landmark: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    place_source: Mapped[str | None] = mapped_column(String(16))  # gazetteer | nominatim
    since_when: Mapped[str | None] = mapped_column(Text)

    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("complaints.id"))
    report_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # Privacy: a keyed hash plus the last 4 digits for display. Never the full number.
    caller_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    caller_last4: Mapped[str | None] = mapped_column(String(4))
    channel: Mapped[str] = mapped_column(String(16), default="phone", server_default="phone")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def tracking_id(self) -> str:
        return f"CV-{self.tracking_number}"


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (
        CheckConstraint(
            "outcome is null or outcome in ('" + "', '".join(CALL_OUTCOMES) + "')",
            name="ck_calls_outcome",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vobiz_call_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    channel: Mapped[str] = mapped_column(String(16), default="phone", server_default="phone")
    caller_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(16))
    complaint_id: Mapped[int | None] = mapped_column(ForeignKey("complaints.id"))


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (_one_of("turns", "speaker", SPEAKERS),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    speaker: Mapped[str] = mapped_column(String(8))
    text_local: Mapped[str | None] = mapped_column(Text)
    text_en: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(8))
    stt_ms: Mapped[int | None] = mapped_column(Integer)
    llm_ms: Mapped[int | None] = mapped_column(Integer)
    tts_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClerkEvent(Base):
    """Every thought, tool call and decision Gemma makes — the "Gemma's mind" panel and the audit trail."""

    __tablename__ = "clerk_events"
    __table_args__ = (_one_of("clerk_events", "kind", EVENT_KINDS),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
