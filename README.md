# Citizen's Voice

**Report a civic problem by phone — any phone, no internet, in Kannada, Hindi or English. Gemma 4 acts as the municipal clerk.**

A citizen calls a Bengaluru number and describes a pothole, a water cut or a dead streetlight in the
language they speak every day. Gemma 4 understands the complaint, asks what is missing until the exact
location is pinned, reads it back, files it and speaks a tracking number. Officials watch complaints
arrive live on a map, with Gemma's reasoning shown beside each one.

Built for **Hacktoberfest Hack Day Bengaluru 2026** — Track 1, *Best Use of Gemma 4* (problem statement
G2, voice-first AI). All code written from 14 October 2026.

## Status — honest

| Phase | What | State |
|---|---|---|
| 0 | Foundation: API, dashboard shell, database, health check | ✅ merged 16 Oct |
| 2 | Gemma clerk + try-it page (speak or type in the browser) | ✅ built 16 Oct; 12/12 scripted conversations pass against the real Gemma; browser microphone not yet tried by a person |
| 1 + 3 | Phone line: Vobiz audio stream → end-of-speech detection → Sarvam → Gemma clerk → Sarvam voice; "one moment" filler; silence nudge; hang-up after filing | ✅ built 16 Oct and tested with a simulated call (real Sarvam + real Gemma); **not yet tried on a real phone** — needs the live server URL |
| 4–8 | Live dashboard + map, smarter clerk, photo check + call-back, demo hardening | planned |

The full plan is in [docs/implementation-plan.md](docs/implementation-plan.md)
([plain-language version](docs/implementation-plan-simple.md)).

## How it works

```
Caller ─► Vobiz (phone line) ─► Sarvam (speech → text) ─► Gemma 4 clerk ─► tools (place lookup, file complaint…)
                                                               │
Caller ◄───────────── Sarvam (text → speech) ◄─────────────────┘        Dashboard ◄─ live events
```

**Gemma suggests, code checks:** map coordinates only ever come from real place data, and a complaint
is filed only when the place is known and the caller has confirmed the read-back.

**What Gemma does:** runs the whole conversation in the caller's everyday language, decides when to
look up a place (`find_place` over 10,201 OpenStreetMap places in Bengaluru North, Kannada names
included), when to raise an emergency, when to check a complaint's status, and when to file. Every
decision is shown live as "Gemma's steps". If a reply slips into another script (Tamil, Telugu…),
code catches it and asks again.

**Try it:** open `/try` on the live site, press *Start talking*, and speak (or type) in Kannada,
Hindi or English.

## Built with

- **Gemma 4** (26B A4B for live calls, 31B for background reasoning) via the **Gemini API**; OpenRouter as fallback
- **Sarvam AI** — speech-to-text and text-to-speech for Indian languages
- **Vobiz** — Indian phone number and call audio
- **OpenStreetMap** — map and place data (© OpenStreetMap contributors, ODbL)
- **Supabase** (Postgres), **FastAPI**, **React + Vite**, hosted on **DigitalOcean App Platform**

## Run it locally

Requirements: Python 3.11, Node 22+.

```bash
cp .env.example .env            # fill in the values

# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate    # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head            # creates the tables in DATABASE_URL — check it points where you think
uvicorn app.main:app --reload   # http://localhost:8000/health

# Dashboard (development, hot reload on :5173)
cd web
npm install
npm run dev
```

Production: one container (see [Dockerfile](Dockerfile)) — FastAPI serves the API and the built dashboard.

## Tests

```bash
cd backend && python -m pytest          # 38 tests: safety rules, tools, try-it API, phone line (fakes, no network)
cd web && npm test                      # 7 tests
cd backend && python -m scripts.golden  # 12 scripted conversations against the REAL Gemma (no DB writes)
```

## Privacy

All tables have row-level security enabled, so Supabase's public API cannot read them (done).
Callers' phone numbers will be stored only as a keyed hash plus the last four digits, and the dashboard
will never show a full number (built with the phone line, Phase 1–3).

## Licence

[Apache-2.0](LICENSE)
