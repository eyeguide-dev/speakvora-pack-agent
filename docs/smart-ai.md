# A smarter AI: it learns your business, and stays inside your limits

![AI controls](https://speakvora.com/assets/guide/sheet-aicontrols.png)

![The Your AI form](https://speakvora.com/assets/guide/sheet-ai.png)

*Screens come from a throwaway test setup; addresses and secrets shown are fake examples.*


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

## Write for me (0.24.0)
Not sure how to word a line? In **Add your own phrases**, under **Or let your AI write it**, say when you would use it (for example: *tell a customer their order is delayed*) and press **Write options**. Your own AI writes a few different ways to say it, in your business's voice. Nothing is voiced or added until you press **Add** on one you like; then it is voiced once and joins your library. The AI writes only general lines (no names, numbers, prices, times or contact details, no advice, and no promises such as refunds or discounts), and it needs your AI connected (Connect, Apps).

## Add your own phrases (0.7.1)
In the dashboard, open **Library**: the first box is **Add your own phrases**. Type or paste one phrase on each line (up to 30 at a time) and press **Add to my library**. Each line is voiced once in your bundle's voice and becomes a line any workflow can play, instant, free and offline. **Suggest more with my AI** asks your connected AI for up to 10 new lines in the same voice; they wait as suggestions until you press Add or No thanks. Lines with emails, links or card-like numbers are skipped with the reason shown. Same monthly character budget as below. API: `POST /dash/api/learned/{lines,suggest,dismiss}`.

## Lines your AI keeps saying become library lines (0.7.1)
When your AI writes the same customer-facing text or email again and again (and you approved it), the agent counts it. At the repeat count you choose (default 3, range 2 to 20) it shows up in **Library, Lines your AI keeps saying**. Press **Add** and the line is voiced once with your Speakvora API key (`SPEAKVORA_KEY`) in your bundle's own voice, saved in `agent-state/learned/`, and joins your library: any workflow can play it by id (`learned:<id>`) or search, instantly, offline and free from then on. **Remove** deletes it.
- Only generic lines qualify. Anything with digits, emails, links, a person's name or personal data is skipped (it would not repeat, and could hold customer data).
- Automatic adding is **off** until you switch it on in Settings. It then adds at most 3 a day.
- Spend is capped in code: a monthly character budget (default 3,000, ceiling 20,000). A line that does not fit is not added.
- Only the line to voice is sent to Speakvora. API: `GET /dash/api/learned`, `POST /dash/api/learned/{add,remove}`.

## Connecting a caller to a person
Press 0 in the phone menu, or set the staff number (`oncall_phone`) and the agent dials it with `<Dial>` and bridges the call. With no number set, the caller hears a polite fallback and your team is notified. The `transfer` action can also be added to any phone-menu option in `workflows.json`: `{"action":"transfer","to":"{{fact:oncall_phone}}"}`.

## What is released and what is not
Released in 0.7.0: business profile (learn, review, approve, forget), guardrails storage and dashboard, human transfer from the phone menu, detection of "person/manager/operator" words (`guardrails.wants_human`).
**Not in this release:** the live two-way phone conversation (interrupting, speaking replies in real time) and AI text replies. The switches for them are saved but do nothing yet; they will be listed here when they exist and have passed real calls.

API: `GET /dash/api/brain`, `POST /dash/api/brain/{learn,approve,save,forget}`, `GET|POST /dash/api/guardrails` (token-protected, local only like every dashboard route).
