# Answer customers on Telegram

Customers message your Telegram bot and the agent answers. Free, and live in about 5 minutes.

## Before you start
- A Telegram account on your phone or computer. That is all. No public address is needed: the agent checks for new messages itself, while it is running.

## Step 1. Make the bot
1. In Telegram search for **@BotFather** (the official one has a blue tick) and open it.
2. Send `/newbot`.
3. Type a display name, for example "Bella Support".
4. Type a username that ends in `bot`, for example `bella_support_bot`.
5. BotFather replies with a **token**: a long line like `123456789:AA...`. Copy it. Treat it like a password; anyone with it can control the bot.

## Step 2. Connect it
1. In the agent open **Connect, Telegram**.
2. Paste the token and press **Save and test**.
3. It shows your bot's name when it works.

## Step 3. Try it
1. Open your bot's link (t.me/your_bot_username) in Telegram and press **Start**.
2. Send "what are your hours". The agent answers in the chat.
3. Share that link on your website, business card or in your email signature.

## Make the bot look professional (optional, in BotFather)
- `/setdescription` shows text before someone presses Start.
- `/setuserpic` adds your logo.
- `/setcommands` adds a menu, for example `hours - Opening hours`.

## Good to know
- Customers must message the bot first; a bot cannot start a chat with someone.
- Telegram does not give bots voice calls. Voice messages are not answered yet; text only.
- If you later give the agent a public address, it switches to instant delivery by itself.
- To stop everything: send `/revoke` to BotFather to cancel the token.
