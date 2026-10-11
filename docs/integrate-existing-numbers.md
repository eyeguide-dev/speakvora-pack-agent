# Use the phone and text numbers you already have

Everything here happens in YOUR accounts. The agent never sees a number that you do not point at it, and Speakvora hosts nothing.

## Texts
| You have | How to connect | Notes |
|---|---|---|
| A **Twilio** number | In Twilio, set the number's "A message comes in" webhook to `https://YOUR-AGENT/twilio/sms` and fill `twilio` in agent.json | Fastest path. US numbers need carrier registration (A2P 10DLC or toll-free verification) in your Twilio account. |
| A number at **another provider** (Bandwidth, Vonage, Plivo, Telnyx, MessageBird, a local carrier API...) | Describe its send API once in `sms_provider` (url, headers, json with `{{to}}` and `{{text}}`) and map its inbound webhook as a `source` with `"as": "sms"` | No Twilio account needed. See `connect-anything.md`. Your provider bills you. |
| A **landline or toll-free number** you want to keep | Ask your carrier/Twilio about "hosted SMS" or porting the number to a texting provider | Porting is done by your provider; it can take days. Keep your old number until it completes. |
| Only a **mobile number** | Use a new business number for the agent and tell customers; do not automate a personal mobile number | Carriers block automated texting from personal numbers. |

## Calls
| You have | How to connect |
|---|---|
| **Twilio** number | Set "A call comes in" to `https://YOUR-AGENT/twilio/call`. Outbound calls use the same number. |
| Your **existing business line** at a carrier or phone company | Keep it. Turn on call forwarding (all calls, or only when busy / no answer) to a Twilio number that points at the agent. Customers still dial your number. |
| A **PBX or phone system** (3CX, RingCentral, Asterisk, FreePBX...) | Add a SIP trunk from the PBX to Twilio (or another SIP provider) and route the calls you choose to it, for example after hours. |
| Another provider that understands TwiML-style instructions (TeXML) | Use `call_provider` with the `{{twiml}}` value. Inbound menus need Twilio today. |

## Chat and calendars
Slack and Teams: your own app or incoming webhook in your workspace. Calendars: a private ICS link (read-only) or your own OAuth client for Google or Microsoft 365. See `setup-services.md`. Nothing is installed in your chat or calendar tenant by us.

## Your applications
Send events with one signed web request, map any system's webhook, or call any web API (`connect-anything.md`). Your app keeps working if the agent is stopped.

## Try it safely
Everything starts in dry-run: the agent writes what it would do to `agent-state/agent.log.jsonl`. Connect one thing at a time, use a test number you control as the only allowed recipient (`recipients.allow`), then widen.
