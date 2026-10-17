"""The dashboard's API: complaints, what happens after filing, the office scorecard, live updates.

Anyone can read (sensitive reports show no details publicly). Changing anything — status,
office, the "fixed" photo — needs an officer sign-in (app/officer.py).
"""

import csv
import io
import re
import statistics
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app import brief, emerging, events, officer, vision
from app.db import repo
from app.db.models import DEPARTMENTS
from app.settings import get_settings

router = APIRouter(prefix="/api", tags=["dashboard"])

MAX_PHOTO_BYTES = 5_000_000
OFFICER_STATUSES = ("in_progress", "fixed", "reopened")


def _number(tracking_id: str) -> int:
    digits = re.sub(r"\D", "", tracking_id)
    if not digits:
        raise HTTPException(404, "no such complaint")
    return int(digits)


def _with_follow_up(c: dict) -> dict:
    return {**c, **officer.follow_up(c)}


# ---- reading ---------------------------------------------------------------------------------

@router.get("/complaints")
def complaints(
    limit: int = Query(200, ge=1, le=500),
    department: str | None = Query(None),
    sort: str = Query("newest", pattern="^(newest|priority)$"),
    authorization: str | None = Header(None),
) -> list[dict]:
    if department and department not in DEPARTMENTS:
        raise HTTPException(422, "unknown office")
    items = [_with_follow_up(c) for c in repo.list_complaints(limit, officer.is_officer(authorization), department)]
    if sort == "priority":
        items.sort(key=lambda c: c["priority"], reverse=True)
    return items


@router.get("/complaints/{tracking_id}")
def complaint(tracking_id: str, authorization: str | None = Header(None)) -> dict:
    found = repo.complaint_detail(_number(tracking_id), officer.is_officer(authorization))
    if found is None:
        raise HTTPException(404, "no such complaint")
    return _with_follow_up(found)


