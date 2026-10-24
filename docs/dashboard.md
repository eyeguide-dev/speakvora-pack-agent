# The dashboard

![Home](https://speakvora.com/assets/guide/home.png)

![Settings](https://speakvora.com/assets/guide/settings.png)

![Library](https://speakvora.com/assets/guide/library-saved.png)

*Screens come from a throwaway test setup; addresses and secrets shown are fake examples.*


A small page that runs inside your agent, on your own computer. Start the agent and open the address it prints (`.../dashboard#token=...`). The part after `#` is your access token: it never goes to a server and never appears in a log. It is kept in `agent-state/dashboard-token`, or set your own with `SV_DASHBOARD_TOKEN`.

It is built so a business owner can set everything up alone: four places on a bar at the bottom, plain words, one big button for the thing you came to do, and every detail one tap away. At the top: your business name (tap it for your business details, and your locations if you have several) and a green **Agent live** or amber **Practice mode** pill (tap it to go live).

## Home: your day at a glance
* **Handled / Needs you / Orders** counts for today.
* **All caught up**, or the cards that need you: big **Approve** and **Decline** buttons for anything the agent is holding (and for each suggestion from your AI). **Remember my choice** does the same thing automatically next time (or never, if you declined). A message the agent could not confirm shows **It arrived** or **It did not: send again**; a failure shows **Try again** or **Dismiss** with the reason in plain words.
* **Phrases to review**: drafts from your assistant waiting in the Library.
* **Ask Speakvora**: a box to ask or tell your own AI something ("Summarize today", "Write phrases"). It only suggests.
* **Latest activity**: calls, texts, orders and messages in plain sentences, with an **Insights** button (conversations, how many needed a person, texts your AI answered, how fast it answered, top topics and the questions it could not answer, for 7 or 30 days); **View all** filters by calls, texts, needed a person, orders and problems. Tap a call or text for its summary and (if switched on) its words.

## Connect: Apps, Assistant, Orders
* **Apps**: what is connected (Twilio texts and calls, Slack, Google Calendar, your AI...), a search box, and every app you can add with a **Connect** button: Microsoft Teams, Email, tools such as Shopify, GitHub, GitLab, PagerDuty, Stripe, Calendly and point of sale (each opens a step-by-step guide with your address, a secret to copy or paste, a **Save and test** button and a **Connected** state; see [tool-connections.md](tool-connections.md)), and **My apps** (send to your own system, or let your system send events here). Tap a connected app to change or test it.
* **Assistant**: a chat with your own AI about your calls and texts, or to have it write phrases. It answers from short summaries (never the words said) and cannot send, change settings or approve anything. **What your assistant knows about your business**: the profile it learned (from your facts, workflow names and optional website and notes), for you to review, approve or forget. Needs your AI connected.
* **Orders**: every order tracking link, saved for good: search by order number, **Active** and **Completed**, **Copy link**, **Open**, **History**, **Export** to a spreadsheet. **Tracking page appearance** turns the links on or off and sets what customers see (your business name, phone, hours); see [orders-and-private-records.md](orders-and-private-records.md).

## Library
Your phrases, organized: how many are **saved** and how many are **to review**.
* **Saved**: every line your bundle can say (play any of them), your own lines first. A row of filters is always shown (All, Orders, Reservations, Hours & info, Payments, Greetings, Help & safety, Added by you); slide it sideways to see more. **Add your own phrases** (one per line, each voiced once, then free and instant) and **Suggest more with my AI**. **Missing phrases** opens the lines your workflows use that the bundle lacks, so Speakvora can write them.
* **To review**: drafts from your assistant and lines your AI keeps repeating. Tick what you want and press **Add to library**; **x** removes a draft. See [smart-ai.md](smart-ai.md).

* **Knowledge**: what your AI answers from. **Try it** (ask a question a customer would ask and see the answer and which source it came from), **Add knowledge** (upload a PDF, Word or text file, add your website, or paste text), **Questions it could not answer** (what customers asked that nothing covered, with an **Add answer** button) and every source, tap to read or remove it. See [knowledge.md](knowledge.md).

## Settings
* **Ask before sending**: customer texts, phone calls, emails. Switch on and the agent shows each one on Home to approve first.
* **AI controls**: **Activity log** and **View-only access** ([roles-and-activity-log.md](roles-and-activity-log.md)), **Test my agent** (see what it would do, nothing sent; [test-my-agent.md](test-my-agent.md)), **Workflows** (make your own "when this happens, do this", or switch the ready-made ones on and off; see [workflow-builder.md](workflow-builder.md)), **Go live**, **Test my voice**, **Answer texts** and **Answer calls** (shown as coming soon); **Built-in safeguards** (always on, plus your own limits and the monthly budget for new voiced lines).
* **Location** (only with several locations): tap 1, 2, 3... to switch between them.
* **Saved automations**, **Missing phrase requests**, **Locations & license** (commercial licence for several branches), **Speakvora agent** (pair with a code; billing, renewals, updates).
* **Your business details**, **Privacy & data** (transcripts of calls and texts, off by default, and how many days customer details stay), **Call handling controls** (the draft rules for your industry).
* **Pause all sending**: stops every send until you resume. Nothing is lost.

## Sharing missing phrases with Speakvora
When a workflow needs a spoken line your bundle does not have, the agent can tell Speakvora so the line gets written, checked, recorded and added to the next version of every bundle for that industry and language (included in the first 12 months of updates and support that come with the agent bundle; afterwards renewing is an optional $99 a year per location, and what you already have keeps working). It is **off until you switch it on**. What is sent: the moment the line is for, an example sentence, your industry, language and bundle name. Never customer names, numbers or messages.

## Safety
The page is served with a strict content policy and refuses requests from other websites and from anything that arrives through a tunnel or proxy. By default the agent listens on 127.0.0.1 only. See [security.md](security.md).
