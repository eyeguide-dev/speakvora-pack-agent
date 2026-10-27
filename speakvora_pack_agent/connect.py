"""The dashboard's Connect tab: set the agent up without editing JSON or setting environment variables, and see what is wrong in plain words.
Cards: Your business, Texts and calls (Twilio), Slack, Microsoft Teams, Google or Outlook calendar, Email, AI reasoning, then Go live. Each card saves to agent.json (a backup is kept) and secrets.json, applies at once (no restart),
and has a Test button that checks the connection and says what to fix. Secrets are never sent back to the page: only whether they are set and their last four characters.
Only the fields listed in CARDS can be written, so the page cannot change anything else in agent.json."""
import json, os, re, secrets as _rnd, smtplib, ssl, time
from urllib.parse import quote

from . import reasoner as R, secrets_store as SS, slots as SL, web
from .connectors.slack import Slack
from .connectors.teams import Teams
from .connectors import atlassian as ATL

TIMEZONES = ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Phoenix", "America/Anchorage", "Pacific/Honolulu", "America/Toronto", "America/Vancouver", "America/Mexico_City", "America/Sao_Paulo",
             "Europe/London", "Europe/Dublin", "Europe/Paris", "Europe/Berlin", "Europe/Madrid", "Europe/Rome", "Europe/Amsterdam", "Africa/Cairo", "Africa/Johannesburg", "Asia/Dubai", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo",
             "Asia/Seoul", "Asia/Shanghai", "Australia/Sydney", "Pacific/Auckland", "UTC"]
# field: (key, label, kind text|secret|select|number|url, agent.json path, env name for a secret, help)
CARDS = {
    "business": {"title": "Your business", "blurb": "What the agent says about you in texts and messages. Fill in what applies; leave the rest empty.", "fields": [
        ("business", "Business name", "text", "business", None, "Used in messages, for example \"Bella: your order is ready\"."),
        ("website", "Business website", "url", "facts.website", None, "Your own website address. Customers see it on their order page and it is saved with your business details."),
        ("phone", "Customer service phone", "text", "facts.phone", None, "The number customers should call with a question, with the country code, for example +15551234567. It becomes the Call button on every order page."),
        ("service_numbers", "Other customer service numbers (optional)", "text", "facts.service_numbers", None, "One or more, with a label, for example: Billing +15551230001, Returns +15551230002."),
        ("info", "Other things customers ask (optional)", "text", "facts.info", None, "For example: Visiting hours 2 to 8 PM. Parking is free in the east lot. Billing office +15551234567. Sent when someone texts parking, visiting, departments or billing."),
        ("hours", "Opening hours", "text", "facts.hours", None, "For example: Tue to Sun, 5 to 10 PM. Sent when someone texts \"hours\"."),
        ("address", "Address", "text", "facts.address", None, "Sent when someone texts \"where are you\"."),
        ("review_url", "Review link (optional)", "url", "facts.review_url", None, "Where happy customers are asked to leave a review."),
        ("oncall_phone", "Your own phone for urgent alerts (optional)", "text", "facts.oncall_phone", None, "Include the country code, for example +15551234567."),
        ("timezone", "Time zone", "select", "timezone", None, "Quiet hours and reminders use this."),
        ("mode", "How careful", "select", "mode", None, "Careful sends the fewest messages and keeps longer quiet hours. Normal is the default. Open removes the per-person and hourly limits (STOP replies and required notices stay on)."),
        ("public_base_url", "Public address of this agent", "url", "public_base_url", None, "Needed for order tracking links, for phone calls that play your recordings and for replies to inbound texts: a permanent web address that reaches this machine, such as your own domain or a named tunnel. Customers' links start with this address, so keep it the same."),
    ]},
    "twilio": {"title": "Texts and calls (Twilio)", "blurb": "Sends texts and places calls that play your recordings, from your own Twilio number. Twilio bills you directly.", "fields": [
        ("account_sid", "Account SID", "secret", "twilio.account_sid", "TWILIO_ACCOUNT_SID", "Twilio console > Account info. It starts with AC."),
        ("auth_token", "Auth token", "secret", "twilio.auth_token", "TWILIO_AUTH_TOKEN", "Twilio console > Account info > Auth token (click to show)."),
        ("from_number", "Your Twilio phone number", "text", "twilio.from_number", None, "With the country code, for example +15551234567."),
        ("fallback_url", "Backup for calls if this computer is off (optional)", "text", "twilio.fallback_url", None, "A web address Twilio asks when it cannot reach this computer, so calls still go to your team. See \"If this computer is off\" in the Twilio section."),
    ]},
    "slack": {"title": "Slack", "blurb": "Tells your team in Slack when something needs them. Paste one webhook URL and you are done.", "fields": [
        ("bot_token", "Bot token", "secret", "slack.bot_token", "SLACK_BOT_TOKEN", "Slack app > OAuth & Permissions > Bot User OAuth Token (starts with xoxb-). Or use a webhook below."),
        ("channel", "Channel", "text", "slack.channel", None, "For example #general. Invite the bot to the channel first."),
        ("webhook_url", "Webhook URL (instead of a bot token; text only)", "secret", "slack.webhook_url", "SLACK_WEBHOOK_URL", "Slack app > Incoming Webhooks."),
        ("signing_secret", "Signing secret (for slash commands)", "secret", "slack.signing_secret", "SLACK_SIGNING_SECRET", "Slack app > Basic Information > Signing Secret."),
    ]},
    "teams": {"title": "Microsoft Teams", "blurb": "Posts to a Teams channel. Text only. Add the outgoing webhook token to let your team answer bug alerts from Teams.", "fields": [
        ("webhook_url", "Workflow / webhook URL", "secret", "teams.webhook_url", "TEAMS_WEBHOOK_URL", "In Teams: channel > Workflows > \"Send webhook alerts to a channel\" (older name: \"Post to a channel when a webhook request is received\"), then copy its URL."),
        ("outgoing_secret", "Outgoing webhook security token (to answer from Teams)", "secret", "teams.outgoing_secret", "TEAMS_OUTGOING_SECRET", "Optional. Teams > channel > Manage team > Apps > Create an outgoing webhook: after you press Create, Teams shows a security token once. Paste it here so people can reply to bug alerts from Teams."),
    ]},
    "atlassian": {"title": "Jira and Confluence", "blurb": "Reports bugs to your own Jira and keeps a known-issues page in your own Confluence. Needs your own Atlassian account and API token.", "fields": [
        ("site", "Your Atlassian site", "text", "atlassian.site", None, "The address you use for Jira, for example yourcompany.atlassian.net."),
        ("email", "Your Atlassian email", "text", "atlassian.email", None, "The email you sign in to Atlassian with."),
        ("api_token", "API token", "secret", "atlassian.api_token", "ATLASSIAN_API_TOKEN", "id.atlassian.com, Security, Create and manage API tokens, Create API token. Copy it once."),
        ("project", "Jira project key", "text", "atlassian.project", None, "The short capital letters in your tickets, for example BUG in BUG-12."),
        ("issue_type", "Ticket type for bugs", "text", "atlassian.issue_type", None, "Usually Bug. Use the exact name your project uses."),
        ("link_type", "How to link a bug to a story", "text", "atlassian.link_type", None, "Optional. Usually Relates. Use a link name from your Jira, for example Blocks."),
        ("space", "Confluence space key (optional)", "text", "atlassian.space", None, "The space for the known-issues page, for example ENG. Leave empty to use Jira only."),
        ("page_title", "Known-issues page title", "text", "atlassian.page_title", None, "Optional. The page is created if it does not exist. Default: Known issues."),
    ]},
    "calendar": {"title": "Google or Outlook calendar", "blurb": "Reads your bookings to send reminders (a private link is enough). To also add, move and cancel bookings in Google Calendar, fill in the Google sign-in details below.", "fields": [
        ("ics_url", "Private calendar link (iCal / ICS)", "secret", "google_calendar.ics_url", "CALENDAR_ICS_URL", "Google Calendar: Settings > your calendar > Integrate calendar > Secret address in iCal format. Outlook: Settings > Calendar > Shared calendars > Publish a calendar > ICS link."),
        ("client_id", "Google client ID (to change bookings)", "text", "google_calendar.client_id", None, "Optional. From your own Google Cloud project: APIs and services > Credentials > OAuth client ID (Web application). Step by step: docs/google-calendar.md."),
        ("client_secret", "Google client secret", "secret", "google_calendar.client_secret", "GOOGLE_CLIENT_SECRET", "Shown once when you create the client."),
        ("refresh_token", "Google refresh token", "secret", "google_calendar.refresh_token", "GOOGLE_REFRESH_TOKEN", "Get it in the Google OAuth Playground with the scope https://www.googleapis.com/auth/calendar.events (see docs/google-calendar.md)."),
        ("calendar_id", "Which calendar", "text", "google_calendar.calendar_id", None, "Leave empty for your main calendar, or paste a calendar's ID (calendar settings > Integrate calendar) to keep bookings apart."),
        ("allow_create", "What the agent may do", "select", "google_calendar.allow_create", None, "Read only is the safe default. The other choice lets it add bookings and move, cancel or delete only the ones it added itself; it never touches your own events."),
    ]},
    "email": {"title": "Email", "blurb": "Sends emails from your own mailbox. Gmail needs an app password, not your normal one.", "fields": [
        ("host", "Mail server", "text", "email.host", None, "Gmail: smtp.gmail.com. Outlook: smtp.office365.com."),
        ("port", "Port", "number", "email.port", None, "465 for Gmail; 587 for most others."),
        ("username", "Username", "text", "email.username", None, "Usually your full email address."),
        ("password", "Password or app password", "secret", "email.password", "EMAIL_PASSWORD", "Gmail: Google Account > Security > App passwords."),
        ("from", "Send from", "text", "email.from", None, "For example: Bella <hello@bella.com>."),
    ]},
    "sip": {"title": "Use my existing business number", "blurb": "Connect a compatible office phone system. Keep your number and provider. No Twilio account needed. The agent signs in to your phone system as an extension, answers the calls you send to it, plays your recorded menu and transfers to your staff.", "fields": [
        ("phone_system", "Who provides your phone service?", "select", "sip.provider", None, "Pick your phone system so the next steps match it. Choose \"I'm not sure\" if you do not know."),
        ("answer_when", "When should the agent answer?", "select", "sip.answer_when", None, "Start with calls nobody answers or after hours. You set this rule in your phone system; the agent answers whatever is sent to its extension."),
        ("server", "Phone system address", "text", "sip.server", None, "The server name or IP your desk phones sign in to, for example sip.yourprovider.com or 192.168.1.5."),
        ("server_port", "Port (optional)", "number", "sip.server_port", None, "5060 unless your phone system uses a different one."),
        ("username", "Extension / username", "text", "sip.username", None, "The extension you created for the agent, for example 101."),
        ("password", "Extension password", "secret", "sip.password", "SIP_PASSWORD", "The SIP password of that extension (not the admin password)."),
        ("auth_username", "Authorization name (optional)", "text", "sip.auth_username", None, "Only if your provider gives a different sign-in name from the extension (RingCentral and Zoom Phone do)."),
        ("domain", "Domain (optional)", "text", "sip.domain", None, "Only if it differs from the address above."),
        ("fallback_number", "If something goes wrong, send callers to (optional)", "text", "sip.fallback_number", None, "A person's extension or number, so a caller is never left in silence."),
        ("transport", "Encrypted connection", "select", "sip.transport", None, "Most office phone systems use the normal (not encrypted) connection. Zoom Phone and some hosted systems require the encrypted one (TLS)."),
        ("srtp", "Encrypted audio", "select", "sip.srtp", None, "Use it when the phone system offers it is right for most. Choose Require it if your provider insists on encrypted audio."),
        ("tls_ca_file", "Certificate file (optional)", "text", "sip.tls_ca_file", None, "Only if your phone system uses its own certificate: the full path of the certificate file your phone admin gives you."),
        ("speech", "Let callers speak", "select", "sip.speech", None, "Callers can say what they need instead of pressing keys. Needs your Speakvora key; their words are turned into text by Speakvora (about $0.0015 a minute) and the audio is not kept."),
        ("external_ip", "This computer's public IP (optional)", "text", "sip.external_ip", None, "Only for a cloud phone system when the agent sits behind a router and the caller hears nothing."),
    ]},
    "address": {"title": "Permanent address", "blurb": "A fixed web address for this agent, so Twilio, WhatsApp, Telegram and your own apps always reach it and you never type 127.0.0.1 and a port number again. Free with Cloudflare Tunnel (use your own domain) or Tailscale.", "fields": [
        ("hostname", "Webhook address", "text", "address.hostname", None, "A name on your domain, for example hooks.yourbusiness.com."),
        ("token", "Cloudflare tunnel token", "secret", "address.token", "TUNNEL_TOKEN", "The long token from your tunnel's page in Cloudflare."),
    ]},
    "android_sms": {"title": "Your Android phone (texts)", "blurb": "Texts from your own phone number and SIM, instantly: no Twilio, no carrier registration. Install the free SMS Gateway for Android app on the phone, sign in, and paste its details here.", "fields": [
        ("username", "Username", "text", "android_sms.username", None, "SMS Gateway for Android app > Home tab > Cloud server > username."),
        ("password", "Password", "secret", "android_sms.password", "ANDROID_SMS_PASSWORD", "The password shown next to the username in the app."),
        ("signing_key", "Webhook signing key", "secret", "android_sms.signing_key", "ANDROID_SMS_SIGNING_KEY", "In the app: Settings > Webhooks > Signing key. Customer texts are only accepted when signed with it."),
        ("lines_text", "Your phones / lines (optional)", "text", "android_sms.lines_text", None, "Only if you use more than one phone, for example: Front desk=DEVICE-ID, Billing=DEVICE-ID. A reply leaves from the phone the customer texted. Device IDs are in the app."),
        ("base_url", "Phone address (optional, advanced)", "url", "android_sms.base_url", None, "Leave empty to go through the app's cloud relay. To keep everything on your own network, use the phone's address, for example https://192.168.1.20:8080."),
    ]},
    "telegram": {"title": "Telegram", "blurb": "Customers message your Telegram bot and the agent answers, free and instantly. Create the bot in Telegram with @BotFather and paste its token. Telegram does not let bots take voice calls.", "fields": [
        ("bot_token", "Bot token", "secret", "telegram.bot_token", "TELEGRAM_BOT_TOKEN", "In Telegram, message @BotFather, send /newbot, and copy the token it gives you."),
    ]},
    "whatsapp": {"title": "WhatsApp Business (Meta)", "blurb": "Answers WhatsApp messages through Meta's own Cloud API, without Twilio. You need a Meta developer app with the WhatsApp product; replies are free within 24 hours of the customer's message.", "fields": [
        ("access_token", "Access token", "secret", "whatsapp.access_token", "WHATSAPP_TOKEN", "Meta for Developers > your app > WhatsApp > API Setup. Use a permanent token from a system user for real use."),
        ("phone_number_id", "Phone number ID", "text", "whatsapp.phone_number_id", None, "On the same API Setup page (not the phone number itself)."),
        ("waba_id", "WhatsApp Business Account ID", "text", "whatsapp.waba_id", None, "Shown next to the phone number ID as the Messaging account ID. Lets the agent subscribe your app so Meta sends it incoming messages."),
        ("app_secret", "App secret", "secret", "whatsapp.app_secret", "WHATSAPP_APP_SECRET", "Meta for Developers > App settings > Basic > App secret. Used to check that messages really come from Meta."),
    ]},
    "account": {"title": "Your Speakvora agent", "blurb": "Connects this agent to your Speakvora account so it can create your hosted order pages (the links customers open), voice new phrases and ask for missing lines. Only order numbers and steps are sent for order pages, never customer details.", "fields": [
        ("api_key", "Speakvora API key", "secret", "speakvora.api_key", "SPEAKVORA_KEY", "On speakvora.com open your account, Voice API tab, and create a key. Paste it here."),
    ]},
    "ai": {"title": "AI reasoning (your own key)", "blurb": "Lets the agent think about requests the rules cannot handle. It only proposes; you approve in Activity. You pay your AI provider, we charge nothing, and only what a workflow chooses is sent.", "fields": [
        ("provider", "Which AI", "select", "reasoner.provider", None, "Pick the company whose key you have."),
        ("api_key", "Your API key", "secret", "reasoner.api_key", "AI_API_KEY", "Claude: console.anthropic.com, API keys. OpenAI: platform.openai.com, API keys. You pay them directly; we charge nothing."),
        ("workspace_id", "Workspace ID (optional)", "text", "reasoner.workspace_id", None, "Only if Claude says your key is not tied to a workspace: the ID from console.anthropic.com, Settings, Workspaces."),
        ("model", "Model", "text", "reasoner.model", None, "Pick a fast one for live answers: Claude Haiku (claude-haiku-5-5) or GPT-4o mini (gpt-4o-mini). Type the model name exactly as the company writes it."),
        ("base_url", "Server address", "url", "reasoner.base_url", None, "Only for a local model or another company that works like OpenAI (Groq, Together, OpenRouter, Azure). Example: http://localhost:11434/v1. Leave empty for Claude and OpenAI."),
    ]},
}
SELECTS = {"transport": [("udp", "Not encrypted (UDP): most office phone systems"), ("tls", "Encrypted (TLS): needed by Zoom Phone and some hosted systems")],
           "speech": [("on", "Yes, when a Speakvora key is set"), ("off", "No, keypad only")],
           "srtp": [("optional", "Use it when the phone system offers it"), ("required", "Require it"), ("off", "Never")],
           "phone_system": [("asterisk", "Asterisk or FreePBX"), ("3cx", "3CX"), ("ringcentral", "RingCentral"), ("zoom", "Zoom Phone"), ("8x8", "8x8"), ("ooma", "Ooma"), ("vonage", "Vonage Business"), ("telnyx", "Telnyx"), ("other", "Another system that offers SIP extensions"), ("unsure", "I'm not sure")],
           "answer_when": [("unanswered", "Only calls nobody answers (safest to start)"), ("after_hours", "After hours only"), ("all", "Every call")],
           "provider": [("anthropic", "Claude (Anthropic)"), ("openai", "ChatGPT (OpenAI)"), ("local", "Another or local AI (needs a server address)")], "allow_create": [("", "Read only"), ("true", "Add, move, cancel and delete its own bookings")], "mode": [("strict", "Careful"), ("standard", "Normal"), ("open", "Open (no limits)")]}
