# Connection tests: what was checked, and how you can check yours

Every app in **Connect, Apps** has the same flow: fill the few boxes, press **Save and test**. The result says **Connected** or says plainly why not, and a connected app moves to the **Connected** list with **Remove** to undo it.

## What was verified end to end (2026-10-18, live test agent)
| App | Result |
|---|---|
| Speakvora agent (pairing code) | Pairs, saves its own key, **Test my voice** voices a line (speech generation on) |
| Your AI (Claude Haiku) | Save and test answers; Remove my key deletes the key |
| Twilio | Find my numbers lists the account's numbers, Point my number sets the call and text addresses, Save and test reaches the account; real texts and calls answered by the AI, staff transfer dials the staff phone |
| Slack | One webhook URL; Save and test posts a real test message; the AI's "tell my team" alerts arrive in #front |
| Calendar | An iCal address; Save and test reads the next 7 days |
| GitHub, GitLab, PagerDuty, Stripe, Shopify, Calendly, point of sale | Each: Save and test says Connected, the tile moves to Connected, a correctly signed message is accepted and understood, a wrongly signed one is refused (401), and the tile then shows "Last message" |
| My apps | "Let my app send events here" gives an address and token; an event with the token is accepted, a wrong token is refused; "Send to my own app" saves, and a wrong address fails with a plain reason |
| Microsoft Teams, Email | A wrong webhook or password fails with a plain reason and Remove disconnects (tested with wrong values; a real webhook and mailbox are yours to add) |

## Checking your own setup
1. Connect, Apps: everything you use should be under **Connected**.
2. Press any app and **Save and test** again at any time; nothing is sent except where the button says (Slack and Teams post one test message).
3. Settings, **AI controls**, **Test my voice**: confirms new lines are being voiced.
4. Home, **Insights**: shows conversations, speed and what it could not answer.
5. For a tool (GitHub and the rest), send a test event from that tool: the tile then says **Last message** with the time.

## Plain-words errors you may see
| Message | What to do |
|---|---|
| That was not accepted: check the key or token | The key is wrong, expired or for the wrong account: copy it again |
| Could not reach that address. Check it for typos | A webhook or calendar address is wrong, or this computer is offline |
| The mail server hung up while signing in | The password is wrong or your provider needs an app password |
| Your agent has no public web address yet | Twilio and the tools can only reach an address on the internet: see getting-started.md, step 7 |
| This Claude key is not tied to a workspace | Create the key inside your Default workspace |
