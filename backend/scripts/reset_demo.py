"""Reset the database for a demo: delete every complaint and call, then add a believable sample set.

The sample set: mixed problems and offices, a few overdue, one emergency, one pothole reported by
four people (one tracking ID, priority raised), two fixed complaints with their timelines, one
reopened, one sensitive (bribe) report. Sample complaints have no recorded conversation and no
photos: those only come from real calls, so nothing on screen pretends to be a call that never
happened.

SAFETY — this DELETES data in whatever database DATABASE_URL points to.
- With no flags it is a dry run: prints the database host and what it would do, touches nothing.
- To really run it: --yes, then type the database host exactly when asked.

Run (from backend/):
    python -m scripts.reset_demo           dry run
    python -m scripts.reset_demo --yes     really reset (asks you to type the host)

Run it the morning of the demo: "overdue" is worked out from each complaint's age.
"""

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class Seed:
    """One sample complaint. Ages are in hours before the moment of seeding."""

    category: str
    department: str
    summary_en: str
    summary_local: str | None
    language: str
    place_name: str
    lat: float
    lon: float
    place_id: str  # the gazetteer row the coordinates came from (checked by the tests)
    age_hours: float
    urgency: int = 3
    status: str = "open"
    landmark: str | None = None
    since_when: str | None = None
    channel: str = "phone"
    caller_last4: str | None = None
    is_emergency: bool = False
    sensitive: bool = False
    # Later steps in the timeline after "filed": (status, changed_by, note, hours ago).
    history: tuple[tuple[str, str, str, float], ...] = ()
    # Other people reporting the same problem: (hours ago, last 4 digits).
    duplicates: tuple[tuple[float, str], ...] = field(default_factory=tuple)

    @property
    def report_count(self) -> int:
        return 1 + len(self.duplicates)


