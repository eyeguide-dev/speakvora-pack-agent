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

## Slash commands (optional)
1. In the Slack app open **Basic Information** and copy the **Signing Secret** into the agent's Slack section.
2. Open **Slash Commands**, create `/agent`, and set its address to your agent's public address plus `/slack/command`.

## If something is wrong
- Message does not appear: invite the bot to the channel (bot token) or check the webhook was created for that channel.
- Test says token not accepted: copy the xoxb- token again after reinstalling the app.
