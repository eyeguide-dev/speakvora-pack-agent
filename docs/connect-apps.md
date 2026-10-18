# Connect every app, step by step

Everything below is done in your **local dashboard** (the address your agent printed, starting `http://127.0.0.1:8787/dashboard`), in the **Connect** tab, **Apps**. Tap an app, fill in the few boxes, press **Save and test**. If something is wrong it tells you why in plain words. When it works it says **Connected**, the window closes and the app moves to the **Connected** list. Every app has a **Remove** button that deletes its keys from your computer.

![The Connect tab, Apps: connected apps on top, the apps you can add below](https://speakvora.com/assets/guide/connect-apps.png)

Advanced users can set everything in `agent.json` instead: see [setup-services.md](setup-services.md).

---
## 1. Speakvora agent (do this first)
Pairs this agent with your Speakvora account so it can **voice new lines in your bundle's voice**, answer calls in real time and make order pages. No key to copy.
1. On **speakvora.com/account** press **Connect my agent**. A code like `SV-ABCD-EFGH` appears (it works once and lasts 15 minutes).
2. Open your local dashboard, **Connect** tab, tap **Speakvora agent**, type the code, press **Pair**. (On **Home** the card **Connect your Speakvora agent** opens the same form.)
![The Speakvora agent form: type the pairing code and press Pair](https://speakvora.com/assets/guide/sheet-agent.png)
The agent now has its own key, shown as "Agent (paired)" in your account's key list, where you can revoke it any time. Prefer a key? Open "Or paste a key instead".

## 2. Your AI (Claude, ChatGPT or Other)
Lets the agent answer customers in real time and learn your business. You pay your AI company directly; Speakvora charges nothing for it.
1. Pick **Claude**, **ChatGPT** or **Other**.
2. Paste your key: Claude at console.anthropic.com, API keys (create it inside your **Default workspace**); OpenAI at platform.openai.com, API keys.
3. Pick a model. The one marked fastest is best for live calls and texts (Claude Haiku, or GPT-4o mini).
4. Press **Save and test**.
![The Your AI form: provider tabs, key, model, Save and test](https://speakvora.com/assets/guide/sheet-ai.png)
**Remove my key** deletes the key from this computer.

## 3. Texts and calls (Twilio)
Your phone number. Twilio bills you directly.
1. In console.twilio.com copy your **Account SID** and **Auth token** (Account info).
2. Paste them and press **Find my numbers**, then tap your number.
3. Press **Save and test**. A passing test says it reached your Twilio account and found the number.
4. Last step: **Point my number at my agent** sets Twilio's call and text addresses for you. This needs your agent to have a public web address: see [getting-started.md](getting-started.md), step 6.
![The Twilio form: SID, token, Find my numbers](https://speakvora.com/assets/guide/sheet-twilio.png)
US texting also needs your number registered with carriers (A2P 10DLC or toll-free verification) in your Twilio account. STOP and START replies are handled for you.

## 4. Slack
(Alerts from your AI about bookings and complaints post to the Slack channel you chose; the restaurant workflows use the role `#front`, so a channel named front is a good choice.)
1. In Slack open api.slack.com/messaging/webhooks, create your app, turn on **Incoming Webhooks**, **Add New Webhook to Workspace**, pick a channel and copy the URL.
2. Paste it in **Incoming webhook URL** and press **Save and test**. A real test message appears in that channel.
3. Need slash commands, file uploads or a specific channel? Open **Advanced** and add the bot token, channel and signing secret.
![The Slack form: one webhook URL, Advanced underneath](https://speakvora.com/assets/guide/sheet-slack.png)

## 5. Microsoft Teams
In Teams open the channel, **Workflows**, "Post to a channel when a webhook request is received", copy the URL, paste it and press **Save and test** (a test message is posted).
![The Microsoft Teams form: one webhook URL](https://speakvora.com/assets/guide/sheet-teams.png)

## 6. Calendar
In Google Calendar settings for the calendar copy the **Secret address in iCal format** (Outlook: Settings, Shared calendars, Publish, copy the ICS link), paste it and press **Save and test**. It says how many events it can see in the next 7 days. Put `Phone: 646-555-0101` and `SMS OK: yes` in an event's notes so the agent may text that customer.
![The Calendar form: the private calendar link](https://speakvora.com/assets/guide/sheet-calendar.png)
Google refreshes secret links slowly (a new event can take hours): use the OAuth option in setup-services.md for reminders that must fire on time.

## 7. Email
Pick Gmail, Outlook, Yahoo, iCloud or Another provider, type your address and a password, press **Save and test**. Gmail, Yahoo and iCloud need an **app password** (not your normal password): the form says where to make one.
![The Email form: provider, address, password](https://speakvora.com/assets/guide/sheet-email.png)

## 8. Tools that send you events (GitHub, GitLab, PagerDuty, Stripe, Shopify, Calendly, point of sale)
Each opens a guide with the exact clicks in that tool, your address to paste, a secret to copy (or paste), what it understands and **Save and test**. See [tool-connections.md](tool-connections.md).
![The GitHub guide: address, secret, steps](https://speakvora.com/assets/guide/sheet-github.png)

## 9. Your own app
**My apps**: send events to your own system, or get a private address and token so your app, Zapier or Make can start your workflows. See [connect-anything.md](connect-anything.md).

---
## After connecting: check the whole picture
Press the status pill at the top (**Practice mode** / **Agent live**) to see the Go live checklist: at least one service connected and passing its test. Settings, **AI controls**, **Test my voice** confirms speech generation is on.
![The Go live checklist](https://speakvora.com/assets/guide/sheet-golive.png)
