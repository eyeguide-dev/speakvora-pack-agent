# Connect your calendar for reminders and bookings

The agent reads your calendar to send appointment reminders. With extra setup it can also add, move and cancel bookings. Start with the simple read-only link.

## Easiest: a private calendar link (works for Google and Outlook)
**Google Calendar**
1. Open calendar.google.com on a computer. Press the gear icon, then **Settings**.
2. On the left, under **Settings for my calendars**, click your calendar, then **Integrate calendar**.
3. Copy **Secret address in iCal format** (a long address ending in .ics).

**Outlook / Microsoft 365**
1. Open Outlook on the web, then Settings, Calendar, **Shared calendars**.
2. Under **Publish a calendar** choose your calendar and **Can view all details**, then Publish.
3. Copy the **ICS** link.

**In the agent**
1. Open **Connect, Google or Outlook calendar**, paste the link into **Private calendar link**, and press **Save and test**.
2. It should say how many events it found in the next seven days. An empty calendar is fine.

## Keep the link private
Anyone with the link can read your calendar. If it leaks, reset it in your calendar's settings.

## To change bookings from the agent (Google, about 10 minutes)
Create a Desktop app OAuth client in your own Google Cloud project (free), then run `python3 tools/connect_google_calendar.py --agent-dir . --email you@gmail.com` in the agent folder. Google's consent page opens; the answer is caught on your own computer and saved in agent-state/secrets.json. The steps are in docs/google-calendar.md. The agent only moves or cancels bookings it created itself.

## Booking format
Put the customer's phone in the event description (for example "Phone: 646-555-0120 SMS OK: yes") so reminders know who to text and that they agreed to texts.
