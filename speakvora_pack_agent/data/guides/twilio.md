# Texts and calls with Twilio

Twilio sells phone numbers and carries your texts and calls. You pay Twilio directly; Speakvora adds no per-message fee. Time: 20 minutes for calls, a few days for business texting to be approved. If you want to text sooner, connect your Android phone, Telegram or WhatsApp as well (see their guides).

## Step 1. Create the account and buy a number
1. Go to twilio.com and sign up. A trial account works for testing but can only reach phone numbers you verify, and adds a "trial" message to calls.
2. To remove the trial limits, upgrade the account and add a small balance (for example $20).
3. In the Console open **Phone Numbers, Manage, Buy a number**. Choose your country, tick Voice and SMS, and buy a local number. About $1.15 a month in the US.

## Step 2. Find your account details
1. On the Console home page find **Account SID** (starts with AC) and **Auth Token** (press the eye icon to show it).
2. Keep them private. Anyone with them can spend your Twilio balance.

## Step 3. Connect it to the agent
1. In the agent open **Connect, Texts and calls (Twilio)**.
2. Paste the Account SID and Auth Token and press **Save and test**.
3. Press **Find my numbers** and choose the number you bought.
4. Under **Last step** press the button that points that number at your agent. The agent sets the number's call and text addresses in Twilio for you, so you never edit them by hand. This needs your agent's public web address (Settings, Your business details).

## Step 4. If you are in the US: register for business texting
US carriers block business texts from unregistered numbers.
1. In the Twilio Console open **Messaging, Regulatory Compliance, A2P 10DLC** and register your business (a brand) and a campaign. Choose "Customer care" as the use case. Approval takes a few days.
2. Or use a toll-free number and complete its verification (also a few days).
3. Until approved, calls work but texts to US numbers may be blocked.

## Step 5. If this computer is off
Calls would otherwise go unanswered. In the agent, Connect, Texts and calls, open **If this computer is off** and follow the steps there so Twilio rings your staff phone instead.

## Try it
1. Call your Twilio number. You should hear your menu.
2. Text it "what are your hours" (after texting is approved).

## If something is wrong
- Test says the account was not accepted: re-copy the SID and token.
- A number is missing from the list: it must be on the same Twilio account (not a subaccount) as the SID you pasted.
- Customers do not get texts: check Twilio, Monitor, Logs, Messaging for the error code (often a missing registration).
