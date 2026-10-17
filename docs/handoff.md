STATUS: taken over 2026-10-17

> For the next Sara: you are the orchestrator (method in ~/.claude/CLAUDE.md). Vinay now runs sessions on Anthropic API credits, so cost per prompt grows with context: keep sessions short and hand off early. Use Sonnet for workers. Telegram webhook: Vinay ran the registration commands on 17 Oct (07:30); ask him for the --check output and the result of his first /start + voice-note test.

# Handoff — Citizen's Voice, 17 Oct 2026

Read this alone; it is meant to be enough. Submission is **Sun 18 Oct, 3:30 PM IST**.

## Where things stand

- **Branch:** `phase-6-loop` in `C:\Users\vinay\Desktop\Citizen's Voice`. Working tree clean. Nothing pushed.
- **Last code commit:** `fe9b130` (places that share a name). This note is committed right after it.
- **Tests:** backend **203 passed**, web **17 passed**. The live-Gemma "golden" conversations were last run 16 Oct, **before** the call-back, Telegram, WhatsApp and places changes; not re-run since (it spends API quota).
- **`main` is 32 commits behind** `phase-6-loop` (main has only Phase 0). Everything below exists only on this branch until pull requests are merged.
- **Built (all tested with fakes unless stated):** phone line (real calls worked 16 Oct), browser try-it page, Gemma clerk with five tools, live dashboard and map, duplicate merging, offices and deadlines, overdue, "most urgent first" (open emergencies always first), office scorecard, officer sign-in, fix-photo check by Gemma 4 31B, call-back after "fixed" (phone, Telegram, WhatsApp), Telegram and WhatsApp chats (text, voice note, photo, location pin), emerging issues, Morning Brief (`/api/brief`, officers only), demo scripts (`reset_demo`, `smoke_test`), `docs/demo-script.md`, `docs/judge-questions.md`.
- **Not built:** sending complaints into government systems, per-officer accounts, overdue notifications, cost logging, load testing, WhatsApp messages outside its 24-hour window.

## What is live where

- **Railway** (the public site) was deployed on 16 Oct from an **earlier** build. I have not checked what it runs now; assume it lacks everything after Phase 5 until you look at the Railway dashboard.
- **Laptop:** on 17 Oct the server was started from `phase-6-loop` and a new Cloudflare quick tunnel was started, and its address was written to `PUBLIC_BASE_URL` in the main folder's `.env`. The sandbox then **blocked** further steps, so the server is **stopped** and the Telegram webhook was **not registered**. An older `cloudflared` process (PID 772) is still running; I could not stop it. A quick-tunnel address changes every time the tunnel restarts, so that `PUBLIC_BASE_URL` line is only valid while that exact tunnel runs.
- **Vobiz phone line** still points at an old, dead tunnel address. Phone calls to the laptop will not work until it is repointed. Nobody changed Vobiz.

## What is left (in order)

1. **Telegram live test (needs Vinay's go):** start the server (`uvicorn app.main:app --host 127.0.0.1 --port 8000` from `backend/`), confirm `/health`, make sure the tunnel address matches `PUBLIC_BASE_URL`, then `python -m scripts.telegram_webhook` and its `--check` option. Then message the bot: a text complaint, a photo, a location pin.
2. **Railway deploy:** merge the pull requests into `main` (or deploy `phase-6-loop`), then set Railway variables: `CONTACT_ENCRYPTION_KEY`, `OFFICER_PASSCODE`, `CALLER_HASH_KEY` (a long random value; the default is not secret), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, plus the existing database, Gemma, Sarvam and Vobiz ones. Set `PUBLIC_BASE_URL` to the Railway address, re-register the Telegram webhook against it, repoint Vobiz to it.
3. **Judging morning:** `python -m scripts.reset_demo` (dry run: read the host it prints), then `--yes` and type the host. Then `python -m scripts.smoke_test <live address>` must say READY. The reset **deletes all complaints and calls**.
4. **Rehearse** the 3-minute run in `docs/demo-script.md` three times on the real line (the Kannada call script has never been run end to end). **Record the backup video.**

## Vinay's open decisions

- **Photo-check speed:** it is slow because Google's timeout for the bigger model is long. Recommended: a shorter Google timeout so it falls back to OpenRouter sooner.
- **WhatsApp voice replies** need `ffmpeg` to make the voice-bubble format. Recommended: skip; replies arrive as a normal audio message.
- **WhatsApp template:** after 24 hours of silence WhatsApp only allows pre-approved template messages, so later call-backs need one (not built).
- **Rotate the keys** that were exposed earlier in chat or screenshots.
- **Should `/api/brief` stay officers-only?** It is today.

## Known caveats

- Chat conversations, "awaiting a reply to the call-back" and the retry timer live **in memory** on one server; a restart forgets them (the citizen can still confirm by calling the helpline).
- The Morning Brief in Kannada had a meaning slip (reported earlier); the English one is the one to show.
- Judge answers say plainly that the call-back and chat channels were tested with fakes, never with a real phone or chat. After the Telegram test, update `docs/judge-questions.md` Q20/Q21 to match what really happened.
- Places: a bare name shared by several places now picks the suburb nearest central Bengaluru and also offers a far-apart namesake, so the clerk may ask "which one?". Not yet measured on real calls.
- `PUBLIC_BASE_URL` in `.env` makes `tests/test_phone.py` read it; that test is now pinned so it no longer cares.
