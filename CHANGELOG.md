# Changelog

## 0.11.0
Orders tab: every tracking link is saved permanently from the first order (SQLite, order number, steps and times only) with search, copy and open, step history, spreadsheet export, and a warning when a link was made with an address that is no longer your public address. Links no longer expire by default. Setup now asks for the business website, customer service phone, other service numbers, hours and address, and order links cannot go live until those are filled in and the public address has been tested. See docs/orders-and-private-records.md.

## 0.10.0
New order tracking page: Speakvora logo, your business name and initials badge, a headline for each step, a step bar worded for your industry, your own pickup or delivery estimate, the time of the latest update, and Call / Text buttons so a customer can reach your business straight from the page. Pharmacy and dispensary orders get the page too (never showing what was ordered) and keep their texts at placed, ready and picked up. See docs/orders-and-private-records.md.

## 0.9.1
First real order-tracker test passed (one text with the link, delivered; the page followed received, preparing, ready, picked up). Fix: a spoken line that is not in the bundle yet no longer leaves a double space in a text.

## 0.9.0
Order tracking links: customers get one text with a private page that follows their order (received, preparing, ready, picked up; or on its way, delivered); later texts are opt-in. Pharmacy and dispensary texts at order placed, ready and picked up, never naming the contents. Private details only from your own connected records system, only to a number your system lists, only after you approve the settings that make that safe; erased from the agent's own records right after sending. A 1,140-rule draft catalog of industry call-handling controls with the policy settings to complete, shown in Settings, and the first controls enforced in code (emergency redirect, no passwords or card numbers, caller ID is never identity). Laundry bundles now have order workflows. See docs/orders-and-private-records.md.

## 0.8.1
Fixes from the first live phone test: after an answer the agent asks whether there is anything else and ends politely on "no thanks" (it used to hang up); silence no longer drops the call (re-asks once, then connects a person); callers can interrupt the prompt by speaking; the "anything else" prompt listens for a small set of words so "no thanks" is not misheard as "person". Tested on a real call: hours by voice, goodbye, and "I need to speak to a person" connecting the staff phone.

## 0.8.0
Service-business call flow: callers can say what they want (opt-in, English) as well as press a key; asking for a person always connects to your staff phone; two misses connect a person instead of looping. Follow-up workflows with team tasks for quotes, finished work and next visits. Industry rules (what the AI may never say, blocked terms that stop an AI-written message from being sent) for clinic, pharmacy, legal, finance, collections, corrections, education, public services and more. Customer details are removed from finished jobs and old log lines after the days you choose. See docs/industry-rules.md.

## 0.7.1
Library now has an Add your own phrases box (one phrase per line, each voiced once and added to your library) and Suggest more with my AI. Lines your AI keeps saying become library lines: when your connected AI writes the same generic customer line several times, you can add it to your library (voiced once, then instant, free and offline), or switch on automatic adding inside a monthly character budget. Digits, emails, links and names are never learned. See docs/smart-ai.md.

## 0.7.0
Smarter AI. After your AI passes its connection test the agent learns your business (from facts you typed, workflow names, calendar event types, and a website or notes you provide) into a profile you review, edit and approve before the AI uses it; nothing about customers is read and nothing goes to Speakvora. New limits card in Settings with fixed safety rules and ceilings for AI conversations. A caller who presses 0 is connected to your staff phone (new `transfer` workflow action), with a polite fallback when no number is set. Live AI phone conversations and AI text replies are not in this release; their switches are saved but inactive. See docs/smart-ai.md.

## 0.6.1
Settings now has an "Open my account" button to your Speakvora account on the website (renew, add a location, licence codes, new versions). The agent itself still needs no internet.

## 0.6.0
Several business locations in one dashboard (commercial licence). A Locations button at the top (orange, only with a commercial licence code) opens a menu to switch between your locations, shows which need you or need setup, and offers an All locations overview and Add a location. Each location keeps its own agent, data and licence; this dashboard opens the others' dashboards through itself, with a Back bar. Licence codes are checked offline (Ed25519, standard library): only the Locations menu depends on the code, never your bundle or its audio; after the 12-month term there are 30 days of grace. See docs/multi-location.md.

## 0.5.4
Wording: the bundle licence is now a 12-month licence per business location that covers updates, the dashboard and support; renewing is optional and the audio you downloaded keeps working for ever. The agent's update notices say so. No behaviour change.

## 0.5.3
Security hardening. The dashboard now opens only on the computer running the agent: a request that arrives through a tunnel or reverse proxy (forwarding headers, or a public Host name) is refused, so putting the agent's webhook routes on the internet no longer exposes the dashboard (set `dashboard.allow_remote` to true to turn this off on purpose). Webhook routes accept at most 240 requests a minute per sender. New tests: hostile model output and injected customer messages cannot add recipients, actions, channels or destinations beyond what the workflow allows; unsigned events are refused; logs never contain keys. See docs/security.md.

