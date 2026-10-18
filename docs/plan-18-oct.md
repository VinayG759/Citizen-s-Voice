# Citizen's Voice — plan for the fixes and features of 17–18 Oct

Written 2026-10-18, submission day (**closes 3:30 PM IST**). Source: Tharun's two test reports and
Vinay's 11-point review of the officer side. The reference version; a plain-language version is in
[plan-18-oct-simple.md](plan-18-oct-simple.md). If they disagree, this one wins.

Every task answers four questions (Vinay's working rule): **who gets value**, **the simplest version
that works**, **what it replaces**, and **what goes wrong if someone misuses it**.

**Rule for today:** nothing new is started after **1 PM**. After that, only fixes for what testing
breaks, then rehearsal.

WhatsApp is out of scope for today (built, tested with fakes, not connected).

---

## 1. Status at a glance

| # | Task | State |
|---|---|---|
| A1 | Place in the named area beats the same name far away | ✅ deployed 17 Oct, retested live |
| A2 | Complaint page shows every person who reported it | ✅ deployed 17 Oct, retested live |
| A3 | Chats follow a change of language at once | ✅ deployed 17 Oct, retested live |
| A4 | A rejected place is never offered again; chat asks for a location pin | ✅ deployed 17 Oct, retested live |
| A5 | 2.5x more places (shops, banks, apartments…) | ✅ deployed 17 Oct, retested live |
| B1 | Telegram: an image sent as a file counts as a photo | ✅ deployed 18 Oct, **Tharun testing** |
| B2 | No filing without a read-back that names the place | ✅ deployed 18 Oct, **Tharun testing** |
| B3 | Browser: optional mobile number for the call-back | ✅ deployed 18 Oct, **Tharun testing** |
| B4 | Telegram message on every status change | ✅ deployed 18 Oct, **Tharun testing** |
| B5 | Caller asking "what happened?" hears the full status | ✅ deployed 18 Oct, **Tharun testing** |
| B6 | Officer's fix photo is optional | ✅ done (`fde781c`), not yet pushed |
| B7 | Google Maps links give the exact spot (Telegram, browser) | ✅ done (`3d5ae3d`), not yet pushed |
| C1 | Note box says it is public | ✅ done (`fde781c`), not yet pushed |
| C2 | Photo comparison, in full, on the complaint page | to do (medium) |
| C3 | Gemma's steps in detail | to do (small) |
| C4 | "Calling the citizen…" shown live on the complaint page | to do (small), only if the call-back test passes |
| C5 | Photo GPS and time check | only if time is left before 1 PM |
| E1 | Same-named places ("MG Road") offered as distinct, described options | to do (medium) — **highest risk in a live demo** |
| E2 | Optional pincode for a precise area | to do (medium) |
| E3 | Same problem, same area: count, map badge, priority | mostly built; to do: radius per kind of problem (small) |
| D1 | Judge answers and demo script updated | to do, last |
| D2 | Morning steps: reset, smoke test, rehearse, backup video | Vinay, after the code freeze |

---

## 2. Done on 17 Oct (from Tharun's first and second reports)

| Commit | What | Why |
|---|---|---|
| `e2077c0` | `gazetteer.find`: every namesake of the area counts (`area_centres`); a place in the area whose distinctive words match ranks first; a place outside the area is never read back | "St. Mary's School, Dasarahalli" pinned a school 15 km away in Kothanur |
| `52022ad` | A linked report's call links to the report row; the complaint page lists "Also reported by" with each person's details and conversation | A Telegram report looked replaced by an earlier phone call ("fabricated") |
| `5d33be9` | `LanguageLock.instant` for chats: follow a clear change at once, never ask; replies under 3 words never flip it | Each language change cost a turn asking "shall we continue in …?" |
| `97d57a9` | Prompt: never re-offer a rejected place; fall back to the area plus the landmark in words; chats ask for a location pin first | St. Mary's Convent is not on OpenStreetMap; the bot offered the namesake twice |
| `6ba5ebb` | `build_places.py` fetches every named shop, bank, ATM, restaurant, pharmacy, fuel station, office, apartment, building and layout; street furniture left out. 26,935 → 65,755 places | People give directions by shops and banks |

---

## 3. Done on 18 Oct (morning), deployed, being tested

### B1 — Telegram: an image sent as a file (`7072e06`)
- **Value:** citizens on Telegram Desktop (which always sends `.webp` as a file) and anyone who picks "send as file".
- **Simplest version:** `telegram.py` treats a `document` whose `mime_type` starts with `image/` exactly like a photo. The real type is still checked from the bytes (`vision.image_type`) before Gemma sees it.
- **Replaces:** the silent drop (CV-1013 kept only the caption).
- **Misuse:** a non-image file is still ignored; size capped at 5 MB by the download.

### B2 — No filing without a read-back (`d6ded83`)
- **Value:** every citizen; the read-back is a claim we make to judges.
- **Simplest version:** the conversation records the clerk's last message (`ToolState.last_reply`). `file_complaint` refuses unless that message names the place (any distinctive word of its names). Refused **at most once** per complaint (`readback_refused`), so a read-back in words we can't match never traps a caller.
- **Replaces:** trusting Gemma's own `caller_confirmed` flag alone (CV-1013 filed straight after "how long has it been?").
- **Misuse / limit:** a message that names the place but isn't a full read-back still passes; the once-only valve means a determined model can file on the second try.

### B3 — Browser citizens can leave a number (`5e6ca4e`)
- **Value:** browser citizens, who could not be reached at all.
- **Simplest version:** after filing, `/try` shows an optional box. `POST /api/try/contact` accepts a 10-digit Indian mobile (6–9 first digit, `+91`/`0` prefix allowed), seals it as `phone:+91…` (same as a phone caller) and stores it on the report row. The existing call-back rings it.
- **Replaces:** nothing; fills the "no way to reach the citizen" gap.
- **Misuse:** someone can enter another person's number, who then gets one call. A real service verifies by OTP over SMS (needs DLT registration): **planned, not built**. Refused on sensitive reports; rate-limited like the rest of `/try`.

### B4 — Telegram updates on every status change (`4e102c5`)
- **Value:** Telegram citizens, who heard nothing between filing and the fix.
- **Simplest version:** `followup.notify_update` runs in the background after Start work, Re-route (names the new office), Reopen and Mark fixed. It messages **every** chat reporter of the problem (original and linked reports), in their language (Kannada, Hindi, English), with the officer's note. On "fixed" the original reporter gets the "is it really fixed?" question instead, so only the others get the message.
- **Decided by Vinay:** phone and browser citizens are **called once, after the fix**; no SMS.
- **Misuse:** the officer's note is sent to the citizen as written; see C1.
- **Tests:** `tests/test_updates.py`; `tests/conftest.py` fakes the contact lookup so no test reads the real database.

### B5 — "What happened to my complaint?" gives the full status (`0c93ba8`)
- **Value:** phone citizens, who otherwise hear only the fix call.
- **Simplest version:** `get_complaint_status` adds the office, the deadline, overdue or not, and the last three officer/citizen updates with notes. Gemma's photo verdict is left out of the notes.
- **Replaces:** the bare "the officer is working on it".

### B6 — The officer's fix photo is optional (`fde781c`)
- **Value:** officers whose fix can't be photographed (a pension paid, a bus route restored).
- **Simplest version:** `POST /complaints/{id}/fixed` takes the photo as optional. Without one, nothing goes to Gemma, the timeline says "marked fixed without a photo", and the page shows a public badge "No fix photo · the citizen's answer decides".
- **Replaces:** the hard rule "Mark fixed needs a photo".
- **Misuse:** officers could stop adding photos; the public badge makes that visible. The citizen's call-back answer is then the only check.

### B7 — Google Maps links give the exact spot (`3d5ae3d`)
- **Value:** Telegram and browser citizens: a link is more precise than any landmark, and covers places missing from OpenStreetMap.
- **Simplest version:** `app/places/maps_link.py` reads the coordinates from the link (`!3d…!4d…`, `?q=lat,lon`, `@lat,lon`). Short links (`maps.app.goo.gl/…`) are opened one hop at a time until the coordinates appear. The spot then works exactly like a location pin (`chat.pin_note`): Bengaluru only, filed there without asking where. The welcome message and the clerk's "ask for a pin" rule mention links.
- **Misuse:** only Google addresses are ever opened (`maps.app.goo.gl`, `goo.gl`, `*.google.com`, `*.google.co.in`); any other hop stops it, so a link can't make our server visit another website or an internal address. Unreadable link → the clerk asks for a landmark.
- **Not yet tested with a real short link:** Tharun to share one from the Google Maps app.

### C1 — The note box says it is public (`fde781c`)
- One hint line under the note box: "Shown on the public timeline and sent to the citizen."

---

## 4. To do today, in order (code freeze 1 PM)

### Image analysis by Gemma — what it does today, and what C2 adds
Gemma 4 31B looks at photos in two places:
1. **A citizen's photo (Telegram):** `vision.look_at_problem` describes it ("a deep pothole on a tarred road"), guesses the category and severity (1–5), and flags danger to life. The clerk is told, so it doesn't ask what the photo already shows. Saved with the photo; **not shown anywhere yet**.
2. **The officer's fix photo:** `vision.check_fix` compares it with the complaint, and with the citizen's photo when there is one: looks fixed / not fixed / can't tell, same place likely, and a reason. **Only a small badge is shown.**

Both are advice: Gemma never changes a status. C2 below makes all of it visible.

### C2 — Photo comparison, in full (medium)
- **Value:** officers and judges see *why* Gemma thinks it's fixed; the most visible use of Gemma's vision.
- **Today's gap:** `vision.check_fix` already sends the citizen's photo as a second image and asks `same_place_likely`, but the page shows only the verdict and reason; the same-place answer and Gemma's description of the citizen's photo (`what_i_see`, severity) are never shown.
- **Simplest version:**
  - Backend, `vision.py`: the fix prompt also asks for `matching` (things seen in both photos: a wall, a tree, a sign, road markings), `differences`, and `confidence` (low/medium/high). Cleaned by code like the other fields (lists of at most 5 short strings, known values only).
  - Frontend, `ComplaintPage.tsx`: a "Photo check" card with the citizen's photo and the fix photo **side by side**, then: Gemma's verdict, same place (yes / no / can't tell / "no citizen photo to compare"), what matches, what differs, confidence, the reason, and the model. Under the citizen's photo: what Gemma saw and the severity.
- **Replaces:** the small verdict badge under each photo.
- **Misuse / limit:** Gemma can be fooled by a photo of a different, similar road. It stays **advice**; the citizen's call-back answer decides. Say so on the card.
- **Tests:** `test_vision.py` (cleaning of the new fields), `ComplaintPage.test.tsx` (the card renders both photos and the comparison).

### C3 — Gemma's steps in detail (small, front-end only)
- **Value:** judges and officers see the clerk's reasoning, not just its actions.
- **Today's gap:** `steps.ts` turns `find_nearby_complaints` into "Using find_nearby_complaints" / "Done", and hides what Gemma chose.
- **Simplest version:** every step gets a full sentence from data already saved with it:
  - place search: what was searched, the area, the top matches with confidence and distance from the area, and whether a warning was given;
  - duplicate check: "Checked for the same problem within 150 m → CV-1004, 40 m away, 1 report" or "nothing nearby";
  - filing: category, urgency, office and its deadline, "added to CV-… as report N", or why it was refused (e.g. "read it back first");
  - each step has a "details" fold-out with the raw inputs and outputs.
- **Replaces:** the one-line descriptions.

### C4 — "Calling the citizen…" shown live (small) — only if the call-back test passes
- **Value:** the demo: the audience sees the call-back happen.
- **Simplest version:** the complaint page listens to the server's existing `callback` and `complaint_updated` live events (`useLiveEvents`) for its own tracking ID: shows "Calling the citizen…" / "Asked on Telegram…", then the answer, and reloads the complaint.
- **Replaces:** a manual refresh.

### C5 — Photo GPS and time check (medium) — only if time is left before 1 PM
- **Value:** a fact, not an opinion: "taken 30 m from the complaint, 2 h after it was filed".
- **Simplest version:** read the EXIF location and time from the officer's uploaded photo; show the distance from the complaint pin and whether it was taken after filing.
- **Limit:** Telegram strips EXIF and many phones turn location off; it helps only sometimes. Never blocks marking fixed.

### E1 — Same-named places, offered as distinct options (medium)
- **Value:** every caller who names a common place; a judge may well say "MG Road".
- **Found 18 Oct:** `find("MG Road")` ranks a village road "M G Road" at the city's western edge (13.10, 77.40) first, ahead of the central MG Road (spelled "Mahatma Gandhi Road" in OpenStreetMap); short look-alike names ("OMG", "MIG") reach the list because "road" is dropped from the query and "mg" is tiny; and matches carry no area, so the clerk can't ask "the one near Trinity, or the one in Yelahanka?".
- **Simplest version:**
  - well-known initials expand before searching: MG → Mahatma Gandhi, KG → Kempegowda, JC → Jayachamarajendra, KR → Krishna Rajendra;
  - a query of 3 letters or fewer only matches names that are the same letters, never a fuzzy look-alike;
  - each match carries **where** it is: the nearest neighbourhood or suburb ("near Shivajinagar");
  - points of one long road within 4 km count as one option, so a single road is never offered as three;
  - up to 4 genuinely different places are returned, and the clerk asks the caller to choose, naming each by where it is.
- **Replaces:** the top-scoring match being read back on its own.
- **Tests:** "MG Road" offers the central one with its area; "MG Road, Yelahanka" (if one exists there) picks that one; "OMG" never matches "MG Road".

### E2 — Optional pincode (medium)
- **Value:** callers who know their pincode get the right area, even when the area's name is shared ("Dasarahalli" is three places).
- **Data, no new source:** our cached OpenStreetMap download holds `addr:postcode` on many places: **134 Bengaluru pincodes**, 111 with 5+ points. The median point of each is its centre (560057 → 13.049, 77.509, T. Dasarahalli; 560001 → MG Road; 560064 → Yelahanka). Built into `data/pincodes.json` by `build_places.py`.
- **Simplest version:** `find_place` takes an optional `pincode`; its centre acts like the area's centre (places within 4 km come first, others are not read back). The clerk may ask **once**, and only when the place is unclear: "if you know the pincode, tell me; otherwise that's fine". Never required. A pincode we don't know is ignored.
- **Misuse:** a wrong pincode pulls the search towards the wrong area; the read-back (which names the place) catches it.

### E3 — Same problem, same area (mostly built)
- **Built:** a second report of the same problem within **150 m** is added to the first: one tracking ID, the dashboard row says "N reports", the map pin shows a count badge, priority rises 6 points per extra report, urgency rises by one every 3rd report. Live example: CV-1004 (phone + Telegram).
- **Limit:** 150 m suits a pothole or a streetlight, but not a whole street without water or power.
- **Simplest version:** the radius depends on the kind of problem: 150 m for point problems (road, streetlight, trees, drainage), 500 m for area-wide ones (water, electricity, garbage). Gemma still decides whether it is the *same* problem and tells the caller.
- **Misuse:** a wider radius could merge two different problems; Gemma's check and the caller's read-back stay in place.

### D1 — Documents (last)
- `docs/judge-questions.md`: Q9/Q10 (photo check, transparency), browser call-back numbers, Telegram updates, what was tested live today; WhatsApp stays "built, not connected".
- `docs/demo-script.md`: the call-back moment after "Mark fixed" (~20 s): the phone rings on stage, answer "ಇಲ್ಲ, ಇನ್ನೂ ಕತ್ತಲು ಇದೆ", it reopens. Fallback: no ring in 20 s → "the call-back is on its way", move on.

---

## 5. Testing (Tharun, after each push)

1. **Phone call-back:** a **new** phone complaint → officer: Start work, photo, Mark fixed → the phone rings → "no" → reopened. (CV-1004 could not ring: filed 16 Oct, before numbers were stored.) Only 9 AM–8 PM.
2. **Telegram:** an image sent as a file appears in Photos; Start work with a note → Telegram message with the note; re-route → message names the office.
3. **Browser:** file on `/try`, leave a number, mark fixed → the phone rings.
4. **Phone:** call in, "what happened to my complaint?" → office, overdue or not, latest update.
5. **Read-back:** in any channel, the bot reads the complaint back (problem, place, since when) before "registered".

---

## 6. After the hackathon (not built — say so plainly)

| Item | Why not today |
|---|---|
| SMS: "ticket created", status updates, an upload link for phone callers | India requires DLT registration of every business SMS template (TRAI): takes days |
| OTP check of browser numbers | Needs SMS (above) |
| Keeping voice notes (only their text is kept) | Storage and privacy decision |
| Media in a file store instead of the database | Fine at this size |
| Google Places for places missing from OpenStreetMap | A billing decision |
| Per-officer accounts; notifying seniors when a complaint is overdue | "Escalated" is a label today |
| Sending complaints into government systems | CSV export is the bridge |
