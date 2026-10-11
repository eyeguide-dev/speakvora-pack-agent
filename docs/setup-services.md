# Connect your services (about 15 minutes, once)

Keep keys out of `agent.json`: write `"env:NAME"` and set the variable in the environment that runs the agent.

## Twilio (texts and calls)
1. Buy a number in Twilio. US texting needs the number registered with carriers (A2P 10DLC or toll-free verification) in your Twilio account.
2. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` (+1...).
3. In Twilio, for the number: "A message comes in" -> `https://YOUR-AGENT-ADDRESS/twilio/sms` (POST); "A call comes in" -> `https://YOUR-AGENT-ADDRESS/twilio/call` (POST).
4. Set `public_base_url` to that same public address. Twilio plays your pack audio from `/audio/...`. Phone calls need mp3 or wav: the workflow lines are mp3; the pack's .m4a lines need ffmpeg installed so the agent can convert them.
STOP and START replies are handled for you, as carriers require. Twilio bills you directly for texts and calls; Speakvora adds no fee.

## Slack
1. Create a Slack app (api.slack.com/apps) in your workspace. Bot token scopes: `chat:write`, `files:write`. Install it and copy the Bot token (`xoxb-...`) into `SLACK_BOT_TOKEN`; invite the bot to the channels you use.
2. Optional staff command: add a slash command `/say` pointing to `https://YOUR-AGENT-ADDRESS/slack/command`; copy the app's Signing Secret into `SLACK_SIGNING_SECRET`. Example: `/say order_ready +16465550123` texts that customer the pack's "your order is ready" line.
3. Channels: workflows post to roles such as #front, #kitchen and #host. Set one real channel with `"slack": {"channel": "#general"}` and every role goes there. To split them, add `"channels": {"#kitchen": "#orders"}`; roles you do not list use the default channel.
4. Only text goes to Slack by default; audio uploads happen when a workflow asks for it.

## Google Calendar
Option A (simplest, read-only): in Google Calendar settings for the calendar, copy the "Secret address in iCal format" and set `CALENDAR_ICS_URL`; use `"mode": "ics"`. Repeating events are not expanded in this mode.
Option B (read and, if you allow it, create events): create an OAuth client in your own Google Cloud project, get a refresh token for your account with the Calendar scope, set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `"mode": "oauth"`, and `"allow_create": true` only if you want the agent to add events.
Google refreshes secret iCal feeds slowly (a new event can take hours to appear), so use the OAuth option for reminders that must fire on time.
The agent finds the customer's phone number and consent in the event notes: write `Phone: 646-555-0101` and `SMS OK: yes`. `SMS OK: no` or nothing means it will not text them.

## Microsoft Teams
In the Teams channel choose Workflows, "Post to a channel when a webhook request is received", and copy the URL into `teams.webhook_url`. The `notify` action posts to Slack and/or Teams, whichever you connected.

## Microsoft 365 / Outlook calendar
Easiest: Outlook calendar settings > Shared calendars > Publish, copy the ICS link, use `"microsoft_calendar": {"mode": "ics", "ics_url": "env:OUTLOOK_ICS_URL"}`. Or your own Azure app (Calendars.Read, offline_access) with `"mode": "oauth"`, `client_id`, `refresh_token`. Google and Microsoft calendars can both be connected at once.

## WhatsApp
Same Twilio account. Enable WhatsApp on your Twilio sender, set `twilio.whatsapp_from`, then use `"channel": "whatsapp"` on an `sms` action. People who message your WhatsApp number are answered by the same keyword workflows as texts. WhatsApp has its own rules about messaging first (templates); check Twilio's WhatsApp documentation.

## Inbound email (customers writing to you)
Set `inbox` (IMAP host, username, app password, `folder`). Use a dedicated folder or label such as `Support` so personal mail is never read; mail stays unread, newsletters and auto-replies are ignored, and each message is handled once. Workflows start with `{"on": {"email": {"keywords": ["hours"]}}}` (no keywords = every email). Replies go out through your `email` SMTP settings.

## Helpdesk and customer apps
Any system with a REST API is reached with the `http` action; any system that sends webhooks is mapped in `sources` (see connect-anything.md). The `support` profile's `email_ticket` workflow shows creating a ticket in a helpdesk and confirming it to the customer.

## Email (optional)
SMTP details under `email` (Gmail needs an app password). Used by the `email` action.

## Run it
`sh sv-agent check`, then `sh sv-agent run` (dry-run), then `sh sv-agent run --live` when the log looks right. The log is `agent-state/agent.log.jsonl`. To stop everything instantly create a file named `STOP` in `agent-state/`.


## Did the text really arrive?
Twilio accepting a text only means it was queued. When your agent has an https `public_base_url`, it asks Twilio for delivery updates at `/twilio/status` and logs `delivered` or `undelivered` (with the carrier's error code, for example 30034 = US numbers not yet registered for business texting) as a `delivery` line in the agent log. Calls log `delivered` when Twilio reports them completed.