@router.get("/complaints/{tracking_id}/photos/{photo_id}")
def photo(tracking_id: str, photo_id: int) -> Response:
    found = repo.get_photo(_number(tracking_id), photo_id)
    if found is None:
        raise HTTPException(404, "no such photo")
    mime, data = found
    return Response(data, media_type=mime, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/scorecard")
def scorecard() -> list[dict]:
    """Per office: filed, open, fixed, overdue, and the median days from filing to fixed."""
    by_office: dict[str, list[dict]] = {}
    for c in repo.all_for_scorecard():
        by_office.setdefault(c["department"], []).append(_with_follow_up(c))
    rows = []
    for dept, items in by_office.items():
        days = [(datetime.fromisoformat(c["fixed_at"]) - datetime.fromisoformat(c["created_at"])).total_seconds() / 86400
                for c in items if c.get("fixed_at")]
        rows.append({
            "department": dept, "office": officer.OFFICE_NAMES.get(dept, dept), "filed": len(items),
            "open": sum(c["status"] != "fixed" for c in items), "fixed": sum(c["status"] == "fixed" for c in items),
            "overdue": sum(c["overdue"] for c in items), "deadline_days": officer.DEADLINE_DAYS.get(dept, 7),
            "median_days_to_fix": round(statistics.median(days), 1) if days else None,
        })
    return sorted(rows, key=lambda r: (-r["overdue"], -r["open"]))


@router.get("/emerging")
def emerging_issues(headlines: bool = Query(True)) -> dict:
    """Spikes and clusters counted from recent reports, each with its evidence (app/emerging.py)."""
    return emerging.emerging(repo.reports_since, use_gemma=headlines)


@router.get("/brief", dependencies=[Depends(officer.require_officer)])
def morning_brief() -> dict:
    """Today's brief for officers: numbers by code, sentences by Gemma, every number checked (app/brief.py)."""
    return brief.morning_brief(repo.all_for_scorecard())


# ---- officer actions -------------------------------------------------------------------------

class Login(BaseModel):
    passcode: str


@router.post("/officer/login")
def officer_login(body: Login) -> dict:
    token = officer.issue_token(body.passcode)
    if token is None:
        raise HTTPException(401, "wrong passcode")
    return {"token": token, "hours": officer.TOKEN_HOURS}


class StatusUpdate(BaseModel):
    status: str
    note: str | None = None


@router.post("/complaints/{tracking_id}/status", dependencies=[Depends(officer.require_officer)])
def set_status(tracking_id: str, body: StatusUpdate) -> dict:
    if body.status not in OFFICER_STATUSES or body.status == "fixed":
        # "Fixed" needs a photo: POST /complaints/{id}/fixed
        raise HTTPException(422, "status must be in_progress or reopened (use /fixed with a photo)")
    updated = repo.change_status(_number(tracking_id), body.status, "officer", body.note)
    if updated is None:
        raise HTTPException(404, "no such complaint")
    events.publish("complaint_updated", tracking_id=updated["tracking_id"], status=updated["status"])
    return _with_follow_up(updated)


class Route(BaseModel):
    department: str
    note: str | None = None


@router.post("/complaints/{tracking_id}/route", dependencies=[Depends(officer.require_officer)])
def route(tracking_id: str, body: Route) -> dict:
    if body.department not in DEPARTMENTS:
        raise HTTPException(422, "unknown office")
    updated = repo.reroute(_number(tracking_id), body.department, body.note)
    if updated is None:
        raise HTTPException(404, "no such complaint")
    events.publish("complaint_updated", tracking_id=updated["tracking_id"], department=updated["department"])
    return _with_follow_up(updated)


@router.post("/complaints/{tracking_id}/fixed", dependencies=[Depends(officer.require_officer)])
def mark_fixed(tracking_id: str, background: BackgroundTasks, photo: UploadFile = File(...),
               note: str | None = Form(None)) -> dict:
    """An officer marks it fixed WITH a photo. Gemma checks the photo against the complaint (advice,
    shown to everyone); the citizen is then asked to confirm (see app/followup.py)."""
    number = _number(tracking_id)
    data = photo.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "photo too large (5 MB max)")
    mime = photo.content_type or "image/jpeg"
    if not mime.startswith("image/"):
        raise HTTPException(422, "that is not a photo")
    _, current = repo.contact_for(number)
    if current is None:
        raise HTTPException(404, "no such complaint")
    verdict = None
    if get_settings().feature_photo_check:
        verdict = vision.check_fix((mime, data), current, repo.citizen_photo(number))
    repo.add_photo(number, "fix", mime, data, verdict)
    reason = f"Gemma: {verdict['looks_fixed']} — {verdict.get('reason', '')}" if verdict else None
    updated = repo.change_status(number, "fixed", "officer", " · ".join(x for x in (note, reason) if x))
    events.publish("complaint_updated", tracking_id=updated["tracking_id"], status="fixed",
                   gemma=(verdict or {}).get("looks_fixed"))
    if get_settings().feature_callback:
        from app.followup import ask_citizen  # imported here: needs the phone/chat channels
        background.add_task(ask_citizen, number)
    return {**_with_follow_up(updated), "gemma_verdict": verdict}


@router.get("/export.csv", dependencies=[Depends(officer.require_officer)])
def export_csv() -> Response:
    """Every complaint as a spreadsheet, for forwarding to official systems (BBMP Sahaaya, CPGRAMS)."""
    rows = [_with_follow_up(c) for c in repo.list_complaints(500, officer=True)]
    cols = ["tracking_id", "status", "category", "office", "summary_en", "place_name", "landmark", "lat", "lon",
            "since_when", "urgency", "is_emergency", "report_count", "channel", "created_at", "overdue", "priority_why"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        # A cell starting with = + - @ would run as a formula in a spreadsheet: neutralise it.
        w.writerow({k: ("'" + v if isinstance(v, str) and v[:1] in "=+-@" else v) for k, v in r.items()})
    return Response("﻿" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=citizens-voice-complaints.csv"})


# ---- live updates ------------------------------------------------------------------------------

@router.get("/events")
async def live_events() -> StreamingResponse:
    return StreamingResponse(
        events.stream(events.subscribe()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
