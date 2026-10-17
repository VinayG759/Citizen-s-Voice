STATUS: waiting for the next Sara

> For the next Sara: you are the orchestrator (method in ~/.claude/CLAUDE.md). Vinay runs on Anthropic API credits: keep sessions short. His friend **Tharun** is testing the LIVE site now with a test sheet; Vinay will paste Tharun's report. Start there: triage the report, fix what failed, redeploy.

# Handoff — Citizen's Voice, 17 Oct 2026 (evening)

Submission is **Sun 18 Oct, 3:30 PM IST**.

## Where things stand

- **Branch:** `phase-6-loop`, last commit `634f553` (+ this note). Pushed. `main` on GitHub = `phase-6-loop` in both repos.
- **Live:** https://citizens-voice-production.up.railway.app — Railway on **Tharun's** account, builds from **`TharunMurugesh/citizens-voice` branch `main`**. To deploy: `git push https://github.com/TharunMurugesh/citizens-voice.git phase-6-loop:main` (Vinay runs pushes; the sandbox blocks them for Claude). It went live ~50 s after the push on 17 Oct; all 7 pages load, `/health` ok.
- **Tests:** backend all pass except `tests/test_followup.py`, whose websocket timing tests are **flaky** (fail ~half the runs with or without any change; a busy laptop makes it worse). Web 28 pass, build ok.
- **Laptop:** server stopped; tunnels are throwaway. `.env` `PUBLIC_BASE_URL` points at a dead quick tunnel (harmless).
- **Uncommitted, leave it:** `.gitignore` gained `.gstack/` (from the gstack tool), not ours to commit unasked.

## Done on 17 Oct

- **Telegram tested for real:** CV-1008 (typed, English, Rajajinagar → BESCOM) and CV-1009 (Kannada voice notes, Kadu Malleshwara Temple → BBMP), both correct end to end.
- `cfbcbb2` a place name inside Kannada (Sarvam labels it English) no longer flips the reply to English; chat closing shows the ID once, no "thanks for calling".
- `4455c6c` try-it rate limit keys on Railway's `X-Real-IP` (was DigitalOcean's header, so all judges shared one limit). Railway staff say their edge overwrites it; some users report oddities, so verify on the live site.
- `7eaef73` fix-photo check waits 25 s for Google (`PHOTO_CHECK_GOOGLE_TIMEOUT_S`) before OpenRouter, not 60.
- `634f553` **Sangam-style sidebar** merged (Live desk, Complaints with filters, Map, Offices, Emerging issues, Morning brief + CSV). Vinay approved it.
- `f3b81db` map pins: Google-style teardrops coloured by urgency, report-count badge, selected pin bigger (replaces the circles). `39dc8de` responsive fixes for phones (CSS only: feed rows, 40px tap targets, filters two to a row). **Committed locally, NOT deployed:** Vinay said not to push until Tharun's report is in; ship them with the report's fixes. Not yet seen by Vinay on real map tiles.
- `docs/deploy-readiness.md`: the Railway audit, with the full env-var table.
- `docs/judge-questions.md` Q29 updated (Telegram text + Kannada voice really tested).
- Test sheet for Tharun (private artifact, Vinay shares it): https://claude.ai/artifact/KavMUpcVckdEJDUErNGy1p — 26 checks, copyable report.

## Not yet confirmed (Vinay was doing these when this note was written)

1. **Railway variables** — the sandbox blocked probing them. Must match `.env`: `CALLER_HASH_KEY`, `CONTACT_ENCRYPTION_KEY`, `OFFICER_PASSCODE`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, plus DB, Gemini, OpenRouter, Sarvam, Vobiz, and `PUBLIC_BASE_URL=https://citizens-voice-production.up.railway.app`. Same DB as the laptop, so the keys must be identical. Saved variables need a **Deploy** to apply.
2. **Telegram webhook → Railway:** Vinay runs (PowerShell, from `backend/`): `$env:PUBLIC_BASE_URL="https://citizens-voice-production.up.railway.app"`, `python -m scripts.telegram_webhook`, `... --check`, `Remove-Item Env:PUBLIC_BASE_URL`. A 401 in `--check` = secret missing or different on Railway.
3. **Vobiz → Railway:** Answer URL `…/api/phone/answer`, Hangup URL `…/api/phone/hangup`, both POST.

## What is left (in order)

1. Triage Tharun's report; fix; redeploy (push to Tharun's main).
2. After his photo / pin / call-back results, update `docs/judge-questions.md` Q20/Q21 to match what really happened.
3. Judging morning: `python -m scripts.reset_demo` (dry run, read the host) → `--yes`; then `python -m scripts.smoke_test https://citizens-voice-production.up.railway.app` must say READY. Reset deletes all complaints, Tharun's TEST ones included.
4. Rehearse `docs/demo-script.md` (now says "click Offices" etc.) three times; record the backup video.

## Vinay's open decisions

- **WhatsApp:** not configured anywhere (no `WHATSAPP_*` in `.env`). Skip for the demo, or set it up?
- **WhatsApp voice replies** (needs ffmpeg) and the 24-hour template — recommended: skip.
- **Rotate the keys** exposed earlier in chat or screenshots.
- **`/api/brief` officers-only?** It is today.

## Known caveats (after the deadline)

- Chats keep one conversation per chat in memory: after filing, the next complaint's transcript starts with the tail of the last ("ok thank u").
- Google's Gemma returned 500s and timeouts all afternoon on 17 Oct; replies came via OpenRouter, slower.
- Flaky `test_followup.py` (above).
- Chats, the call-back wait and retry timers live in memory: a Railway redeploy forgets them. Keep one replica.
