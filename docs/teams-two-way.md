# Teams, two-way (Outgoing Webhook)

The agent already posts bug alerts to Teams. With an **Outgoing Webhook** your team can also answer from Teams: `@Speakvora BUG-17 fixed: the key was renewed`. No Azure subscription or bot registration is needed.

## Set it up (Connect, Microsoft Teams)
1. In the Teams channel's team: **Manage team, Apps, Create an outgoing webhook**. Name it (people @mention that name).
2. Callback URL: your agent's public address plus `/teams/messages`, for example `https://your-agent.example.com/teams/messages` (needs the permanent address from Connect, Permanent address).
3. Teams shows a **security token** once. Paste it into the second box on the Teams card (`teams.outgoing_secret`, stored in secrets.json as `TEAMS_OUTGOING_SECRET`) and press Save.
4. Press **Test answering from Teams**. The agent signs a sample with the saved token, runs it through its own handler, and checks that a wrongly signed one is refused. Then in the channel: `@name BUG-17 looking into it`.

Config in agent.json: `teams.outgoing_secret` (secret), `teams.allow` (optional list of display names or emails, any case; empty means anyone who can @mention the bot in that channel).

## What happens
- `POST /teams/messages` checks `Authorization: HMAC <base64>` (HMAC-SHA256 of the raw body, key = the base64-decoded token) with a constant-time compare. Missing or wrong gives 401; eight wrong tries from one address in ten minutes lock that address out for the rest of the ten minutes (the same lockout as the dashboard token). The route also shares the 240 requests per minute limit.
- A signed message older than 15 minutes (its `timestamp`) is refused, and the same message id is never handled twice.
- The `<at>Bot</at>` mention and markup are stripped. The ticket is found by a key in the text (any key the agent has opened in Jira), else by the conversation remembered for it. The first time someone names a ticket in a thread, that thread is remembered, so later messages there ("approve", notes) need no key. Teams does not tell the agent the id of an alert it posted through the workflow, so threads bind on the first key.
- The text goes to the same bug-desk logic as Slack replies (`bugdesk.handle`), through a thin adapter in `teams_in.py`: notes, In progress / Blocked moves, "fixed" / "won't fix" (asks "Close BUG-17? Reply approve"), "approve" / "keep open", reopen. `guardrails.bug_close` (ask, auto, off) works exactly as for Slack, and private details (cards, emails, phone numbers, keys) are redacted before they reach Jira.
- The answer is the JSON reply `{"type":"message","text":...}`, which Teams shows as the bot's reply.
- When two-way is on, alerts posted to Teams end with the ticket key and "@mention the bot, for example: BUG-17 fixed: what you did".
- Say `ping` to the bot to check it is alive. Secrets, signatures and message text are never written to the log.

## Limits of this path
- Teams only sends a message when someone @mentions the bot, and it must be written in the channel (not a private chat). The agent cannot see other messages.
- Replies must come within about five seconds; the bug desk answers locally, but a slow Jira can time out (the action still completes).
- No proactive messages: the reply to a mention is the only thing the bot can say from this route. Alerts still go through the workflow webhook.

## What a full Azure bot would add later (not built)
A registered Azure Bot (Bot Framework) gives real threads (the agent could remember the alert's own conversation id and reply inside it), proactive messages (direct messages, reminders, approval cards), adaptive-card buttons for Approve / Keep open, reading every message of a conversation the bot is in (no @mention), and personal chats. It costs an Azure subscription, an app registration and OAuth token handling, which is why it is left for later.
