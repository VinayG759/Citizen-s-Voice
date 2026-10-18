STATUS: waiting for the next Sara

> For the next Sara: you are the orchestrator (method in ~/.claude/CLAUDE.md). Vinay runs on Anthropic API credits: keep the session short. **Submission is today, Sun 18 Oct, 3:30 PM IST.** No new features: only preparation, and fixes for anything the rehearsal breaks.

# Handoff — Citizen's Voice, 18 Oct 2026 (early morning)

## Where things stand

- **Branch:** `phase-6-loop` (+ this note). `main` on GitHub = `phase-6-loop` in both repos.
- **Live:** https://citizens-voice-production.up.railway.app, Railway on **Tharun's** account, builds from `TharunMurugesh/citizens-voice` `main`. Vinay pushes (the sandbox blocks pushes for Claude): `git push origin phase-6-loop phase-6-loop:main` (`origin` pushes to both repos). Goes live ~1 min later, with no downtime and no visible version, so ask Vinay to check Railway → Deployments → Active.
- **Railway variables:** match `.env` (Vinay confirmed 17 Oct).
- **Tests:** backend all pass except `tests/test_followup.py`, which is **flaky** (fails ~1 run in 3 even without any change). Web 33 pass, build ok.
- **Uncommitted, leave it:** `.gitignore` gained `.gstack/` (from the gstack tool).

## Done on 17 Oct (evening), all deployed and re-tested by Tharun on the live site: "everything working"

From Tharun's test report (Telegram, St. Mary's School, T. Dasarahalli):
- `e2077c0` **Places:** a place inside the area the caller names beats the same name elsewhere (Bengaluru has three Dasarahallis; all count). A place outside the named area is never read back.
- `52022ad` **Complaint page** shows every person who reported a merged problem ("Also reported by"), each with their own details and conversation. Before, a second reporter's Telegram chat looked replaced by the first caller's phone call. Reports made before this fix show no conversation for the second person (old linking); the morning reset removes them anyway.
- `5d33be9` **Chats** follow a change of language at once; phone calls keep the two-turn rule.
- `97d57a9` A place the caller rejects is **never offered again**. Chats ask for a **location pin**; otherwise the complaint is filed at the area with the landmark in words.
- `6ba5ebb` **2.5x more places** (65,755): shops, banks, ATMs, restaurants, pharmacies, petrol pumps, apartments, offices. Street furniture is left out. Search is ~0.1 s slower per lookup.
- Also deployed: `f3b81db` teardrop map pins and `39dc8de` phone-width fixes.
- `542db03` `docs/judge-questions.md`: Q11 updated, new **Q11a** ("place not on the map?"), Q29 updated.

## What is left (in order)

1. **Unconfirmed:** did Tharun test the phone call, photos in chat, and the call-back after a fix? If so, update Q29 in `docs/judge-questions.md` (it still says "fakes only" for those).
2. **Vobiz → Railway** (unconfirmed): Answer URL `…/api/phone/answer`, Hangup URL `…/api/phone/hangup`, both POST. Without them, the phone demo fails.
3. **Judging morning:** from `backend/`, `python -m scripts.reset_demo` (dry run: read the host it prints) → `--yes`; then `python -m scripts.smoke_test https://citizens-voice-production.up.railway.app` must say READY. The reset deletes every complaint, Tharun's TEST ones included.
4. **Call-back showcase** (planned with Vinay 18 Oct; only works 9 AM–8 PM IST, `CALL_HOURS` in `backend/app/followup.py`):
   a. **Test it for real first** (never tested live): phone complaint → officer: Start work, photo, Mark fixed → Vobiz should ring the filing phone → answer "no" → complaint reopens, words in the timeline. Same on Telegram (the bot asks in chat).
   b. If it works, and Vinay agrees: the complaint page listens for the server's `callback` live events (already published by `followup._publish`, ignored by the web today) and shows "Calling the citizen…" then the result without a refresh.
   c. Add the moment to `docs/demo-script.md` after "Mark fixed" (~20 s): the phone rings on stage, answer "ಇಲ್ಲ, ಇನ್ನೂ ಕತ್ತಲು ಇದೆ", it reopens. Fallback if no ring within 20 s: "the call-back is on its way", move on.
5. Rehearse `docs/demo-script.md` three times; record the backup video **between 9 AM and 8 PM** (or the call-back won't fire).

## Vinay's open decisions

- **WhatsApp:** not configured. Recommended: skip for the demo.
- **Rotate the exposed keys:** recommended **after** judging.
- **`/api/brief` officers-only?** It is today; recommended: keep.
- **Google Places** for places missing from OpenStreetMap: a billing decision, after the hackathon.

## Known caveats (after the deadline)

- Chats keep one conversation per chat in memory: after filing, the next complaint's transcript starts with the tail of the last one.
- Google's Gemma was often slow or erroring on 17 Oct; replies then come via OpenRouter, slower.
- Chats, the call-back wait and retry timers live in memory: a redeploy forgets them. Keep one replica.
- Places missing from OpenStreetMap (e.g. St. Mary's Convent, T. Dasarahalli) are covered by the location pin or the area plus the landmark in words, not found by name.
