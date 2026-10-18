# Workflows: make your own

A workflow is "when this happens, do this". You make them in the dashboard, with no files and no code.

**Where:** Settings, **AI controls**, **Workflows**.

![Workflows: yours on top, the ready-made ones below, each with a switch](https://speakvora.com/assets/guide/sheet-workflows.png)

* **Yours**: the workflows you made, each with a switch and a one-line summary ("Someone texts “menu” or “specials” → reply to their text"). Tap one to edit it.
* **Ready-made for your industry**: the ones that came with your bundle. Switch them on or off, and choose "Also tell" an app of yours.
* **New workflow**: start from scratch, or tap one of the ideas: "Send my menu when someone texts menu", "Thank customers after a visit", "Remind customers the day before a booking", "Send my team a morning summary".

## Making one
![The workflow builder: When, Then, Name it](https://speakvora.com/assets/guide/sheet-workflow-builder.png)

**1 · When** (pick one)
| Choice | What it needs from you |
|---|---|
| SMS Person: someone texts a word | The words, for example `menu, specials`. Any text containing one of them starts it, even inside a long message. Your words win over the ready-made ones. STOP, START and HELP are handled for you by law |
| App Event: something happens in my app | Pick the event (an order is ready, someone books, a payment fails...) or type the event name your app sends |
| Booking: a booking is coming up | How long before (15 minutes to 2 days), and optionally a word the booking's title must contain. Needs your calendar connected |
| Daily: every day at a time | The time and the days |

**2 · Then** (up to 5 steps, in order)
| Step | What it does |
|---|---|
| Reply to their text | Answers the text they just sent (only when the trigger is a text) |
| Text the customer | Sends a text to the customer (needs Twilio; follows consent, STOP, quiet hours and your limits) |
| Tell my team | Posts to Slack or Teams |
| Email someone | Sends an email (needs Email connected) |
Write the message, or press **Use a line from my library** to insert one of your saved phrases. The **Insert** chips add the details that change: your business name, hours, address, phone, the customer's name, the booking time, what they texted, today's bookings.

**3 · Name it**, then **Preview** (shows each message with sample details; nothing is sent) and **Save and turn on**.

## What keeps it safe
* A workflow you make runs through exactly the same checks as the ready-made ones: consent, STOP, quiet hours, per-person and hourly limits, **Ask before sending** (approve on Home) and practice mode. Until you press **Go live**, it only records what it would do.
* The builder explains problems in plain words: a missing name, no words, a variable it does not know, a message that looks like a card number or password.
* Your workflows are saved in `agent-state/custom_workflows.json`, separate from the bundle, so a bundle update never overwrites them. Up to 30.
* A workflow can be switched off or deleted at any time (open it, **Delete workflow**).

## Examples
* **Menu by text**: When a customer texts `menu` → Reply: "Hi from {{business}}! Our menu is at …. We are open {{fact:hours}}."
* **Thank after a visit**: When your app sends `visit.completed` → Text the customer: "Thanks for visiting {{business}}, {{customer.name}}!"
* **Day-before reminder**: Booking: a booking is coming up, 1 day before → Text: "Hi {{customer.name}}, a reminder from {{business}}: we have you booked for {{start_local}}."
* **Morning summary**: Every day at 09:00 → Tell my team: "Good morning! Today: {{today_text}}".
