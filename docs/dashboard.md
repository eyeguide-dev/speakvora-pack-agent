# The dashboard

A small page that runs inside your agent, on your own machine. Start the agent and open the address it prints (`.../dashboard#token=...`). The part after `#` is your access token: it never goes to a server and never appears in a log. It is kept in `agent-state/dashboard-token`, or set your own with `SV_DASHBOARD_TOKEN`.

Five places (a bar at the bottom on a phone, at the top on a computer), plus an orange **Locations** button when you have a commercial licence ([multi-location.md](multi-location.md)).

## Home: what needs you
A plain card for everything that needs a decision, with big buttons:
* **Approve / Decline** for an action the agent is holding (see Settings, Ask me first) and for each suggestion from your AI. Switch on **Remember my choice** and the same kind of action is done automatically next time (or never, if you declined). Saved choices are listed in Settings and can be reset.
* **It arrived / It did not: send again** when the agent could not tell whether something arrived.
* **Try again / Dismiss** for something that failed, with the reason in plain words.
Below that: what is waiting for the internet, and **What the agent has done**, a simple feed in sentences ("Text message to Ann Lee: Delivered") with filters for Problems, Texts, Calls, Slack and Teams, Email and My apps. Tap an item for the details.

## Orders: every tracking link, saved
Shown when your bundle sends order, visit, repair or request tracking links ([orders-and-private-records.md](orders-and-private-records.md)). Every link is saved from the first one and never expires. Search by order number, copy or open a link, see the step history, export everything to a spreadsheet.

## Connect: your connections
Everything you have connected, and a **+ Add** button: Slack (with a ready-made app manifest), Microsoft Teams, texts and calls (Twilio), Google or Outlook calendar, email, AI reasoning with your own key, tools that start workflows (Shopify, GitHub, GitLab, PagerDuty, Stripe, Calendly, point of sale), and **your own apps** (send to them, let them send events here, or connect your records system for verified private lookups). At the top: **Order tracking pages (optional)** and your **Speakvora account** pairing. Below the connections: switch each workflow on or off, and a **Go live** checklist. Setup details: [connect-dashboard.md](connect-dashboard.md).

## Library
* **Add your own phrases**: one phrase per line, each voiced once in your bundle's voice and added to your library (instant, free and offline afterwards). **Suggest more with my AI** proposes similar lines for you to add. **Lines your AI keeps saying** become one-click additions. See [smart-ai.md](smart-ai.md).
* **What your AI knows about your business**: the profile your connected AI learned, for you to review, edit, approve or forget.
* How complete your bundle is, missing lines (the agent can ask Speakvora for them, with your permission), and a banner when a newer version of your bundle exists.

## Settings
* **Ask me first**, **My saved choices**, **Pause everything** (the kill switch), and **Let the agent ask Speakvora for missing lines**.
* **Limits for your AI in live conversations**: the rules that are always on, your own limits inside fixed ceilings, the monthly budget for new voiced lines, how long customer names and numbers stay on this computer. See [smart-ai.md](smart-ai.md) and [industry-rules.md](industry-rules.md).
* **Call handling controls**: the draft rules for your industry, the policy settings to complete, and which controls the agent already enforces. Private records stay off until you approve them. See [orders-and-private-records.md](orders-and-private-records.md).
* **Your commercial licence** and **Open my account** (renew, add a location, new versions).

## Sharing missing phrases with Speakvora
When a workflow needs a spoken line your bundle does not have, the agent can tell Speakvora so the line gets written, checked, recorded and added to the next version of every bundle for that industry and language (included in your 12-month licence). It is **off until you switch it on**. What is sent: the moment the line is for, an example sentence, your industry, language and bundle name. Never customer names, numbers or messages.

## Safety
The page is served with a strict content policy and refuses requests from other websites and from anything that arrives through a tunnel or proxy. By default the agent listens on 127.0.0.1 only. See [security.md](security.md).
