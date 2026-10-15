"""The actions Gemma may take. Gemma proposes; this code checks every input.

Rules enforced here, not trusted to the model:
- Coordinates come only from places `find_place` actually returned in this conversation.
- A complaint is filed only after the caller has had a turn to confirm the place
  (the place must have been found before the caller's latest message).
- One complaint per conversation; filing twice returns the first one.
- No tool can change a complaint's status. Tools only create and read.
"""

import re
from dataclasses import dataclass, field

from app.db.models import CATEGORIES
from app.llm.types import ToolSpec
from app.places import gazetteer


@dataclass
class OfferedPlace:
    place: gazetteer.Place
    found_at_turn: int  # the caller-turn number when find_place returned it


@dataclass
class ToolState:
    """What the tools remember during one conversation."""

    caller_turn: int = 0  # increases each time the caller speaks
    offered: dict[str, OfferedPlace] = field(default_factory=dict)
    filed: object | None = None  # FiledComplaint once filed
    emergency_reason: str | None = None


SPECS = [
    ToolSpec(
        "find_place",
        "Look up a real place or landmark in Bengaluru North (Yelahanka, Rajanukunte, Hebbal and around). "
        "Returns up to 3 candidates with ids. Use the place name the caller said, in English letters if you can.",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "the place or landmark, e.g. 'Presidency University'"},
            "area": {"type": "string", "description": "village or area if the caller said one, e.g. 'Rajanukunte'"},
        }, "required": ["query"]},
    ),
    ToolSpec(
        "file_complaint",
        "File the complaint. Only after you read it back and the caller said yes. Returns the tracking ID.",
        {"type": "object", "properties": {
            "category": {"type": "string", "enum": list(CATEGORIES)},
            "summary_en": {"type": "string", "description": "one sentence in English for the officer"},
            "summary_local": {"type": "string", "description": "the same sentence in the caller's language"},
            "place_id": {"type": "string", "description": "id of the place the caller confirmed, from find_place"},
            "landmark": {"type": "string", "description": "extra detail, e.g. 'near the main gate'"},
            "since_when": {"type": "string", "description": "how long the problem has existed, if the caller said"},
            "urgency": {"type": "integer", "description": "1 (minor) to 5 (danger to life)"},
            "caller_confirmed": {"type": "boolean", "description": "true only if the caller said the read-back is right"},
        }, "required": ["category", "summary_en", "place_id", "caller_confirmed"]},
    ),
    ToolSpec(
        "get_complaint_status",
        "Look up a complaint by its tracking number, when the caller asks what happened to a complaint.",
        {"type": "object", "properties": {
            "tracking_id": {"type": "string", "description": "e.g. 'CV-1042' or '1042'"},
        }, "required": ["tracking_id"]},
    ),
    ToolSpec(
        "raise_emergency",
        "Use at once if anyone may be in danger: open manhole, fallen live wire, gas smell, collapsing wall, "
        "flooding with current. Alerts officers immediately. Then tell the caller to call 112 if life is at risk.",
        {"type": "object", "properties": {
            "reason": {"type": "string", "description": "what the danger is, in English"},
        }, "required": ["reason"]},
    ),
]


def find_place(state: ToolState, query: str, area: str | None = None) -> dict:
    matches = gazetteer.find(query, area)
    # "Presidency University Hostel" is part of "Presidency University": same place for a caller.
    if matches:
        top = matches[0].place.label.lower()
        matches = [matches[0]] + [m for m in matches[1:] if not m.place.label.lower().startswith(top)]
    for m in matches:
        state.offered.setdefault(m.place.id, OfferedPlace(m.place, state.caller_turn))
    if not matches:
        return {"matches": [], "note": "No such place found. Ask for a nearby landmark, bus stop or road name."}
    return {
        "matches": [{"id": m.place.id, "name": m.place.label, "name_kn": m.place.name_kn,
                     "kind": m.place.kind, "confidence": round(m.score)} for m in matches],
        "note": "If the first match fits what the caller said, read it back for a yes/no. "
                "Ask the caller to choose only if the matches are genuinely different places.",
    }


def file_complaint(state: ToolState, repo, session_info: dict, **a) -> dict:
    if state.filed is not None:
        return {"ok": True, "already_filed": True, "tracking_id": state.filed.tracking_id,
                "say_tracking_id_as": spoken_id(state.filed.tracking_number)}
    problems = []
    if a.get("category") not in CATEGORIES:
        problems.append(f"category must be one of {list(CATEGORIES)}")
    offered = state.offered.get(a.get("place_id", ""))
    if offered is None:
        problems.append("place_id must be one returned by find_place in this conversation")
    elif offered.found_at_turn >= state.caller_turn:
        problems.append("the caller has not yet confirmed this place: read it back and ask first")
    if not a.get("caller_confirmed"):
        problems.append("the caller has not confirmed the read-back yet")
    if not (a.get("summary_en") or "").strip():
        problems.append("summary_en is empty")
    if problems:
        return {"ok": False, "not_filed": True, "fix": problems}

    p = offered.place
    urgency = a.get("urgency") if isinstance(a.get("urgency"), int) else 3
    if state.emergency_reason:
        urgency = 5
    filed = repo.file_complaint(
        category=a["category"],
        summary_en=a["summary_en"].strip()[:500],
        summary_local=(a.get("summary_local") or "").strip()[:500] or None,
        language=session_info.get("language"),
        urgency=max(1, min(5, urgency)),
        is_emergency=bool(state.emergency_reason),
        place_name=p.label,
        landmark=(a.get("landmark") or "").strip()[:200] or None,
        lat=p.lat,
        lon=p.lon,
        place_source="gazetteer",
        since_when=(a.get("since_when") or "").strip()[:100] or None,
        caller_hash=session_info.get("caller_hash"),
        caller_last4=session_info.get("caller_last4"),
        channel=session_info.get("channel", "web"),
    )
    state.filed = filed
    return {"ok": True, "tracking_id": filed.tracking_id, "say_tracking_id_as": spoken_id(filed.tracking_number),
            "place": p.label}


def get_complaint_status(repo, tracking_id: str) -> dict:
    digits = re.sub(r"\D", "", tracking_id or "")
    if not digits:
        return {"found": False, "note": "Ask for the tracking number, e.g. C V 1 0 4 2."}
    st = repo.complaint_status(int(digits))
    if not st:
        return {"found": False, "note": "No complaint with that number. Ask the caller to repeat it."}
    return {"found": True, "tracking_id": st.tracking_id, "status": st.status, "category": st.category,
            "summary": st.summary_en, "place": st.place_name, "filed_on": st.created_at.date().isoformat()}


def raise_emergency(state: ToolState, reason: str) -> dict:
    state.emergency_reason = (reason or "danger reported").strip()[:200]
    return {"ok": True, "next_steps": [
        "Tell the caller to call 112 now if anyone's life is at risk.",
        "Call find_place with the place the caller already named (don't ask for it again).",
        "Read back the problem and place in one sentence; when the caller says yes, call file_complaint "
        "with urgency 5. Officers can only reach it once it is filed with a place.",
    ]}


def spoken_id(tracking_number: int) -> str:
    """CV-1042 -> 'C V 1 0 4 2': read out one character at a time."""
    return "C V " + " ".join(str(tracking_number))