# which card a workflow action needs
STEPS = {
    "android_sms": ["Install the free SMS Gateway for Android app on the phone and switch on its Cloud server.", "Paste its username, password and webhook signing key below, then press Save and test."],
    "telegram": ["In Telegram message @BotFather, send /newbot, and copy the token it gives you.", "Paste the token below and press Save and test."],
    "whatsapp": ["Create a Meta developer app with the WhatsApp product and copy the access token, phone number ID and app secret.", "Paste them below, press Save and test, then paste the callback address it shows into Meta."],
    "teams": ["In Teams open your channel, then Manage team, Apps, Create an outgoing webhook. Name it (this is the name people @mention).", "For the callback URL paste your agent's public address followed by /teams/messages. Teams then shows a security token once: paste it in the token box below and press Save (the alert webhook box stays as it is).", "Press Test answering from Teams, then in the channel write @name KAN-17 fixed: what you did."],
    "sip": ["Create a SIP extension for the agent in your phone system.", "Paste its address, extension and password below, press Save and test, then send calls to that extension."],
}
GUIDES = {"android_sms": "android-sms", "telegram": "telegram", "whatsapp": "whatsapp", "sip": "office-phone", "twilio": "twilio", "slack": "slack", "teams": "teams", "atlassian": "atlassian", "calendar": "calendar", "email": "email", "ai": "ai", "account": "account", "address": "permanent-address"}
EXTRA_GUIDES = {"automations": "automations", "jira": "atlassian"}          # guides for a page of the dashboard rather than a connection (the Automations tab)


def _md_inline(t):
    from html import escape
    t = escape(t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", t)


def guide_html(name, download=False):
    """The full setup guide as one standalone web page (pictures embedded, so the saved file works offline). It holds no secrets and needs no sign-in: a new browser tab can open it."""
    import base64
    from html import escape
    g = guide(name); d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "guides", "img"); out = []; lst = None
    def close():
        nonlocal lst
        if lst:
            out.append(f"</{lst}>"); lst = None
    for line in g["markdown"].split("\n"):
        ol, ul, im = re.match(r"^\d+\.\s+(.*)", line), re.match(r"^-\s+(.*)", line), re.match(r"^!\[([^\]]*)\]\(([\w.-]+)\)\s*$", line)
        if ol or ul:
            tag = "ol" if ol else "ul"
            if lst != tag:
                close(); out.append(f"<{tag}>"); lst = tag
            out.append("<li>" + _md_inline((ol or ul).group(1)) + "</li>"); continue
        close()
        if im:
            f = os.path.join(d, os.path.basename(im.group(2)))
            if os.path.exists(f):
                out.append(f'<figure><img alt="{escape(im.group(1))}" src="data:image/jpeg;base64,{base64.b64encode(open(f, "rb").read()).decode()}"><figcaption>{escape(im.group(1))}</figcaption></figure>')
        elif line.startswith("# "):
            out.append("<h1>" + _md_inline(line[2:]) + "</h1>")
        elif line.startswith("## "):
            out.append("<h2>" + _md_inline(line[3:]) + "</h2>")
        elif line.strip():
            out.append("<p>" + _md_inline(line) + "</p>")
    close(); title = next((re.sub(r"<[^>]+>", "", x) for x in out if x.startswith("<h1>")), "Setup guide")
    css = ":root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--acc:#d9541e;--card:#f5f3ef}@media(prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--mut:#aaa;--acc:#ff8a5c;--card:#222}}body{background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,sans-serif;margin:0;padding:24px 16px}main{max-width:720px;margin:0 auto}h1{font-size:28px;margin:0 0 6px}h2{font-size:19px;margin:30px 0 4px;color:var(--acc)}code{background:var(--card);padding:1px 6px;border-radius:5px}figure{margin:14px 0}img{max-width:min(100%,340px);border-radius:12px;border:1px solid var(--card)}figcaption{color:var(--mut);font-size:13px}.note{color:var(--mut);font-size:13px;margin-top:36px}"
    return ("<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>" + escape(title) + " | Speakvora agent</title><style>" + css + "</style></head><body><main>"
            + "".join(out) + "<p class=note>Speakvora agent setup guide. Screenshots have the account details blurred out. Save this page (File, Save) to keep a copy.</p></main></body></html>")


def guide(name):
    """The full A-to-Z setup guide for a channel (plain text with simple Markdown), shown in the dashboard."""
    slug = next((v for k, v in {**GUIDES, **EXTRA_GUIDES}.items() if name in (k, v)), None)
    if not slug:
        return _tool_guide(name)
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "guides", slug + ".md")
    return {"name": slug, "markdown": open(p, encoding="utf-8").read()}


def _tool_guide(name):
    """A tool that sends events here (GitHub, Stripe...) has its steps in toolguides.py: the full guide is made from them, so the connect window itself stays short."""
    from .toolguides import GUIDES as TG
    g = TG.get(name)
    if not g:
        raise SetupError("There is no guide for that.")
    md = [f"# Connect {g['title']} to your agent", "", "Your agent needs a permanent web address first (Connect, Permanent address). Then:", ""]
    md += [f"{i}. {s}" for i, s in enumerate(g.get("steps", []), 1)]
    if g.get("where"):
        md += ["", f"Where to find it: {g['where']}."]
    if g.get("says"):
        md += ["", "## What the agent understands", ""] + [f"- {v}" for v in dict.fromkeys(g["says"].values())]
    md += ["", "## The two things to copy", "", "In the agent open Connect, find this tool, and copy the address it shows (and the secret, if it shows one). Paste them where the steps above say so, then press Save and test in the agent."]
    return {"name": name, "markdown": "\n".join(md) + "\n"}


NEEDS = {"sms": "twilio", "call": "twilio", "slack": "slack", "teams": "teams", "notify": "slack", "jira_bug": "atlassian", "confluence_log": "atlassian", "email": "email", "calendar_create": "calendar", "calendar_reschedule": "calendar", "calendar_cancel": "calendar", "calendar_delete": "calendar", "reason": "ai"}
TRIGGER_WORDS = {"event": "when your app sends this event", "calendar": "from your calendar", "sms": "when someone texts", "call": "when someone calls", "email": "when someone emails", "slack_command": "from a Slack command", "schedule": "every day"}


class SetupError(ValueError):
    pass


def _get(raw, path):
    cur = raw
    for p in path.split("."):
        cur = cur.get(p) if isinstance(cur, dict) else None
    return cur


def _set(raw, path, value):
    cur = raw; parts = path.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
        if not isinstance(cur, dict):
            raise SetupError("agent.json has an unexpected shape at " + path)
    if value is None:
        cur.pop(parts[-1], None)
    else:
        cur[parts[-1]] = value


def _raw(agent):
    return json.load(open(agent.cfg["_path"], encoding="utf-8"))


def _write_raw(agent, raw):
    p = agent.cfg["_path"]
    try:
        open(p + ".bak", "w", encoding="utf-8").write(open(p, encoding="utf-8").read())             # one step back, in case a change was a mistake
    except OSError:
        pass
    tmp = p + ".tmp"; json.dump(raw, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, p)


def _reload(agent):
    from . import config
    agent.reload(config.load(agent.cfg["_path"], lazy_secrets=True))


