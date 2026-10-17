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

from app.db.models import CATEGORIES, DEFAULT_DEPARTMENT, DEPARTMENTS
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
    nearby_seen: dict[str, int] = field(default_factory=dict)  # tracking_id → number, from find_nearby_complaints
    report_count: int | None = None  # set when this call was added to an existing complaint


SPECS = [
    ToolSpec(
        "find_place",
        "Look up a real place or landmark in Bengaluru North (Yelahanka, Rajanukunte, Hebbal and around). "
        "Returns up to 3 candidates with ids. Use the place name the caller said, in English letters if you can.",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "the place or landmark, e.g. 'Presidency University'"},
            "area": {"type": "string", "description": "village or area if the caller said one, e.g. 'Rajanukunte'"},
            "road": {"type": "string", "description": "the road the problem is ON, if the caller named one, "
                                                     "e.g. 'Kakolu Road' — the pin is then placed on that road"},
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
            "same_as": {"type": "string", "description": "tracking ID from find_nearby_complaints if this is the SAME "
                                                         "problem already reported; leave out for a new problem"},
            "department": {"type": "string", "enum": list(DEPARTMENTS),
                           "description": "the office responsible: bbmp (city roads, garbage, drains, lights, "
                                          "trees, stray animals), bescom (power), bwssb (water), bmtc (buses), "
                                          "traffic_police, police (non-emergency), health, education, "
                                          "food_civil_supplies (ration shops), revenue (pensions, certificates), "
                                          "pollution_board, panchayat (villages outside the city), lokayukta "
                                          "(bribes, corruption), unrouted (no office clearly fits)"},
            "sensitive": {"type": "boolean", "description": "true for harassment, violence, abuse or corruption: "
                                                            "the caller's identity is not kept"},
        }, "required": ["category", "summary_en", "place_id", "caller_confirmed"]},
    ),
    ToolSpec(
        "find_nearby_complaints",
        "After the place is found and before the read-back: check whether this problem was already reported "
        "within about 150 m. Returns open complaints of the same category nearby.",
        {"type": "object", "properties": {
            "place_id": {"type": "string", "description": "id of the place from find_place"},
            "category": {"type": "string", "enum": list(CATEGORIES)},
        }, "required": ["place_id", "category"]},
    ),
    ToolSpec(
        "get_complaint_status",
        "Look up a complaint when the caller asks what happened to it. Give the tracking number if they know it; "
        "leave it out to look up this caller's own latest complaint (phone calls only).",
        {"type": "object", "properties": {
            "tracking_id": {"type": "string", "description": "e.g. 'CV-1042' or '1042', if the caller said it"},
        }},
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


def find_place(state: ToolState, query: str, area: str | None = None, road: str | None = None) -> dict:
    matches = gazetteer.find(query, area)
    # "Presidency University Hostel" is part of "Presidency University": same place for a caller.
    if matches:
        top = matches[0].place.label.lower()
        matches = [matches[0]] + [m for m in matches[1:] if not m.place.label.lower().startswith(top)]
    # "On Kakolu Road near Presidency University": the problem is on the road, so the pin goes on
    # the road at the point nearest the landmark — not in the middle of the campus.
    if matches and road:
        p = matches[0].place
        snapped = gazetteer.snap_to_road(p.lat, p.lon, road)
        if snapped:
            lat, lon, road_name, _ = snapped
            on_road = gazetteer.Place(f"{p.id}@road", f"{road_name} near {p.label}", "", "road_point",
                                      round(lat, 6), round(lon, 6), p.area)
            matches = [gazetteer.Match(on_road, matches[0].score, None)] + matches
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

    same_as = (a.get("same_as") or "").strip().upper()
    if same_as and same_as not in state.nearby_seen:
        return {"ok": False, "not_filed": True,
                "fix": ["same_as must be a tracking ID returned by find_nearby_complaints in this conversation"]}

    p = offered.place
    urgency = a.get("urgency") if isinstance(a.get("urgency"), int) else 3
    if state.emergency_reason:
        urgency = 5
    department = a.get("department") if a.get("department") in DEPARTMENTS else DEFAULT_DEPARTMENT[a["category"]]
    sensitive = bool(a.get("sensitive")) or a["category"] == "corruption"
    fields = dict(
        category=a["category"],
        department=department,
        sensitive=sensitive,
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
        # Sensitive reports keep no trace of who reported them.
        caller_hash=None if sensitive else session_info.get("caller_hash"),
        caller_last4=None if sensitive else session_info.get("caller_last4"),
        contact_enc=None if sensitive else session_info.get("contact_enc"),
        channel=session_info.get("channel", "web"),
    )
    if same_as:
        # Same problem: one tracking ID for everyone; the original gets this report counted.
        filed, count, raised = repo.add_report(state.nearby_seen[same_as], **fields)
        state.filed, state.report_count = filed, count
        return {"ok": True, "added_to_existing": True, "tracking_id": filed.tracking_id,
                "say_tracking_id_as": spoken_id(filed.tracking_number), "you_are_reporter_number": count,
                "priority_raised": raised, "place": p.label}
    filed = repo.file_complaint(**fields)
    state.filed = filed
    return {"ok": True, "tracking_id": filed.tracking_id, "say_tracking_id_as": spoken_id(filed.tracking_number),
            "place": p.label, "sent_to": department}


def find_nearby_complaints(state: ToolState, repo, place_id: str, category: str) -> dict:
    offered = state.offered.get(place_id or "")
    if offered is None:
        return {"error": "place_id must come from find_place"}
    if category not in CATEGORIES:
        return {"error": f"category must be one of {list(CATEGORIES)}"}
    if category in ("safety", "corruption"):  # never merge people's sensitive reports together
        return {"matches": [], "note": "Sensitive reports are always filed on their own."}
    found = repo.nearby_open(offered.place.lat, offered.place.lon, category)[:3]
    for f in found:
        state.nearby_seen[f["tracking_id"]] = f["tracking_number"]
    if not found:
        return {"matches": [], "note": "Nothing similar reported nearby: this is a new complaint."}
    return {"matches": [{k: v for k, v in f.items() if k != "tracking_number"} for f in found],
            "note": "If one of these is clearly the SAME problem, tell the caller it is already reported "
                    "(by how many people) and that their report will be added; then read back and file with "
                    "same_as. If unsure, ask the caller one short question. Otherwise file as new."}


def get_complaint_status(repo, tracking_id: str | None, caller_hash: str | None = None, channel: str = "web") -> dict:
    digits = re.sub(r"\D", "", tracking_id or "")
    if digits:
        st = repo.complaint_status(int(digits))
        if not st:
            return {"found": False, "note": "No complaint with that number. Ask the caller to repeat it."}
    elif channel == "phone" and caller_hash:
        # Only the caller's OWN complaints, recognised by their (hashed) number.
        st = repo.latest_for_caller(caller_hash)
        if not st:
            return {"found": False, "note": "No complaint from this phone number. Ask for the tracking number."}
    else:
        return {"found": False, "note": "Ask for the tracking number, e.g. C V 1 0 4 2."}
    plain = {"open": "registered, waiting for the officer", "in_progress": "the officer is working on it",
             "fixed": "marked as fixed", "reopened": "reopened after the citizen said it was not fixed"}
    return {"found": True, "tracking_id": st.tracking_id, "status": plain.get(st.status, st.status),
            "say_tracking_id_as": spoken_id(int(st.tracking_id.split("-")[1])), "category": st.category,
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
    """CV-1042 -> 'C V, 1 0, 4 2': digits read in pairs with a pause between, as people say numbers."""
    d = str(tracking_number)
    pairs = [d[max(0, i - 2):i] for i in range(len(d), 0, -2)][::-1]
    return "C V, " + ", ".join(" ".join(p) for p in pairs)
