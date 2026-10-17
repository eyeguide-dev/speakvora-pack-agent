# The dashboard

A small page that runs inside your agent, on your own machine. Start the agent and open the address it prints (`.../dashboard#token=...`). The part after `#` is your access token: it never goes to a server and never appears in a log. It is kept in `agent-state/dashboard-token`, or set your own with `SV_DASHBOARD_TOKEN`.

Four places (a bar at the bottom on a phone, at the top on a computer):

## Home: what needs you
A plain card for everything that needs a decision, with big buttons:
* **Approve / Decline** for an action the agent is holding (see Settings > Ask me first) and for each suggestion from your AI. Switch on **Remember my choice** and the same kind of action is done automatically next time (or never, if you declined). Saved choices are listed in Settings and can be reset.
* **It arrived / It did not: send again** when the agent could not tell whether something arrived.
* **Try again / Dismiss** for something that failed, with the reason in plain words.
Below that: what is waiting for the internet, and **What the agent has done**, a simple feed in sentences ("Text message to Ann Lee: Delivered") with filters for Problems, Texts, Calls, Slack and Teams, Email and My apps. Tap an item for the details.

## Connect: your connections
Everything you have connected, and a **+ Add** button to add more at any time: Slack (with a ready-made app manifest), Microsoft Teams, texts and calls (Twilio), Google or Outlook calendar, email, AI reasoning with your own key, tools that start workflows (Shopify, GitHub, GitLab, PagerDuty, Stripe, Calendly, point of sale), and **your own apps**:
* **Send to my own app**: a web address plus no key, an API key in a header, a bearer token or basic auth. A Test button posts a small message. Each workflow can also tell your app what it did (tick the app under the workflow).
* **Let my app send events here**: a private address and token. Your app, Zapier, Make, n8n or a form can post a JSON event ("event": "order.ready", ...) to start workflows. The card shows a ready-to-copy example.
Below the connections: switch each workflow on or off, and a **Go live** checklist. Setup details: [connect-dashboard.md](connect-dashboard.md).

## Library
How complete your bundle is. Missing lines can be sent to Speakvora by the agent itself (see below), and you can ask for any line you want. A banner tells you when a newer version of your bundle exists.

## Settings
* **Ask me first**: switch on texts, calls or emails to see each one on Home before it goes out.
* **My saved choices**: what you told it to do automatically or never, with "Ask me again".
* **Pause everything** (the kill switch).
* **Let the agent ask Speakvora for missing lines**.

## Sharing missing phrases with Speakvora
When a workflow needs a spoken line your bundle does not have, the agent can tell Speakvora so the line gets written, checked, recorded and added to the next version of every bundle for that industry and language (included in your 12-month licence). It is **off until you switch it on**. What is sent: the moment the line is for, an example sentence, your industry, language and bundle name. Never customer data, messages or keys. A line you type yourself is always sent. No delivery date is promised.

## Safety
The page is served with a strict content policy and refuses requests from other websites. By default the agent listens on 127.0.0.1 only. Anything exposed to the internet needs your own HTTPS and access control: the token is the only lock.
