# Google Calendar: create, move, cancel and delete bookings

Tested live (agent 0.26.0) against a real Google Calendar: create, reschedule, cancel and delete, plus a check that the agent refuses to change an event it did not create.

## Two ways to connect
* **Read only (easiest).** Calendar settings, your calendar, "Secret address in iCal format". Paste it in the dashboard, Connect, Google Calendar (it must be a web address; the test checks that it really returns a calendar). The agent reads bookings and sends reminders. It cannot change the calendar.
* **Read and change (OAuth).** For the agent to add, move, cancel or delete entries.

## Set up the read-and-change mode (about 10 minutes, free)
1. In your own Google Cloud project turn on the **Google Calendar API**.
2. OAuth consent screen: type External, add your own Google account as a test user.
3. Create an **OAuth client ID** of type Web application with the redirect URI `https://developers.google.com/oauthplayground`.
4. In the OAuth Playground (gear icon: tick "Use your own OAuth credentials", paste the client ID and secret), authorize the scope `https://www.googleapis.com/auth/calendar.events` with your account, press "Exchange authorization code for tokens" and copy the **refresh token**.
5. In `agent.json`:
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

## Safety
* Entries are found by your booking reference and a tag the agent adds when it creates them. Anything without the tag is refused ("No calendar entry made by this agent was found").
* Nothing changes unless `allow_create` is true, and nothing changes in practice mode (dry run).
* If the internet is down, the change waits in the offline outbox and goes out in order when it returns.
* The read-only link mode can never change your calendar.