## 0.5.2
New `sv-agent demo`: a 30-second tour that needs no keys, no placeholders and no internet. It fires a sample "order ready" event in dry run, prints the text it would send, and plays the recorded line (afplay on macOS, ffplay/mpv/paplay/aplay on Linux, PowerShell on Windows). It works at any time of day (quiet hours are off for the demo) and changes nothing on disk. Docs now say plainly that dry run never queues; the offline queue fills only in live mode when the internet is down, and anything that may have arrived is held for review rather than sent again.

## 0.5.1
Fix: `queue flush`, `jobs retry` and `proposals approve` no longer stop with "Environment variable ... is not set" when an optional key you never needed (for example a Slack signing secret) is not filled in. They now work like the dashboard and `run`. The running agent already sent its queue by itself; this fixes the manual command.

## 0.5.0
Set everything up from the dashboard, no developer needed. A new Connect tab (the first thing you see before anything has been sent) has a card for your business, texts and calls (Twilio), Slack (with a ready-made app manifest), Microsoft Teams, Google or Outlook calendar (private link), email and AI reasoning with your own key. Each card saves to agent.json (previous version kept as .bak) and to a private key store (agent-state/secrets.json, mode 600; environment variables still win), applies without a restart, and has plain-language Test buttons. Switch workflows on and off, add tools that send events (Shopify, GitHub, GitLab, PagerDuty, Stripe, Calendly, point of sale), and go live only when a checklist passes; the choice is remembered. `run` no longer stops when a key is missing: it starts so the dashboard can collect it. See docs/connect-dashboard.md.
A new, simpler dashboard: Home shows what needs you as plain cards with Approve, Decline and "do this automatically from now on" (saved choices apply next time; an Ask me first switch holds texts, calls or emails until you click); a + Add button on Connect for more connections including your own apps (send to a web address with a key, tell it what workflows did, or get a private address and token so your app, Zapier, Make or n8n can send events); a Library tab where the agent can send Speakvora the lines it is missing, if you agree, and notices newer bundle versions; Settings for the switches, saved choices, pause and sharing. Failed jobs can be dismissed. See docs/dashboard.md.

## 0.4.0
Optional reasoning with your own AI key. A workflow can add a `reason` step for requests the rules cannot handle ("review these conversations and decide who needs a refund"). Only the inputs the workflow chooses are sent (emails, phone numbers and card-like numbers redacted, contacts by id and name only) to your own provider (any OpenAI-compatible endpoint including a local Ollama for fully offline use, or Anthropic). The model only PROPOSES: proposals are checked against the actions, channels and URLs the workflow allows, wait in the dashboard under Needs you with the reasoning and exactly what was sent, and run as normal journaled sends (consent, STOP, quiet hours, limits, kill switch) only after a person approves. `auto_allow` can run chosen low-risk actions without a click. Per-hour limit, offline queueing, dry run that never calls the model, slash commands answered at once and reasoned in the background. New `proposals list|approve|reject` commands and dashboard approve/reject. See docs/reasoning.md and examples/refund-review/.

## 0.3.0
Job journal. Every send (text, call, Slack or Teams post, email, calendar entry, webhook, API write) is written down before it is sent and tracked through pending, sending, queued, sent, delivered or undelivered (from Twilio's status callback), needs_review, failed, blocked, expired and cancelled. A crash while sending is never sent again by itself (needs_review); jobs written but not started are queued; events accepted from your app are written down before the answer and resumed after a restart without repeating finished actions. A timeout or server error is now needs_review instead of a plain error. New `jobs list|cancel|retry|mark-sent` commands, job counts in `/health`, Twilio idempotency header and a configurable idempotency header for your own providers (best effort). See docs/jobs-and-recovery.md. Replaces the 0.2.0 outbox list (converted automatically).
Local dashboard at /dashboard on the running agent: counts, jobs that need you (cancel, retry, mark arrived or send again after a review), recent activity, bundle coverage, pause-all button and a form to request more lines. See docs/dashboard.md.

## 0.2.0
Offline queue: when the network is down, texts, calls, Slack and Teams posts, email, calendar entries and webhooks wait in an outbox on disk and are sent in order when the connection returns. Only requests that provably never left the machine are queued (a timeout or server error is never retried, so nothing is sent twice); safety checks (consent, STOP, quiet hours, limits, kill switch) run again at send time; old actions expire (`queue.max_age_minutes`). New `queue list|flush|drop` command, `queued` in `/health` and `check`. See docs/offline-and-queue.md.

## 0.1.0
First public release: workflows from events, calendars (Google, Microsoft 365), texts and calls (Twilio or any provider API), WhatsApp, Slack, Teams, SMTP and IMAP email, webhook mappings (GitHub, GitLab, PagerDuty, Stripe, Shopify, Calendly, generic), the `http` action, required industry notices, consent, STOP, quiet hours, limits modes, kill switch, dry-run by default, and the `slots` command that asks for missing spoken lines.
