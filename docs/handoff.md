STATUS: taken over 2026-10-18

> For the next Sara: you are the orchestrator (method in ~/.claude/CLAUDE.md). Vinay runs on Anthropic API credits: keep the session short. **Submission closes TODAY, Sun 18 Oct, 3:30 PM IST.** Your job: implement the rest of [plan-18-oct.md](plan-18-oct.md) in the order below, **code freeze 1:30 PM**, then push, test, rehearse. Read the plan's sections E1, E2, E3 and C2 before starting; they hold the findings and the simplest version of each.

# Handoff — Citizen's Voice, 18 Oct 2026 (around noon)

## Where things stand

- **Branch:** `phase-6-loop`. `main` on GitHub = `33ae18a` in both repos; only `e24f4fd` (plan docs) and this note are unpushed.
- **Live:** https://citizens-voice-production.up.railway.app, Railway on Tharun's account, builds from `TharunMurugesh/citizens-voice` `main`. **Vinay pushes** (Claude's pushes are blocked): `git push origin phase-6-loop phase-6-loop:main` (`origin` pushes to both repos). Live ~1 min later with no downtime and no visible version: ask Vinay to check Railway → Deployments → Active.
- **Tests:** backend 226 pass (`python -m pytest -q --ignore=tests/test_followup.py`); `tests/test_followup.py` is **flaky** (fails ~1 run in 3 with or without any change). Web 35 pass, build ok (`npx vitest run`, `npm run build` in `web/`).
- **Test safety:** `backend/tests/conftest.py` fakes `repo.reporter_contacts`, so officer tests never read the real database. Keep tests off the real DB (it is shared with production).
- **Uncommitted, leave it:** `.gitignore` gained `.gstack/` (from the gstack tool).
- **Editing tip (Windows):** Python source files use CRLF. Heredocs in Git Bash mangle `\` line continuations and can choke on quotes: write edit scripts to the scratchpad and run them with `python <file>`, or use the Edit tool.

## Done today (18 Oct), all pushed and live

| Commit | What |
|---|---|
| `7072e06` | Telegram: an image sent as a file counts as a photo (CV-1013's webp was dropped) |
| `d6ded83` | No filing without a read-back that names the place (refused at most once) |
| `5e6ca4e` | Browser `/try`: optional mobile number after filing, used for the call-back |
| `4e102c5` | Telegram citizens get a message on every status change, with the officer's note (all reporters of the problem) |
| `0c93ba8` | Phone caller asking "what happened?" hears office, deadline, overdue, latest updates |
| `fde781c` | Officer's fix photo optional ("No fix photo · the citizen's answer decides" badge); note box says it is public |
| `3d5ae3d` | Google Maps links give the exact spot (Telegram + browser); short links followed via Google hosts only |

**Decided by Vinay:** Telegram = a message on every update; phone and browser = **one call after the fix**, and full status whenever they call in. No SMS. WhatsApp out of scope today.

## Waiting on Tharun's test report (Vinay will paste it): triage it FIRST

1. **Phone call-back:** a NEW phone complaint → officer Start work → Mark fixed → does the phone ring? (CV-1004 never could: filed 16 Oct, before numbers were stored.) Only 9 AM–8 PM IST (`CALL_HOURS`, `backend/app/followup.py`). The outbound Vobiz call has **never run for real**: if it fails, Railway's logs say why (Vinay can read them).
2. Telegram: image as a file shows in Photos; Start work with a note → message; re-route → names the office.
3. Browser: leave a number, mark fixed → rings.
4. Phone: "what happened to my complaint?" → full status.
5. A real `maps.app.goo.gl` short link (never tested for real) in Telegram and `/try`.
6. Mark fixed without a photo → badge, call-back still happens.

## To do, in this order (agreed with Vinay; freeze 1:30 PM)

1. **E1 — "MG Road" and shared names** (~45 min). `find("MG Road")` ranks a village "M G Road" (13.10, 77.40) first; central MG Road is "Mahatma Gandhi Road" in OSM; "OMG"/"MIG" match because "road" is a filler word and "mg" is tiny. Expand MG/KG/JC/KR; ≤3-letter queries match only the same letters; each match gets "where" (nearest suburb/neighbourhood); one long road within 4 km = one option; up to 4 options; prompt: ask the caller to choose by area. Files: `backend/app/places/gazetteer.py`, `backend/app/tools/clerk_tools.py` (find_place output), `backend/app/clerk/prompt.py`, `backend/tests/test_places.py`. Re-run the whole place test file: earlier fixes (Dasarahalli, Koramangala, Presidency gate) must still pass.
2. **E3 — radius per kind of problem** (~10 min). `repo.nearby_open(radius_m=150)` and `find_nearby_complaints` in `clerk_tools.py`: 150 m for road, streetlight, trees, drainage; 500 m for water, electricity, garbage. Update the tool description ("about 150 m").
3. **C2 — photo check card** (~45 min). `backend/app/vision.py` `check_fix`: also ask for `matching` and `differences` (≤5 short strings each, cleaned by code) and `confidence` (low/medium/high). `web/src/ComplaintPage.tsx`: a "Photo check" card, citizen photo and fix photo side by side, verdict, same place (yes/no/can't tell/"no citizen photo to compare"), matches, differences, confidence, reason, model; under the citizen photo, Gemma's `what_i_see` and severity (already saved in `Photo.gemma_verdict`, never shown). Say on the card that it is advice; the citizen decides. Tests: `test_vision.py`, `ComplaintPage.test.tsx`.
4. **E2 — optional pincode** (~30 min), only if done by 1:30. `scripts/build_places.py` writes `data/pincodes.json` from the cached Overpass tiles (`backend/.cache/overpass/`, median point per `addr:postcode` starting 56, ≥5 points; 111 qualify). `find_place` takes an optional `pincode` that acts as the area centre. Prompt: may ask once, only when the place is unclear; never required.
5. **Skip today, say "planned":** C3 (Gemma's steps in detail), C5 (photo GPS/time). C4 (live "Calling the citizen…" on the complaint page) only if the call-back test passed AND there is time.
6. **D1 docs at the freeze:** `docs/judge-questions.md` (photo optional, Maps links, browser numbers, Telegram updates, what was tested live today) and `docs/demo-script.md` (the call-back moment after Mark fixed, ~20 s; fallback if no ring in 20 s: "the call-back is on its way", move on). Update `docs/plan-18-oct*.md` status tables.

## After the freeze (Vinay)

1. Push; Tharun retests the new items.
2. From `backend/`: `python -m scripts.reset_demo` (dry run: read the host it prints) → `--yes`; then `python -m scripts.smoke_test https://citizens-voice-production.up.railway.app` must say READY. Reset deletes every complaint, Tharun's test ones included.
3. Rehearse `docs/demo-script.md` three times; record the backup video **before 8 PM** (no call-back at night).
4. Submit by 3:00 PM.

## Vinay's open decisions

- Rotate the exposed keys: recommended **after** judging.
- `/api/brief` officers-only: recommended keep.
- After the hackathon: SMS (needs DLT registration), OTP for browser numbers, Google Places, per-officer accounts, voice-note storage, WhatsApp setup.

## Known caveats

- Chats keep one conversation per chat in memory; chats, call-back waits and retry timers are forgotten on a redeploy. Keep one replica.
- Google's Gemma API is often slow or erroring; replies then come via OpenRouter, slower.
- Places missing from OpenStreetMap: covered by a location pin, a Google Maps link, or the area plus the landmark in words.
