# Connect anything

The agent has one connector shape. Whatever system you use, you connect it by writing a short mapping in `agent.json`. No code, and your app keeps working if the agent is off.

## 1. Anything that can send a webhook -> events (`sources`)
Most tools (Shopify, Square, Toast, Calendly, a booking plugin, your own app) can POST to a web address when something happens. Point them at `https://YOUR-AGENT-ADDRESS/hook/<name>` and describe how its fields map to the agent's event:

```json
"sources": [{
  "name": "shopify", "path": "/hook/shopify",
  "auth": {"type": "hmac", "header": "X-Shopify-Hmac-Sha256", "secret": "env:SHOPIFY_WEBHOOK_SECRET", "encoding": "base64"},
  "map": {
    "event": {"from": "headers.x-shopify-topic", "values": {"orders/fulfilled": "order.ready"}},
    "id": "headers.x-shopify-webhook-id",
    "customer.name": "payload.customer.first_name",
    "customer.phone": "payload.customer.phone",
    "customer.sms_consent": {"from": "payload.customer.sms_marketing_consent.state", "values": {"subscribed": true}, "default": false},
    "order.number": "payload.order_number"}}]
```
* Left side: where the value goes in the event (`event`, `id`, `customer.name`, `customer.phone`, `customer.sms_consent`, `order.number`, `start_text`, `party`, anything your workflows use).
* Right side: where it comes from: `payload.a.b` (the JSON body), `headers.name`, `query.name`, `{"const": value}`, or `{"from": ..., "values": {...}, "default": ...}` to translate values.
* An event the map does not know (no `event` after mapping) is ignored, so you only act on what you choose.
* **Consent matters:** map `customer.sms_consent` to a real field where the customer agreed to texts. If there is none, leave it out and the agent will not text that person (it will still tell your staff on Slack).
* Auth types: `token_header` (GitLab: a header holding the shared secret), `hmac` (any header carrying an HMAC of the body, hex or base64), `stripe_style` (`t=...,v1=...`, used by Stripe and Calendly), `bearer`, and `sv_hmac` (our own, for your app). A source without auth is refused unless the agent is in dry-run.
* Ready-made mappings, added with one command (`sh sv-agent source add NAME`): **github**, **gitlab**, **pagerduty**, **stripe**, **shopify**, **calendly**, **generic-pos**. GitHub and GitLab turn failed pipelines, review requests, releases and security alerts into events; the devops workflows text and call your on-call phone (even at night) and post to Slack or Teams.
* An event can be built from several fields: `{"template": "{{headers.x-github-event}}.{{payload.action}}", "values": {...}}`.

## 2. Call any API from a workflow (`http` action)
```json
{"action": "http", "method": "GET", "url": "https://api.yourcrm.com/orders/{{order.number}}", "headers": {"Authorization": "Bearer env..."}, "save_as": "crm"}
```
Later actions can use the answer: `{{http.crm.status}}`. The server name must be written out literally (only the path, query and body can use `{{...}}`), so data from a webhook can never choose where a request goes.

## 3. Your own app: one signed call
Send `POST /event` with `X-SV-Timestamp` and `X-SV-Signature` (`sha256=` + HMAC-SHA256 of `timestamp.body` with your shared secret). The restaurant example's `agent_hook.py` is 15 lines, never waits more than 2 seconds and never raises, so the agent can't break your app.

## 4. Calendar, chat, phone, texts, email and WhatsApp
Google Calendar and Microsoft 365 calendars, Slack and Teams, Twilio texts, calls and WhatsApp, SMTP email and an inbound-email inbox are built in.
Set up once in `agent.json` (see `setup-services.md`). Google Calendar can be a private iCal address (no sign-in) or your own OAuth client.

## 5. Missing a spoken line?
`sh sv-agent slots` lists lines your workflows need that this pack does not have yet. `sh sv-agent slots --send` asks Speakvora; the phrase bot writes and voices them for every pack of this industry and language and they arrive in the next pack version.