def _real(v):
    s = str(v or "")
    return bool(s) and "YOUR-" not in s and not s.startswith("env:")


def ensure_basics(agent):
    """The signing secret for events from your app is made for you the first time, so nobody has to invent one."""
    sd = agent.state.dir
    if not SS.read(sd).get("SV_EVENT_SECRET") and not os.environ.get("SV_EVENT_SECRET"):
        SS.set_value(sd, "SV_EVENT_SECRET", _rnd.token_hex(16))
    raw = _raw(agent)
    if _get(raw, "events.secret") != "env:SV_EVENT_SECRET":
        _set(raw, "events.secret", "env:SV_EVENT_SECRET"); _write_raw(agent, raw); _reload(agent)


def _field_view(agent, raw, card, f):
    key, label, kind, path, env, help_ = f
    cur = _get(raw, path)
    v = {"key": key, "label": label, "kind": kind, "help": help_}
    shown = cur if not (isinstance(cur, str) and cur.startswith("env:")) else None
    resolved = _get(agent.cfg, path)                                     # the real value, whether it came from an environment variable, the key store or the file
    if kind == "secret":
        val = resolved if _real(resolved) else ""
        v.update(set=bool(val), hint=SS.hint(val))
    else:
        txt = "" if resolved is None else str(resolved)
        v["value"] = "" if (not txt or "YOUR-" in txt) else txt
    if key == "allow_create":
        v["value"] = "true" if resolved else ""
    if kind == "select":
        v["options"] = SELECTS[key] if key in SELECTS else [(z, z) for z in TIMEZONES]
        if key == "provider" and not v["value"]:
            v["value"] = ""
    return v


def connected(agent, name):
    c = agent.cfg
    if name == "twilio":
        return bool(agent.twilio.configured and _real(agent.twilio.sid) and _real(agent.twilio.from_number))
    if name == "address":
        from . import address as AD
        v = AD.view(agent)
        return bool(v["in_use"] and (v["tunnel"].get("connected") or v["provider"] in ("tailscale", "own")))
    if name == "sip":
        return bool(agent.sip.configured)
    if name == "android_sms":
        return bool(agent.android.configured)
    if name == "telegram":
        return bool(agent.telegram.configured)
    if name == "whatsapp":
        return bool(agent.whatsapp.configured and _real(agent.whatsapp.phone_id))
    if name == "texts":                                            # any way of sending a text: your phone, Telegram, WhatsApp, Twilio or your own provider
        return bool(connected(agent, "twilio") or connected(agent, "android_sms") or connected(agent, "telegram") or connected(agent, "whatsapp") or agent.sms_provider.configured)
    if name == "slack":
        return bool(agent.slack.configured)
    if name == "teams":
        return bool(agent.teams.configured)
    if name == "atlassian":
        return bool(agent.atlassian.jira_ready)
    if name == "email":
        return bool(agent.mail.configured)
    if name == "calendar":
        return bool(agent.gcal.configured or agent.outlook.configured)
    if name == "ai":
        r = c.get("reasoner") or {}
        return bool(r.get("model") and (r.get("api_key") or str(r.get("provider")) == "local" or r.get("base_url")))
    if name == "business":
        return _real(c.get("business"))
    if name == "account":
        from . import sharing
        return bool(sharing._key(agent))
    return False


def capabilities(agent):
    """What the agent can really do right now, by connection: incoming calls, outgoing calls, sending texts, receiving replies. Each says which connection provides it, or what to connect."""
    base = str(agent.cfg.get("public_base_url", "")).rstrip("/"); public = _real(base) and base.startswith("https://")
    tw = connected(agent, "twilio"); sip = connected(agent, "sip") and bool(agent.sip.registered)
    send = [n for n, ok in (("Your Android phone", connected(agent, "android_sms")), ("Telegram", connected(agent, "telegram")), ("WhatsApp", connected(agent, "whatsapp")), ("Twilio", tw), ("your own provider", agent.sms_provider.configured)) if ok]
    recv = [n for n, ok in (("Telegram", connected(agent, "telegram")),) if ok]                  # Telegram needs no public address: the agent asks for messages itself
    if public:
        recv += [n for n, ok in (("Your Android phone", connected(agent, "android_sms") and bool(agent.android.signing_key)), ("WhatsApp", connected(agent, "whatsapp") and bool(agent.whatsapp.app_secret)), ("Twilio", tw)) if ok]
    callin = [n for n, ok in (("Office phone system", sip), ("Twilio", tw and public)) if ok]
    callout = [n for n, ok in (("Twilio", tw), ("your own provider", agent.call_provider.configured)) if ok]
    def cap(id_, label, via, fix):
        return {"id": id_, "label": label, "ready": bool(via), "via": ", ".join(via), "fix": "" if via else fix}
    warn = []
    if (agent.state.data or {}).get("wa_token_bad"):
        warn = [{"id": "wa_token", "label": "WhatsApp access token", "ready": False, "via": "", "fix": "It expired, so customers get no WhatsApp replies. Paste a new token (a permanent system-user token does not expire): Connect, WhatsApp Business, Full Guide."}]
    return warn + [cap("calls_in", "Answer incoming calls", callin, "Connect your office phone system or Twilio" + ("" if public else ", and set your public address (Settings, Your business details)")),
            cap("calls_out", "Place calls", callout, "Connect your office phone system or Twilio"),
            cap("texts_out", "Send texts and messages", send, "Connect your Android phone, Telegram, WhatsApp or Twilio"),
            cap("texts_in", "Receive replies", recv, "Connect a messaging app and set your public address (Settings, Your business details)" if not public else "Connect a messaging app and finish its signing key")]


def status(agent):
    ensure_basics(agent); raw = _raw(agent); tested = agent.state.data.get("tested", {}); cards = []
    for name, card in CARDS.items():
        cards.append({"name": name, "title": card["title"], "blurb": card["blurb"], "steps": STEPS.get(name, []), "guide": name in GUIDES, "connected": connected(agent, name), "tested": tested.get(name), "fields": [_field_view(agent, raw, name, f) for f in card["fields"]]})
    base = str(agent.cfg.get("public_base_url", "")).rstrip("/")
    listen = agent.cfg.get("listen") or {}
    return {"cards": cards, "capabilities": capabilities(agent), "workflows": workflows(agent), "readiness": readiness(agent), "live": not agent.dry, "event_url": (base if _real(base) else f"http://{listen.get('host', '127.0.0.1')}:{listen.get('port', 8787)}") + "/event",
            "has_public": _real(base), "slack_manifest": slack_manifest(agent) if connected(agent, "business") or True else None, "sources": sources(agent)}


def disconnect(agent, card):
    """Removes what was saved for one app, including its key from this computer's secrets file. The business details are never removed this way."""
    if card not in CARDS or card == "business":
        raise SetupError("That section cannot be removed.")
    raw = _raw(agent); sd = agent.state.dir
    for _k, _label, kind, path, env, _h in CARDS[card]["fields"]:
        _set(raw, path, None)
        if kind == "secret" and env:
            SS.set_value(sd, env, "")
    if card == "ai":
        _set(raw, "reasoner.local", None); _set(raw, "reasoner", None)
    _write_raw(agent, raw); _reload(agent)
    agent.state.data.get("tested", {}).pop(card, None); agent.state.save()
    return {"removed": card}


def save(agent, card, values):
    if card not in CARDS:
        raise SetupError("Unknown section.")
    spec = {f[0]: f for f in CARDS[card]["fields"]}
    raw = _raw(agent); sd = agent.state.dir
    for key, val in (values or {}).items():
        if key not in spec:
            continue
        _k, label, kind, path, env, _h = spec[key]
        val = "" if val is None else str(val).strip()
        if kind == "secret":
            if val == "":                                        # an empty secret box means "leave it as it is"
                continue
            if key == "ics_url":                                 # a calendar link must really be a web address, never stray pasted text
                val = re.sub(r"^webcal://", "https://", val, flags=re.I)
                if not re.match(r"^https?://[^\s]+$", val):
                    raise SetupError(f"{label} must be a web address that starts with https:// (copy the secret iCal address from your calendar's settings).")
            SS.set_value(sd, env, val); _set(raw, path, "env:" + env); continue
        if key == "allow_create":
            _set(raw, path, True if val == "true" else None); continue
        if kind == "number":
            if val and not val.isdigit():
                raise SetupError(f"{label} must be a number.")
            _set(raw, path, int(val) if val else None); continue
        if key == "service_numbers" and val:
            for part in re.split(r"[;,\n]+", val):
                if part.strip() and not re.search(r"\+\d{8,15}", part.replace(" ", "").replace("-", "")):
                    raise SetupError(f"{label}: each entry needs a number with the country code, for example Billing +15551230001.")
        if key in ("from_number", "oncall_phone", "phone") and val and not re.fullmatch(r"\+\d{8,15}", val.replace(" ", "")):
            raise SetupError(f"{label}: include the country code and digits only, for example +15551234567.")
        if key == "fallback_url" and val and not re.match(r"^https://[^\s]+$", val):
            raise SetupError(f"{label} must start with https:// (Twilio needs a secure address).")
        if key in ("review_url", "public_base_url", "base_url", "website") and val and not re.match(r"^https?://[^\s]+$", val):
            raise SetupError(f"{label} must start with http:// or https://.")
        if key == "timezone" and val and val not in TIMEZONES:
            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(val)
            except Exception:  # noqa: BLE001
                raise SetupError("That time zone name is not recognised.")
        if key == "mode" and val not in ("strict", "standard", "open"):
            raise SetupError("Choose Careful, Normal or Open.")
        if key == "provider" and val and val not in ("openai", "anthropic", "local"):
            raise SetupError("Choose one of the listed AIs.")
        if key == "channel" and val and not val.startswith(("#", "C", "G")):
            val = "#" + val
        if card == "atlassian" and key == "project":
            val = val.upper()
        if card == "atlassian" and key == "site" and val and not re.fullmatch(r"(https?://)?[A-Za-z0-9\-]+\.atlassian\.net/?", val):
            raise SetupError("The Atlassian site looks like yourcompany.atlassian.net.")
        if card == "ai" and key == "provider" and val == "local":
            _set(raw, "reasoner.provider", "openai")
            if not (values.get("base_url") or _get(raw, "reasoner.base_url")):
                _set(raw, "reasoner.base_url", "http://localhost:11434/v1")
            _set(raw, "reasoner.local", True); continue
        if card == "ai" and key == "provider":
            _set(raw, "reasoner.local", None)
        _set(raw, path, val if val != "" else None)
    if card == "calendar":
        gc = raw.get("google_calendar") or {}; given = {k for k, v in (values or {}).items() if str(v or "").strip()}
        oauth_ready = bool(gc.get("client_id") and gc.get("client_secret") and gc.get("refresh_token"))
        if "ics_url" in given and not given & {"client_id", "client_secret", "refresh_token"}:         # the last thing the owner pasted decides
            _set(raw, "google_calendar.mode", "ics")
        elif oauth_ready:
            _set(raw, "google_calendar.mode", "oauth")
        elif gc.get("ics_url"):
            _set(raw, "google_calendar.mode", "ics")
    if card == "ai" and _get(raw, "reasoner.local") and not _get(raw, "reasoner.api_key"):
        pass
    _write_raw(agent, raw); _reload(agent)
    agent.state.data.get("tested", {}).pop(card, None); agent.state.save()
    if card == "atlassian" and agent.atlassian.jira_ready and not agent.state.data.get("bug_text_on"):          # first time Jira is connected: switch on "a customer's text that reports a problem becomes a bug" (once; your own switch is kept afterwards)
        try:
            set_workflow(agent, "auto_bug_text", True); agent.state.data["bug_text_on"] = True; agent.state.save()
        except SetupError:
            pass
    if card in ("business", "account", "twilio") and tracking_needed(agent):               # keep the hosted pages in step with what was just saved (best effort: offline is retried later)
        try:
            from . import tracker
            if tracker.mode(agent) == "hosted" and connected(agent, "account"):
                tracker.push_business(agent)
        except Exception:  # noqa: BLE001
            pass
    return next(c for c in status(agent)["cards"] if c["name"] == card)


def _explain(e):
    if isinstance(e, web.NetworkDown):
        return "Could not reach that address. Check it for typos, and that this computer is online."
    if isinstance(e, web.HttpError):
        if e.status in (401, 403):
            return "That was not accepted: check the key or token and try again."
        if e.status == 404:
            return "That address was not found: check it for typos."
        if e.status == 0:
            return "The server did not answer in time."
        try:                                                                    # the provider's own plain-words reason, when it gives one (never the key)
            body = e.body if isinstance(e.body, dict) else json.loads(e.body)
            msg = str((body.get("error") or {}).get("message") or "")
        except Exception:  # noqa: BLE001
            msg = ""
        if "workspace" in msg.lower():
            return "This Claude key is not tied to a workspace. In console.anthropic.com create the key inside your Default workspace (or paste that workspace's ID under Advanced), then try again."
        return f"The service answered with an error ({e.status})." + (" " + msg[:160] if msg else "")
    if isinstance(e, smtplib.SMTPServerDisconnected):
        return "The mail server hung up while signing in. That usually means the password is wrong or your provider needs an app password (Gmail, Yahoo and iCloud do)."
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return "The mail server refused the username or password. For Gmail you need an app password."
    if isinstance(e, (smtplib.SMTPException, OSError, ssl.SSLError)):
        return "Could not reach the mail server: check the server name and port."
    return str(e)[:200] or "Something went wrong."


