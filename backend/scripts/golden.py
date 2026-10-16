"""Golden conversations: scripted callers talk to the REAL Gemma clerk; a pass table is printed.

Nothing is written to the database (a fake one records what would be filed).
Each script feeds the caller's lines one per turn and stops once the outcome is reached.

Run:  python -m scripts.golden            (all)
      python -m scripts.golden 3 8        (only these numbers)
"""

import re
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

    def nearby_open(self, lat, lon, category, radius_m=150):
        # One existing pothole complaint at Yelahanka New Town bus station.
        if category == "road" and abs(lat - 13.0957) < 0.005 and abs(lon - 77.5790) < 0.005:
            return [{"tracking_id": "CV-1042", "tracking_number": 1042, "summary": "Big potholes outside the bus station",
                     "place": "Yelahanka New Town", "report_count": 2, "metres_away": 30, "filed_on": "2026-10-15"}]
        return []

    def add_report(self, parent, **fields):
        self.filed.append({**fields, "same_as": parent})
        return FiledComplaint(42, parent), 3, True

    def latest_for_caller(self, caller_hash):
        if caller_hash == "known-caller":
            return ComplaintStatus("CV-1004", "in_progress", "road", "Potholes in front of St. Mary's School",
                                   "St. Mary's School", datetime(2026, 10, 16))
        return None

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
    same_as: int | None = None  # expect the report to be added to this existing complaint
    channel: str = "web"
    caller_hash: str | None = None
    final_language: str | None = None  # the language the clerk should end up speaking
    expect_landmark_question: bool = False
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
    Case("Already reported: adds to the original", "en-IN",
         ["There are big potholes on the road at Yelahanka New Town bus station.", "Yes, that's the one.",
          "About a week.", "Yes, correct."],
         category="road", place_contains="Yelahanka New Town", expect_tool="find_nearby_complaints", same_as=1042),
    Case("Tamil streetlight", "ta-IN",
         ["வணக்கம், Hebbal flyover பக்கத்தில் street light ஒரு வாரமா எரியவில்லை.", "ஆமாம், Hebbal flyover.",
          "ஒரு வாரமா.", "ஆமாம், சரி."],
         category="streetlight", place_contains="Hebbal"),
    Case("Telugu garbage", "te-IN",
         ["నమస్కారం, Yelahanka New Town bus station దగ్గర చాలా చెత్త పేరుకుపోయింది.", "అవును, అదే.",
          "రెండు వారాలుగా.", "అవును, సరిగ్గా ఉంది."],
         category="garbage", place_contains="Yelahanka New Town"),
    Case("Urdu water, answered in Hindi", "ur-IN",
         ["السلام علیکم، ہمارے علاقے میں دو دن سے پانی نہیں آ رہا۔", "Jakkur lake کے پاس۔", "دو دن سے۔", "جی ہاں، صحیح ہے۔"],
         category="water", place_contains="Jakkur"),
    Case("Switches from Kannada to English halfway", "kn-IN",
         [("ನಮಸ್ಕಾರ, ನಮ್ಮ area ಅಲ್ಲಿ streetlight ಕೆಲಸ ಮಾಡ್ತಿಲ್ಲ.", "kn-IN"),
          ("Actually it is near Jakkur Lake, on the main road.", "en-IN"),
          ("Yes, English is fine. It has been one week.", "en-IN"), ("Yes, correct.", "en-IN")],
         category="streetlight", place_contains="Jakkur", final_language="en-IN"),
    Case("Area only: asks once for a street or landmark", "hi-IN",
         ["मेरे इलाके जयनगर में तीन दिन से पानी नहीं आ रहा है।", "चौथा block, 11th main road के पास।", "हाँ, सही है।"],
         category="water", place_contains="Jayanagar", expect_landmark_question=True),
    Case("Status of my complaint, no number (phone)", "kn-IN",
         ["ನನ್ನ complaint ಏನಾಯ್ತು? Number ನೆನಪಿಲ್ಲ."],
         expect_tool="get_complaint_status", must_not_file=True, channel="phone", caller_hash="known-caller"),
]


def run(case: Case) -> tuple[bool, str, float]:
    repo = FakeRepo()
    conv = Conversation(call_id=0, repo=repo, language=case.language, channel=case.channel,
                        caller_hash=case.caller_hash)
    tools_used: set[str] = set()
    t0 = time.perf_counter()
    replies = []
    for line in case.caller:
        line, lang = line if isinstance(line, tuple) else (line, case.language)
        result = conv.turn(line, lang)
        replies.append(result.reply)
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
    if case.same_as and (not filed or filed.get("same_as") != case.same_as):
        problems.append(f"not added to CV-{case.same_as}")
    said = re.sub(r"[\s,]", "", " ".join(case.transcript))  # "C V, 1 0, 0 4" -> "CV1004"
    if case.caller_hash and "1004" not in said and "St.Mary" not in said:
        problems.append("did not tell the caller about their complaint (CV-1004, St. Mary's School)")
    if case.final_language:
        from app.clerk.language import written_in
        last_questions = [r for r in replies[1:-1]]  # after the switch, before the fixed tracking-ID line
        if any(written_in(r, "kn-IN") != case.final_language for r in last_questions[1:]):
            problems.append(f"did not settle into {case.final_language}")
    if case.expect_landmark_question and not any(
            w in " ".join(replies[:-1]).lower() for w in ("landmark", "street", "गली", "लैंडमार्क", "block", "ब्लॉक", "road", "रोड", "जगह")):
        problems.append("never asked for a street or landmark")
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
