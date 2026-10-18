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

## Still to do today (before 1 PM)

1. **The officer's note box says it's public.** The note goes into the public timeline and to the citizen, so the officer should know that.
2. **Show the photo check properly.** The citizen's photo and the officer's "fixed" photo **side by side**, with what Gemma noticed:
   - is it the same place?
   - what matches in both photos (a wall, a tree, a shop sign)?
   - what's different?
   - how sure is it?

   Gemma's opinion is **advice**: the citizen's "yes" or "no" on the call-back is what counts.
3. **Show Gemma's thinking in more detail.** For example: "checked for the same problem nearby: found CV-1004, 40 m away"; "sent to BBMP, 7-day deadline". Each step can be opened to see exactly what went in and came out.
4. **Show the call-back as it happens** ("Calling the citizen…", then their answer), but only if Tharun's test shows the call-back really rings.
5. *If time is left:* check the hidden GPS location and time stored in the officer's photo, to confirm it was taken at the right place after the complaint.
6. **Update the judge answers and the demo script.** The demo gets a new moment: the officer marks it fixed, your phone rings on stage, you say "no, it's still dark", and it reopens.

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