def voice_check(agent):
    """Voices one short line with the paired Speakvora key and returns it to play, plus this month's live-voice use. This is how the owner confirms speech generation is on."""
    from . import learned, sharing
    if not sharing._key(agent):
        raise SetupError("Connect your Speakvora agent first (Connect tab, Speakvora agent): it holds the key that voices new lines.")
    text = "This is a test of your voice. If you can hear this, speech generation is on."
    try:
        data, ext = learned._voice(agent, text)
        url = agent.audio.put_dynamic(data, ext, text) if agent.audio.base else ""
        if url:
            url = "/audio/" + url.rsplit("/", 1)[1]
        else:                                                                      # no public address yet: serve it from this computer's own cache
            import hashlib
            name = "talk_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:14]; path = os.path.join(agent.audio.cache, name + ext)
            with open(path, "wb") as f:
                f.write(data)
            url = "/audio/" + name + ".mp3" if ext == ".mp3" else ""
    except Exception as e:  # noqa: BLE001
        raise SetupError(_explain(e) if isinstance(e, (web.HttpError, web.NetworkDown)) else str(e)[:200])
    from . import guardrails as G
    mk = learned.month_key(agent); used = int((agent.state.data.get("talk_spent") or {}).get(mk, 0)); cap = int({**G.DEFAULTS, **(agent.cfg.get("guardrails") or {})}.get("talk_chars_per_month", 20000))
    return {"ok": True, "url": url, "text": text, "live_chars_used": used, "live_chars_cap": cap, "library_chars": learned.budget(agent)}


def twilio_numbers(agent):
    """The phone numbers on the saved Twilio account, so the owner picks one instead of typing it. Needs the SID and token saved first."""
    a = agent.twilio
    if not (a.sid and a.token):
        raise SetupError("Save your Account SID and Auth token first.")
    try:
        _st, r = web.request("GET", f"{a.base}/2010-04-01/Accounts/{a.sid}/IncomingPhoneNumbers.json?PageSize=50", a._auth())
    except Exception as e:  # noqa: BLE001
        raise SetupError(_explain(e))
    nums = [{"number": x.get("phone_number", ""), "name": x.get("friendly_name", ""), "voice_url": x.get("voice_url", ""), "sms_url": x.get("sms_url", ""), "voice_fallback_url": x.get("voice_fallback_url", "")} for x in ((r or {}).get("incoming_phone_numbers") or [])]
    if not nums:
        raise SetupError("That Twilio account has no phone numbers yet. Buy one in Twilio first.")
    return {"numbers": nums}


def _fallback_url(agent):
    u = str((agent.cfg.get("twilio") or {}).get("fallback_url") or "").strip()
    return u if re.match(r"^https://[^\s]+$", u) else ""


def _point_form(agent, base):
    form = {"VoiceUrl": base + "/twilio/call", "VoiceMethod": "POST", "SmsUrl": base + "/twilio/sms", "SmsMethod": "POST"}
    fb = _fallback_url(agent)
    if fb:                                                  # Twilio asks this address when it cannot reach the agent (computer off, offline, crashed)
        form.update({"VoiceFallbackUrl": fb, "VoiceFallbackMethod": "POST"})
    return form


def fallback_twiml(phone):
    """The text to paste into a Twilio TwiML Bin: say a short line, then ring the business's own phone, then apologise if nobody picks up."""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<Response>\n'
            '  <Say>Sorry, we cannot take your call on this line right now. Connecting you to our team.</Say>\n'
            f'  <Dial timeout="25">{phone}</Dial>\n'
            '  <Say>Sorry, nobody is available right now. Please try again later.</Say>\n</Response>')


def twilio_fallback(agent):
    """What happens to calls when this computer is off or offline, and how to make Twilio send them to a person instead."""
    facts = agent.cfg.get("facts") or {}; tw = agent.cfg.get("twilio") or {}
    phone = str(facts.get("phone") or "").replace(" ", ""); own = str(tw.get("from_number") or "").replace(" ", "")
    phone_ok = bool(re.fullmatch(r"\+\d{8,15}", phone)) and phone != own
    out = {"phone": phone if phone_ok else "", "phone_problem": "" if phone_ok else ("Add your customer service phone (with country code) in Settings, Your business details. It must be a different number from your Twilio number." if not phone or phone == own else "Your customer service phone needs the country code, for example +15551234567."),
           "twiml": fallback_twiml(phone) if phone_ok else "", "saved": _fallback_url(agent), "applied": ""}
    a = agent.twilio
    if a.sid and a.token and own:
        try:
            _st, r = web.request("GET", f"{a.base}/2010-04-01/Accounts/{a.sid}/IncomingPhoneNumbers.json?PhoneNumber={quote(own)}", a._auth())
            found = (r or {}).get("incoming_phone_numbers") or []
            out["applied"] = (found[0].get("voice_fallback_url") or "") if found else ""
        except Exception:  # noqa: BLE001
            pass
    out["protected"] = bool(out["saved"] and out["applied"] == out["saved"])
    out["steps"] = ["In Twilio open Develop, TwiML Bins, Create new TwiML Bin.", "Name it, paste the text above, press Create, then copy the URL it shows.", "Paste that URL here and press Save backup. The agent sets it on your number for you."]
    return out


def twilio_fallback_set(agent, url):
    """Saves the backup address and sets it on the Twilio number, so Twilio asks it whenever the agent cannot be reached. An empty address removes it."""
    url = str(url or "").strip()
    was = (agent.state.data.get("tested") or {}).get("twilio")          # saving resets a card's passed-test mark; the backup does not change whether Twilio connects, so keep it
    save(agent, "twilio", {"fallback_url": url})
    if was:
        agent.state.data.setdefault("tested", {})["twilio"] = was; agent.state.save()
    a = agent.twilio; own = str((agent.cfg.get("twilio") or {}).get("from_number") or "").replace(" ", "")
    if not (a.sid and a.token and own):
        return {"saved": url, "applied": False, "message": "Saved. Connect Twilio and choose your number, then press Save backup again to set it on the number."}
    try:
        _st, r = web.request("GET", f"{a.base}/2010-04-01/Accounts/{a.sid}/IncomingPhoneNumbers.json?PhoneNumber={quote(own)}", a._auth())
        found = (r or {}).get("incoming_phone_numbers") or []
        if not found:
            raise SetupError(own + " is not a number on that Twilio account.")
        web.request("POST", f"{a.base}/2010-04-01/Accounts/{a.sid}/IncomingPhoneNumbers/{found[0]['sid']}.json", a._auth(), form={"VoiceFallbackUrl": url, "VoiceFallbackMethod": "POST"})
    except SetupError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SetupError(_explain(e))
    return {"saved": url, "applied": True, "message": ("Backup set. If Twilio cannot reach this computer, it will ask that address and the call goes to your team." if url else "Backup removed.")}


def channel_connect(agent, card):
    """Points a text channel at this agent so customer messages arrive: registers the webhook with the phone app (Android) or Telegram, and for WhatsApp makes the verify token and returns what to paste into Meta's dashboard."""
    base = str(agent.cfg.get("public_base_url", "")).rstrip("/"); sd = agent.state.dir
    if not connected(agent, card):
        raise SetupError("Fill in this section and save it first.")
    if card == "telegram" and not (_real(base) and base.startswith("https://")):         # no public address: the agent asks Telegram for messages itself
        try:
            me = agent.telegram.me(); agent.telegram.delete_webhook(); agent.telegram_sync()
        except Exception as e:  # noqa: BLE001
            raise SetupError(_explain(e))
        return {"card": card, "address": "", "message": f"Done. Open Telegram, search @{me.get('username', '')}, press Start and send a message. The agent checks for messages itself while it is running, so no web address is needed."}
    if not (_real(base) and base.startswith("https://")):
        raise SetupError("Your agent has no public web address yet (Settings, Your business details). Messages can only reach an https address on the internet.")
    try:
        if card == "android_sms":
            agent.android.register_webhook(base + "/android/sms")
            return {"card": card, "address": base + "/android/sms", "message": "Done. Your phone will now send every text it receives to this agent. Text your phone from another number to try it."}
        if card == "telegram":
            if not SS.read(sd).get("TELEGRAM_WEBHOOK_SECRET"):
                SS.set_value(sd, "TELEGRAM_WEBHOOK_SECRET", _rnd.token_hex(24))
            raw = _raw(agent); _set(raw, "telegram.webhook_secret", "env:TELEGRAM_WEBHOOK_SECRET"); _write_raw(agent, raw); _reload(agent)
            agent.telegram.set_webhook(base + "/telegram/webhook", SS.read(sd)["TELEGRAM_WEBHOOK_SECRET"])
            me = agent.telegram.me()
            return {"card": card, "address": base + "/telegram/webhook", "message": f"Done. Open Telegram, search @{me.get('username', '')} and send it a message to try it."}
        if card == "whatsapp":
            if not SS.read(sd).get("WHATSAPP_VERIFY_TOKEN"):
                SS.set_value(sd, "WHATSAPP_VERIFY_TOKEN", _rnd.token_hex(12))
            raw = _raw(agent); _set(raw, "whatsapp.verify_token", "env:WHATSAPP_VERIFY_TOKEN"); _write_raw(agent, raw); _reload(agent)
            subscribed = False
            try:
                subscribed = agent.whatsapp.subscribe_account()
            except Exception:  # noqa: BLE001 - not fatal: the guide shows how to do it by hand
                pass
            return {"card": card, "address": base + "/whatsapp/webhook", "verify_token": SS.read(sd)["WHATSAPP_VERIFY_TOKEN"], "subscribed": subscribed,
                    "message": ("Your app is subscribed to your WhatsApp account. " if subscribed else "Add the WhatsApp Business Account ID so the agent can subscribe your app, or see the Full Guide. ") + "In Meta for Developers open WhatsApp > Configuration, press Edit on Webhook, paste the callback address and the verify token, then subscribe to \"messages\"."}
    except Exception as e:  # noqa: BLE001
        raise SetupError(_explain(e))
    raise SetupError("That section does not receive messages.")


def twilio_point(agent, number):
    """Points a Twilio number's call and text webhooks at this agent's public address, so the owner never opens the Twilio console."""
    a = agent.twilio; base = str(agent.cfg.get("public_base_url", "")).rstrip("/")
    if not (_real(base) and base.startswith("https://")):
        raise SetupError("Your agent has no public web address yet (Settings, Your business details). Twilio can only reach an address on the internet.")
    number = str(number or "").replace(" ", "")
    if not re.fullmatch(r"\+\d{8,15}", number):
        raise SetupError("Choose one of your Twilio numbers.")
    try:
        _st, r = web.request("GET", f"{a.base}/2010-04-01/Accounts/{a.sid}/IncomingPhoneNumbers.json?PhoneNumber={quote(number)}", a._auth())
        found = (r or {}).get("incoming_phone_numbers") or []
        if not found:
            raise SetupError(number + " is not a number on that Twilio account.")
        web.request("POST", f"{a.base}/2010-04-01/Accounts/{a.sid}/IncomingPhoneNumbers/{found[0]['sid']}.json", a._auth(), form=_point_form(agent, base))
    except SetupError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SetupError(_explain(e))
    return {"pointed": number, "calls": base + "/twilio/call", "texts": base + "/twilio/sms"}


