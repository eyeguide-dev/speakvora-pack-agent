# Tell your team in Slack

The agent posts to a Slack channel when something needs a person (a refund request, a bug, a hand-off). Two ways: a simple webhook (text only, 5 minutes) or a bot token (channels you choose, files, slash commands).

## Easiest: an incoming webhook
1. Go to api.slack.com/apps and press **Create New App**, then **From scratch**. Name it (for example "Speakvora agent") and pick your workspace.
2. Open **Incoming Webhooks** in the left menu and switch it on.
3. Press **Add New Webhook to Workspace**, choose the channel, and press Allow.
4. Copy the **Webhook URL** (it starts with https://hooks.slack.com/).
5. In the agent open **Connect, Slack**, paste it under Incoming webhook URL, and press **Save and test**. Use **Send a test message**: it should appear in the channel.

## More control: a bot token
1. In the same Slack app open **OAuth & Permissions**. Under Bot Token Scopes add `chat:write`, `files:write` and `channels:read` (and `groups:read` for private channels).
2. Press **Install to Workspace** and copy the **Bot User OAuth Token** (starts with xoxb-).
3. In Slack, open the channel and type `/invite @Speakvora agent` so the bot can post there.
4. In the agent open **Connect, Slack, Advanced**, paste the token, type the channel (for example #front-desk), and press Save and test.
5. Different channels per event (for example #bugs, #billing): in a workflow's "Tell my team" step type the channel name in its box.

## Make channels for each kind of message (recommended)
A separate channel for each kind of news keeps your team from missing things. We use #reservations, #orders, #urgent, #reviews and #payments in the example.

1. In Slack, scroll to the end of your channel list and press **Add channels**, then **Create a new channel**.

![Slack's Add channels menu](slack-0-add-channels-menu.jpg)

2. Type the name (for example `reservations`), press **Next**, keep it Public, and press **Create**.

![Naming a new channel](slack-1-create-channel.jpg)

3. Slack asks who to add. Type the name of your agent's Slack app (for example `speakvora-agent`), choose it, and press **Add**. The app must be in the channel or it cannot post there.

![Adding the agent's app to the channel](slack-2-add-bot.jpg)

4. The channel now shows that the app joined. Repeat for each channel.

![The app has joined the channel](slack-3-bot-joined.jpg)

5. Tell the agent which team goes where. In the agent folder's `agent.json`, under `slack`, add for example `"channels": {"#host": "#reservations", "#kitchen": "#orders", "#manager": "#urgent", "#billing": "#payments"}` and restart the agent. Workflows that tell "#host" now post in #reservations. (Channels need the bot token, not only a webhook.)
6. Send a test event from the dashboard (Automations, Test). The message appears in the right channel.

![A reservation message arrives in #reservations](slack-4-message-arrives.jpg)

## What the agent's Slack screen looks like
![Connect, Slack in the agent](slack-5-agent-card.jpg)

Open **Advanced** for the bot token, channel and signing secret.

![Slack advanced settings in the agent](slack-6-agent-advanced.jpg)

## Slash commands (optional)
1. In the Slack app open **Basic Information** and copy the **Signing Secret** into the agent's Slack section.
2. Open **Slash Commands**, create `/agent`, and set its address to your agent's public address plus `/slack/command`.

## If something is wrong
- Message does not appear: invite the bot to the channel (bot token) or check the webhook was created for that channel.
- Test says token not accepted: copy the xoxb- token again after reinstalling the app.
