# Citizen's Voice — today's plan in plain words

The easy-reading version of [plan-18-oct.md](plan-18-oct.md). If they ever disagree, the technical one
wins, and we fix this one.

Submission closes **3:30 PM today**. Nothing new starts after **1 PM**: after that we only fix what
testing breaks, then rehearse.

---

## What Tharun found, and what we did about it

**Last night (all fixed, and Tharun says they work):**

| What went wrong | What we changed |
|---|---|
| "St. Mary's School, Dasarahalli" put the pin 15 km away | A place inside the area you name now wins over the same name somewhere else |
| The officer page showed someone else's chat for his complaint | It was a second report of the same pothole. The page now shows **every** person who reported it, each with their own words |
| Switching language made the bot stop and ask "shall we continue in Hindi?" every time | In chats, the bot just follows your language |
| The bot offered the wrong school again after he said "no" | It never offers a rejected place again. On Telegram it asks for your **location pin**; on the phone it files at the area and writes your landmark in words |
| Many shops and banks weren't on our map | We now know **65,755 places**, 2.5 times more |

**This morning (done, Tharun is testing now):**

| What was missing | What we changed |
|---|---|
| A photo sent "as a file" on Telegram vanished | Images sent as files now count as photos |
| The bot once filed without reading the complaint back | It now can't file until it has read back the problem **and the place** |
| People who complain in the browser could never be reached | After filing, they can leave their mobile number for the call-back |
| Telegram users heard nothing until the fix | They now get a message every time the status changes, with the officer's note |
| Phone callers asking "what happened?" got one bare line | They now hear which office has it, whether it's late, and the latest update |

**Who hears what, decided by Vinay:**
- **Telegram:** a message for every update.
- **Phone and browser:** one call, after the fix, asking "is it really fixed?". They can call any time to hear the full status.

---

**Added late this morning (done, pushed, Tharun is testing now):**

| What you asked for | What we changed |
|---|---|
| Not every fix can be photographed | The officer's photo is **optional**. Without one, the page says publicly "No fix photo: the citizen's answer decides" |
| Precise location in chats and the browser | Citizens can paste a **Google Maps link**; the pin goes exactly where it points. Our server only ever opens Google addresses |
| The officer doesn't know the note is public | The note box now says "Shown on the public timeline and sent to the citizen" |

---

## How Gemma looks at photos

- **When a citizen sends a photo:** Gemma describes what it sees ("a deep pothole"), how serious it is (1 to 5), and whether anyone is in danger. The clerk uses that, so it doesn't ask what the photo already shows.
- **When the officer marks it fixed with a photo:** Gemma compares it with the complaint, and with the citizen's photo if there is one: does it look fixed, is it the same place, and why.
- Gemma's view is always **advice**. It never changes a complaint by itself.
- The complaint page now shows all of it on a **Photo check** card (done, see below).

---

## Done before the code freeze (not yet pushed)

| What | What we changed | Commit |
|---|---|---|
| The photo check, shown properly | The citizen's photo and the officer's "fixed" photo **side by side**, with what Gemma noticed: same place or not, what matches, what's different, how sure it is. The card says Gemma's check is advice; the citizen's answer decides | `781c6eb` |
| "MG Road" and other shared names | The bot offers every real match, each named by its area ("MG Road near Shivajinagar, or the other one?"), and lets the caller choose | `66bf6a4` |
| Pincode, if the caller knows it | Never required. The bot may ask once when the place is unclear. We know the centre of 107 Bengaluru pincodes from the map data | `62b5529` |
| Same problem, same area | "Nearby" is 150 m for spot problems (pothole, streetlight, tree, drain) and 500 m for area-wide ones (water, power, garbage) | `1a54f21` |
| Judge answers and demo script | Updated for everything above. The demo gets the call-back moment: the officer marks it fixed, your phone rings on stage, you say "no, it's still dark", and it reopens | this one |

**Not built today (we'll say "planned" if asked):**
- Gemma's thinking in more detail on the complaint page (for example "checked for the same problem nearby: found CV-1004, 40 m away").
- Checking the hidden GPS location and time in the officer's photo.
- Showing the call-back live on the page ("Calling the citizen…"): only if Tharun's test shows the call-back really rings.

---

## Then (Vinay)

1. Reset the demo data, and run the smoke test until it says READY.
2. Rehearse the demo script three times.
3. Record the backup video **before 8 PM** (the call-back doesn't run at night).

---

## Not today (we'll say "planned" if asked)

- Text messages (SMS) for tickets, updates or photo-upload links. Indian rules need every message template registered first, which takes days.
- Checking a browser user's number with a one-time code (needs SMS).
- Keeping voice recordings (we keep only the words).
- A paid map search (Google Places) for places OpenStreetMap doesn't have.
- Separate logins for each officer, and alerts when something is overdue.
- Sending complaints into government systems (the spreadsheet download is the bridge for now).
