# Use your own phone, Telegram or WhatsApp

You do not need Twilio to text customers. Pick what you already have. Every channel answers inbound messages with the same rules, STOP handling and practice mode as a Twilio text.

## Your Android phone (instant, your own number)
1. On the phone install **SMS Gateway for Android** (open source, free) and switch the **Cloud server** on. Note the username and password on its Home tab.
2. In the app open Settings, Webhooks and copy the **signing key**.
3. In the dashboard open Connect, **Your Android phone**, paste the three values, press Save and test. The agent registers its address with the phone app for you (it needs a public https address, see Settings, Your business details).
4. Text the phone from another number to try it.

More than one phone (front desk, billing, returns): fill in "Your phones / lines" as `Front desk=DEVICE-ID, Billing=DEVICE-ID`. A reply goes out from the phone the customer texted. In a workflow's text step you can name the line.

Limits: Android only. Texts go through your own SIM and plan, so keep volume to what a person could send; carriers filter bulk texting from a personal SIM. The phone must be on, have signal and run the app. The agent cannot take or place cellular voice calls through the phone; calls still use Twilio or another call provider.

To keep messages on your own network, put the phone's address (for example https://192.168.1.20:8080) under Phone address.

## Telegram
Message **@BotFather** in Telegram, send /newbot and paste the token under Connect, **Telegram**. Customers must message the bot first. Telegram does not allow voice calls for bots.

## WhatsApp Business (Meta Cloud API)
Create a Meta developer app with the WhatsApp product. Paste the access token, phone number ID and app secret under Connect, **WhatsApp Business**, then copy the callback address and verify token the dashboard shows into WhatsApp, Configuration, Webhook, and subscribe to "messages". Replies are free within 24 hours of the customer's message; starting a conversation outside that window needs an approved template, which is not built yet.

## Your office phone system (calls, no Twilio)
Works with any phone system that gives you SIP extensions: 3CX, FreePBX/Asterisk, RingCentral, 8x8, Zoom Phone, Ooma, Vonage, Telnyx, and an analog line through a small SIP adapter (about $30). Plan for up to an hour.

1. In the phone system's admin page create a new plain SIP (desk phone) extension for the agent. Write down the server address, the extension number and its SIP password. RingCentral and Zoom Phone also show a separate authorization name: put it in "Authorization name".
2. In the dashboard open Connect, **Your office phone system**, fill in the boxes and press **Save and test**. It should say it signed in. If it says the password was refused, re-copy the SIP password (not the admin password).
3. In the phone system send the calls you want answered to that extension. Good choices: an after-hours rule, an overflow or no-answer rule, a ring group, or a queue. Start with after-hours so staff are never in the way.
4. Call your number. You hear your recorded menu. Press 1 for hours and so on; press 0 and the agent transfers the call to your staff phone (Settings, Your business details, your own phone) using a SIP transfer, so make sure your phone system allows transfers from that extension.
5. If callers hear nothing, the audio is blocked: open UDP ports 40000 to 40200 to the computer running the agent, or if the phone system is in the cloud and this computer is behind a router, set "This computer's public IP". Cloud phone systems can also need the agent to run on a computer with a public address.

What works: answering calls, your recorded menu and answers, keypad choices, transfer to staff, hang-up handling, up to 20 calls at once, a fallback number if something fails. What does not (yet): placing calls from the agent, speech recognition (callers use the keypad), TLS-only providers. The computer must stay on while it answers calls; during outages your phone system's normal ring rules should send calls to a person.

Needs ffmpeg installed to convert your recordings for the phone line. Say a line with no recording and the agent uses the computer's own voice if it has one (macOS and espeak-ng do), otherwise skips it.
