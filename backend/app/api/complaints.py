"""Read-only views for the public dashboard, and its live update stream."""

import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app import events
from app.db import repo

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/complaints")
def complaints(limit: int = Query(200, ge=1, le=500)) -> list[dict]:
    return repo.list_complaints(limit)


@router.get("/complaints/{tracking_id}")
def complaint(tracking_id: str) -> dict:
    digits = re.sub(r"\D", "", tracking_id)
    found = repo.complaint_detail(int(digits)) if digits else None
    if found is None:
        raise HTTPException(404, "no such complaint")
    return found


@router.get("/events")
async def live_events() -> StreamingResponse:
    return StreamingResponse(
        events.stream(events.subscribe()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