def test(agent, card, opts=None):
    """Checks a connection and answers in plain words. A test that sends something (a message, an email) says so on its button and only runs when asked (opts)."""
    opts = opts or {}
    if not connected(agent, card) and card != "business" and not (card == "teams" and opts.get("inbound")):
        return {"ok": False, "message": "Fill in this section and save it first."}
    try:
        if card == "account":
            from . import tracker
            r = tracker.push_business(agent)
            return _passed(agent, card, "Connected to your Speakvora account." + (" Your order pages are ready: see a sample at " + r["preview_url"] if r.get("preview_url") else ""))
        if card == "twilio":
            a = agent.twilio
            st, r = web.request("GET", f"{a.base}/2010-04-01/Accounts/{a.sid}.json", a._auth())
            msg = f"Connected to Twilio account \"{(r or {}).get('friendly_name', a.sid)}\"."
            _st, nums = web.request("GET", f"{a.base}/2010-04-01/Accounts/{a.sid}/IncomingPhoneNumbers.json?PhoneNumber={quote(a.from_number)}", a._auth())
            if isinstance(nums, dict) and nums.get("incoming_phone_numbers") == []:
                return {"ok": False, "message": msg + f" But {a.from_number} is not a number on that account: check it."}
            if opts.get("to"):
                to = str(opts["to"]).replace(" ", "")
                if not re.fullmatch(r"\+\d{8,15}", to):
                    return {"ok": False, "message": "Type your own phone number with the country code to receive a test text."}
                a.sms(to, "Test text from your voice bundle's agent. If you got this, texting works.")
                msg += f" A test text was sent to {to}."
            return _passed(agent, card, msg)
        if card == "sip":
            s = agent.sip
            if not s.running:
                return {"ok": False, "message": "The agent's web server is not running, so the phone line cannot sign in. Start the agent, then test again."}
            for _ in range(24):
                if s.registered or s.error:
                    break
                time.sleep(0.25)
            if not s.registered:
                return {"ok": False, "message": (s.error or "No answer from the phone system yet.") + " Check the address, extension and password, and that this computer can reach the phone system."}
            return _passed(agent, card, f"Signed in to {s.server} as extension {s.user}. Send the calls you want answered to that extension.")
        if card == "android_sms":
            a = agent.android; r = a.devices(); n = len(r) if isinstance(r, list) else None
            msg = "Signed in to the SMS Gateway" + (f": {n} phone(s) registered." if n is not None else ".")
            if n == 0:
                return {"ok": False, "message": msg + " Open the app on your phone and switch the Cloud server on."}
            if not a.signing_key:
                return {"ok": False, "message": msg + " Add the webhook signing key (app > Settings > Webhooks) so customer texts can be accepted."}
            if opts.get("to"):
                to = str(opts["to"]).replace(" ", "")
                if not re.fullmatch(r"\+\d{8,15}", to):
                    return {"ok": False, "message": "Type your own phone number with the country code to receive a test text."}
                a.send(to, "Test text from your voice bundle's agent. If you got this, texting from your phone works.")
                msg += f" A test text was sent to {to}."
            return _passed(agent, card, msg)
        if card == "telegram":
            me = agent.telegram.me()
            return _passed(agent, card, f"Connected to the Telegram bot @{me.get('username', '')}. Customers find it by that name.")
        if card == "whatsapp":
            r = agent.whatsapp.me() or {}
            agent.state.data.pop("wa_token_bad", None)
            return _passed(agent, card, f"Connected to WhatsApp number {r.get('display_phone_number', agent.whatsapp.phone_id)} ({r.get('verified_name', 'name pending')}).")
        if card == "slack":
            s = agent.slack; msg = ""
            if s.token:
                _st, r = web.request("POST", f"{s.base}/auth.test", s._h())
                if not (isinstance(r, dict) and r.get("ok")):
                    return {"ok": False, "message": "Slack did not accept that bot token."}
                msg = f"Connected to the Slack workspace \"{r.get('team', '')}\"."
            if opts.get("post"):
                s.post("Test message from your voice bundle's agent. If you can read this, Slack works.", s.channel or None)
                msg += f" A test message was posted to {s.channel or 'the webhook channel'}."
            elif not s.token:
                return {"ok": True, "message": "A webhook is saved. Press \"Send a test message\" to check it."}
            return _passed(agent, card, msg.strip())
        if card == "atlassian":
            at = agent.atlassian
            if not at.configured:
                return {"ok": False, "message": "Fill in your Atlassian site, email and API token first."}
            try:
                me = at.myself()
            except web.HttpError as e:
                return {"ok": False, "message": "Atlassian did not accept the email and token" + (" (the address may be wrong)." if e.status in (404, 0) else ".")}
            msg = f"Signed in as {me.get('displayName', 'your account')}."
            if at.project:
                try:
                    pj = at.project_info()
                except web.HttpError:
                    return {"ok": False, "message": msg + f" The project {at.project} was not found, or your account cannot see it."}
                types = [t.get("name") for t in pj.get("issueTypes", [])]
                if types and at.issue_type not in types:
                    return {"ok": False, "message": msg + f" The project {at.project} has no ticket type called {at.issue_type}. It has: {', '.join(types)}."}
                msg += f" Project {pj.get('name', at.project)} found."
            if at.space:
                try:
                    at.space_id(); msg += f" Confluence space {at.space} found."
                except web.HttpError:
                    return {"ok": False, "message": msg + f" The Confluence space {at.space} was not found, or your account cannot see it."}
            if opts.get("create"):
                if not at.jira_ready:
                    return {"ok": False, "message": msg + " Add the project key first."}
                key = at.create_bug("Speakvora test bug (safe to close)", ATL.adf([("p", "Created by the Test button in the Speakvora agent to check this connection. You can close or delete it.")]), at.labels + ["speakvora-test"])
                msg += f" A test ticket {key} was created: {at.link(key)}"
            return _passed(agent, card, msg)
        if card == "teams" and opts.get("inbound"):
            from . import teams_in
            return teams_in.selftest(agent)
        if card == "teams":
            if not opts.get("post"):
                return {"ok": True, "message": "Saved. Press \"Send a test message\" to check it: Teams cannot be checked without posting."}
            agent.teams.post("Test message from your voice bundle's agent. If you can read this, Teams works.")
            return _passed(agent, card, "A test message was posted to your Teams channel.")
        if card == "calendar":
            for cal in (agent.gcal, agent.outlook):
                if getattr(cal, "mode", "") == "ics" and cal.configured:   # the link must return a real calendar, not a web page or an error
                    _st, txt = web.request("GET", cal.cfg["ics_url"])
                    if "BEGIN:VCALENDAR" not in (txt if isinstance(txt, str) else ""):
                        return {"ok": False, "message": "That address did not return a calendar. Use the secret iCal address (it ends in .ics) from your calendar's settings."}
            now = time.time(); ev = agent._events(now - 86400, now + 7 * 86400)
            can = " The agent may add, move, cancel and delete the bookings it creates." if (agent.gcal.mode == "oauth" and agent.gcal.allow_create) else ""
            return _passed(agent, card, f"Calendar read: {len(ev)} event(s) in the next 7 days." + ("" if ev else " (An empty calendar is fine; check it is the right one.)") + can)
        if card == "email":
            m = agent.mail; port = int(m.cfg.get("port", 465))
            s = smtplib.SMTP_SSL(m.cfg["host"], port, timeout=20) if port == 465 else smtplib.SMTP(m.cfg["host"], port, timeout=20)
            try:
                if port != 465:
                    s.starttls()
                s.login(m.cfg["username"], m.cfg["password"])
            finally:
                try:
                    s.quit()
                except Exception:  # noqa: BLE001
                    pass
            msg = "Signed in to the mail server."
            if opts.get("to"):
                m.send(str(opts["to"]), "Test email from your voice bundle's agent", "If you can read this, email works.")
                msg += f" A test email was sent to {opts['to']}."
            return _passed(agent, card, msg)
        if card == "ai":
            text = R.ping(agent.cfg.get("reasoner") or {})
            from . import brain
            learning = brain.start_learning(agent)                      # the AI works: start learning the business right away (in the background, for the owner to review)
            from . import access as _ax
            if _ax.view(agent)["by"] != "owner":                         # and decide, for this kind of business, how callers who are deaf or find speaking hard are helped (the owner can change it)
                def _choose():
                    try:
                        _ax.suggest(agent)
                    except Exception as e:  # noqa: BLE001
                        agent.state.log(workflow="accessibility", action="ai_choice", status="error", dry_run=False, error=str(e)[:120])
                import threading as _th
                _t = _th.Timer(4.0, _choose); _t.daemon = True; _t.start()                      # a moment after the test settles, so the choice never races the test itself
            return _passed(agent, card, f"The AI answered: \"{text.strip()[:60]}\". Reasoning is ready; it only proposes, and you approve." + (" It is now learning your business: review what it learned in Library." if learning else ""))
        if card == "business":
            return {"ok": True, "message": "Looks complete." if connected(agent, "business") else "Add your business name."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": _explain(e)}
    return {"ok": False, "message": "Unknown section."}


def _passed(agent, card, msg):
    agent.state.data.setdefault("tested", {})[card] = int(agent.now()); agent.state.save()
    return {"ok": True, "message": msg}


def check_public(agent):
    base = str(agent.cfg.get("public_base_url", "")).rstrip("/")
    if not _real(base):
        return {"ok": False, "message": "No public address saved. You only need one for calls that play recordings and for inbound texts."}
    try:
        _st, r = web.request("GET", base + "/health", timeout=10)
        if isinstance(r, dict) and r.get("pack") == agent.pack.meta.get("pack"):
            agent.state.data.setdefault("tested", {})["public_address"] = int(agent.now()); agent.state.save()
            return {"ok": True, "message": "That address reaches this agent."}
        return {"ok": False, "message": "That address answered, but it is not this agent."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": _explain(e)}


def _workflow_file(agent):
    return json.load(open(agent.cfg["workflows"], encoding="utf-8"))


def _kinds(w, skip_optional=False):
    out = set()
    def walk(o):
        if isinstance(o, dict):
            if "action" in o and not (skip_optional and o.get("optional")):          # an optional step (the Jira step of a ready-made automation) is skipped quietly when its service is not connected, so it never blocks going live
                out.add(o["action"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(w.get("do")); walk((w.get("on") or {}).get("call"))
    return out


def workflows(agent):
    from . import recipes, wfedit
    out = []; ed = wfedit.load(agent)
    for w in _workflow_file(agent).get("workflows", []):
        needs = sorted({NEEDS[k] for k in _kinds(w, True) if k in NEEDS}); on = w.get("on") or {}
        if (on.get("sms") or {}).get("when_closed") and not wfedit.hours(agent):
            needs = sorted(set(needs) | {"hours"})
        trig = next((TRIGGER_WORDS[k] for k in TRIGGER_WORDS if k in on), "")
        title, what = recipes.plain(w["name"]) if not w.get("title") else (w["title"], w.get("what") or recipes.NICE.get(w["name"], ""))
        e = ed.get(w["name"]) or {}; st = wfedit.state_of(w, e)
        out.append({"name": w["name"], "title": title, "what": what, "when": trig, "enabled": st == "on", "state": st, "kit": bool(w.get("kit")), "sale": bool(w.get("sale")), "edited": bool(e.get("texts") or e.get("keywords") or e.get("reminder") or e.get("daily_at") or e.get("lead")),
                    "also": w.get("also_send_to") or [], "needs": needs,
                    "missing": [n for n in needs if n == "hours" or not (connected(agent, "texts") if n == "twilio" and "call" not in _kinds(w) else connected(agent, n))]})      # texts alone can go through your phone, Telegram or WhatsApp; calls still need Twilio
    from . import eventflows, builder as _bd
    for ev, why in eventflows.SOON.items():                                                  # listed last, with no switch: coming soon
        out.append({"name": "soon_" + ev.replace(".", "_"), "title": _bd.EVENTS.get(ev, ev), "what": why, "when": "when your app sends this event", "enabled": False, "also": [], "needs": [], "missing": [], "soon": True})
    return out


def set_workflow(agent, name, enabled):
    wf = _workflow_file(agent); hit = False
    for w in wf.get("workflows", []):
        if w["name"] == name:
            if enabled and w.get("kit"):
                from . import wfedit
                if not wfedit.approved(agent, name):
                    raise SetupError("Open it, read the wording and press “Approve and turn on” first.")
            w["enabled"] = bool(enabled); hit = True
    if not hit:
        raise SetupError("No such workflow.")
    p = agent.cfg["workflows"]; open(p + ".bak", "w", encoding="utf-8").write(open(p, encoding="utf-8").read())
    tmp = p + ".tmp"; json.dump(wf, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, p); agent._load_workflows()
    return workflows(agent)


def tracking_needed(agent):
    """Order pages are optional: they are needed only once the business has switched them on."""
    return bool((agent.cfg.get("tracking") or {}).get("enabled")) and any(w.get("enabled", True) and "track" in _kinds(w) for w in _workflow_file(agent).get("workflows", []))


def set_tracking(agent, on):
    """The switch on the dashboard: give customers an order tracking link (needs the business details and a paired Speakvora account)."""
    raw = _raw(agent); raw.setdefault("tracking", {})["enabled"] = bool(on)
    _write_raw(agent, raw); _reload(agent)
    return order_pages(agent)


ORDER_PAGE_FIELDS = (("business", "Business name"), ("website", "Business website"), ("phone", "Customer service phone"), ("hours", "Opening hours"), ("address", "Address"))


def order_pages(agent):
    """Where the order-pages setup stands, for the dashboard: {'needed', 'complete', 'missing': [labels], 'has_key', 'preview_url'}."""
    from . import tracker
    f = agent.cfg.get("facts") or {}
    missing = [lab for k, lab in ORDER_PAGE_FIELDS if not _real(agent.cfg.get("business") if k == "business" else f.get(k))]
    has_key = connected(agent, "account"); hosted = tracker.mode(agent) == "hosted"
    if hosted and not has_key:
        missing.append("Speakvora API key")
    done = not missing and ((tracker.pages_current(agent) and bool((agent.state.data.get("tested") or {}).get("order_pages"))) if hosted else bool((agent.state.data.get("tested") or {}).get("public_address")))
    return {"enabled": bool((agent.cfg.get("tracking") or {}).get("enabled")), "available": any("track" in _kinds(w) for w in _workflow_file(agent).get("workflows", [])), "needed": tracking_needed(agent), "complete": done, "missing": missing, "has_key": has_key, "hosted": hosted, "preview_url": (agent.state.data.get("order_pages") or {}).get("preview_url", "")}


def pair_agent(agent, code):
    """Swaps the short code from the account page (Connect my agent) for this agent's own Speakvora key and saves it. The key can speak (voice new lines, live answers) and make order pages."""
    from . import sharing
    code = re.sub(r"[^A-Za-z0-9-]", "", str(code or "")).upper()
    if not re.fullmatch(r"SV-[A-Z0-9]{4}-[A-Z0-9]{4}", code):
        raise SetupError("The code looks like SV-ABCD-EFGH. Make one on speakvora.com/account with Connect my agent.")
    try:
        st, r = web.request("POST", sharing.host() + "/api/v1/track/pair", body={"code": code}, timeout=15)
    except web.HttpError as e:
        body = e.body if isinstance(getattr(e, "body", None), dict) else {}
        raise SetupError(body.get("detail") or "That code was not accepted. Make a new one in your account.")
    except Exception:  # noqa: BLE001
        raise SetupError("No internet connection right now. Try again when you are online.")
    r = r if isinstance(r, dict) else {}
    if not r.get("api_key"):
        raise SetupError("Speakvora did not return a key. Make a new code and try again.")
    save(agent, "account", {"api_key": r["api_key"]})
    b = r.get("business") or {}
    return {"paired": True, "kind": r.get("kind", "track"), "business": b.get("name") or ""}


def pair_account(agent, code):
    """Swaps the short code from the account page for a key that can only create order pages, and fills in the business details the account already holds. Switches order pages on."""
    from . import sharing
    code = re.sub(r"[^A-Za-z0-9-]", "", str(code or "")).upper()
    if not re.fullmatch(r"SV-[A-Z0-9]{4}-[A-Z0-9]{4}", code):
        raise SetupError("The code looks like SV-ABCD-EFGH. Make one in your Speakvora account under Bundles, Order pages.")
    try:
        st, r = web.request("POST", sharing.host() + "/api/v1/track/pair", body={"code": code}, timeout=15)
    except web.HttpError as e:
        body = e.body if isinstance(getattr(e, "body", None), dict) else {}
        raise SetupError(body.get("detail") or "That code was not accepted. Make a new one in your account.")
    except Exception:  # noqa: BLE001
        raise SetupError("No internet connection right now. Try again when you are online.")
    r = r if isinstance(r, dict) else {}
    if not r.get("api_key"):
        raise SetupError("Speakvora did not return a key. Make a new code and try again.")
    b = r.get("business") or {}
    vals = {"api_key": r["api_key"], "business": b.get("name"), "website": b.get("website"), "phone": b.get("phone"), "hours": b.get("hours"), "address": b.get("address")}
    return setup_order_pages(agent, {k: v for k, v in vals.items() if v})


def setup_order_pages(agent, values):
    """One step for the business: save the details and the key, create the hosted pages, return the sample link. values: business, website, phone, service_numbers, hours, address, api_key."""
    from . import tracker
    v = {k: str(x).strip() for k, x in (values or {}).items() if x is not None}
    if not (agent.cfg.get("tracking") or {}).get("enabled"):
        set_tracking(agent, True)
    biz = {k: v[k] for k in ("business", "website", "phone", "service_numbers", "hours", "address") if v.get(k)}
    if biz:
        save(agent, "business", biz)
    if v.get("api_key"):
        save(agent, "account", {"api_key": v["api_key"]})
    st = order_pages(agent)
    if st["missing"]:
        raise SetupError("Still needed: " + ", ".join(st["missing"]) + ".")
    if st["hosted"]:
        try:
            tracker.push_business(agent)
        except ValueError as e:
            raise SetupError(str(e))
    return order_pages(agent)


def readiness(agent):
    """What must be true before the agent sends for real."""
    wfs = workflows(agent); on = [w for w in wfs if w["enabled"]]; tested = agent.state.data.get("tested", {})
    live_services = [n for n in ("twilio", "sip", "android_sms", "telegram", "whatsapp", "slack", "teams", "atlassian", "email", "calendar") if connected(agent, n)]
    checks = [{"ok": connected(agent, "business"), "text": "Your business name is filled in."},
              {"ok": bool(live_services), "text": "At least one service is connected (texts and calls, Slack, Teams, email or calendar)."},
              {"ok": bool(live_services) and all(tested.get(n) for n in live_services), "text": "Every connected service passed its test."},
              {"ok": bool(on), "text": "At least one workflow is switched on."},
              {"ok": not [w for w in on if w["missing"] and set(w["missing"]) - {"ai"}], "text": "Every workflow that is switched on has what it needs connected (otherwise it will be skipped and logged)."}]
    if tracking_needed(agent):                                                                    # order links are on: the business details are real, and the pages exist (hosted) or the public address works (self-hosted)
        from . import tracker
        f = agent.cfg.get("facts") or {}
        checks.append({"ok": all(_real(f.get(k)) for k in ("website", "phone", "hours", "address")), "text": "Order tracking links need your business website, customer service phone, opening hours and address (Connect, Your business)."})
        if tracker.mode(agent) == "hosted":
            checks.append({"ok": connected(agent, "account") and bool(tested.get("order_pages")) and tracker.pages_current(agent), "text": "Your order pages are created at Speakvora (Connect, Your Speakvora account, then Create my order pages)."})
        else:
            checks.append({"ok": bool(tested.get("public_address")) and _real(agent.cfg.get("public_base_url")), "text": "Your public address is set and the Test button confirmed it reaches this agent."})
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def go_live(agent, on):
    if on:
        r = readiness(agent)
        if not r["ok"]:
            raise SetupError("Not ready yet: " + "; ".join(c["text"] for c in r["checks"] if not c["ok"]))
    agent.set_live(bool(on))
    return {"live": not agent.dry}


def sources(agent):
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sources"); have = {s.get("name") for s in agent.cfg.get("sources", [])}; out = []
    for f in sorted(os.listdir(d)):
        if f.endswith(".json"):
            s = json.load(open(os.path.join(d, f), encoding="utf-8")); out.append({"name": s["name"], "file": f[:-5], "added": s["name"] in have, "path": s.get("path", "")})
    return out


def add_source(agent, name):
    src = _source_def(name); raw = _raw(agent)
    raw["sources"] = [x for x in raw.get("sources", []) if x.get("name") != src["name"]] + [src]; _write_raw(agent, raw); _reload(agent)
    return {"added": src["name"], "path": src.get("path"), "auth": (src.get("auth") or {}).get("secret") or (src.get("auth") or {}).get("token") or ""}


# ---- the tools that send events here: guided setup, secret, test, remove -------------------------------------------------------------------------------------------------------------------------
def _source_def(name):
    """A tool's definition by its file name or by the name inside it (the point-of-sale file is generic-pos, its name is pos)."""
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sources")
    if not re.fullmatch(r"[a-z0-9\-]+", str(name)):
        raise SetupError("Unknown tool.")
    for f in sorted(os.listdir(d)):
        if f.endswith(".json"):
            j = json.load(open(os.path.join(d, f), encoding="utf-8"))
            if f[:-5] == name or j.get("name") == name:
                return j
    raise SetupError("Unknown tool.")


def _secret_env(src):
    a = src.get("auth") or {}; v = str(a.get("secret") or a.get("token") or "")
    return v[4:] if v.startswith("env:") else ""


def tool_view(agent, name):
    from .toolguides import GUIDES
    src = _source_def(name); g = GUIDES.get(name) or GUIDES.get(src["name"]) or {}
    have = {s.get("name"): s for s in agent.cfg.get("sources", [])}; env = _secret_env(src)
    base = str(agent.cfg.get("public_base_url", "")).rstrip("/"); public = _real(base) and base.startswith("https://")
    seen = (agent.state.data.get("tool_seen") or {}).get(src["name"])
    mode = g.get("mode", "generate"); secret_set = bool(env and SS.read(agent.state.dir).get(env))
    ev = (src.get("map") or {}).get("event") or {}; says = g.get("says") or {}
    return {"name": name, "title": g.get("title", name.title()), "added": src["name"] in have, "mode": mode, "secret_label": g.get("secret_label", "Secret"), "secret_set": secret_set,
            "url": (base + src.get("path", "")) if public else "", "public": public, "where": g.get("where", ""), "steps": g.get("steps", []), "extra": g.get("extra", ""), "lead": g.get("lead", ""),
            "events": [{"they": k, "we": v, "says": says.get(v, v)} for k, v in (ev.get("values") or {}).items()], "last_seen": seen}


def tool_secret(agent, name):
    """The secret this agent made for a tool (to paste into that tool). Only for tools where the agent makes it."""
    from .toolguides import GUIDES
    src = _source_def(name); g = GUIDES.get(name) or {}
    if g.get("mode", "generate") != "generate":
        raise SetupError("This tool shows you its own secret. Paste it into the box instead.")
    return {"secret": SS.read(agent.state.dir).get(_secret_env(src), "")}


def tool_save(agent, name, secret=""):
    """Connects a tool: makes (or keeps) the secret, adds the source and returns the view. A tool that shows its own secret needs it pasted here."""
    from .toolguides import GUIDES
    src = _source_def(name); g = GUIDES.get(name) or {}; env = _secret_env(src); sd = agent.state.dir
    if not env:
        raise SetupError("That tool needs no secret.")
    secret = str(secret or "").strip(); have = SS.read(sd).get(env, "")
    if g.get("mode", "generate") == "paste":
        if not secret and not have:
            raise SetupError("Paste the secret " + g.get("title", name) + " showed you, then press Save and test.")
        if secret:
            if len(secret) < 8 or re.search(r"\s", secret):
                raise SetupError("That does not look like a signing secret. Copy it again from " + g.get("title", name) + ".")
            SS.set_value(sd, env, secret)
    elif not have:
        SS.set_value(sd, env, _rnd.token_urlsafe(24))
    add_source(agent, name)
    out = tool_view(agent, name)
    if g.get("mode", "generate") == "generate":
        out["secret"] = SS.read(sd).get(env, "")
    return out


def tool_test(agent, name):
    """Checks the connection: the public address, the secret, and that a sample message from the tool is understood (and which of your workflows it would start)."""
    from . import sources as SRC
    v = tool_view(agent, name)
    if not v["added"]:
        return {"ok": False, "message": "Save it first."}
    problems = []
    if not v["public"]:
        problems.append("Your agent has no public address yet, so " + v["title"] + " cannot reach it. Set it under Settings, Business details, or start a tunnel.")
    if not v["secret_set"]:
        problems.append("The secret is missing.")
    src = next(s for s in agent.cfg.get("sources", []) if s.get("name") == _source_def(name)["name"])
    first = (src.get("map", {}).get("event") or {}).get("values") or {}
    k, we = next(iter(first.items()))
    ev = src["map"]["event"]; req = {"payload": {}, "headers": {}, "query": {}}
    if ev.get("template"):
        t = ev["template"]
        if name == "github":
            req["headers"]["x-github-event"] = "workflow_run"; req["payload"] = {"action": "completed", "workflow_run": {"conclusion": "failure"}}; we = "pipeline.failed"
        else:
            req["headers"]["x-gitlab-event"] = "Pipeline Hook"; req["payload"] = {"object_attributes": {"status": "failed"}}; we = "pipeline.failed"
    else:
        path = str(ev.get("from", "")).split(".")
        tgt = req
        for i, part in enumerate(path):
            if i == len(path) - 1:
                tgt[part] = k
            else:
                tgt = tgt.setdefault(part, {})
    got = SRC.map_request(src, req)
    if not got or not got.get("event"):
        problems.append("A sample message from " + v["title"] + " was not understood. This is a bug, please report it.")
    elif got["event"] != we:
        problems.append("A sample message was read as " + got["event"] + ", not " + we + ".")
    wfs = sorted({w["name"] for w in (_workflow_file(agent).get("workflows") or []) if (w.get("on") or {}).get("event") == (got or {}).get("event")})
    if problems:
        return {"ok": False, "message": " ".join(problems)}
    msg = "Connected. A sample " + v["title"] + " message is understood as “" + got["event"] + "”." + (" It starts: " + ", ".join(wfs) + "." if wfs else " None of your workflows use that event yet.")
    msg += (" Last real message received " + time.strftime("%b %d, %H:%M", time.localtime(v["last_seen"])) + ".") if v["last_seen"] else " Waiting for the first real message from " + v["title"] + "."
    agent.state.data.setdefault("tested", {})["tool:" + name] = int(time.time()); agent.state.save()
    return {"ok": True, "message": msg, "event": got["event"], "workflows": wfs}


def tool_remove(agent, name):
    src = _source_def(name); raw = _raw(agent)
    raw["sources"] = [x for x in raw.get("sources", []) if x.get("name") != src["name"]]; _write_raw(agent, raw)
    env = _secret_env(src)
    if env:
        SS.set_value(agent.state.dir, env, "")
    _reload(agent)
    return {"removed": name}


def slack_manifest(agent):
    """Paste this into Slack (api.slack.com/apps > Create New App > From a manifest): it sets up the bot, its permissions and your slash commands in one step."""
    base = str(agent.cfg.get("public_base_url", "")).rstrip("/")
    cmds = sorted({(w.get("on") or {}).get("slack_command") for w in _workflow_file(agent).get("workflows", []) if (w.get("on") or {}).get("slack_command")})
    m = {"display_information": {"name": (agent.cfg.get("business") if _real(agent.cfg.get("business")) else "Voice bundle agent")[:35]},
         "features": {"bot_user": {"display_name": "Voice bundle agent", "always_online": True}},
         "oauth_config": {"scopes": {"bot": ["chat:write", "files:write", "commands", "channels:history", "groups:history"]}},
         "settings": {"org_deploy_enabled": False, "socket_mode_enabled": False, "token_rotation_enabled": False,
                      "event_subscriptions": {"request_url": (base if _real(base) else "https://YOUR-PUBLIC-ADDRESS") + "/slack/events", "bot_events": ["message.channels", "message.groups"]}}}
    if cmds:
        m["features"]["slash_commands"] = [{"command": c, "url": (base if _real(base) else "https://YOUR-PUBLIC-ADDRESS") + "/slack/command", "description": "Voice bundle agent", "should_escape": False} for c in cmds]
    return m


# ---- your own apps: send to them, receive from them -----------------------------------------------------------------------------------------------------------------------------------------------
def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")[:30]
    if not s:
        raise SetupError("Give it a name.")
    return s


def _env(prefix, slug, suffix):
    return f"{prefix}_{slug.upper().replace('-', '_')}_{suffix}"


def _public_or_local(agent):
    base = str(agent.cfg.get("public_base_url", "")).rstrip("/")
    listen = agent.cfg.get("listen") or {}
    return base if _real(base) else f"http://{listen.get('host', '127.0.0.1')}:{listen.get('port', 8787)}"


def connections(agent):
    """Your own apps. Outgoing: addresses the agent can post to (workflows can also send them what they did). Incoming: addresses your app or any tool can post events to."""
    raw = _raw(agent); tested = agent.state.data.get("tested", {})
    out = [{"id": c["id"], "name": c.get("name", c["id"]), "url": c.get("url", ""), "auth": (c.get("auth") or {}).get("type", "none"), "tested": tested.get("conn:" + c["id"])} for c in raw.get("connections", [])]
    inc = [{"id": s["name"], "name": s["name"], "path": s["path"], "url": _public_or_local(agent) + s["path"]} for s in raw.get("sources", []) if str(s.get("name", "")).startswith("custom-")]
    return {"outgoing": out, "incoming": inc}


def add_connection(agent, v):
    name = str(v.get("name", "")).strip(); slug = _slug(name); url = str(v.get("url", "")).strip(); kind = str(v.get("auth_type") or "none")
    if not re.match(r"^https://[^\s/]+", url) and not re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?(/|$)", url):
        raise SetupError("The address must start with https:// (http:// is allowed only for localhost).")
    if kind not in ("none", "header", "bearer", "basic"):
        raise SetupError("Choose how your app checks the key: none, a header, a bearer token or basic.")
    raw = _raw(agent); conns = [c for c in raw.get("connections", []) if c.get("id") != slug]; entry = {"id": slug, "name": name, "url": url, "auth": {"type": kind}}
    if kind == "header":
        h = str(v.get("header", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9\-]{1,40}", h):
            raise SetupError("Type the header name your app expects, for example X-Api-Key.")
        entry["auth"]["header"] = h
    if kind != "none":
        secret = str(v.get("secret", "")).strip(); env = _env("CONN", slug, "KEY")
        if secret:
            SS.set_value(agent.state.dir, env, secret)
        elif not SS.read(agent.state.dir).get(env):
            raise SetupError("Paste the key or token your app expects.")
        entry["auth"]["secret"] = "env:" + env
    raw["connections"] = conns + [entry]; _write_raw(agent, raw); _reload(agent)
    agent.state.data.get("tested", {}).pop("conn:" + slug, None); agent.state.save()
    return connections(agent)


def remove_connection(agent, cid):
    raw = _raw(agent); raw["connections"] = [c for c in raw.get("connections", []) if c.get("id") != cid]
    _write_raw(agent, raw); SS.set_value(agent.state.dir, _env("CONN", cid, "KEY"), None)
    wf = _workflow_file(agent); changed = False
    for w in wf.get("workflows", []):
        if cid in (w.get("also_send_to") or []):
            w["also_send_to"] = [x for x in w["also_send_to"] if x != cid]; changed = True
            if not w["also_send_to"]:
                w.pop("also_send_to")
    if changed:
        p = agent.cfg["workflows"]; tmp = p + ".tmp"; json.dump(wf, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, p)
    _reload(agent); return connections(agent)


def test_connection(agent, cid):
    """Posts a small test message ({"test": true}) to your app and tells you what it answered. Only when asked."""
    c = next((x for x in agent.cfg.get("connections", []) if x.get("id") == cid), None)
    if not c:
        return {"ok": False, "message": "Save the connection first."}
    try:
        a = agent._with_connection({"action": "http", "connection": cid, "method": "POST", "json": {"test": True, "from": "speakvora-pack-agent", "message": "Test from your voice bundle's agent."}})
        st, _r = web.request("POST", a["url"], a.get("headers"), body=a["json"], timeout=15)
        agent.state.data.setdefault("tested", {})["conn:" + cid] = int(agent.now()); agent.state.save()
        return {"ok": True, "message": f"Your app answered ({st}). The connection works."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": _explain(e)}


def add_incoming(agent, name, origin=""):
    slug = "custom-" + _slug(name); env = _env("HOOK", slug, "TOKEN"); store = SS.read(agent.state.dir)
    if not store.get(env):
        SS.set_value(agent.state.dir, env, _rnd.token_hex(20))
    raw = _raw(agent)
    src = {"name": slug, "path": "/hook/" + slug, "auth": {"type": "bearer", "token": "env:" + env},
           "map": {"event": "payload.event", "id": "payload.id", "customer.name": "payload.customer.name", "customer.phone": "payload.customer.phone", "customer.email": "payload.customer.email",
                   "customer.sms_consent": {"from": "payload.customer.sms_consent", "default": False}, "order.number": "payload.order.number", "appointment.time": "payload.appointment.time", "party": "payload.party", "data": "payload"}}
    origin = str(origin or "").strip().rstrip("/")
    if re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d+)?", origin):                 # a website whose visitors' browsers may post here directly (an error report from your own page)
        src["origins"] = [origin]
    raw["sources"] = [x for x in raw.get("sources", []) if x.get("name") != slug] + [src]; _write_raw(agent, raw); _reload(agent)
    return {"id": slug, "url": _public_or_local(agent) + src["path"], "token": SS.read(agent.state.dir)[env]}


def incoming_token(agent, cid):
    if not str(cid).startswith("custom-"):
        raise SetupError("Unknown connection.")
    t = SS.read(agent.state.dir).get(_env("HOOK", cid, "TOKEN"))
    if not t:
        raise SetupError("Unknown connection.")
    return {"id": cid, "url": _public_or_local(agent) + "/hook/" + cid, "token": t, "events": sorted({(w.get("on") or {}).get("event") for w in _workflow_file(agent).get("workflows", []) if (w.get("on") or {}).get("event")})}


def remove_incoming(agent, cid):
    if not str(cid).startswith("custom-"):
        raise SetupError("Unknown connection.")
    raw = _raw(agent); raw["sources"] = [x for x in raw.get("sources", []) if x.get("name") != cid]; _write_raw(agent, raw); SS.set_value(agent.state.dir, _env("HOOK", cid, "TOKEN"), None); _reload(agent)
    return connections(agent)


def set_workflow_targets(agent, name, ids):
    ok = {c["id"] for c in _raw(agent).get("connections", [])}; ids = [i for i in (ids or []) if i in ok]
    wf = _workflow_file(agent); hit = False
    for w in wf.get("workflows", []):
        if w["name"] == name:
            if ids:
                w["also_send_to"] = ids
            else:
                w.pop("also_send_to", None)
            hit = True
    if not hit:
        raise SetupError("No such workflow.")
    p = agent.cfg["workflows"]; open(p + ".bak", "w", encoding="utf-8").write(open(p, encoding="utf-8").read()); tmp = p + ".tmp"; json.dump(wf, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, p); agent._load_workflows()
    return workflows(agent)


def catalog(agent):
    """Everything the + Add connection button offers."""
    have = {c["name"] for c in status_cards(agent)}
    short = {"slack": "Tell your team and use slash commands", "teams": "Post to a Teams channel", "atlassian": "Report bugs to Jira and keep a Confluence page", "twilio": "Send texts and make calls", "address": "A fixed web address for your agent, free", "sip": "Keep your number, connect your phone system, no Twilio", "android_sms": "Texts from your own phone, no Twilio", "telegram": "Answer customers on Telegram", "whatsapp": "Answer WhatsApp messages (Meta)", "calendar": "Reminders from your bookings", "email": "Send email from your mailbox", "ai": "Let it think, with your own key", "account": "Pair with a code to voice new lines"}
    tiles = [{"id": n, "kind": "service", "name": t, "blurb": short[n], "added": connected(agent, n)} for n, t in (("slack", "Slack"), ("teams", "Microsoft Teams"), ("atlassian", "Jira and Confluence"), ("twilio", "Texts and calls (Twilio)"), ("address", "Permanent address"), ("sip", "Use my existing business number"), ("android_sms", "Your Android phone (texts)"), ("telegram", "Telegram"), ("whatsapp", "WhatsApp Business"), ("calendar", "Google or Outlook calendar"), ("email", "Email"), ("ai", "AI reasoning (your own key)"), ("account", "Speakvora agent"))]
    tools = {"shopify": "Shopify", "github": "GitHub", "gitlab": "GitLab", "pagerduty": "PagerDuty", "stripe": "Stripe", "calendly": "Calendly", "jira": "Jira ticket updates", "generic-pos": "Point of sale", "pos": "Point of sale"}
    for s in sources(agent):
        seen = (agent.state.data.get("tool_seen") or {}).get(s["name"])
        tiles.append({"id": s["name"], "kind": "tool", "name": tools.get(s["name"], s["name"].title()), "added": s["added"],
                      "blurb": (("Last message " + time.strftime("%b %d, %H:%M", time.localtime(seen))) if seen else "Waiting for the first message") if s["added"] else "Start workflows when something happens"})
    tiles.append({"id": "custom_out", "kind": "custom_out", "name": "Send to my own app", "blurb": "Post to your app's web address", "added": False})
    tiles.append({"id": "custom_in", "kind": "custom_in", "name": "Let my app send events here", "blurb": "An address your app, Zapier or Make can post to", "added": False})
    return tiles


def status_cards(agent):
    return [{"name": n} for n in CARDS]


# ---- every setup step is written to the local setup log (see setuplog.py): what was saved (field names only), what each test said, and what a channel connection returned
def _wrap(name, kind, describe):
    fn = globals()[name]
    def wrapper(agent, *a, **k):
        from . import setuplog
        try:
            out = fn(agent, *a, **k)
        except Exception as e:  # noqa: BLE001
            setuplog.record(agent, kind, **describe(a, k), ok=False, error=f"{type(e).__name__}: {str(e)[:200]}"); raise
        res = out if isinstance(out, dict) else {}
        setuplog.record(agent, kind, **describe(a, k), ok=res.get("ok", True) if kind == "test" else True, **({"message": str(res.get("message", ""))[:200]} if kind in ("test", "channel_connect") else {}))
        return out
    wrapper.__name__ = name; globals()[name] = wrapper
_wrap("save", "save", lambda a, k: {"card": a[0] if a else k.get("card"), "fields": sorted((a[1] if len(a) > 1 else k.get("values") or {}).keys())})
_wrap("test", "test", lambda a, k: {"card": a[0] if a else k.get("card")})
_wrap("channel_connect", "channel_connect", lambda a, k: {"card": a[0] if a else k.get("card")})
_wrap("disconnect", "disconnect", lambda a, k: {"card": a[0] if a else k.get("card")})
_wrap("go_live", "go_live", lambda a, k: {"on": bool(a[0] if a else k.get("on"))})


# ---- guided setup for "Use my existing business number": what each phone system needs, a message for the phone admin, a live checklist and plain-words problems
COMPAT = {"encrypted_untested": "Encrypted calls supported, not tested with this system", "tested": "Tested", "likely": "Should work", "relay": "Works on the office network; remote use needs a relay", "encrypted": "Not supported yet (needs encrypted calls)", "unknown": "Not checked"}
PROVIDERS = {
    "asterisk": {"name": "Asterisk or FreePBX", "compat": "tested", "where": "FreePBX: Applications, Extensions, Add Extension, Add New SIP [chan_pjsip] Extension. Asterisk: add an endpoint, auth and aor named after the extension in pjsip.conf.",
                 "route": "FreePBX: use a Time Condition for after hours, or a Ring Group / Queue with a no-answer destination that is the agent extension. Always set a failover destination to a person or voicemail.",
                 "notes": "The extension's name must be its number (for example 999) or sign-in is refused. We tested the agent against Asterisk."},
    "3cx": {"name": "3CX", "compat": "relay", "where": "Extensions, Add, give it a number and name. Open the extension's Phone Provisioning tab to read the SIP ID and password.",
            "route": "Use an office-hours rule, a ring group with a no-answer destination, or Digital Receptionist to send calls to the extension. Set the no-answer destination to a person or voicemail.",
            "notes": "A third-party SIP client on the same network as the 3CX server can register with those details. Away from that network 3CX normally needs its SBC (a small relay program) or a public address with ports forwarded, which a plain extension cannot replace."},
    "ringcentral": {"name": "RingCentral", "compat": "likely", "where": "Admin Portal, Phone System, Phones & Devices, Add Phone, choose Other or third-party phone. RingCentral then shows the SIP domain, outbound proxy, SIP ID (user name), authorization ID and password.",
                    "route": "Use call handling rules (business hours, after hours) or a call queue with an overflow destination that is the agent extension. Keep a person or voicemail as the final failover.",
                    "notes": "RingCentral may restrict which devices can register, and some plans or devices need RingCentral support to enable third-party registration. Ask them for SIP credentials for a third-party phone using UDP."},
    "zoom": {"name": "Zoom Phone", "compat": "encrypted_untested", "where": "Zoom accepts third-party SIP devices only with encrypted signaling (TLS 1.2) and encrypted audio (SRTP), and Zoom support must enable it for your account. Zoom then shows a user name, authorization ID, password and outbound proxy (usually port 5091).",
             "route": "Use Zoom's call handling (business hours, after hours or overflow) to send calls to that user, and keep a person as the failover.", "preset": {"transport": "tls", "srtp": "required", "server_port": "5091"},
             "notes": "The agent speaks encrypted SIP (TLS) and encrypted audio (SRTP), which Zoom requires. We have not tested it against Zoom Phone itself, so treat the first connection as a pilot."},
    "8x8": {"name": "8x8", "compat": "unknown", "where": "Ask 8x8 for SIP credentials for a third-party phone (server, user name, authorization name, password) over UDP.",
            "route": "Use your auto-attendant or ring group overflow to send calls to that extension and keep a person as the failover.", "notes": "Not individually tested. Ask the provider whether third-party devices are allowed on your plan."},
    "ooma": {"name": "Ooma", "compat": "unknown", "where": "Ask Ooma whether your plan allows a third-party SIP device and for its credentials over UDP.",
             "route": "Route unanswered or after-hours calls to that extension and keep a person as the failover.", "notes": "Not individually tested."},
    "vonage": {"name": "Vonage Business", "compat": "unknown", "where": "Ask Vonage for SIP credentials for a third-party phone (server, user name, password) over UDP.",
               "route": "Use call forwarding rules or a ring group overflow to send calls to the extension and keep a person as the failover.", "notes": "Not individually tested."},
    "telnyx": {"name": "Telnyx", "compat": "likely", "where": "Telnyx portal: SIP Connections, create a Credential connection and note the user name and password. The agent signs in to sip.telnyx.com.",
               "route": "Assign your number to that connection, or forward unanswered calls to it, and keep a person as the failover.", "notes": "Use UDP and G.711 (PCMU or PCMA) and turn off encrypted media for this connection."},
    "other": {"name": "Another SIP phone system", "compat": "unknown", "where": "Create a plain SIP extension (a desk-phone style extension) and note the server, user name, authorization name and password.",
              "route": "Send the calls you choose (after hours, unanswered, or a queue overflow) to that extension and keep a person as the failover.", "notes": "Needs UDP SIP and G.711 audio without encryption."},
    "unsure": {"name": "Not sure yet", "compat": "unknown", "where": "Ask whoever pays your phone bill or set up your phones: \"Who provides our phone service, and can they give us a third-party SIP extension?\" Use Copy message for my phone admin below.",
               "route": "", "notes": "If your phones are plain mobile numbers with no phone system, use the Android phone or Telegram for messages and see the guide for calls."},
}


def _local_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("203.0.113.1", 9)); return s.getsockname()[0]
    except OSError:
        return "this computer's address"
    finally:
        s.close()


def sip_providers():
    return [{"id": k, "name": v["name"], "compat": v["compat"], "compat_text": COMPAT[v["compat"]], "where": v["where"], "route": v["route"], "notes": v["notes"], "preset": v.get("preset") or {}} for k, v in PROVIDERS.items()]


def sip_admin_message(agent, provider):
    """A plain message the owner can paste to the person who runs the phone system."""
    pr = PROVIDERS.get(provider) or PROVIDERS["other"]; cfg = agent.cfg.get("sip") or {}; biz = agent.cfg.get("business") or "our business"
    when = {"unanswered": "calls nobody answers", "after_hours": "calls outside business hours", "all": "every incoming call"}.get(cfg.get("answer_when"), "the calls we choose")
    lines = [f"Hi, we are setting up an automated voice assistant for {biz} that answers calls on our existing phone system. It needs one dedicated SIP extension. Could you set it up and send me the details below?", "",
             f"Phone system: {pr['name']}", "", "1. Create a new extension for it:", f"   {pr['where']}", "",
             "2. Use these settings: transport UDP port 5060 (no TLS), audio G.711 u-law (PCMU) or A-law (PCMA) with no audio encryption, DTMF as RFC 2833 or SIP INFO, one concurrent call is enough to start, allow it to place transfers (SIP REFER).",
             "", f"3. Send it {when}:", f"   {pr['route'] or 'Route the calls we choose to that extension.'}",
             "   Please also set a failover: if the extension does not answer within about 15 seconds, the call should ring a person or go to voicemail. This protects us if the computer is off.", "",
             "4. Network: the assistant runs on a computer in our office at " + _local_ip() + ". If the phone system is in the cloud or on another network, please allow UDP traffic between them on port 5060 and UDP ports 40000 to 40200.", "",
             "5. Please send me back: the server address, the port, the extension number, the authorization name if it differs, and the password."]
    if pr["notes"]:
        lines += ["", "Notes: " + pr["notes"]]
    return "\n".join(lines)


SIP_PROBLEMS = {
    "login_refused": ("Phone sign-in rejected", "The phone system refused the extension's user name or password. Re-copy the SIP password (not the admin password). RingCentral and Zoom also need the authorization name."),
    "no_response": ("Can't reach your phone system", "Nothing answered at that address and port. Check the address for typos, that this computer is on the same network (or can reach it), and that a firewall is not blocking UDP 5060."),
    "cannot_send": ("This computer can't send to the phone system", "The network refused the connection. Check the address and that the computer is online."),
    "key_refused": ("Speech recognition key refused", "Speakvora did not accept the API key, so callers can use the keypad but not speak. Check the key under Connect, Speakvora agent."),
    "free_minutes_used": ("Free speech minutes used", "Your free speech-to-text minutes are used up, so callers can use the keypad but not speak. Add credit in your Speakvora account to turn speaking back on."),
    "stt_unavailable": ("Speech recognition didn't answer", "Speakvora could not turn the caller's words into text just now. Callers can still use the keypad; the agent will try again on the next call."),
    "tls_certificate": ("The phone system's certificate isn't trusted", "The encrypted connection was refused because this computer does not trust the phone system's certificate. Ask your phone admin for the certificate file and put its path in Certificate file, or choose the not encrypted connection if your system allows it."),
    "tls_failed": ("Encrypted connection failed", "The phone system did not complete the encrypted (TLS) connection. Check the address and port (usually 5061 or 5091 for encrypted), and that your phone system allows encrypted extensions."),
    "connection_lost": ("Connection to the phone system was lost", "The agent is reconnecting by itself. If this keeps happening, check this computer's network and ask your phone admin whether the system closes idle connections."),
    "no_inbound_audio": ("Caller audio isn't reaching your computer", "The call connected but no audio came in. First say a few words during the test call, because some phone systems send nothing while the caller is silent. If it still fails, open UDP ports 40000 to 40200 to this computer, or set This computer's public IP in the card if your phone system is in the cloud and this computer is behind a router."),
}


def sip_status(agent):
    """The live checklist for the setup wizard: each item says whether it is proven, and the first problem is explained in plain words (technical details kept apart for the phone admin)."""
    s = agent.sip; cfg = agent.cfg.get("sip") or {}; configured = bool(s.configured)
    live = [{"t": int(x.started), "secs": int(time.time() - x.started), "audio_in": x.rx_audio, "audio_out": x.tx, "keys": x.digit_count, "transferred": x.transferred, "problem": x.problem, "caller": x.caller[-4:].rjust(4, "*"), "live": True} for x in list(s.calls.values())]
    calls = list(s.history) + live; last = calls[-1] if calls else None; tested_ok = [h for h in calls if h["audio_in"] > 0 and h["audio_out"] > 0]
    ok_ts = (agent.state.data or {}).get("sip_test_ok") or (tested_ok[-1]["t"] if tested_ok else 0)
    facts = agent.cfg.get("facts") or {}; fallback = bool(str(cfg.get("fallback_number") or "").strip() or _real(facts.get("oncall_phone")))
    items = [{"id": "online", "label": "Agent online", "ok": bool(s.running), "detail": "" if s.running else "The agent's web server is not running."},
             {"id": "signed_in", "label": "Phone system signed in", "ok": bool(s.registered), "detail": "" if s.registered else (s.error or "Not signed in yet.")},
             {"id": "call", "label": "Test call received", "ok": bool(last or ok_ts), "detail": "Call your business number now." if not (last or ok_ts) else ""},
             {"id": "audio", "label": "Audio works both ways", "ok": bool(ok_ts), "detail": "" if ok_ts else ("Caller audio did not arrive." if last and last["audio_in"] == 0 else "Waiting for a test call.")},
             {"id": "keys", "label": "Keypad press registered", "ok": any(h["keys"] > 0 for h in calls) or bool((agent.state.data or {}).get("sip_keys_ok")), "detail": "Press a menu key during the test call.", "optional": True},
             {"id": "transfer", "label": "Transfer to staff attempted", "ok": any(h["transferred"] for h in calls) or bool((agent.state.data or {}).get("sip_transfer_ok")), "detail": "Press 0 during a test call.", "optional": True},
             {"id": "speech", "label": "Callers can speak", "ok": bool((agent.state.data or {}).get("sip_speech_ok")), "optional": True,
              "detail": ("Add your Speakvora key (Connect, Speakvora agent) so callers can say what they need." if not s.speech_ok(agent) else "Say \"what are your hours\" during a test call.")},
             {"id": "fallback", "label": "Backup for when the agent can't answer", "ok": fallback, "detail": "" if fallback else "Add a staff number below, and set a no-answer rule in your phone system."}]
    code = ""
    if configured and not s.registered and s.err_code:
        code = s.err_code
    elif last and last.get("problem"):
        code = last["problem"]
    elif configured and getattr(s, "stt_error", ""):
        code = s.stt_error
    problem = None
    if code in SIP_PROBLEMS:
        problem = {"code": code, "title": SIP_PROBLEMS[code][0], "fix": SIP_PROBLEMS[code][1], "tech": s.error or code}
    ready = configured and bool(s.registered) and bool(ok_ts) and fallback
    first_missing = next((i["label"] for i in items if not i["ok"] and not i.get("optional")), "")
    return {"configured": configured, "ready": ready, "summary": "Ready: your business number is connected." if ready else ("Not ready: " + first_missing if first_missing else "Not ready"), "items": items, "problem": problem,
            "last_call": last, "last_test": ok_ts, "provider": cfg.get("provider") or "", "mode": cfg.get("answer_when") or ""}
