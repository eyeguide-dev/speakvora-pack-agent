# Google Calendar: create, move, cancel and delete bookings

Tested live (agent 0.27.0) against a real Google Calendar: create, reschedule, cancel, delete, double-booking protection, reminders from a live read, and a check that the agent refuses to change an event it did not create.


![Google Calendar card in the agent dashboard (example screen)](img/dashboard-calendar-card.jpg)

## Two ways to connect
* **Read only (easiest).** Calendar settings, your calendar, "Secret address in iCal format". Paste it in the dashboard, Connect, Google Calendar (it must be a web address; the test checks that it really returns a calendar). The agent reads bookings and sends reminders. It cannot change the calendar.
* **Read and change (OAuth).** For the agent to add, move, cancel or delete entries.

### Read only: where to find the private link
In Google Calendar open Settings, click your calendar, scroll to **Integrate calendar**. (Example screen from a throwaway test account; the calendar ID and addresses are blurred.)

![Integrate calendar section, addresses blurred](img/google-calendar-1-integrate.jpg)

Use **Secret address in iCal format** (press the eye to show it, the copy icon to copy it) and paste it into the dashboard card. Do not use the public address. Pressing **Reset** invalidates a secret address that leaked.

![Secret address and Reset button, blurred](img/google-calendar-2-secret-address.jpg)

## Set up the read-and-change mode (about 10 minutes, free)
1. In your own Google Cloud project turn on the **Google Calendar API**.
2. OAuth consent screen: type External, add your own Google account as a test user.
3. Create an **OAuth client ID** of type Web application with the redirect URI `https://developers.google.com/oauthplayground`.
4. In the OAuth Playground (gear icon: tick "Use your own OAuth credentials", paste the client ID and secret), authorize the scope `https://www.googleapis.com/auth/calendar.events` with your account, press "Exchange authorization code for tokens" and copy the **refresh token**.
5. Easiest: dashboard, **Connect**, **Google Calendar**: paste the client ID, client secret and refresh token, pick **Add, move, cancel and delete its own bookings**, optionally a calendar ID, and press Save and test. Or in `agent.json`:
```json
"google_calendar": {"mode": "oauth", "client_id": "env:GOOGLE_CLIENT_ID", "client_secret": "env:GOOGLE_CLIENT_SECRET", "refresh_token": "env:GOOGLE_REFRESH_TOKEN", "calendar_id": "primary", "allow_create": true}
```
Use a separate calendar (its Calendar ID is in that calendar's settings) if you want to keep bookings apart from your own events.

## The four actions
Your app sends an event that names the booking (`appointment.id`). The recipes for clinics, salons and similar businesses already do this:

| Your app sends | The agent does | In Google Calendar |
| --- | --- | --- |
| `appointment.created` | `calendar_create` with `ref: "{{appointment.id}}"` | a new entry |
| `appointment.changed` | `calendar_reschedule` with the new `start_epoch` and `minutes` | the same entry moves |
| `appointment.cancelled` | `calendar_cancel` | stays, titled "Cancelled: ..." and shown as free |
| (your own event) | `calendar_delete` | the entry is removed |

You can use the same actions in your own workflows:
```json
{"action": "calendar_reschedule", "ref": "{{appointment.id}}", "start": "{{start_epoch}}", "minutes": "{{minutes}}"}
```

## Double-booking protection
Before it adds or moves a booking the agent looks at that calendar. If a timed entry that is marked busy already overlaps, it does not book and the workflow shows why ("That time is already taken..."), so you can alert your team. Back-to-back bookings are fine; all-day entries and entries marked free never block. Moving a booking within or next to its own old slot is fine. To allow double booking set `"double_booking": "allow"` in `google_calendar`, or add `"ignore_busy": true` to one action.

## What it covers, and what it does not
Covers: reading bookings for reminders and daily summaries, adding, moving, cancelling and deleting the agent's own bookings from your app's events, double-booking protection, one chosen calendar, the offline outbox.
Does not (yet): invite guests or add video-call links, change repeating series, write to Outlook/Microsoft calendars (read only), or let the AI move or cancel a booking during a conversation (the AI can add one when you allow it).

## Safety
* Entries are found by your booking reference and a tag the agent adds when it creates them. Anything without the tag is refused ("No calendar entry made by this agent was found").
* Nothing changes unless `allow_create` is true, and nothing changes in practice mode (dry run).
* If the internet is down, the change waits in the offline outbox and goes out in order when it returns.
* The read-only link mode can never change your calendar.
