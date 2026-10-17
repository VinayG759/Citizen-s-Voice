# Demo script — 3 minutes

For Vinay on stage. Times are targets; rehearse three times with a stopwatch. The exact call script
below has **not** been run end to end yet. Rehearse it on the real line before judging.

---

## The night before / the morning of

| Do | How | Why |
|---|---|---|
| Reset the sample data (morning) | `cd backend` → `python -m scripts.reset_demo` (dry run: check the **host** it prints) → `python -m scripts.reset_demo --yes` and type the host | Fills the dashboard with 14 believable complaints: 4 overdue, 1 emergency, 1 pothole reported by 4 people, 2 fixed, 1 reopened. "Overdue" counts from now, so run it on the day |
| Check the live site | `python -m scripts.smoke_test https://<live address>` | Must say **READY**. A WARN about the helpline number means the phone number isn't set on the server |
| Officer passcode | Make sure `OFFICER_PASSCODE` is set on the server and you know it | "Mark fixed" needs sign-in |
| Fix photo | Have a photo of a working streetlight (or a clean road) on the laptop desktop | The officer step uploads it |
| Backup video | Record one full run (call → pin → mark fixed → scorecard), 2–3 min | Plan C if the network dies |
| Tabs open | Tab 1: dashboard (`/`). Tab 2: `/try`. Tab 3: the backup video, paused at 0:00 | Switching tabs is faster than typing addresses |
| Phones | Your phone charged, speaker tested; a second phone with a different number as backup; mobile hotspot on | The line allows 5 calls per hour per number. Don't burn them rehearsing in the last hour |

**Place names checked on 17 Oct:** Jayanagar 4th Block, Hebbal, Malleswaram, Rajajinagar, Basavanagudi,
HSR Layout, Whitefield, Koramangala (and 5th Block), Indiranagar, Yelahanka New Town. A bare "Koramangala" used to pin
a village 40 km away; fixed 17 Oct (it now picks the suburb and also offers the namesake, so the clerk may ask which).

---

## The run (3:00)

### 0:00–0:15 — The hook (say it, don't read it)

> "To report a pothole in Bengaluru today you need an app, a website, or someone on a helpline to type it
> up. Citizen's Voice is just a phone number. Call from any phone, speak Kannada, Hindi or English, and
> **Gemma 4 is the clerk**: it pins the exact spot, files it, and the city can see who is overdue."

### 0:15–1:30 — The live call, in Kannada

Put your phone on speaker, held near the mic. Dial the helpline number shown at the top of the dashboard.

1. The greeting plays in Kannada, Hindi and English. **Answer in Kannada**; that sets the language.
2. Say: **"ನಮಸ್ಕಾರ, ಜಯನಗರ 4th Block ಅಲ್ಲಿ street light ಕೆಲಸ ಮಾಡ್ತಿಲ್ಲ, ರಾತ್ರಿ ಪೂರ್ತಿ ಕತ್ತಲು."**
   (Hello, the streetlight in Jayanagar 4th Block isn't working, it's completely dark at night.)
3. Answer its questions in a few words. If it asks for a landmark: **"bus stop ಹತ್ತಿರ"** (near the bus stop).
   If it asks since when: **"ಒಂದು ವಾರ"** (one week).
