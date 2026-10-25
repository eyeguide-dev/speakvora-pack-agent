# The bug desk: bugs handled from Slack

**Want screenshots and the setup in order? See [bug-desk-walkthrough.md](bug-desk-walkthrough.md).**

When something breaks, the agent opens the ticket (see `workflows.md`: `app.error`, `bug.reported`, a text, a call or an email). The bug desk lets your team finish the job by just talking in Slack.

## What happens
1. The agent posts the alert in Slack (for example "Site error: Alex got a 403 error ... Ticket KAN-16"). It remembers that message as the ticket's thread.
2. **A reply in that thread, or any message that names the ticket, becomes a team note on the Jira ticket** ("Team note from Slack on 2026-10-24 ..."). Private details (card numbers, passwords, emails, phone numbers, keys) are removed first.
3. **When someone says it is fixed** ("fixed and deployed", "resolved", "rolled out") the agent asks in the thread: "Close KAN-16 as fixed? Reply approve ... or keep open."
4. **Reply `approve`** (or yes, ok, close it, go ahead): the agent adds your note to the ticket, closes it, marks the row Fixed with the date on your Confluence known-issues page, tells the team (and Teams, if connected) and confirms in the thread. **Reply `keep open`** (or no, not yet, wait) and nothing changes.
5. Sentences like "not fixed yet", "will be fixed after lunch" or "still not working" are only notes.

Setting in `agent.json` (`guardrails.bug_close`): `"ask"` (the default: approval first), `"auto"` (close as soon as the team says it is fixed) or `"off"` (notes only). A pending question expires after a day. In Practice mode nothing is written anywhere. A ticket already closed in Jira is still picked up by the agent within a few minutes, and the Confluence page is updated.

## It can move the ticket to any status, not only Done
If you connected your own AI (the Reasoning card), it reads each message and decides what the team meant, and Jira does the rest:
| The team says | The ticket |
|---|---|
| "I'll dig into the payment service this afternoon" | moves to **In Progress** (applied at once, announced in the thread) |
| "can't go on until Stripe support answers" | moves to **Blocked** (or whatever your project calls a waiting status) |
| "the redirect is sorted, went out in 2.4.1" | asks first, then **Done** |
| "duplicate of the old checkout bug" | asks first, then your project's **Won't Do** type status, marked "Closed, not fixed" on the Confluence page |
| "customers are seeing the 403 again" (on a closed ticket) | asks first, then **To Do** again and the page row shows Open |
| a question, a plan, a guess | a note on the ticket, nothing else |
Safety: the AI is shown only the moves Jira says that ticket can make right now and can only choose one of them; anything else becomes a note. Private details are removed before the model sees the message, and the team's words are treated as data, never as instructions. Closing, closing as not fixed and reopening always wait for approval (unless `guardrails.bug_close` is `auto`). Without an AI (or with `guardrails.bug_ai: false`, or if the model is down) plain-word rules do the same job for the common cases. At most 60 model reads an hour.

## Connect it (once, about five minutes)
The agent needs to hear your Slack channel. In your Slack app (api.slack.com/apps, your app, **Event Subscriptions**): turn them on, set the **Request URL** to `https://YOUR-ADDRESS/slack/events` (the same address as your slash commands), subscribe to the bot events `message.channels` and `message.groups`, and under **OAuth and Permissions** add the scopes `channels:history` and `groups:history`; then reinstall the app and invite it to the channel (`/invite @your-agent`). The manifest on the Connect tab already has all of this. The agent checks Slack's signature on every event.

Microsoft Teams: the Teams connection can only send messages, so replies in Teams are not read. Teams still gets every alert and every "fixed and closed" message, and you can approve from Slack, from the `/fixed` command, from the `bug.resolved` event or by closing the ticket in Jira.
