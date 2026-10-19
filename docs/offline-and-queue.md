# When the internet goes away: the offline queue

![Home shows what happened and what is waiting](https://speakvora.com/assets/guide/home.png)

*Screens come from a throwaway test setup; addresses and secrets shown are fake examples.*


The voice lines in your pack are files on your own machine, so they keep playing with no connection. Texts, calls, Slack and Teams posts, email, calendar entries and webhooks need the internet. The agent does not lose them.

## What happens
1. A workflow runs while the connection is down.
2. Each action that needs the internet is written to the **outbox** (`agent-state/state.json`, so a restart or a power cut keeps it) and logged as `queued`. Your app still gets an answer (`"status": "queued"`) and `{{last.sms}}` in later steps says `queued`.
3. About once a minute (and once at start-up) the agent tries the outbox, oldest first. When the connection is back, the actions go out in order and are logged as `delivered_from_queue`. It stops at the first action that still cannot leave, so order is kept.
4. The safety checks run again at send time: consent, opt-outs (STOP), quiet hours, limits and the kill switch. Someone who texted STOP while you were offline never gets the queued text.

## What is queued, and what is not
* Queued only when the request provably never left your machine (no network route, DNS failed, connection refused). That is what makes it safe to send again without ever sending twice.
* NOT queued: a timeout or a server error. The other side may already have received it, so the agent logs the error and does not retry. The agent never re-sends it by itself: it is held for your review (needs review) so you can check with the provider and retry or mark it sent.
* Reading from a calendar or inbox while offline is skipped and logged; the next tick tries again.
* Inbound texts and calls reach the agent only when your internet and Twilio can reach it. Nothing can answer an inbound call while the line is down.

## Old actions expire
A reminder call that arrives three hours late is worse than none. Each kind has a life, in minutes, and an action older than that is dropped and logged as `expired`:

```json
"queue": {"enabled": true, "max_age_minutes": {"call": 15, "sms": 120, "email": 1440, "slack": 1440, "teams": 1440, "webhook": 1440, "http": 1440, "calendar_create": 10080}}
```
Change any of them in `agent.json`. A text held back only by quiet hours or a rate limit keeps waiting (until it expires) and goes out when the window opens.

## Commands
```
python -m speakvora_pack_agent queue list          # what is waiting, and for how long
python -m speakvora_pack_agent queue flush         # try to send now
python -m speakvora_pack_agent queue drop <id>     # remove one;  "drop all" removes everything
python -m speakvora_pack_agent check               # also shows how many are waiting
```
`GET /health` shows `"queued": N`.

## Good to know
* Dry-run never queues (it never sends).
* A queued action is stored as the workflow rendered it. Keep secrets in `env:NAME` values in `agent.json`, not written into workflow files.
* The STOP file (kill switch) pauses the queue; removing it lets the queue go out (and anything past its life still expires).


## Dry run never queues
In dry run (the default) nothing is sent and nothing is queued: the agent only records what it would do. The queue fills only in live mode, when a send fails because the internet is down. To see the queue work, go live with a connected service, turn your Wi-Fi off, send an event, check `sv-agent queue list`, and turn Wi-Fi back on.
