# Workflows reference

![Workflows list](https://speakvora.com/assets/guide/sheet-workflows.png)

![The workflow builder](https://speakvora.com/assets/guide/sheet-workflow-builder.png)

*Screens come from a throwaway test setup; addresses and secrets shown are fake examples.*


`workflows.json` is a list of workflows: **on** (what starts it), optional **when**, and **do** (actions in order). Every send passes the safety checks first.

## Triggers (`on`)
| Trigger | Example | Starts when |
|---|---|---|
| `event` | `{"event": "order.ready"}` | your app or a mapped webhook sends that event |
| `calendar` | `{"calendar": {"starts_in_minutes": 1440, "window_minutes": 30, "title_contains": "Reservation"}}` | a Google Calendar event is about to start (once per event) |
| `sms` | `{"sms": {"keywords": ["hours", "open"]}}` | someone texts your number a message with a keyword (STOP/START/HELP are built in) |
| `call` | `{"call": {"menu": {"prompt": "menu_prompt", "options": {"1": [...], "0": [...]}}}}` | someone calls: plays the prompt, then runs the actions of the digit they press |
| `slack_command` | `{"slack_command": "/say"}` | staff use the slash command |
| `email` | `{"email": {"keywords": ["refund"]}}` | a customer emails your support inbox (needs `inbox` in agent.json) |
| `schedule` | `{"schedule": {"at": "09:30", "days": ["mon","tue"]}}` | a time of day (your timezone) |
| `calendar` with `smart` | `{"calendar": {"smart": true, "title_contains": "Appointment"}}` | the **smart reminder**: the times you tick in the dashboard (the day before, the morning of, two hours before...); the line said fits each time (`{{slotvar:reminder.slot}}`) |
| `sms` with `when_closed` | `{"sms": {"when_closed": true}}` | a text nothing else answered, outside the opening times you set (never when unset) |

## Actions (`do`)
`notify` (text: tells your staff on Slack and/or Teams, whichever you connected), `teams` (text), `sms` (to, text, optional `"channel": "whatsapp"`), `call` (to, play: [lines]), `slack` (text, channel, optional audio), `email` (to, subject, text, optional audio), `http` (any API), `calendar_create`, `reply` (answer to the text, call or slash command in progress), `play` (add pack lines to the call), `log`. Add `"if": {"customer.prefers_call": "*"}` to run an action only when a value exists.

## Ready-made kits
Each industry's ready-made workflows carry `title` and `what` (plain words shown in the dashboard), `kit: true`, `enabled: false` and `approved: false`: a kit workflow runs only after you have opened it and pressed Approve and turn on (see `industry-kits.md`). `priority: true` puts a careful answer (a sensitive question passed to a person) before the general keyword answers. The action `sale_watch` is Announce a sale (see `announce-a-sale.md`).

## Values
`{{customer.name}}`, `{{order.number}}`, `{{start_local}}` (calendar), `{{fact:hours}}` (from `facts` in agent.json), `{{slot:order_ready}}` (the text of a pack line), `{{slotvar:command.arg1}}` (a line chosen at run time), `{{last.sms}}` (what really happened to the earlier text: sent, blocked, skipped, error or dry_run). Templates only substitute text; nothing in a payload can run code.

## Lines (slots)
Workflows ask for **slots** ("order_ready"), not phrase numbers, so the same workflow runs on every pack of the industry in any language. `sh sv-agent slots --all` shows every slot your industry normally needs.
