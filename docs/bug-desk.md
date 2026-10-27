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

## It knows what changed, and tells the customer when it is fixed
**What changed before the bug (GitLab and GitHub).** Connect GitLab or GitHub on the Connect tab (it is the same one-address webhook as before: tick Pipeline, Merge request, Release and Deployment events in GitLab; Deployments, Pull requests and Releases in GitHub). The agent remembers each deploy, release and merge (on your computer). When a bug ticket is opened it adds one line to the ticket and to the Slack and Teams alert, for example: *Timing only, not a diagnosis: the newest change before this report was a deploy Fix checkout redirect to production (a1b2c3d) by sam, 35 minutes earlier.* Staging deploys and anything older than 48 hours are ignored (`changes.window_hours`, `changes.environments`, `changes.enabled` in agent.json). If the bug is reported again after a newer deploy, the ticket says so, which shows whether a hotfix helped.
**The customer hears it.** Everyone who reported the bug by text, by email, or through an app event that names them with consent is texted or emailed once when the ticket is closed as fixed: *"good news, the problem you reported is fixed. Please try again, and reply here if it still does not work."* It goes through the normal checks (consent, STOP, quiet hours, limits). A ticket closed as "won't fix" sends nothing. The Jira ticket and the Slack thread say how many people were told. Turn it off with `guardrails.bug_tell_customers: false`.

## When a closed bug comes back (regression)
If a report matches a ticket that was already closed as fixed, the agent opens a new ticket and says so everywhere: the new ticket starts with *"Regression of KAN-17 (closed on 2026-10-20)"*, the two tickets are linked in Jira (if your Jira refuses the link, the old ticket gets a comment instead), the old ticket gets a comment *"The same problem was reported again after it was closed: KAN-21"*, and the Slack and Teams alert begins *"REGRESSION: KAN-17 was marked fixed on 2026-10-20 and was reported again. Reply reopen to reopen it instead."* followed by the usual timing line.
**Reply `reopen` in that alert's thread** and the agent asks the usual question for the OLD ticket ("Reopen KAN-17? Reply approve ..."); `approve` reopens it, `keep open` leaves it closed. Any other reply in that thread is a note on the NEW ticket. Teams cannot be read, so reopen from Slack. The old ticket keeps a count of how many times it came back.
Setting in `agent.json`: `guardrails.bug_regression`: `"flag"` (the default) or `"off"` (a plain new ticket, as before).

## Was the fix real? Fix checks
A person saying "fixed" is not proof. You can give the agent small web checks (for example "does the checkout health page answer 200?") and it will run the right one for the ticket. Add them to `agent.json`:
```
"bug_checks": [{"name": "Checkout page", "match": "checkout pay", "url": "https://shop.example.com/health/checkout",
                "method": "GET", "expect_status": 200, "expect_text": "", "allow_private": false}]
```
`match` is a list of words that must ALL appear in the ticket's summary, page or action (capitals do not matter). A ticket that matches no check is never checked; the thread says so once. `method` is GET or POST (`body` is sent as JSON). `expect_text` is optional text that must appear in the answer.
The thread, the Jira ticket and the log always keep two facts apart: *"Marked fixed by sam at 2026-10-26 14:02 UTC"* (a person said so) and *"Verified by check Checkout page: passed (200 in 340 ms)"* (the check ran). If the check fails you read *"Check Checkout page FAILED (status 500): the ticket is NOT verified. Reply reopen to reopen it."* A failed check never changes the ticket by itself.
**When it runs** (`guardrails.bug_verify`): `"ask"` (the default) runs only when someone replies *verify*, *run the check* or *check it again* in the ticket's thread; `"auto"` runs it right after the ticket is closed; `"auto_reopen"` is like auto and a failed check also asks to reopen the ticket (it reopens without asking only if `bug_close` is `"auto"`); `"off"` never runs one.
**Customers:** `guardrails.bug_tell_after_verify: true` makes the agent text or email the people who reported the bug *only after* a check passed (the default `false` tells them when the ticket is closed, as before). With no matching check, nobody is told while this is on.
**Safety:** one request with an 8 second limit; only the first 20 KB of the answer is read; only http and https; the address must be a public one, so this computer, a private network and cloud metadata addresses are refused unless that one check has `"allow_private": true` (use it for your own internal service); a redirect to a different host is not followed. The check address is never written to Jira or Slack, and nothing is sent in practice mode.

## Evidence on the ticket: what changed, the stack, the logs
Connect your code host in `agent.json` (there is no Connect-tab card for it yet): `"code": {"provider": "github", "repo": "acme/shop", "token": "env:CODE_HOST_TOKEN"}` (GitLab: `"provider": "gitlab"`, repo is the project path or number). Use a read-only token. Together with the deploys the agent already remembers (see above), a new bug ticket then gets a section **Possible causes (evidence, not a diagnosis)**:
1. the files that changed between the previous deploy and the one the report follows: names and plus/minus line counts only, at most 15, never file contents or diffs (a file with a secret-looking name such as `.env`, `secrets.yml` or `id_rsa` is listed by name and marked *(sensitive file name)*);
2. the first 12 lines of the error's stack trace, if the report carried one (`error.stack`), with private details removed;
3. up to 5 recent log lines the site sent (`error.logs`), with private details removed;
4. up to 3 changed files that share words with a stack frame or with the page or action, each with the compare link and the sentence *"Matches stack frame ..."*. This is plain word matching, not an AI, so treat it as a lead to check.
If no code host is set, there is no earlier deploy to compare with, or the code host does not answer, the ticket is created as before with nothing added. The token goes only to your code host; it is never written to a ticket, a message or the log.

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