# Coordinates are copied from backend/data/gazetteer.csv.gz (OpenStreetMap), never invented.
SEEDS: tuple[Seed, ...] = (
    # Four people reported the same potholes: one tracking ID, priority raised at the 3rd report
    # (urgency 3 → 4, the rule in repo.add_report). 10 days old, BBMP has 7 → overdue.
    Seed("road", "bbmp", "Big potholes on the road outside Yelahanka New Town bus stand; two-wheelers keep falling.",
         "ಯಲಹಂಕ ನ್ಯೂ ಟೌನ್ ಬಸ್ ಸ್ಟ್ಯಾಂಡ್ ಹೊರಗೆ ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿಗಳು, ಬೈಕ್‌ಗಳು ಬೀಳ್ತಿವೆ.", "kn-IN",
         "Yelahanka New Town", 13.097804, 77.581189, "osm-n959499372", age_hours=240, urgency=4,
         landmark="outside the bus stand", since_when="about a month", caller_last4="4821",
         duplicates=((170, "1907"), (96, "3365"), (30, "7702"))),
    # Danger to life: emergency, 1-day deadline whatever the office.
    Seed("electricity", "bescom", "Electric wire fallen on the footpath after the rain, still sparking.",
         "ಮಳೆ ಆದ್ಮೇಲೆ footpath ಮೇಲೆ current wire ಬಿದ್ದಿದೆ, ಇನ್ನೂ spark ಆಗ್ತಿದೆ.", "kn-IN",
         "Hebbal", 13.038218, 77.5919, "osm-n529277252", age_hours=2, urgency=5, is_emergency=True,
         landmark="near the flyover service road", since_when="this morning", caller_last4="5530"),
    # BWSSB has 2 days; 3 days old → overdue.
    Seed("water", "bwssb", "No water supply for three days in the whole lane.",
         "तीन दिन से पूरी गली में पानी नहीं आ रहा है।", "hi-IN",
         "Jayanagar 4th Block", 12.926574, 77.583504, "osm-n494013065", age_hours=74, urgency=4,
         since_when="three days", caller_last4="2290"),
    # Ration shops have 5 days; 6 days old → overdue.
    Seed("ration", "food_civil_supplies", "Ration shop has not given rice to card holders this month.",
         "ಈ ತಿಂಗಳು ration ಅಂಗಡಿಯವರು card ಇರೋರಿಗೆ ಅಕ್ಕಿ ಕೊಟ್ಟಿಲ್ಲ.", "kn-IN",
         "Rajajinagar", 12.988234, 77.554883, "osm-n429857523", age_hours=146, since_when="this month",
         caller_last4="6614"),
    # Health has 3 days; 4 days old → overdue.
    Seed("health", "health", "No doctor at the primary health centre for the last four days.",
         "ನಾಲ್ಕು ದಿನದಿಂದ primary health centre ಅಲ್ಲಿ doctor ಇಲ್ಲ.", "kn-IN",
         "Yelahanka", 13.100698, 77.596345, "osm-n430143744", age_hours=98, urgency=4,
         since_when="four days", channel="web"),
    # Officer has started work.
    Seed("drainage", "bbmp", "Drain overflowing onto the road, smells bad, mosquitoes everywhere.",
         None, "en-IN", "HAL 2nd Stage", 12.968941, 77.643711, "osm-n1857028749", age_hours=120,
         status="in_progress", landmark="near 12th Main", since_when="one week", caller_last4="8847",
         history=(("in_progress", "officer", "Desilting crew assigned.", 48),)),
    Seed("streetlight", "bbmp", "Three streetlights not working; the street is completely dark at night.",
         "ಮೂರು street light ಕೆಲಸ ಮಾಡ್ತಿಲ್ಲ, ರಾತ್ರಿ ರಸ್ತೆ ಪೂರ್ತಿ ಕತ್ತಲು.", "kn-IN",
         "Koramangala 5th Block", 12.934843, 77.618977, "osm-n9790284747", age_hours=40,
         since_when="one week", caller_last4="1186"),
    Seed("transport", "bmtc", "The bus route to the tech park stopped running in the mornings.",
         None, "en-IN", "Whitefield", 12.969637, 77.749745, "osm-n377219489", age_hours=22,
         since_when="two weeks", channel="web"),
    Seed("trees", "bbmp", "A big branch has fallen across the road and is blocking one lane.",
         "ಒಂದು ದೊಡ್ಡ ಕೊಂಬೆ ರಸ್ತೆಗೆ ಬಿದ್ದಿದೆ, ಒಂದು lane block ಆಗಿದೆ.", "kn-IN",
         "Basavanagudi", 12.941726, 77.575502, "osm-n429937956", age_hours=9, urgency=4,
         since_when="last night", caller_last4="3071"),
    Seed("noise", "police", "Loudspeakers from a hall play past midnight every night.",
         "हर रात आधी रात के बाद तक हॉल से लाउडस्पीकर बजते हैं।", "hi-IN",
         "HSR Layout", 12.911623, 77.638862, "osm-n456016994", age_hours=30, urgency=2,
         since_when="two weeks", caller_last4="9452"),
    # Sensitive: details hidden from the public dashboard; no caller identity kept.
    Seed("corruption", "lokayukta", "An official asked for money to process a khata transfer.",
         None, "kn-IN", "Shivajinagar", 12.985529, 77.60545, "osm-n429303186", age_hours=26,
         sensitive=True, caller_last4=None),
    # Fixed, with the full timeline: filed → started → fixed.
    Seed("garbage", "bbmp", "Garbage not collected for a week; pile spreading onto the road.",
         "ಒಂದು ವಾರದಿಂದ ಕಸ ತೆಗೆದುಕೊಂಡು ಹೋಗಿಲ್ಲ, ರಸ್ತೆಗೆ ಹರಡ್ತಿದೆ.", "kn-IN",
         "Malleswaram", 13.002735, 77.570325, "osm-n427595936", age_hours=150, status="fixed",
         since_when="one week", caller_last4="7319",
         history=(("in_progress", "officer", "Pourakarmika team informed.", 100),
                  ("fixed", "officer", "Pile cleared and area swept.", 30))),
    Seed("water", "bwssb", "Pipe leaking at the corner, water wasting all day.",
         "ಮೂಲೆಯಲ್ಲಿ pipe leak ಆಗ್ತಿದೆ, ದಿನವಿಡೀ ನೀರು waste ಆಗ್ತಿದೆ.", "kn-IN",
         "Banashankari", 12.92782, 77.556621, "osm-n12816045429", age_hours=90, status="fixed",
         since_when="two days", caller_last4="5048",
         history=(("in_progress", "officer", "Plumber sent.", 70),
                  ("fixed", "officer", "Joint replaced.", 52))),
    # Marked fixed, then reopened: the citizen said it was not fixed.
    Seed("streetlight", "bbmp", "Streetlight outside the school not working.",
         "ಶಾಲೆ ಹೊರಗೆ street light ಕೆಲಸ ಮಾಡ್ತಿಲ್ಲ.", "kn-IN",
         "Basavanagudi", 12.941726, 77.575502, "osm-n429937956", age_hours=130, status="reopened", urgency=4,
         landmark="outside the school gate", caller_last4="2633",
         history=(("fixed", "officer", "Bulb replaced.", 60),
                  ("reopened", "officer", "Citizen called: still dark at night.", 20))),
)


def database_host(url: str) -> str:
    """The host part of a database URL — the only part of it ever printed (never the password)."""
    try:
        host = make_url(url.strip()).host
    except Exception:
        host = None
    if not host:
        raise ValueError("DATABASE_URL has no host")
    return host


