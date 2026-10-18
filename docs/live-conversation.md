# Live conversation

Your own AI answers customers in real time, on texts and on calls, inside limits that live in this program and cannot be switched off from a dashboard.

## Turn it on
1. Connect your AI (Connect, Assistant) and add your staff phone (Connect, Apps, Twilio texts and calls, or `facts.oncall_phone`), so a person can always take over.
2. Settings, **AI controls**: switch on **Answer texts** and/or **Answer calls** (calls: English bundles for now).
3. Stay in **Practice mode** first: for texts the agent records what it *would* have said (Home, Latest activity) and sends nothing. Go live when you like the answers.

## What the customer experiences
* **Texts**: keyword workflows (hours, address, reservations, order status, a person) still answer first, instantly. Anything else goes to the AI, which answers in one or two short sentences from your business profile, facts, approved lines and (when tracking is on) the status of an order number the customer gives. The first reply says it is the automated assistant.
* **Calls**: a short greeting, then an open microphone: the caller can speak at any time, even over the assistant, or press a key. What the menu already handles (hours, booking, status, a person) plays your recorded lines at once. Anything else goes to the AI, which plays an approved library line (instant and free) or writes a short answer that is voiced in your bundle's voice (cached, so a repeated answer costs nothing). If the AI needs more than about a second, a short "one moment" plays and the call waits, so the line never goes quiet. After an answer the caller can keep talking; silence or "that's all" ends the call politely.

## Actions (only what you allow)
In Settings, Built-in safeguards, **Actions your AI may do by itself** you can allow three things: tell the team (**notify**, a short summary to Slack or Teams for a booking request, a callback or a complaint), text the customer a confirmation (**sms**), and add a booking to your calendar (**calendar_create**, only when the customer gave a day and time). Nothing is allowed by default. Anything else the AI asks for is dropped, and every allowed action goes through the usual checks, quiet hours, limits and "ask before sending", so you can still approve each one on Home. Each industry gets a short working style: a service business (trades, beauty, auto, laundry) collects name, need and preferred time one question at a time and notifies the team; a restaurant does the same for reservations; a store hands returns and special orders to a person.

## Knowledge
Add your menu, price list, policies or website in Library, Knowledge ([knowledge.md](knowledge.md)). The passages that match a customer's question go to the AI with it, and a price, time or phone number that appears in your knowledge counts as approved. Questions nothing answers are collected there so you can add the answer.

## Limits (always on)
* Emergencies, poison/exposure, passwords and card numbers, opt-out words and "a person please" never reach the AI. They are handled by the agent exactly as before.
* Every answer is checked before it is said: your industry's blocked terms (a clinic never says a diagnosis, a restaurant never promises "allergy free"), phone numbers that are not yours, prices that are not in your facts or approved lines, claiming to be a person. A failed check, an AI that is down or slow, or a reached cap connects a person (the staff transfer on calls, your "a person will contact you" workflow on texts).
* Caps (Settings, Built-in safeguards): turns per conversation, minutes per call, AI replies per hour, and the monthly characters voiced for live answers (`talk_chars_per_month`).
* Industries with private records (clinic, pharmacy, dispensary, legal, finance, education, lodging, public) never get order or record status from the AI: they use the connected-system lookups only.
* The AI only answers. It cannot send, change, refund or approve anything.

## Learning
Lines the AI keeps writing become suggestions in **Library, To review**. You approve them once and from then on they play as recorded library lines: instant, and free.

## Cost
The AI's own provider bills you per answer (a few hundred tokens). Voicing a new live answer uses your Speakvora characters (cached for a day, capped monthly). Library lines and the menu cost nothing extra.
