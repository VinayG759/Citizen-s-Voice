# Deploy readiness — Citizen's Voice on Railway

Audit of branch `deploy-check` (from `phase-6-loop` at `550c5cb`), 17 Oct 2026. Read-only: no database,
no network calls to Railway, Vobiz, Telegram, WhatsApp or the AI providers, nothing spent. The worktree has
no `.env`, like Railway.

## What was run

| Check | Result |
|---|---|
| Backend tests, fresh folder, no `.env`, no `DATABASE_URL` | **203 passed**, 0 failed. Nothing secretly depends on `.env`. |
| Web tests | **17 passed** (3 files) |
| Web build (`npm ci` + `npm run build`, the Dockerfile's first stage) | builds; `dist/` has `index.html` and assets |
| `requirements.txt` into a **clean** virtual environment, then import `app.main` and every script | all import. No missing dependency. |
| Migrations, rendered as SQL only (no database touched) | two migrations apply in order; every column of every model is covered; the tracking-number sequence is created |
| `docker build .` | **Skipped.** Docker is installed but its engine is not running. Not started. |

## BLOCKERS

**1. Officer access can be forged unless `CALLER_HASH_KEY` is set.** Officer sign-in tokens are signed with
`CALLER_HASH_KEY`, whose default is the public string `dev-only-not-secret`. Verified: with the default key
and *no passcode set at all*, a token anyone can compute is accepted. That token allows marking fixed,
rerouting, the CSV export, the Morning Brief and reading sensitive reports. Set a long random
`CALLER_HASH_KEY` **before the site is public**, and do not change it afterwards (see Risks).

**2. The browser page's rate limit would be shared by every visitor.** `/try` limits turns per visitor
(20 per 10 minutes) using the header `do-connecting-ip`, which is DigitalOcean's. Railway does not send it
(I could not test Railway itself). Without it, every visitor appears as the proxy's address, so after about
four conversations *everyone* gets "too many turns". That breaks judges trying `/try` at once. Needs a
decision on which header Railway can be trusted to set (the Dockerfile deliberately refuses to trust
`X-Forwarded-For`, which visitors can fake), or a higher limit for the demo.

**3. The container will not start without a working `DATABASE_URL`.** The start command runs
`alembic upgrade head` first; with no database, a wrong address or a wrong pooler it exits and Railway
restarts it in a loop. Use the Supabase **session** pooler (port 5432). The transaction pooler (6543) is
not safe with this driver. Direct Supabase hosts may be IPv6-only; I believe Railway's outbound traffic is
IPv4, so use the pooler (not verified).

**4. `main` holds only Phase 0.** It is 32+ commits behind `phase-6-loop`. Deploying `main` as it is would put
a placeholder online. Merge first, or point Railway at `phase-6-loop`.

## RISKS

- **A malformed `CONTACT_ENCRYPTION_KEY` breaks every phone call and chat.** It must be a valid Fernet key.
  Verified: a bad value raises an error inside the code that runs at the start of each call and chat.
  Left empty it fails quietly instead: no contact is stored, so the call-back after a fix can never reach
  anyone.
- **Hang-up fails silently without the Vobiz credentials.** `hang_up` returns false and the call stays open
  after the tracking ID is read until someone hangs up. Also no helpline number shows on the dashboard.
- **The call-back needs `PUBLIC_BASE_URL`.** Inbound calls work without it (the address comes from the
  request's Host header). The outgoing call-back logs "not placed" and does nothing without it.
- **Changing `CALLER_HASH_KEY` later** logs officers out and breaks "what happened to my complaint?" for
  complaints filed before the change, because stored caller hashes no longer match. Choose it once.
- **Everything live is in memory on one server:** try-it sessions, phone stream tokens, call and chat rate
  limits, chat conversations, "awaiting a call-back reply", retry timers, the dashboard's live subscribers.
  A restart or redeploy drops calls in progress and forgets all of it. Keep Railway at **one** replica.
- **Nothing is written to disk.** Nothing on Railway's disk is lost on restart (checked: only in-memory
  audio buffers).
- **Every start re-speaks about 36 fixed phone lines through Sarvam** (greeting, "one moment", and so on) so
  the first caller doesn't wait. It costs a little Sarvam credit on each deploy or restart.
- **A missing key degrades quietly, with no crash:** no `SARVAM_API_KEY` means nobody can be heard or
  answered (the clerk says "sorry" every turn); no `GEMINI_API_KEY` and no `OPENROUTER_API_KEY` means the
  clerk says "technical problem" every turn; with only Gemini there is no fallback when Google refuses
  (it did, often, in testing).
- **The clerk's "today" uses the server's clock** (`date.today()`), which on Railway is UTC. Between 00:00
  and 05:30 IST it is yesterday's date. Minor.
- **`.env.example` is out of date:** it lacks `PUBLIC_BASE_URL`, the Telegram and WhatsApp variables, the
  feature switches and the model settings.
- **The API documentation pages (`/docs`, `/openapi.json`) are public.** They list endpoints, not data.
- **The handoff note's Railway list leaves out** `OPENROUTER_API_KEY`, the four `WHATSAPP_*` variables
  and the `VOBIZ_*` ones (it only says "existing"), and does not say which database pooler to use.

## ENV VARS

Read by `backend/app/settings.py`, plus `PORT` read by the Dockerfile's start command. "Required" means the
feature or the deploy fails without it.

| Variable | Default | If missing or wrong |
|---|---|---|
| `DATABASE_URL` | empty | **Required.** Container exits at start (migrations); `/health` says degraded. Session pooler. |
| `PORT` | `8080` (Dockerfile) | Railway sets it; the server listens on it. Fine. |
| `GEMINI_API_KEY` | empty | Silently uses OpenRouter instead. With neither key: every turn fails politely. |
| `OPENROUTER_API_KEY` | empty | No fallback when Google errors or takes over 2.5 s. |
| `SARVAM_API_KEY` | empty | **Required for voice.** No hearing or speaking; fixed lines not prepared. |
| `CALLER_HASH_KEY` | `dev-only-not-secret` | **Insecure default** (Blocker 1). Set once, long and random. |
| `CONTACT_ENCRYPTION_KEY` | empty | Empty: no call-back is possible. Malformed: calls and chats crash. Valid Fernet key only. |
| `OFFICER_PASSCODE` | empty | Empty: sign-in disabled (but see Blocker 1). Needed to mark anything fixed. |
| `PUBLIC_BASE_URL` | empty | Call-back not placed. Inbound uses the Host header. Set to the Railway address. |
| `VOBIZ_AUTH_ID`, `VOBIZ_AUTH_TOKEN` | empty | Calls never hang up by themselves; no call-back. |
| `VOBIZ_PHONE_NUMBER` | empty | No helpline number on the dashboard; no call-back. |
| `TELEGRAM_BOT_TOKEN` | empty | Telegram off (the webhook answers 404). |
| `TELEGRAM_WEBHOOK_SECRET` | empty | Telegram webhook refuses everything (401). |
| `WHATSAPP_ACCESS_TOKEN` | empty | WhatsApp off (404). |
| `WHATSAPP_PHONE_NUMBER_ID` | empty | Every incoming message ignored. |
| `WHATSAPP_VERIFY_TOKEN` | empty | Meta's one-time address check fails (403). |
| `WHATSAPP_APP_SECRET` | empty | Every WhatsApp webhook refused (401). |
| `FEATURE_PHOTO_CHECK` | `true` | Optional switch: `false` skips Gemma's photo look. |
| `FEATURE_CALLBACK` | `true` | Optional switch: `false` stops the call-back. |
| `LLM_LIVE_MODEL` | `gemma-4-26b-a4b-it` | Optional. |
| `LLM_BACKGROUND_MODEL` | `gemma-4-31b-it` | Optional. |
| `LLM_PRIMARY_TIMEOUT_S` | `2.5` | Optional: seconds before a live turn tries OpenRouter. |
| `SARVAM_STT_MODEL` | `saaras:v3` | Optional. |
| `SARVAM_TTS_MODEL` | `bulbul:v3` | Optional. |
| `SARVAM_TTS_SPEAKER` | `roopa` | Optional. |
| `SARVAM_TTS_PACE` | `0.95` | Optional. |
| `SARVAM_TTS_TEMPERATURE` | `0.7` | Optional. |
| `APP_VERSION` | `0.1.0` | Shown by `/health`. Cosmetic. |

## Docker and runtime, as read

- **Web front-end:** built in the Dockerfile's first stage (`npm ci`, `npm run build`) and copied to
  `/app/web/dist`, where `main.py` looks for it. Correct.
- **Runtime files:** `COPY backend/` brings `data/` (places and roads), `migrations/`, `alembic.ini`,
  `scripts/`. `.dockerignore` excludes only things the app never reads (`docs`, `.env`, caches, recordings).
- **Port:** the start command listens on `${PORT:-8080}` on `0.0.0.0`. Correct for Railway.
- **Migrations:** run automatically at every container start, not by hand. Safe to repeat (nothing to do once
  at the latest version). Any future migration will run against whatever database `DATABASE_URL` names.
- **Runs as a non-root user.** Nothing needs write access.
- **Stale text:** a Dockerfile comment still says DigitalOcean (see the fix draft below).

## Draft fixes (unreviewed; outside app logic)

Committed separately, only `.dockerignore` and a comment in the `Dockerfile`:
1. `.dockerignore` now also skips `**/.cache` (the 1+ GB map download cache) and `*.tsbuildinfo`, so a local
   `docker build` from a working folder doesn't copy them. Railway builds from git and is unaffected.
2. The Dockerfile comment about the client-IP header names the real situation (Blocker 2) instead of DigitalOcean.

Not drafted, because they touch app logic or need Vinay's choice: the client-IP header (Blocker 2), checking
the encryption key at start-up instead of at the first call, and a start-up refusal when `CALLER_HASH_KEY`
is still the default.
