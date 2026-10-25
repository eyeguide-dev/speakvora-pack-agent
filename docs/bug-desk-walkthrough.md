# Walkthrough: a bug that reports itself and is closed from Slack

Follow this page from top to bottom and you will have: your website reporting its own errors, a Jira ticket and a dated Confluence row opened for each one, your team alerted in Slack and Teams, and your team moving the ticket along just by replying in the Slack thread. Allow about 20 minutes.

*All screenshots are from a practice setup. Names, addresses, accounts and keys are blurred or replaced with examples (`YOUR-ADDRESS`, `YOUR-TOKEN`). Yours will show your own values. Never post your token anywhere.*

You need: your Speakvora agent running with Jira and Confluence connected (Connect tab), Slack connected with a bot token and signing secret, and (optional) Microsoft Teams. For the AI part, connect your own AI on the Connect tab (Assistant).

---

## Part 1. Let your website report its errors

**1. Create the address.** In your dashboard open **Connect**. In the **Add an app** list find **Send events here** and press **Connect**.

![Connect, Send events here](img/bug-desk/dash-connect-send-events.png)

**2. Name it and list your website.** Type a name, and (only if visitors' browsers will send the error straight from the page) your website address. Press **Create address**. The agent shows a private address and a token. Copy them into your website's error handler. Treat the token like a password.

![The form](img/bug-desk/dash-connect-form.png)

**3. Send the error from your site.** When the payment step fails, post one small message. The page at `web/demo/bell-and-basil/order.html` in the Speakvora repository does exactly this; the core of it is:

```js
fetch("YOUR-ADDRESS", {
  method: "POST",
  headers: { "content-type": "application/json", "authorization": "Bearer YOUR-TOKEN" },
  body: JSON.stringify({
    event: "app.error", id: "pay-403",
    customer: { name: "Alex" },
    error: { code: 403, message: "Forbidden: the payment session could not be created",
             page: "Order page", action: "Pay and place order" }
  })
});
```

The customer sees your normal error message. The agent hears about it in the same moment.

![The order page after the error](img/bug-desk/site-order-error.png)

**4. Check the workflow is on.** In **Your agent**, the ready-made workflow **Report a website or app error to Jira and your team** does the rest. Open it to read, or change, the words it sends.

![The workflow in the list](img/bug-desk/dash-workflow-app-error.png)
![Inside the workflow](img/bug-desk/dash-workflow-app-error-open.png)

---

## Part 2. What you get the moment it happens

**Slack and Teams** are told who hit the error, on which page, and what they clicked, with the ticket number. If the same error happens again the agent adds to the same ticket and counts the reports instead of opening a new one.

![Slack alert](img/bug-desk/slack-alert.png)
![Teams alert](img/bug-desk/teams-open.png)

**Jira** gets a ticket with the details (private details removed) and **Confluence** gets a row on your known-issues page with today's date.

![The Jira ticket](img/bug-desk/jira-open.png)
![The Confluence row](img/bug-desk/conf-open.png)

---

## Part 3. Let the agent hear your team in Slack (once, about 5 minutes)

This is what lets the team finish the job by replying in the thread. You do it once in your Slack app (api.slack.com/apps, your app).

**1. Turn on Event Subscriptions.** Open **Event Subscriptions** and switch **Enable Events** on.

![Enable events](img/bug-desk/slack-events-on.png)

**2. Paste the request address.** It is your agent's public address followed by `/slack/events`, for example `https://YOUR-ADDRESS/slack/events`. Slack checks it and shows **Verified**. If it does not verify, the agent is not reachable from the internet, or the signing secret in Slack and in your agent do not match.

![Verified](img/bug-desk/slack-events-verified.png)

**3. Subscribe to the messages.** Under **Subscribe to bot events** add `message.channels` (and `message.groups` for private channels). Slack adds the matching permissions `channels:history` and `groups:history`. Press **Save Changes**.

![Events saved](img/bug-desk/slack-events-saved.png)

**4. Reinstall the app.** Slack asks you to reinstall because the permissions changed. Choose a channel and press **Allow**. Your existing token keeps working.

![Reinstall](img/bug-desk/slack-reinstall.png)

**5. Invite the bot to the channel** where the alerts go. In that channel type `/invite @your-agent-name` and send it. The bot only hears channels it has been added to.

![Invite](img/bug-desk/slack-invite-typed.png)
![Invited](img/bug-desk/slack-invite-done.png)

---

## Part 4. Your team talks, the agent does the paperwork

Everything below happens in the alert's thread.

**A teammate says they are on it.** The agent reads the message with your own AI and moves the Jira ticket to **In Progress**. The thread tells everyone, and the known-issues page follows. Every reply is also added to the ticket as a note, with private details removed.

![Moved to In Progress](img/bug-desk/slack-moved.png)
![Jira in progress](img/bug-desk/jira-inprogress.png)

**The team says it is fixed.** The agent does not close anything on its own. It asks first.

![The agent asks](img/bug-desk/slack-asked.png)

**Someone replies `approve`.** The ticket moves to **Done** with the team's note, the Confluence row says Fixed with the date, Teams is told, and the thread confirms.

![Approved and closed](img/bug-desk/slack-closed.png)
![Jira done](img/bug-desk/jira-done.png)
![The notes on the ticket](img/bug-desk/jira-comments.png)
![Confluence says fixed](img/bug-desk/conf-fixed.png)
![Teams is told](img/bug-desk/teams-fixed.png)

Reply `keep open` (or `not yet`) instead, and nothing changes.

---

## What the AI may and may not do
* It only chooses from the moves Jira says that ticket can make right now (for example In Progress, Blocked, Done, Won't Do, To Do). It cannot invent a status.
* Moves like In Progress or Blocked are applied at once and announced in the thread. **Closing, closing as "won't fix" and reopening always wait for an `approve`.** To close without asking, set `guardrails.bug_close` to `auto`; to keep notes only, set it to `off`. `guardrails.bug_ai: false` switches the AI off and plain-word rules take over.
* Private details (card numbers, passwords, emails, phone numbers, keys) are removed before the AI reads a message and before anything is written to Jira.
* In Practice mode nothing is written to Jira, Confluence or Slack.
* Microsoft Teams can only receive alerts, so replies there are not read. Reply in Slack (or move the ticket in Jira; the agent notices that too).

More detail: `bug-desk.md`.
