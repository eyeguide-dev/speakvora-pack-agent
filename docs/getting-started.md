# Getting started, A to Z

Everything you need, in the order you need it. Everything runs on your own computer; the only things that reach Speakvora are the ones you switch on.

## 1. Run the agent
1. Install Python 3.9 or newer if you do not have it (free, python.org/downloads; on Windows tick **Add Python to PATH**).
2. Unzip your bundle and **double-click `Start Speakvora Agent.command`** (Mac) or **`Start Speakvora Agent.bat`** (Windows). It sets itself up the first time and **opens your dashboard in the browser**. Leave the window open while the agent runs; close it to stop. Start it again the same way any day.
   * Mac says it cannot open the file? Right-click it, choose **Open**, then **Open**.
   * Linux or Terminal: `sh sv-agent start` does the same.
3. Keep the dashboard address private (it ends in `#token=...` and is saved in `agent-state/dashboard-token`). The dashboard only works on this computer.
4. The agent starts in **practice mode**: it records what it would do and sends nothing, until you press **Go live** (top right).

## 2. The dashboard map
![Home: today at a glance, Finish setting up, activity and Insights](https://speakvora.com/assets/guide/home.png)
* **Home**: today at a glance, things that need you, **Finish setting up**, ask your assistant, latest activity, **Insights**.
* **Connect**: **Apps** (everything you can connect), **Assistant** (chat with your own AI), **Orders** (tracking links).
* **Library**: **Saved** phrases (play any), **To review** (drafts), **Knowledge** (documents your AI answers from).
* **Settings**: **Ask before sending**, **AI controls** (what your AI may do), your business details, privacy, call handling, pause.
Details: [dashboard.md](dashboard.md).

## 3. Connect what you use (Connect, Apps)
Full step-by-step with pictures: **[connect-apps.md](connect-apps.md)**.

Tap an app, fill the form, press **Save and test**. If something is wrong it says why in plain words. When it works it says **Connected** and moves to the Connected list. Each can be removed with **Remove**.
| App | What it is for | Guide |
|---|---|---|
| **Speakvora agent** | Pair with a code: voices new lines and live answers, makes order pages | below |
| **Your AI** (Claude, ChatGPT or Other) | Answers customers in real time, learns your business | [live-conversation.md](live-conversation.md) |
| **Texts and calls (Twilio)** | Your phone number for texts and calls | [setup-services.md](setup-services.md) |
| **Slack, Microsoft Teams** | Tell your team, slash commands | [setup-services.md](setup-services.md) |
| **Email, Calendar** | Send email, read bookings | [setup-services.md](setup-services.md) |
| **GitHub, GitLab, PagerDuty, Stripe, Shopify, Calendly, point of sale** | Start workflows when something happens there | [tool-connections.md](tool-connections.md) |
| **My apps** | Send to your own app, or let it send events here | [connect-anything.md](connect-anything.md) |

### Connect your Speakvora agent (no key to copy)
1. On **speakvora.com/account** press **Connect my agent**. A code like `SV-ABCD-EFGH` appears (it works once and lasts 15 minutes).
2. Open your **local dashboard** (the address the agent printed, starting `http://127.0.0.1:8787/dashboard`), go to the **Connect** tab, tap **Speakvora agent**, type the code and press **Pair**.
The agent gets its own key (named "Agent (paired)" in your account's key list; revoke it there any time). Prefer a key? Open "Or paste a key" in the same form.

### Your AI
Pick **Claude**, **ChatGPT** or **Other**, paste the key, pick a model (the fastest is marked for live use) and press **Save and test**. Claude keys must belong to a workspace (create the key inside your Default workspace). **Remove my key** deletes it from this computer.

## 4. Make sure speech generation is on, and save money
Settings, **AI controls**, **Test my voice** confirms new lines are being voiced. How to cache phrases so repeats are free: **[saving-money.md](saving-money.md)**.

## 5. Teach it your business
* **Settings, Your business details**: name, phone, hours, address.
* **Library, Knowledge**: upload a menu, price list or policy (PDF, Word, text), add your website, paste notes, or add an exact answer to a question. Use **Try it** to ask a question and see the answer and its sources. See [knowledge.md](knowledge.md).
* **Connect, Assistant**: **What your assistant knows about your business** (the profile it learned: review, approve or forget).
* **Library**: add your own phrases (each is voiced once, then plays free) and review drafts. See [smart-ai.md](smart-ai.md).

## 6. Make your own workflows
Settings, AI controls, **Workflows**, **New workflow**: pick when (a customer texts a word, something happens in your app, a booking is coming up, a time of day) and what to do (reply, text the customer, tell your team, email). Preview it, save it, done. See [workflow-builder.md](workflow-builder.md).

## 7. Let your AI answer texts and calls
Settings, **AI controls**: switch on **Answer texts** and/or **Answer calls**. Allow actions (tell the team, text a confirmation, add a booking) under **Built-in safeguards**. Start in practice mode. Everything it will and will not do is in [live-conversation.md](live-conversation.md) and [safety.md](safety.md).

## 8. Go public (so Twilio and the tools can reach you)
Twilio and the tools you connect send messages to an address on the internet. You need a public address for this computer:
* **Quick test**: `cloudflared tunnel --url http://127.0.0.1:8787` prints an `https://....trycloudflare.com` address (it changes every time).
* **Permanent**: a server or your own domain. Put the address under Settings, Your business details, Public address, and press **Check my public address**.
Then in Twilio set your number's **Voice** webhook to `<address>/twilio/call` and **Messaging** webhook to `<address>/twilio/sms` (POST). The dashboard's Twilio form shows both.

## 9. Test it end to end
1. **Texts**: text your number "do you have outdoor seating". The first reply says it is the automated assistant. Check Home, Latest activity.
2. **Calls**: call your number, ask something that is not on the menu. A short "let me check that" line plays, then the answer. Say "I want to speak to a person": it connects your staff phone (Twilio form, staff phone).
3. **Tools**: open a tool (for example GitHub) and press **Save and test**; then send a test event from that tool.
4. **Insights** (Home) shows counts, speed and the questions it could not answer; add answers in Library, Knowledge.
5. When happy, press **Go live**.

## 10. Orders and tracking links
Connect, Orders: every customer tracking link, searchable, with Copy link, History and Export. Set the page's look under **Tracking page appearance**. See [orders-and-private-records.md](orders-and-private-records.md).

## 11. Several locations
One licence per location, one shared dashboard with a location switcher. See [multi-location.md](multi-location.md).

## 12. Safety, privacy and limits
Practice mode first; consent, STOP, quiet hours and limits on every send; emergencies, secrets and "a person please" never reach the AI; customer details removed after the days you choose; the pause button stops everything. See [safety.md](safety.md), [security.md](security.md), [limits-and-control.md](limits-and-control.md), [jobs-and-recovery.md](jobs-and-recovery.md).

## 13. When something does not work
| Symptom | What to check |
|---|---|
| A form says "not accepted" | The key or token is wrong or expired: copy it again, press Save and test |
| Claude says the key is not tied to a workspace | Create the key inside your Default workspace (or paste the workspace ID under Advanced) |
| Texts arrive but nothing replies | Practice mode is on (press Go live), or Answer texts is off, or your AI is not connected |
| A call says "application error" | The public address is wrong or the tunnel stopped: Settings, Your business details, Check my public address |
| The AI always hands to a person | It has nothing about that question: Library, Knowledge, Questions it could not answer, Add answer |
| New lines are not voiced | Connect your Speakvora agent (Connect tab, Speakvora agent) |
| A tool says Waiting for first message | Send a test event from that tool; check its webhook shows a green delivery |
More in each guide linked above. Questions: support@eyeguide.ai.
