# Connecting GitHub, GitLab, PagerDuty, Stripe, Shopify, Calendly and your point of sale

These tools **send messages to your agent** when something happens (a build fails, an order is fulfilled, a payment fails). In the dashboard open Connect, Apps, tap the tool and follow the guide. Each guide shows:

* **Your address**: where the tool sends its messages (needs your agent's public address, see Settings, Business details).
* **A secret**: how the agent knows a message is really from the tool. Either the agent makes it and you paste it into the tool (GitHub, GitLab, Calendly, point of sale), or the tool shows you one and you paste it here (PagerDuty, Stripe, Shopify).
* **The exact clicks** in that tool, and **what it understands** (the events your workflows can start from).
* **Save and test**: saves, then checks the address, the secret and that a sample message from the tool is understood and which of your workflows it would start. A problem is explained in plain words. When it passes the tool moves to **Connected**, and shows "Waiting for the first message" until the tool's first real message arrives, then the time of the last one.
* **Remove**: disconnects the tool and deletes its secret from this computer.

| Tool | Secret | Where in the tool |
|---|---|---|
| GitHub | the agent makes it | repository, Settings, Webhooks |
| GitLab | the agent makes it | project, Settings, Webhooks |
| PagerDuty | PagerDuty shows it | Integrations, Generic Webhooks (v3) |
| Stripe | Stripe shows it (whsec_) | Developers, Webhooks |
| Shopify | Shopify shows it | Settings, Notifications, Webhooks |
| Calendly | the agent makes it | created through Calendly's API (a ready command is shown) |
| Point of sale | the agent makes it | your POS vendor's webhook settings, or Zapier or Make |

Apps you connect with a key (Slack, Teams, Twilio, email, calendar, your AI) use one form: paste, **Save and test**, and the result says Connected or why not.
