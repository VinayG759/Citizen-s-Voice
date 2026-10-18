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

from app import events, officer
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
    # What the clerk said just before the caller's latest words (set by the conversation; None when the
    # tools are used on their own). A real read-back names the place.
    last_reply: str | None = None
    readback_refused: bool = False  # refused once at most, so a read-back we can't match never traps a caller


SPECS = [
    ToolSpec(
        "find_place",
        "Look up a real place anywhere in Bengaluru: an area, landmark, bus stop, school, temple, road or "
        "campus gate. "
        "Returns up to 4 different places with ids, each with where it is (the nearest suburb). Use the place name the caller said, in English letters if you can.",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "the place or landmark, e.g. 'Presidency University'"},
            "area": {"type": "string", "description": "village or area if the caller said one, e.g. 'Rajanukunte'"},
            "road": {"type": "string", "description": "the road the problem is ON, if the caller named one, "
                                                     "e.g. 'Kakolu Road' — the pin is then placed on that road"},
            "pincode": {"type": "string", "description": "6-digit pincode, only if the caller said one; "
                                                        "places in it come first"},
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
        "nearby (150 m for a pothole, streetlight, tree or drain; 500 m for water, power or garbage, which "
        "affect a whole street). Returns open complaints of the same category nearby.",
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
        "Use at once if anyone may be in danger (open manhole, fallen live wire, gas leak, collapsing wall, "
        "flooding with current) or a resource is being wasted by the minute (burst water main, pipe gushing "
        "water). Marks this complaint as an emergency (urgency 5, flagged at the top of the "
        "officers' dashboard once filed); it does not call 112 or anyone else. Then tell the caller to call 112 "
        "if life is at risk.",
        {"type": "object", "properties": {
            "reason": {"type": "string", "description": "what the danger is, in English"},
        }, "required": ["reason"]},
    ),
]


OPTIONS = 4  # at most this many different places offered for one name
OPTION_KM = 1.5  # matches closer than this are one place for a caller