def describe(seeds: tuple[Seed, ...] = SEEDS) -> list[str]:
    linked = sum(len(s.duplicates) for s in seeds)
    lines = [
        "It would DELETE every row in: status_changes, photos, clerk_events, turns, calls, complaints.",
        f"Then add {len(seeds)} sample complaints (+{linked} linked reports of the same problem):",
    ]
    for s in seeds:
        flags = [f for f, on in (("EMERGENCY", s.is_emergency), ("sensitive", s.sensitive),
                                 (f"{s.report_count} reports", s.report_count > 1)) if on]
        age = f"{s.age_hours / 24:.1f} days" if s.age_hours >= 24 else f"{s.age_hours:.0f} hours"
        lines.append(f"  - {s.category:<12} {s.department:<20} {s.status:<11} {age:>10} old  "
                     f"{s.place_name}" + (f"  [{', '.join(flags)}]" if flags else ""))
    lines.append("Sample complaints have no conversation or photos; tracking numbers continue from the current one.")
    return lines


def apply_reset(seeds: tuple[Seed, ...], now: datetime, out: Callable[[str], None]) -> None:
    """Delete everything and insert the sample set, in ONE transaction (all or nothing)."""
    from sqlalchemy import delete, func, select
    from sqlalchemy.orm import Session

    from app.db.models import Call, ClerkEvent, Complaint, Photo, StatusChange, Turn
    from app.db.session import get_engine

    with Session(get_engine()) as s, s.begin():
        before = {t.__tablename__: s.scalar(select(func.count()).select_from(t))
                  for t in (Complaint, Call, Turn, ClerkEvent, Photo, StatusChange)}
        out("Rows now: " + ", ".join(f"{k} {v}" for k, v in before.items()))
        # Children first, so no foreign key is left pointing at a deleted row.
        for table in (StatusChange, Photo, ClerkEvent, Turn, Call):
            s.execute(delete(table))
        s.execute(delete(Complaint).where(Complaint.duplicate_of.is_not(None)))
        s.execute(delete(Complaint))

        for seed in seeds:
            filed_at = now - timedelta(hours=seed.age_hours)
            common = dict(
                category=seed.category, department=seed.department, sensitive=seed.sensitive,
                summary_en=seed.summary_en, summary_local=seed.summary_local, language=seed.language,
                is_emergency=seed.is_emergency, place_name=seed.place_name, landmark=seed.landmark,
                lat=seed.lat, lon=seed.lon, place_source="gazetteer", since_when=seed.since_when,
                channel=seed.channel,
            )
            c = Complaint(**common, status=seed.status, urgency=seed.urgency, report_count=seed.report_count,
                          caller_last4=None if seed.sensitive else seed.caller_last4,
                          created_at=filed_at, updated_at=filed_at)
            s.add(c)
            s.flush()
            s.add(StatusChange(complaint_id=c.id, status="open", changed_by="system", note="filed", created_at=filed_at))
            for status, by, note, hours_ago in seed.history:
                s.add(StatusChange(complaint_id=c.id, status=status, changed_by=by, note=note,
                                   created_at=now - timedelta(hours=hours_ago)))
            for hours_ago, last4 in seed.duplicates:
                at = now - timedelta(hours=hours_ago)
                s.add(Complaint(**common, duplicate_of=c.id, status="open", urgency=seed.urgency,
                                caller_last4=last4, created_at=at, updated_at=at))
        s.flush()
        added = s.scalar(select(func.count()).select_from(Complaint))
    out(f"Done: {added} complaint rows now ({len(seeds)} shown on the dashboard).")


def run(argv: list[str] | None = None, *, database_url: str | None = None,
        ask: Callable[[str], str] = input, out: Callable[[str], None] = print,
        apply: Callable[..., None] = apply_reset, now: datetime | None = None) -> int:
    p = argparse.ArgumentParser(description="Reset the demo database (dry run unless --yes).")
    p.add_argument("--yes", action="store_true", help="really delete and re-seed (you will type the host)")
    args = p.parse_args(argv)

    if database_url is None:
        from app.settings import get_settings
        database_url = get_settings().database_url
    if not database_url:
        out("DATABASE_URL is not set. Nothing to do.")
        return 2
    try:
        host = database_host(database_url)
    except ValueError as e:
        out(f"Cannot read the database address: {e}.")
        return 2

    out(f"Database host: {host}")
    for line in describe():
        out(line)
    if not args.yes:
        out("DRY RUN: nothing was changed. To really do it: python -m scripts.reset_demo --yes")
        return 0

    typed = ask(f"This deletes ALL complaints and calls on {host}. Type the host to confirm: ").strip()
    if typed != host:
        out("Host did not match. Nothing was changed.")
        return 1
    apply(SEEDS, now or datetime.now(timezone.utc), out)
    return 0


if __name__ == "__main__":
    sys.exit(run())
