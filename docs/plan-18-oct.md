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
| C1 | Note box says it is public | to do (tiny) |
| C2 | Photo comparison, in full, on the complaint page | to do (medium) |
| C3 | Gemma's steps in detail | to do (small) |
| C4 | "Calling the citizen…" shown live on the complaint page | to do (small), only if the call-back test passes |
| C5 | Photo GPS and time check | only if time is left before 1 PM |
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

---

## 4. To do today, in order (code freeze 1 PM)

### C1 — The note box says it is public (tiny)
- **Value:** officers, who don't know the note is public and is now sent to the citizen.
- **Simplest version:** one hint line under the note box in `OfficerActions` (`ComplaintPage.tsx`): "Shown in the public timeline and sent to the citizen."

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
