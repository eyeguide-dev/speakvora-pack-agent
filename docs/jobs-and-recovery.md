# Jobs: every send is written down first

![Insights](https://speakvora.com/assets/guide/sheet-insights.png)

*Screens come from a throwaway test setup; addresses and secrets shown are fake examples.*


Everything the agent sends out into the world (a text, a call, a Slack or Teams post, an email, a calendar entry, a webhook, a write to your own API) becomes a **job** in `agent-state/state.json` BEFORE it is sent. That is what makes a crash, a power cut or a lost connection safe: nothing is lost, and nothing is sent twice.

## The statuses
| Status | Meaning |
|---|---|
| `pending` | written down, the network call has not started |
| `sending` | the network call started. If the agent dies now, nobody knows whether it arrived |
| `queued` | waiting for the internet (see [offline-and-queue.md](offline-and-queue.md)) or for a quiet-hours window |
| `sent` | the provider accepted it (Twilio gave an id, Slack said ok) |
| `delivered` / `undelivered` | the provider's later report (Twilio's status callback), with its error code if there is one |
| `needs_review` | we cannot know whether it arrived: a timeout, a server error, a dropped connection, or a crash while sending. **It is never sent again by itself** |
| `failed` | the provider refused it (a 4xx, an error answer) or it is not set up. Nothing was sent |
| `blocked` | a safety rule said no (no consent, STOP, kill switch...) |
| `expired` | too old to be useful (calls 15 min, texts 2 h, by default) |
| `cancelled` | stopped by a person |

## What happens after a crash
At start-up the agent calls `recover()`:
* a job caught in `sending` becomes `needs_review`. Check the provider (Twilio's log, Slack), then **mark it sent** or **retry it**;
* a job that was written but never started becomes `queued` and goes out;
* an event your app sent is written down before the app gets its answer. If the agent stopped before every action ran, the event is resumed: actions that already have a job are skipped, the rest run. (Resume covers events sent by your app. Calendar reminders and daily schedules use their own once-per-day keys.)

## Controls
```
python -m speakvora_pack_agent jobs list [--status needs_review]
python -m speakvora_pack_agent jobs cancel <id>          # a job that has not been sent, or one waiting for review
python -m speakvora_pack_agent jobs retry <id>           # failed / expired / cancelled / blocked: back in the queue (safety checks run again)
python -m speakvora_pack_agent jobs retry <id> --confirm-not-sent   # needs_review: you looked at the provider and it did NOT arrive
python -m speakvora_pack_agent jobs mark-sent <id>       # needs_review: you looked and it DID arrive
```
`GET /health` shows the count per status under `jobs`.

## Idempotency
The agent sends Twilio's `I-Twilio-Idempotency-Token` header with the job id on texts and calls, and for your own provider settings (`sms_provider`, `call_provider`) you can add `"idempotency_header": "Idempotency-Key"` and the job id is sent in it. That header is a best-effort extra: support depends on the provider. The guarantee comes from the journal and from never retrying an uncertain send.

## Housekeeping
Finished jobs are kept for 30 days (at most 5,000 jobs). Jobs that are not finished are never removed automatically. A queued job written by agent 0.2.0 is converted when 0.3.0 starts.
