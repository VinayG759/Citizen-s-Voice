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
| Backup video | Record one full run (call → pin → mark fixed → photo check → call-back → scorecard), 2–3 min, **before 8 PM** | Plan C if the network dies |
| Tabs open | Tab 1: the **Live desk** (`/`), signed in as an officer (sidebar, bottom: *Officer sign-in*; it stays signed in for that tab). Tab 2: `/try`. Tab 3: the backup video, paused at 0:00 | Switching tabs is faster than typing addresses |
| Phones | Your phone charged, speaker tested; a second phone with a different number as backup; mobile hotspot on | The line allows 5 calls per hour per number. Don't burn them rehearsing in the last hour |
| Call-back hours | The call-back only rings **9 AM–8 PM IST**. Check the judging slot is inside that; record the backup video before 8 PM | Outside those hours the call-back waits, and the stage moment doesn't happen |
| Ringer on | Your phone's ringer loud, not silent or Do Not Disturb. The call-back comes from our line's number, not a saved contact | It rings the phone that made the stage call |

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

Put your phone on speaker, held near the mic. Dial the helpline number shown on the Live desk (the *Live call* panel says it while it waits).

1. The greeting plays in Kannada, Hindi and English. **Answer in Kannada**; that sets the language.
2. Say: **"ನಮಸ್ಕಾರ, ಜಯನಗರ 4th Block ಅಲ್ಲಿ street light ಕೆಲಸ ಮಾಡ್ತಿಲ್ಲ, ರಾತ್ರಿ ಪೂರ್ತಿ ಕತ್ತಲು."**
   (Hello, the streetlight in Jayanagar 4th Block isn't working, it's completely dark at night.)
3. Answer its questions in a few words. If it asks for a landmark: **"bus stop ಹತ್ತಿರ"** (near the bus stop).
   If it asks since when: **"ಒಂದು ವಾರ"** (one week).
4. It reads the complaint back once. Say **"ಹೌದು, ಸರಿ"** (yes, that's right).
5. It says the tracking ID twice and hangs up.

**While it talks, point at the Live desk** (tab 1): the *Live call* panel shows each turn and Gemma's steps
as plain sentences ("Looking up 'Jayanagar 4th Block'" → "Found: …" → "Filing the complaint" →
"Filed as CV-…") as they happen.

Say once, briefly: "Sarvam is the ears and the mouth: speech to text and back. Every decision is
Gemma's: what to ask, which place, which office, when to file."

### 1:30–1:45 — The Live desk updates live

Stay on the Live desk: everything for this moment is on one screen.

- The new complaint appears at the top of **Newest complaints** and as a **pin on the map**, without a refresh.
- Click **Details** on it → the complaint page: the conversation, **Gemma's steps**, the office (BBMP) and its deadline (7 days).
- Say: "The pin comes from map data, never from the model, and it can't file until the caller says yes."

### 1:45–2:15 — The officer marks it fixed; Gemma checks the photo

1. On the new complaint's page: if you are not already signed in, **Officer sign-in** (header) → passcode. An **Officer actions** card appears.
2. **Start work** → **Add photo (optional)** (the fix photo) → **Mark fixed**.
3. The **Photo check** card appears (takes a few seconds): the fix photo, Gemma 4 31B's verdict
   (looks fixed / not fixed / can't tell), its reason, its confidence, and the model. A phone call has
   no citizen photo, so it says **"No citizen photo to compare"**; with a Telegram photo it puts the
   two side by side and lists what matches and what differs.
4. Say: "Gemma's check is advice. It never closes anything. The citizen decides, and here's how."

### 2:15–2:35 — The call-back: the citizen decides (~20 s)

1. Within a few seconds of *Mark fixed*, **your phone rings** (the phone that made the call). Answer on speaker.
2. It asks, in Kannada, whether the problem is really fixed. Say **"ಇಲ್ಲ, ಇನ್ನೂ ಕತ್ತಲು ಇದೆ"** (no, it's still dark).
3. Refresh the complaint page: the timeline shows the citizen's answer and the complaint is **reopened**, with higher priority.
4. Say: "The officer said fixed. The citizen said no. The citizen wins."

**No ring within 20 s:** say "The call-back is on its way; it rings the citizen after every fix," and
move straight to the scorecard. Don't wait, don't redial.

### 2:35–2:50 — The scorecard

- Go back (browser *Back*), click **Offices** in the sidebar: the scorecard, per office: filed / open / fixed / **overdue** / median days to fix.
- Say: "Every office's overdue count, in public."

### 2:50–2:55 — Close

> "Any phone, any of three languages, no app. Gemma 4 does the clerk's job; the city gets a map and a
> scorecard. That's Citizen's Voice."

---

The run is 2:55, with 5 s spare. To fit the call-back, the Live desk beat and the scorecard are
shorter than before, and "Most urgent first" moved to the extras below.

## Optional extras

**If a judge asks how the queue is ordered:** click **Complaints** in the sidebar, then **"Most urgent
first"**: each complaint shows *why* it ranks there ("urgency 4 · 4 reports · overdue by 3 days").
"Plain rules, shown openly. The AI doesn't decide who waits."

**If a judge asks about the photo comparison:** the stage complaint has no citizen photo. To show the
full card, prepare one before judging: after the reset, send a Telegram complaint **with a photo**
(a pothole), then sign in and mark it fixed with a photo of a clean road. Keep its page open in a
fourth tab: the two photos side by side, what matches, what differs, Gemma's confidence. Its Telegram
chat will get the "is it really fixed?" question: answer it, or leave it.

**If a judge asks "which MG Road?":** on `/try`, type **"MG Road ಅಲ್ಲಿ street light ಕೆಲಸ ಮಾಡ್ತಿಲ್ಲ"**.
The clerk should ask which MG Road, naming each by its area ("near Shivajinagar…"). You don't need
to file it. Don't promise a specific list of areas; it's new today.

**If a judge asks "what is trending?":** click **Emerging issues** in the sidebar (spikes and clusters, each with its evidence). Opening it asks Gemma for the headlines (the server remembers them), so open it once before the demo to make it instant; inside one tab it only reloads when you press *Refresh*. **Morning brief** (officers only) gives today's numbers and a *Download CSV* button.

**If a judge asks about duplicates:**

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
| Call-back doesn't ring | No ring within 20 s of *Mark fixed* (or it's after 8 PM) | "The call-back is on its way; it rings the citizen after every fix." | Go to the scorecard. Don't wait or redial |
| Live updates don't appear | List doesn't change after filing | "Let me refresh." | Refresh the page once. The complaint is in the database |
| Venue Wi-Fi dies | Pages won't load | "Wi-Fi's down, so here's the recording." | Laptop to phone hotspot. If that fails too: tab 3, the backup video |
| Projector / laptop dies | — | — | Video on your phone; hand the phone to the judge |

**Kill switches** (server environment, no new code needed): `FEATURE_PHOTO_CHECK=false` skips Gemma's photo
check; `FEATURE_CALLBACK=false` stops the follow-up request.

---

## After the demo

If judges filed test complaints and you want a clean board for the next group, run
`python -m scripts.reset_demo --yes` again (it shows the host first; type it to confirm).
