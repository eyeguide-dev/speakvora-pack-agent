# Service-business call flow, industry rules and customer-data privacy

## The call flow (every bundle, tuned for service businesses)
A caller hears the required "automated call" notice, then your menu prompt. They can press a key or, if you switch on `twilio.speech_input` in `agent.json` (English bundles; Twilio bills speech recognition a little extra), just say it. The agent asks Twilio for its phone-call recognition model, and for health bundles (clinic, pharmacy, dispensary) the more accurate, slightly dearer "enhanced" version; set `twilio.speech_enhanced` to true or false to choose:
- **hours / address / where are you** → option 1 (plays your hours line, says your hours)
- **book / appointment / reschedule / quote / estimate** → option 2 (tells the team to call back)
- **status / order / running late** → option 3
- **person / manager / operator / human / someone** → option 0, always, from anywhere: the call is connected to your staff phone (`facts.oncall_phone`) right away.

If the caller says or presses nothing useful, they are asked once more; the second miss connects them to a person. Nobody is left stuck in a menu. With no staff number set, the caller hears a polite call-back message and the team is told.

## Follow-ups for service businesses (trades, beauty and similar)
Your own system sends three events when they are due: `quote.followup_due`, `job.followup_due`, `visit.next_due`. The agent texts the customer (consent and quiet hours apply as always) and, for the first two, posts a "Follow-up task" to your team channel so a person can call. New spoken lines these use (quote check-in, finished-work check-in, next visit due, call-back promise) are listed under Library until your bundle includes them.

## Industry rules (on top of every workflow and every AI suggestion)
Each industry has rules in `industry_rules.py`: what the AI must never say, when it hands over to a person, and blocked terms. An AI-written text or email that contains a blocked term is **never sent** (the card shows it as blocked). Examples: clinic and pharmacy messages may give times and "your order is ready" but never why someone is coming, test results, medicines or dosage; collections never states a debt in a message; education never sends grades.

## What is stored where
- **Speakvora (our servers):** never receives customer names, numbers, messages or appointment details from the agent. Only the line you ask to voice, or a missing-line request, is sent.
- **This computer (the agent):** while it works it keeps customer details in queued jobs and the activity list. After the days you set in Settings (**Days to keep customer names and numbers**, default 7, 0 to 90) finished jobs lose their customer details and old log lines have phone numbers and emails masked. Waiting jobs are never touched.
- **Your AI provider (if connected):** receives only what is sent for a suggestion, with emails, phone numbers and card-like numbers replaced first.

## Please read: this is not a compliance certificate
Not having our servers receive customer data greatly reduces risk, but it does **not** by itself make a business HIPAA-compliant or compliant with any other law. The local computer, the phone provider (for example Twilio), the calendar or email you connect, and any AI provider you connect each handle data too. A health, legal, finance or similar business should have its own compliance review and a signed agreement with each provider that touches regulated data (for HIPAA that is a business associate agreement), or leave that data out of the AI and out of texts. The industry rules above reduce what the agent will say; they do not replace that review.

## Every industry's own "a person takes this" words
Each industry has words that mean the question needs a staff member, not the assistant, taken from what that industry's staff must decide (see the draft controls in Settings). A caller who says one is connected to staff and a texter is told a team member will call; your team is notified. Examples: restaurants hand any allergy question to staff; hotels never confirm who is staying; retail and laundry send refunds, damage and claims to a person; trades send gas, flooding and permits; auto repair sends diagnosis, authorising repairs and warranty; education sends grades, records, custody and pickup; legal sends advice, deadlines and the case; finance sends balances, transfers and fraud; collections send disputes and hardship; corrections send anything about a person held; public services send cases, benefits and immigration; IT support sends security incidents and admin changes. In every industry these words also go to a person: complaint, lawyer, attorney, lawsuit, scam, stolen.

A caller who says "stop calling me", "do not call" or "take me off" is opted out at once (calls and texts), with no staff approval, the same as replying STOP.