4. It reads the complaint back once. Say **"ಹೌದು, ಸರಿ"** (yes, that's right).
5. It says the tracking ID twice and hangs up.

**While it talks, point at the screen** (tab 1): the live call panel shows each turn and Gemma's steps
as plain sentences ("Looking up 'Jayanagar 4th Block'" → "Found: …" → "Filing the complaint" →
"Filed as CV-…") as they happen.

Say once, briefly: "Sarvam is the ears and the mouth: speech to text and back. Every decision is
Gemma's: what to ask, which place, which office, when to file."

### 1:30–2:00 — The dashboard updates live

- The new complaint appears at the top of the list and as a **pin on the map**, without a refresh.
- Click it → the complaint page: the conversation, **Gemma's steps** (what it looked up and why), the
  office it was sent to (BBMP), its deadline (7 days) and the timeline.
- Say: "The map pin comes from OpenStreetMap data, never from the model. Gemma can't invent a place,
  and it can't file until the caller says yes."

### 2:00–2:35 — The officer closes the loop with a photo

1. On the new complaint's page: **Officer sign-in** (header) → passcode. An **Officer actions** card appears.
2. **Start work** → then **Choose photo** (the fix photo) → **Mark fixed**.
3. **Gemma 4 31B looks at the photo** against the complaint and shows its verdict: looks fixed / not
   fixed / can't tell, with one sentence of reasoning. Takes a few seconds.
4. Say: "Gemma's verdict is advice to people. It never closes anything on its own. If the citizen
   says it isn't fixed, it's reopened and its priority goes up."

### 2:35–2:55 — The scorecard

- Scroll to the **office scorecard**: per office, filed / open / fixed / **overdue** / median days to fix.
- Back on the dashboard, switch the list to **"Most urgent first"**: each complaint shows *why* it ranks there ("urgency 4 · 4 reports ·
  overdue by 3 days"). "Plain rules, shown openly. The AI doesn't decide who waits."

### 2:55–3:00 — Close

> "Any phone, any of three languages, no app. Gemma 4 does the clerk's job; the city gets a map and a
> scorecard. That's Citizen's Voice."

---

## Optional extra (if a judge asks about duplicates)

On `/try`, type or say: **"ಜಯನಗರ 4th Block ಅಲ್ಲಿ ಮೂರು ದಿನದಿಂದ ನೀರು ಬರ್ತಿಲ್ಲ"** (no water in Jayanagar 4th
Block for three days). The sample data already has that complaint, so the clerk should say it was
already reported, add this report to the **same tracking ID**, and the count goes up. Every third
report raises the priority.

---

## When something fails

Rule: **never debug on stage.** Say one sentence, switch to the next plan, keep the clock.

| What fails | You'll notice | Say | Do |
|---|---|---|---|
| Phone line (no ring, rejected, silence) | No greeting within ~5 s | "The phone network is shy today, so here's the same clerk in the browser." | Tab 2, `/try`: press *Start talking*, same Kannada lines. Same Gemma, same tools, same dashboard |
| Rejected after several rehearsal calls | Call drops at once | (same as above) | 5 calls/hour per number: use the second phone, or `/try` |
| Gemma slow | "One moment" filler, long pauses | "It's checking the map, and the slow part is the network." | Wait up to ~10 s per turn. The server already switches to the same Gemma via OpenRouter after 2.5 s. If it's still stuck, go to `/try` and **type** the lines |
| Gemma unreachable | Clerk says "small technical problem, say that again" | "Our AI provider is having a moment." | Repeat once. Then play the video (tab 3) |
| Sarvam voice down | Text appears on `/try`, no audio | "The voice service is down. Here's what it said." | Keep going on `/try`. Replies are shown as text |
| Photo check slow or fails | Spinner, or verdict "can't tell" | "Gemma couldn't see the photo clearly, so a person decides. That's the design." | It still marks fixed and records it. Move on |
| Live updates don't appear | List doesn't change after filing | "Let me refresh." | Refresh the page once. The complaint is in the database |
| Venue Wi-Fi dies | Pages won't load | "Wi-Fi's down, so here's the recording." | Laptop to phone hotspot. If that fails too: tab 3, the backup video |
| Projector / laptop dies | — | — | Video on your phone; hand the phone to the judge |

**Kill switches** (server environment, no new code needed): `FEATURE_PHOTO_CHECK=false` skips Gemma's photo
check; `FEATURE_CALLBACK=false` stops the follow-up request.

---

## After the demo

If judges filed test complaints and you want a clean board for the next group, run
`python -m scripts.reset_demo --yes` again (it shows the host first; type it to confirm).
