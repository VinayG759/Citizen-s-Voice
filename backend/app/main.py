"""Citizen's Voice — one FastAPI service: the API, and the built dashboard as static files."""

import asyncio
import logging
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import events
from app.api import complaints, phone, try_it
from app.channels import telegram, whatsapp
from app.db.session import database_is_up
from app.phone.call import warm_clips
from app.settings import get_settings

WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

app = FastAPI(title="Citizen's Voice", version=get_settings().app_version)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# httpx logs every request URL at INFO; keep it quiet so no URL (or anything in one) reaches the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)


@app.on_event("startup")
async def connect_live_events() -> None:
    events.attach_loop(asyncio.get_running_loop())


@app.on_event("startup")
def prepare_phone_clips() -> None:
    # Speak the fixed phone lines once in the background, so the first caller isn't kept waiting.
    if get_settings().sarvam_api_key:
        threading.Thread(target=warm_clips, daemon=True).start()


@app.get("/health")
def health() -> JSONResponse:
    db_ok = database_is_up()
    body = {"status": "ok" if db_ok else "degraded", "db": "ok" if db_ok else "down",
            "version": get_settings().app_version}
    # 200 even when the database is down: the server itself is alive, and the
    # body says what is wrong. The hosting platform only needs "is it running".
    return JSONResponse(body)


def display_phone(e164: str) -> str:
    """+918065356055 -> '080 6535 6055' (how people in Bengaluru write it)."""
    digits = e164.removeprefix("+91")
    if len(digits) == 10 and digits.startswith("80"):
        return f"0{digits[:2]} {digits[2:6]} {digits[6:]}"
    return e164


@app.get("/api/config")
def public_config() -> dict:
    """Public, non-secret settings the dashboard needs."""
    number = get_settings().vobiz_phone_number
    return {"helpline_number": number, "helpline_display": display_phone(number) if number else ""}


app.include_router(try_it.router)
app.include_router(phone.router)
app.include_router(complaints.router)
app.include_router(telegram.router)
app.include_router(whatsapp.router)

# API routers are included ABOVE this line: the dashboard catch-all below must
# be registered last, or it would swallow API addresses.

# The dashboard (React, built by Vite). Only present after `npm run build`.
if WEB_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    def dashboard(path: str) -> FileResponse | JSONResponse:
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        # Real files (favicon etc.) are served as-is; every other address gets
        # index.html so the dashboard's own router can handle it.
        candidate = (WEB_DIST / path).resolve()
        if path and candidate.is_file() and WEB_DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
