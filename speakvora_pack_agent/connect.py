"""The dashboard's Connect tab: set the agent up without editing JSON or setting environment variables, and see what is wrong in plain words.
Cards: Your business, Texts and calls (Twilio), Slack, Microsoft Teams, Google or Outlook calendar, Email, AI reasoning, then Go live. Each card saves to agent.json (a backup is kept) and secrets.json, applies at once (no restart),
and has a Test button that checks the connection and says what to fix. Secrets are never sent back to the page: only whether they are set and their last four characters.
Only the fields listed in CARDS can be written, so the page cannot change anything else in agent.json."""
import json, os, re, secrets as _rnd, smtplib, ssl, time
from urllib.parse import quote

from . import reasoner as R, secrets_store as SS, slots as SL, web
from .connectors.slack import Slack
from .connectors.teams import Teams

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
    "teams": {"title": "Microsoft Teams", "blurb": "Posts to a Teams channel. Text only.", "fields": [
        ("webhook_url", "Workflow / webhook URL", "secret", "teams.webhook_url", "TEAMS_WEBHOOK_URL", "In Teams: channel > Workflows > \"Post to a channel when a webhook request is received\", then copy its URL."),
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
SELECTS = {"provider": [("anthropic", "Claude (Anthropic)"), ("openai", "ChatGPT (OpenAI)"), ("local", "Another or local AI (needs a server address)")], "allow_create": [("", "Read only"), ("true", "Add, move, cancel and delete its own bookings")], "mode": [("strict", "Careful"), ("standard", "Normal"), ("open", "Open (no limits)")]}
# which card a workflow action needs
NEEDS = {"sms": "twilio", "call": "twilio", "slack": "slack", "teams": "teams", "notify": "slack", "email": "email", "calendar_create": "calendar", "calendar_reschedule": "calendar", "calendar_cancel": "calendar", "calendar_delete": "calendar", "reason": "ai"}
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
    if name == "slack":
        return bool(agent.slack.configured)
    if name == "teams":
        return bool(agent.teams.configured)
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


def status(agent):
    ensure_basics(agent); raw = _raw(agent); tested = agent.state.data.get("tested", {}); cards = []
    for name, card in CARDS.items():
        cards.append({"name": name, "title": card["title"], "blurb": card["blurb"], "connected": connected(agent, name), "tested": tested.get(name), "fields": [_field_view(agent, raw, name, f) for f in card["fields"]]})
    base = str(agent.cfg.get("public_base_url", "")).rstrip("/")
    listen = agent.cfg.get("listen") or {}
    return {"cards": cards, "workflows": workflows(agent), "readiness": readiness(agent), "live": not agent.dry, "event_url": (base if _real(base) else f"http://{listen.get('host', '127.0.0.1')}:{listen.get('port', 8787)}") + "/event",
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
    if not connected(agent, card) and card != "business":
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


def _kinds(w):
    out = set()
    def walk(o):
        if isinstance(o, dict):
            if "action" in o:
                out.add(o["action"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(w.get("do")); walk((w.get("on") or {}).get("call"))
    return out


def workflows(agent):
    from . import recipes
    out = []
    for w in _workflow_file(agent).get("workflows", []):
        needs = sorted({NEEDS[k] for k in _kinds(w) if k in NEEDS}); on = w.get("on") or {}
        trig = next((TRIGGER_WORDS[k] for k in TRIGGER_WORDS if k in on), "")
        out.append({"name": w["name"], "title": re.sub(r"\s+", " ", w["name"].replace("_", " ")).capitalize(), "what": recipes.NICE.get(w["name"], ""), "when": trig, "enabled": w.get("enabled", True), "also": w.get("also_send_to") or [], "needs": needs,
                    "missing": [n for n in needs if not connected(agent, n)]})
    return out


def set_workflow(agent, name, enabled):
    wf = _workflow_file(agent); hit = False
    for w in wf.get("workflows", []):
        if w["name"] == name:
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
    live_services = [n for n in ("twilio", "slack", "teams", "email", "calendar") if connected(agent, n)]
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
            "url": (base + src.get("path", "")) if public else "", "public": public, "where": g.get("where", ""), "steps": g.get("steps", []), "extra": g.get("extra", ""),
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
         "oauth_config": {"scopes": {"bot": ["chat:write", "files:write", "commands"]}},
         "settings": {"org_deploy_enabled": False, "socket_mode_enabled": False, "token_rotation_enabled": False}}
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


def add_incoming(agent, name):
    slug = "custom-" + _slug(name); env = _env("HOOK", slug, "TOKEN"); store = SS.read(agent.state.dir)
    if not store.get(env):
        SS.set_value(agent.state.dir, env, _rnd.token_hex(20))
    raw = _raw(agent)
    src = {"name": slug, "path": "/hook/" + slug, "auth": {"type": "bearer", "token": "env:" + env},
           "map": {"event": "payload.event", "id": "payload.id", "customer.name": "payload.customer.name", "customer.phone": "payload.customer.phone", "customer.email": "payload.customer.email",
                   "customer.sms_consent": {"from": "payload.customer.sms_consent", "default": False}, "order.number": "payload.order.number", "appointment.time": "payload.appointment.time", "party": "payload.party", "data": "payload"}}
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
    short = {"slack": "Tell your team and use slash commands", "teams": "Post to a Teams channel", "twilio": "Send texts and make calls", "calendar": "Reminders from your bookings", "email": "Send email from your mailbox", "ai": "Let it think, with your own key", "account": "Pair with a code to voice new lines"}
    tiles = [{"id": n, "kind": "service", "name": t, "blurb": short[n], "added": connected(agent, n)} for n, t in (("slack", "Slack"), ("teams", "Microsoft Teams"), ("twilio", "Texts and calls (Twilio)"), ("calendar", "Google or Outlook calendar"), ("email", "Email"), ("ai", "AI reasoning (your own key)"), ("account", "Speakvora agent"))]
    tools = {"shopify": "Shopify", "github": "GitHub", "gitlab": "GitLab", "pagerduty": "PagerDuty", "stripe": "Stripe", "calendly": "Calendly", "generic-pos": "Point of sale", "pos": "Point of sale"}
    for s in sources(agent):
        seen = (agent.state.data.get("tool_seen") or {}).get(s["name"])
        tiles.append({"id": s["name"], "kind": "tool", "name": tools.get(s["name"], s["name"].title()), "added": s["added"],
                      "blurb": (("Last message " + time.strftime("%b %d, %H:%M", time.localtime(seen))) if seen else "Waiting for the first message") if s["added"] else "Start workflows when something happens"})
    tiles.append({"id": "custom_out", "kind": "custom_out", "name": "Send to my own app", "blurb": "Post to your app's web address", "added": False})
    tiles.append({"id": "custom_in", "kind": "custom_in", "name": "Let my app send events here", "blurb": "An address your app, Zapier or Make can post to", "added": False})
    return tiles


def status_cards(agent):
    return [{"name": n} for n in CARDS]
