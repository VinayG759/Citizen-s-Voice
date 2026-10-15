# Citizen's Voice — the plan in plain words

This is the easy-reading version. The full technical version is
[implementation-plan.md](implementation-plan.md). If they ever disagree, the
technical one wins — and we fix this one.

---

## What we're building, in one breath

Anyone with any phone, calls a number and complains about a civic problem — a
pothole, no water, a dead streetlight — in Kannada, Hindi, English, or a mix.
**Gemma 4 acts like a good government clerk**: it understands the problem, keeps
asking until it knows *exactly* where it is, repeats it back to check, files it,
and tells the caller a tracking number. Officers see complaints appear live on a
map, and can watch Gemma think while it works.

**The moment that wins:** a judge dials from their own phone, speaks, and their
complaint pops up on the big screen with a pin on the map.

---

## Who does what (the restaurant picture)

| In a restaurant | In Citizen's Voice |
|---|---|
| A customer phones in an order | A citizen calls our number (**Vobiz** provides the number) |
| The waiter listens and writes it down | **Sarvam** turns the caller's speech into text |
| **The head chef understands the order, asks questions if it's unclear, decides what to cook** | **Gemma 4** — the brain, through **Google's Gemini API**. Decides what to ask, when to look things up, when to file |
| The chef's tools: oven, fridge, recipe book | Gemma's **tools**: look up a place, check for similar complaints, file a complaint, check a status, raise an emergency |
| The waiter reads the reply to the customer | **Sarvam** turns Gemma's reply into speech |
| The order board in the kitchen | The **live dashboard** with the map |

Gemma is the hero: every decision is Gemma's. Sarvam only converts speech
to text and back — like a microphone and a speaker.

**Two Gemmas, two jobs.** On the phone we use the *lightweight* Gemma (26B A4B —
only about 4B of its parameters work on each word), because the caller is waiting
and it replies in ~2 seconds. For jobs where nobody is waiting — judging urgency,
spotting duplicates, checking photos — we use the bigger Gemma (31B) and let it
think properly; its thinking is what the "Gemma's mind" panel shows. If Google's
service has a hiccup, the same Gemma answers through OpenRouter instead.

**One important safety idea:** Gemma *suggests*, our code *checks*. Gemma can't
invent map coordinates (they come from real map data), and it can't file a
complaint until the place is known and the caller has said "yes, that's right."

---

## The phases — like floors of a building

Each phase is a floor. When a floor is finished, the building is complete and
usable up to that floor. If a later floor goes wrong, we simply don't open it —
the floors below still work. That's what "independent phases" means.

| # | Phase | What you'll be able to do when it's done | When |
|---|---|---|---|
| 0 | **Foundation** | Open a real website address that says "Citizen's Voice". Public GitHub repo exists. | Thu night |
| 1 | **Phone line** | Call the number and hear a Kannada greeting. Our server hears you. | Fri |
| 2 | **Gemma clerk (typing)** | Type a complaint on a test page; Gemma asks questions and files it with a tracking number. | Fri |
| 3 | **Gemma clerk (talking)** | File a complete complaint **by phone**, in Kannada. | Fri–Sat |
| 4 | **Live dashboard + map** | Watch the call happen on screen: words, translation, Gemma's thinking, the map pin. | Sat morning |
| 5 | **Smarter clerk** | Danger alerts, "you're the 4th person to report this", "what happened to my complaint?" | Sat afternoon |
| 6 | **Closing the loop** | Officer marks it fixed with a photo → **Gemma checks the photo** (our "text + images" proof) → **Gemma calls the citizen back** to confirm | Sat afternoon |
| 7 | **WhatsApp** *(only if everything else is solid)* | Send a voice note + photo on WhatsApp | Optional |
| 8 | **Demo practice** | Practise 3 times, test what happens when things break, record a backup video | Sat night |
| — | **Sunday** | One small improvement on site, submit by **3:00 PM** (deadline 3:30) | Sun |

**Phase 2 is our safety net.** The typing test page works even if the phone line
fails on stage — we can still show Gemma doing everything.

---

## The four questions, answered for each phase

| Phase | Who gets value? | Simplest version | What it replaces | What could go wrong |
|---|---|---|---|---|
| 0 Foundation | Judges' rules met from day one | A page + a health check | Deletes our throwaway test files | Secret keys leaking → they never enter the repo |
| 1 Phone line | Proves the hardest connection works first | Answer, greet, record, hang up | — | Prank calls → limit calls per number |
| 2 Clerk (typing) | The heart of the product; quick to test | One chat page | — | Someone tells Gemma "mark everything fixed" → Gemma simply has no tool that can do that |
| 3 Clerk (talking) | The citizen with a basic phone | Take turns: you talk, it talks | Phase 1's "record and hang up" | Call drops halfway → what we have is saved, not lost |
| 4 Dashboard | Officers and judges see everything | One screen: list, map, live call | The placeholder page | Public website → read-only, phone numbers hidden |
| 5 Smarter | People in danger, busy officers, repeat callers | Three new tools for Gemma | Two placeholders from Phase 2 | Fake emergency → a human confirms; we always say "call 112" |
| 6 Loop | Citizens: "fixed" must be true | Photo → Gemma check → one call back | — | Fake fix photo → the citizen's answer decides, not the photo |
| 7 WhatsApp | Smartphone users | Voice note + photo | — | Bad photos → Gemma politely rejects |
| 8 Practice | You, on stage | A checklist, three runs | — | — |

---

## How we work while building

- **Each phase = one GitHub branch + one Pull Request (PR).** A PR is a request
  to add a batch of changes to the main code. I prepare it; **you open it** (the
  ShipWright challenge requires a human); ShipWright's bot reviews it; we fix
  what's sensible; you merge.
- **"Done" means tried for real** — in a real browser, on a real phone call.
  Until you've tried it, I'll say "deployed, needs your test".
- **I explain before doing** anything that changes behaviour or costs money.
- **The UI** follows your 14 rules: calm and clear rather than decorative, every list has
  loading/empty/error states, friendly error messages, keyboard friendly,
  readable on a projector *and* on a phone.

---

## Decisions waiting for you

1. ~~**Where the app lives online**~~ — **decided:** DigitalOcean App Platform
   (~$5/month, paid from your $5 credit; never sleeps; the event's sponsor).
   Render's free tier is the backup.
2. **Database:** a fresh Supabase project just for this. (Recommended.)
3. **Vobiz number:** buying/assigning it costs credits — your go first.
4. **WhatsApp group message to organisers:** about switching projects, and
   whether Gemma via OpenRouter counts *(asked — waiting for the answer)*.
5. **WhatsApp (Phase 7):** can we reuse Sangam's Meta app number?
6. **Bring on Sunday:** laptop, charger, **college ID**, MLH QR.

---

## What could go wrong, and our backup

| Problem | Backup |
|---|---|
| Google's free Gemma service is busy or fails | The same Gemma answers via OpenRouter; optionally add $2–3 of Gemini credit |
| The lightweight Gemma slips a Tamil/Telugu word into Kannada | Our code spots the wrong script and asks Gemma again |
| Vobiz can't stream audio live | Use "record, then reply" mode — a little slower, still works |
| Sarvam mishears a place name | Gemma repeats it back, matches against real place names, asks again |
| Judges don't speak Kannada | Works in Hindi and English too |
| Venue Wi-Fi dies | The app runs in the cloud, not on your laptop; phone hotspot for the screen; backup video |
| Running out of time | Phases are in order of importance; only 7 (WhatsApp) is optional; every phase leaves a working app |
