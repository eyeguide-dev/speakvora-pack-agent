# Set everything up from the dashboard (no developer needed)

Run the agent and open the address it prints (`.../dashboard#token=...`). The **Connect** tab is the first thing you see when nothing is connected yet; later, press **+ Add** to connect more at any time (including your own apps, by web address or webhook; see [dashboard.md](dashboard.md)). It walks you through every service, one card at a time, in plain words:

| Card | What it connects | What you need |
|---|---|---|
| **Your business** | The name, website, customer service phone and other service numbers, hours, address and review link the agent uses in messages and on order pages; your time zone; how careful it is; an optional public address (only for phone calls that play recordings and for self-hosting order pages) | Nothing to sign up for |
| **Connect texts and calls (Twilio)** | Sends texts and places calls that play your recordings | A Twilio account and number (Twilio bills you) |
| **Connect Slack** | Tells your team in Slack; slash commands for staff | A Slack workspace. The card includes a ready-made app manifest to paste into Slack, so you do not configure the app by hand |
| **Connect Microsoft Teams** | Posts to a Teams channel | A Teams workflow URL |
| **Connect Google or Outlook calendar** | Reads your bookings for reminders | Your calendar's private link (no developer work) |
| **Connect email** | Sends email from your own mailbox | Mail server details (Gmail needs an app password) |
| **Your Speakvora account** | Pairs this agent with your Speakvora account so it can host your order pages, voice new phrases and ask for missing lines | A one-time code from your account (Bundles, Order pages), or an API key |
| **Connect AI reasoning (your own key)** | Lets the agent think about requests the rules cannot handle; it only proposes and you approve | An API key from your AI provider, or a local model |

For every card: fill in the boxes, press **Save**, then press a **Test** button. The test says in plain words what works or what to fix ("That was not accepted: check the key", "That number is not on that Twilio account", "The mail server refused the username or password"). Tests that send something (a text, a Slack message, an email) say so on their button and only run when you press it.

Below the cards:
* **Switch on the things the agent does**: every ready-made workflow with a plain description and what it needs. Switch off the ones you do not want; a workflow whose service is not connected is skipped and logged.
* **Connect a tool that sends you events**: Shopify, GitHub, GitLab, PagerDuty, Stripe, Calendly or a point-of-sale system, added with one button.
* **Go live**: a checklist (business name, a service connected, every connected service tested, a workflow switched on). **Switch on sending** stays greyed out until it is all done. Until then the agent is in practice mode: it records what it would do and sends nothing. You can go back to practice mode any time, and the choice is remembered after a restart.

## Order tracking pages (optional)
At the top of Connect: a switch, **Order tracking pages**. Off (the default), customers are simply texted at each step. On, each customer gets one text with a private link that follows their order, and Speakvora hosts the pages, so there is no domain or tunnel to set up.
1. In your Speakvora account (speakvora.com, Bundles, Order pages) save your business details and press **Create pairing code**. The code looks like `SV-ABCD-EFGH`, works once and lasts 15 minutes.
2. In this dashboard switch the order pages on and type the code. Your business details fill in from your account and your pages are created. (No account page handy? Fill the details in here and paste an API key instead.)
3. **Go live** now includes a line for order pages until this is done. Details: [orders-and-private-records.md](orders-and-private-records.md).

## Where your keys go
Keys you type are saved on your own machine in `agent-state/secrets.json` (readable only by you). `agent.json` only says where to find them, so you can share or back up `agent.json` safely. A real environment variable of the same name wins over the saved key. The page never shows a saved key again: only that it is set and its last four characters. Every Save keeps the previous `agent.json` as `agent.json.bak`.

## Seeing failures
Open **Activity**. Anything that failed, was refused or needs a decision is under **Needs you** with the reason, and the buttons to try again, cancel or mark it arrived. A service that stops working (a changed token, an expired password) shows up there as failed sends, and the Connect tab's Test button tells you why.

## Honest limits
* Phone calls that play your recordings and replies to inbound texts need a web address that reaches this machine (the "public address" field). Texts, Slack, Teams, email, reminders and hosted order pages do not.
* Google Calendar and Outlook are connected through their private ICS link, which is read-only. Creating calendar entries needs the developer setup in `docs/setup-services.md`.
* The dashboard runs on your machine and is protected by the token in its address. Do not expose it to the internet without your own HTTPS and access control.
