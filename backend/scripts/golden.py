"""Golden conversations: scripted callers talk to the REAL Gemma clerk; a pass table is printed.

Nothing is written to the database (a fake one records what would be filed).
Each script feeds the caller's lines one per turn and stops once the outcome is reached.

Run:  python -m scripts.golden            (all)
      python -m scripts.golden 3 8        (only these numbers)
"""

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

from app.clerk.clerk import Conversation
from app.db.repo import ComplaintStatus, FiledComplaint


class FakeRepo:
    def __init__(self):
        self.filed = []

    def file_complaint(self, **fields):
        self.filed.append(fields)
        return FiledComplaint(len(self.filed), 1000 + len(self.filed))

    def complaint_status(self, n):
        if n == 1042:
            return ComplaintStatus("CV-1042", "in_progress", "road", "Potholes near Presidency University",
                                   "Presidency University", datetime(2026, 10, 14))
        return None


@dataclass
class Case:
    name: str
    language: str
    caller: list[str]
    category: str | None = None  # expected category if a complaint should be filed
    place_contains: str | None = None
    expect_tool: str | None = None  # a tool that must be called (emergency, status)
    must_not_file: bool = False
    transcript: list[str] = field(default_factory=list)


CASES = [
    Case("Kannada pothole, clear", "kn-IN",
         ["ನಮಸ್ಕಾರ, ನಮ್ಮ road ಅಲ್ಲಿ ತುಂಬಾ ಹಳ್ಳಗಳು ಇವೆ, accident ಆಗ್ತಾ ಇದೆ.",
          "ರಾಜಾನುಕುಂಟೆ, Presidency University gate ಹತ್ತಿರ.", "ಎರಡು ತಿಂಗಳಿಂದ.", "ಹೌದು, ಸರಿ."],
         category="road", place_contains="Presidency"),
    Case("English streetlight", "en-IN",
         ["Hi, the streetlights near Yelahanka New Town bus station have not worked for a week.",
          "Yes, Yelahanka New Town bus station.", "About a week.", "Yes, that's correct."],
         category="streetlight", place_contains="Yelahanka New Town"),
    Case("Hindi water", "hi-IN",
         ["नमस्ते, हमारे इलाके में तीन दिन से पानी नहीं आ रहा है।", "Jakkur में, Jakkur lake के पास।",
          "तीन दिन से।", "हाँ, सही है।"],
         category="water", place_contains="Jakkur"),
    Case("Kanglish garbage", "kn-IN",
         ["Rajanukunte railway station hatra tumba garbage bidtha idare, smell barta ide.",
          "Haudu, railway station hatra.", "Ondu vaara inda.", "Haudu, sari."],
         category="garbage", place_contains="Rajanukunte"),
    Case("Vague start, details later", "en-IN",
         ["Hello, there's a problem in my area.", "The drain is blocked and water is overflowing on the road.",
          "Near Hebbal flyover.", "Since yesterday.", "Yes."],
         category="drainage", place_contains="Hebbal"),
    Case("Unknown place, then a landmark", "kn-IN",
         ["ನಮ್ಮ ಊರು Xyzpura ಅಲ್ಲಿ road ತುಂಬಾ ಹಾಳಾಗಿದೆ.", "Presidency University ಹತ್ತಿರ ಇದೆ.",
          "ಆರು ತಿಂಗಳಿಂದ.", "ಹೌದು."],
         category="road", place_contains="Presidency"),
    Case("Off-topic", "en-IN", ["What's the cricket score today?", "Tell me a joke."], must_not_file=True),
    Case("Emergency: open manhole", "en-IN",
         ["There is an open manhole on the road near Yelahanka Old Town bus station, a child almost fell in!",
          "Yes, Yelahanka Old Town bus station.", "Just now.", "Yes, correct."],
         expect_tool="raise_emergency", category="drainage"),
    Case("Emergency: live wire, Kannada", "kn-IN",
         ["ಜಕ್ಕೂರು lake ಹತ್ತಿರ current wire ಕೆಳಗೆ ಬಿದ್ದಿದೆ, ತುಂಬಾ danger!", "Jakkur lake ಹತ್ತಿರ.",
          "ಈಗ ತಾನೇ.", "ಹೌದು."],
         expect_tool="raise_emergency", category="electricity"),
    Case("Status check", "en-IN",
         ["What happened to my complaint?", "The number is C V 1 0 4 2."],
         expect_tool="get_complaint_status", must_not_file=True),
    Case("Power cut, Hindi-English", "hi-IN",
         ["Hebbal में कल से power cut है, कोई light नहीं है।", "Hebbal station के पास।", "कल शाम से।", "हाँ, सही है।"],
         category="electricity", place_contains="Hebbal"),
    Case("Caller corrects the place", "en-IN",
         ["Big potholes on the road near Presidency University.", "No, not the university. It's near Jakkur Lake.",
          "For a month.", "Yes, Jakkur Lake is right."],
         category="road", place_contains="Jakkur"),
]


def run(case: Case) -> tuple[bool, str, float]:
    repo = FakeRepo()
    conv = Conversation(call_id=0, repo=repo, language=case.language)
    tools_used: set[str] = set()
    t0 = time.perf_counter()
    for line in case.caller:
        result = conv.turn(line, case.language)
        tools_used |= {e["tool"] for e in result.events if e["kind"] == "tool_call"}
        case.transcript += [f"  caller: {line}", f"  clerk:  {result.reply}"]
        if repo.filed or ("get_complaint_status" in tools_used and case.expect_tool == "get_complaint_status"):
            break
    secs = time.perf_counter() - t0

    problems = []
    filed = repo.filed[0] if repo.filed else None
    if case.must_not_file and filed:
        problems.append("filed when it should not")
    if case.category and not filed:
        problems.append("not filed")
    if filed and case.category and filed["category"] != case.category:
        problems.append(f"category {filed['category']} ≠ {case.category}")
    if filed and case.place_contains and case.place_contains.lower() not in (filed["place_name"] or "").lower():
        problems.append(f"place {filed['place_name']!r} lacks {case.place_contains!r}")
    if case.expect_tool and case.expect_tool not in tools_used:
        problems.append(f"never called {case.expect_tool}")
    detail = "; ".join(problems) or (f"filed {filed['category']} @ {filed['place_name']}" if filed else "ok")
    return not problems, detail, secs


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    picks = {int(a) for a in sys.argv[1:]}
    passed = 0
    rows = []
    for i, case in enumerate(CASES, 1):
        if picks and i not in picks:
            continue
        ok, detail, secs = run(case)
        passed += ok
        rows.append((i, case, ok, detail, secs))
        print(f"{i:>2}. {'PASS' if ok else 'FAIL'}  {case.name:<34} {secs:5.1f}s  {detail}")
        if not ok:
            print("\n".join(case.transcript))
    print(f"\n{passed}/{len(rows)} passed")


if __name__ == "__main__":
    main()
