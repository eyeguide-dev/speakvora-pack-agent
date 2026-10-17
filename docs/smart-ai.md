# A smarter AI: it learns your business, and stays inside your limits

When you connect your own AI (Connect, AI reasoning) and the test passes, the agent starts learning your business by itself. Nothing is sent anywhere except to **your** AI provider, and nothing goes to Speakvora.

## What it reads
- the business name and the facts you typed (your staff phone number is left out);
- your bundle's industry and the names of your workflows;
- the types of upcoming calendar events (digits removed), if a calendar is connected;
- a website address and notes, only if you type them in Library.

It never reads customer names, phone numbers, messages or payment details. Emails, phone numbers and card-like numbers are replaced before anything leaves your computer.

## Review before it is used
The result is a short profile: summary, tone, hours, services, policies, common questions with answers, and **things it could not answer**. It starts as *needs review* and your AI does not use it until you press **Approve**. You can edit it, learn again, or **Forget it** (deletes `agent-state/business_profile.json`). The AI is told to use only what the profile says and never to invent prices, hours or policies.

Find it in the dashboard: **Library, What your AI knows about your business**.

## Limits you set (Settings)
Always on, not changeable from any dashboard:
1. It says it is an automated assistant at the start of every call and text conversation.
2. It never takes card numbers, passwords or ID numbers, and gives no medical, legal, financial or emergency advice.
3. It answers only from approved information and says so when it does not know.
4. It cannot refund, charge, cancel, change a record or delete anything.
5. A caller who asks for a person is connected to your staff phone right away; two unanswered questions in a row do the same.
6. Consent, STOP, quiet hours, per-person limits and the pause switch apply to every message and call.

You choose, inside fixed ceilings: whether the AI answers texts, whether it answers calls, most turns per conversation (max 40), longest call (max 20 minutes), most replies per hour (max 200), which actions it may do by itself (tell your team, send a confirmation text, add a calendar booking), topics it must hand to a person, and the words that mean "I want a person". Saved in `agent.json` under `guardrails`.

## Connecting a caller to a person
Press 0 in the phone menu, or set the staff number (`oncall_phone`) and the agent dials it with `<Dial>` and bridges the call. With no number set, the caller hears a polite fallback and your team is notified. The `transfer` action can also be added to any phone-menu option in `workflows.json`: `{"action":"transfer","to":"{{fact:oncall_phone}}"}`.

## What is released and what is not
Released in 0.7.0: business profile (learn, review, approve, forget), guardrails storage and dashboard, human transfer from the phone menu, detection of "person/manager/operator" words (`guardrails.wants_human`).
**Not in this release:** the live two-way phone conversation (interrupting, speaking replies in real time) and AI text replies. The switches for them are saved but do nothing yet; they will be listed here when they exist and have passed real calls.

API: `GET /dash/api/brain`, `POST /dash/api/brain/{learn,approve,save,forget}`, `GET|POST /dash/api/guardrails` (token-protected, local only like every dashboard route).