def find_place(state: ToolState, query: str, area: str | None = None, road: str | None = None,
               pincode: str | None = None) -> dict:
    # Matches close together ("Presidency University" and its hostel, MG Road metro and the Taj on MG Road)
    # are one place for a caller; up to OPTIONS genuinely different places are offered.
    matches: list[gazetteer.Match] = []
    pin = gazetteer.pincode_centre(pincode)
    where_asked = area or (f"pincode {pin.name_en}" if pin else None)
    found = gazetteer.find(query, area, limit=12, pincode=pincode)
    # Places carrying the caller's own distinctive words ("St. Mary's") are the real alternatives, ahead of
    # look-alikes ("St. Paul's"). Tester, 18 Oct: four St. Mary's schools, and the clerk "could only see one".
    found = found[:1] + sorted(found[1:], key=lambda m: gazetteer._distinctive_match(query, m.place) < 90)
    for m in found:
        # "Presidency University Hostel" is part of "Presidency University": same place for a caller.
        if matches and m.place.label.lower().startswith(matches[0].place.label.lower() + " "):
            continue
        if all(gazetteer.km_between(o.place.lat, o.place.lon, m.place.lat, m.place.lon) > OPTION_KM for o in matches):
            matches.append(m)
        if len(matches) == OPTIONS:
            break
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
    out = []
    for m in matches:
        d = {"id": m.place.id, "name": m.place.label, "name_kn": m.place.name_kn,
             "kind": m.place.kind, "where": gazetteer.where(m.place), "confidence": round(m.score)}
        if m.distance_km_from_area is not None:
            d["km_from_area"] = round(m.distance_km_from_area, 1)
        out.append(d)
    if where_asked and matches[0].distance_km_from_area is not None and matches[0].distance_km_from_area > gazetteer.NEAR_KM:
        # Tester's report, 17 Oct: the caller's own words were read back ("St. Mary's School, Dasarahalli")
        # and confirmed, while the pin sat 15 km away. Never read back a place outside the caller's area.
        return {"matches": out,
                "note": f"None of these is in {where_asked}: the nearest is {round(matches[0].distance_km_from_area)} "
                        "km away. Do not read these back. Ask for a nearby landmark, bus stop or road in "
                        f"{where_asked}, then search again."
                        + (f" If that fails too, file at {area} itself with their landmark in words." if area else "")}
    kinds = gazetteer._wanted_kinds(query)
    shared = [d for m, d in zip(matches, out)
              if gazetteer.normalise(d["name"]) == gazetteer.normalise(out[0]["name"])
              or (kinds and m.place.kind in kinds and gazetteer._distinctive_match(query, m.place) >= 90)]
    # A suburb is the famous one ("Koramangala"): no need to ask about a village of that name 40 km out.
    if len(shared) > 1 and not where_asked and matches[0].place.kind not in ("suburb", "town"):
        where = ", ".join(f"near {d['where']}" for d in shared)
        return {"matches": out,
                "note": f"{len(shared)} different places match this name ({where}). Ask the caller which one, "
                        "naming each by where it is, unless what they said already tells you. "
                        "If the caller says it is not the place, never offer it again."}
    return {
        "matches": out,
        "note": "If the first match fits what the caller said, read it back for a yes/no, using its name "
                "as given here. Ask the caller to choose only if the matches are genuinely different places. "
                "If the caller says it is not the place, never offer it again.",
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

    # CV-1013, 18 Oct: Gemma filed straight after "how long has it been?", taking an earlier "yes, that's
    # the one" (about the place) as the caller's yes to a read-back that never happened.
    if state.last_reply is not None and not state.readback_refused and not _names_place(state.last_reply, offered.place):
        state.readback_refused = True
        return {"ok": False, "not_filed": True,
                "fix": ["read the complaint back first: the problem, the place and since when, in one sentence, "
                        "and ask if it is right. File only after the caller says yes to that."]}

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
    # A sensitive report: the call record forgets who called as well (not only the complaint).
    forget = {"forget_call": session_info["call_id"]} if sensitive and session_info.get("call_id") else {}
    if same_as:
        # Same problem: one tracking ID for everyone; the original gets this report counted.
        filed, count, raised = repo.add_report(state.nearby_seen[same_as], **forget, **fields)
        state.filed, state.report_count = filed, count
        return {"ok": True, "added_to_existing": True, "tracking_id": filed.tracking_id,
                "say_tracking_id_as": spoken_id(filed.tracking_number), "you_are_reporter_number": count,
                "priority_raised": raised, "place": p.label}
    filed = repo.file_complaint(**forget, **fields)
    state.filed = filed
    if fields["is_emergency"]:
        # Every open officer dashboard raises an alert straight away (web/src/Shell.tsx).
        events.publish("emergency", tracking_id=filed.tracking_id, emergency_kind=officer.emergency_kind(fields),
                       place=p.label,
                       office=officer.OFFICE_NAMES.get(department, department),
                       summary=None if sensitive else fields["summary_en"][:200])
    return {"ok": True, "tracking_id": filed.tracking_id, "say_tracking_id_as": spoken_id(filed.tracking_number),
            "place": p.label, "sent_to": department}


def _names_place(text: str, place: gazetteer.Place) -> bool:
    """Does the clerk's message name this place? Any distinctive word of its names will do."""
    words = {w for name in (place.name_en, place.name_kn, *place.alt.split("|"))
             for w in gazetteer.normalise(name).split() if len(w) >= 4 and w not in gazetteer._GENERIC}
    said = gazetteer.normalise(text)
    return not words or any(w in said for w in words)


# How far apart two reports can be and still be the same problem. A pothole is a point; no water or
# power is a whole street, so neighbours a few houses apart report the same outage.
SAME_PROBLEM_M = 150
SAME_PROBLEM_AREA_M = 500
AREA_PROBLEMS = ("water", "electricity", "garbage")


def find_nearby_complaints(state: ToolState, repo, place_id: str, category: str) -> dict:
    offered = state.offered.get(place_id or "")
    if offered is None:
        return {"error": "place_id must come from find_place"}
    if category not in CATEGORIES:
        return {"error": f"category must be one of {list(CATEGORIES)}"}
    if category in ("safety", "corruption"):  # never merge people's sensitive reports together
        return {"matches": [], "note": "Sensitive reports are always filed on their own."}
    radius = SAME_PROBLEM_AREA_M if category in AREA_PROBLEMS else SAME_PROBLEM_M
    found = repo.nearby_open(offered.place.lat, offered.place.lon, category, radius_m=radius)[:3]
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
    # The complete picture for a citizen who calls in (18 Oct: phone citizens are called only after the fix,
    # so calling in is how they follow it): which office, the deadline, overdue or not, and what was done.
    due = officer.follow_up({"created_at": st.created_at.isoformat(), "department": st.department,
                             "is_emergency": st.is_emergency, "status": st.status})
    done = [_update_line(u, plain) for u in st.updates if u["by"] in ("officer", "citizen")][-3:]
    return {"found": True, "tracking_id": st.tracking_id, "status": plain.get(st.status, st.status),
            "say_tracking_id_as": spoken_id(int(st.tracking_id.split("-")[1])), "category": st.category,
            "summary": st.summary_en, "place": st.place_name, "filed_on": st.created_at.date().isoformat(),
            "office": due["office"], "deadline_days": due["deadline_days"], "overdue": due["overdue"],
            "updates": done or ["no action yet"],
            "note": "Tell them the status, the office and whether it is overdue, then the latest update "
                    "(with the officer's note if there is one), in two short sentences."}


def _update_line(u: dict, plain: dict) -> str:
    """'2026-10-18: the officer is working on it (Crew sent, work starts Monday)'. Gemma's own photo
    verdict, added to the officer's note when marked fixed, is advice and is left out."""
    note = " · ".join(p for p in (u.get("note") or "").split(" · ") if p and not p.startswith("Gemma:"))
    if u["by"] == "citizen" and note:  # "citizen confirmed it is fixed …" says it all
        return f"{u['at'][:10]}: {note}"
    return f"{u['at'][:10]}: {plain.get(u['status'], u['status'])}" + (f" ({note})" if note else "")


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
