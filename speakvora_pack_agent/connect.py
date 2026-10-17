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
        ("hours", "Opening hours", "text", "facts.hours", None, "For example: Tue to Sun, 5 to 10 PM. Sent when someone texts \"hours\"."),
        ("address", "Address", "text", "facts.address", None, "Sent when someone texts \"where are you\"."),
        ("review_url", "Review link (optional)", "url", "facts.review_url", None, "Where happy customers are asked to leave a review."),
        ("oncall_phone", "Your own phone for urgent alerts (optional)", "text", "facts.oncall_phone", None, "Include the country code, for example +15551234567."),
        ("timezone", "Time zone", "select", "timezone", None, "Quiet hours and reminders use this."),
        ("mode", "How careful", "select", "mode", None, "Careful sends the fewest messages and keeps longer quiet hours. Normal is the default. Open removes the per-person and hourly limits (STOP replies and required notices stay on)."),
        ("public_base_url", "Public address of this agent (optional)", "url", "public_base_url", None, "Needed only for phone calls that play your recordings and for replies to inbound texts: a web address that reaches this machine, such as the one a tunnel service gives you."),
    ]},
    "twilio": {"title": "Texts and calls (Twilio)", "blurb": "Sends texts and places calls that play your recordings, from your own Twilio number. Twilio bills you directly.", "fields": [
        ("account_sid", "Account SID", "secret", "twilio.account_sid", "TWILIO_ACCOUNT_SID", "Twilio console > Account info. It starts with AC."),
        ("auth_token", "Auth token", "secret", "twilio.auth_token", "TWILIO_AUTH_TOKEN", "Twilio console > Account info > Auth token (click to show)."),
        ("from_number", "Your Twilio phone number", "text", "twilio.from_number", None, "With the country code, for example +15551234567."),
    ]},
    "slack": {"title": "Slack", "blurb": "Tells your team in Slack and lets staff use slash commands. A message needs the bot token; slash commands also need the signing secret and a public address.", "fields": [
        ("bot_token", "Bot token", "secret", "slack.bot_token", "SLACK_BOT_TOKEN", "Slack app > OAuth & Permissions > Bot User OAuth Token (starts with xoxb-). Or use a webhook below."),
        ("channel", "Channel", "text", "slack.channel", None, "For example #general. Invite the bot to the channel first."),
        ("webhook_url", "Webhook URL (instead of a bot token; text only)", "secret", "slack.webhook_url", "SLACK_WEBHOOK_URL", "Slack app > Incoming Webhooks."),
        ("signing_secret", "Signing secret (for slash commands)", "secret", "slack.signing_secret", "SLACK_SIGNING_SECRET", "Slack app > Basic Information > Signing Secret."),
    ]},
    "teams": {"title": "Microsoft Teams", "blurb": "Posts to a Teams channel. Text only.", "fields": [
        ("webhook_url", "Workflow / webhook URL", "secret", "teams.webhook_url", "TEAMS_WEBHOOK_URL", "In Teams: channel > Workflows > \"Post to a channel when a webhook request is received\", then copy its URL."),
    ]},
    "calendar": {"title": "Google or Outlook calendar", "blurb": "Reads your bookings to send reminders. Use your calendar's private link, no developer work needed.", "fields": [
        ("ics_url", "Private calendar link (iCal / ICS)", "secret", "google_calendar.ics_url", "CALENDAR_ICS_URL", "Google Calendar: Settings > your calendar > Integrate calendar > Secret address in iCal format. Outlook: Settings > Calendar > Shared calendars > Publish a calendar > ICS link."),
    ]},
    "email": {"title": "Email", "blurb": "Sends emails from your own mailbox. Gmail needs an app password, not your normal one.", "fields": [
        ("host", "Mail server", "text", "email.host", None, "Gmail: smtp.gmail.com. Outlook: smtp.office365.com."),
        ("port", "Port", "number", "email.port", None, "465 for Gmail; 587 for most others."),
        ("username", "Username", "text", "email.username", None, "Usually your full email address."),
        ("password", "Password or app password", "secret", "email.password", "EMAIL_PASSWORD", "Gmail: Google Account > Security > App passwords."),
        ("from", "Send from", "text", "email.from", None, "For example: Bella <hello@bella.com>."),
    ]},
    "ai": {"title": "AI reasoning (your own key)", "blurb": "Lets the agent think about requests the rules cannot handle. It only proposes; you approve in Activity. You pay your AI provider, we charge nothing, and only what a workflow chooses is sent.", "fields": [
        ("provider", "Which AI", "select", "reasoner.provider", None, "OpenAI-compatible covers OpenAI, Groq, Together, OpenRouter, Azure and others. Local keeps everything on this machine (for example Ollama)."),
        ("base_url", "Server address (leave empty for OpenAI or Anthropic)", "url", "reasoner.base_url", None, "Local example: http://localhost:11434/v1"),
        ("api_key", "Your API key", "secret", "reasoner.api_key", "AI_API_KEY", "From your AI provider's website. Not needed for a local model."),
        ("model", "Model name", "text", "reasoner.model", None, "The model you want to use, exactly as your provider names it."),
    ]},
}
SELECTS = {"provider": [("openai", "OpenAI-compatible (OpenAI, Groq, Together, OpenRouter...)"), ("anthropic", "Anthropic"), ("local", "Local model on this machine")], "mode": [("strict", "Careful"), ("standard", "Normal"), ("open", "Open (no limits)")]}
# which card a workflow action needs
NEEDS = {"sms": "twilio", "call": "twilio", "slack": "slack", "teams": "teams", "notify": "slack", "email": "email", "calendar_create": "calendar", "reason": "ai"}
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
    return False


def status(agent):
    ensure_basics(agent); raw = _raw(agent); tested = agent.state.data.get("tested", {}); cards = []
    for name, card in CARDS.items():
        cards.append({"name": name, "title": card["title"], "blurb": card["blurb"], "connected": connected(agent, name), "tested": tested.get(name), "fields": [_field_view(agent, raw, name, f) for f in card["fields"]]})
    base = str(agent.cfg.get("public_base_url", "")).rstrip("/")
    listen = agent.cfg.get("listen") or {}
    return {"cards": cards, "workflows": workflows(agent), "readiness": readiness(agent), "live": not agent.dry, "event_url": (base if _real(base) else f"http://{listen.get('host', '127.0.0.1')}:{listen.get('port', 8787)}") + "/event",
            "has_public": _real(base), "slack_manifest": slack_manifest(agent) if connected(agent, "business") or True else None, "sources": sources(agent)}


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
            SS.set_value(sd, env, val); _set(raw, path, "env:" + env); continue
        if kind == "number":
            if val and not val.isdigit():
                raise SetupError(f"{label} must be a number.")
            _set(raw, path, int(val) if val else None); continue
        if key in ("from_number", "oncall_phone") and val and not re.fullmatch(r"\+\d{8,15}", val.replace(" ", "")):
            raise SetupError(f"{label}: include the country code and digits only, for example +15551234567.")
        if key in ("review_url", "public_base_url", "base_url") and val and not re.match(r"^https?://[^\s]+$", val):
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
    if card == "calendar" and any(str(v).strip() for k, v in (values or {}).items() if k == "ics_url"):
        _set(raw, "google_calendar.mode", "ics")
    if card == "ai" and _get(raw, "reasoner.local") and not _get(raw, "reasoner.api_key"):
        pass
    _write_raw(agent, raw); _reload(agent)
    agent.state.data.get("tested", {}).pop(card, None); agent.state.save()
    return next(c for c in status(agent)["cards"] if c["name"] == card)


def _explain(e):
    if isinstance(e, web.NetworkDown):
        return "No internet connection from this machine right now."
    if isinstance(e, web.HttpError):
        if e.status in (401, 403):
            return "That was not accepted: check the key or token and try again."
        if e.status == 404:
            return "That address was not found: check it for typos."
        if e.status == 0:
            return "The server did not answer in time."
        return f"The service answered with an error ({e.status})."
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return "The mail server refused the username or password. For Gmail you need an app password."
    if isinstance(e, (smtplib.SMTPException, OSError, ssl.SSLError)):
        return "Could not reach the mail server: check the server name and port."
    return str(e)[:200] or "Something went wrong."


def test(agent, card, opts=None):
    """Checks a connection and answers in plain words. A test that sends something (a message, an email) says so on its button and only runs when asked (opts)."""
    opts = opts or {}
    if not connected(agent, card) and card != "business":
        return {"ok": False, "message": "Fill in this section and save it first."}
    try:
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
            now = time.time(); ev = agent._events(now - 86400, now + 7 * 86400)
            return _passed(agent, card, f"Calendar read: {len(ev)} event(s) in the next 7 days." + ("" if ev else " (An empty calendar is fine; check it is the right one.)"))
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


def readiness(agent):
    """What must be true before the agent sends for real."""
    wfs = workflows(agent); on = [w for w in wfs if w["enabled"]]; tested = agent.state.data.get("tested", {})
    live_services = [n for n in ("twilio", "slack", "teams", "email", "calendar") if connected(agent, n)]
    checks = [{"ok": connected(agent, "business"), "text": "Your business name is filled in."},
              {"ok": bool(live_services), "text": "At least one service is connected (texts and calls, Slack, Teams, email or calendar)."},
              {"ok": bool(live_services) and all(tested.get(n) for n in live_services), "text": "Every connected service passed its test."},
              {"ok": bool(on), "text": "At least one workflow is switched on."},
              {"ok": not [w for w in on if w["missing"] and set(w["missing"]) - {"ai"}], "text": "Every workflow that is switched on has what it needs connected (otherwise it will be skipped and logged)."}]
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
            s = json.load(open(os.path.join(d, f), encoding="utf-8")); out.append({"name": s["name"], "added": s["name"] in have, "path": s.get("path", "")})
    return out


def add_source(agent, name):
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sources", name + ".json")
    if not re.fullmatch(r"[a-z0-9\-]+", name) or not os.path.exists(d):
        raise SetupError("Unknown tool.")
    src = json.load(open(d, encoding="utf-8")); raw = _raw(agent)
    raw["sources"] = [x for x in raw.get("sources", []) if x.get("name") != src["name"]] + [src]; _write_raw(agent, raw); _reload(agent)
    return {"added": src["name"], "path": src.get("path"), "auth": (src.get("auth") or {}).get("secret") or (src.get("auth") or {}).get("token") or ""}


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
    short = {"slack": "Tell your team and use slash commands", "teams": "Post to a Teams channel", "twilio": "Send texts and make calls", "calendar": "Reminders from your bookings", "email": "Send email from your mailbox", "ai": "Let it think, with your own key"}
    tiles = [{"id": n, "kind": "service", "name": t, "blurb": short[n], "added": connected(agent, n)} for n, t in (("slack", "Slack"), ("teams", "Microsoft Teams"), ("twilio", "Texts and calls (Twilio)"), ("calendar", "Google or Outlook calendar"), ("email", "Email"), ("ai", "AI reasoning (your own key)"))]
    tools = {"shopify": "Shopify", "github": "GitHub", "gitlab": "GitLab", "pagerduty": "PagerDuty", "stripe": "Stripe", "calendly": "Calendly", "generic-pos": "Point of sale", "pos": "Point of sale"}
    for s in sources(agent):
        tiles.append({"id": s["name"], "kind": "tool", "name": tools.get(s["name"], s["name"].title()), "blurb": "Start workflows when something happens", "added": s["added"]})
    tiles.append({"id": "custom_out", "kind": "custom_out", "name": "Send to my own app", "blurb": "Post to your app's web address", "added": False})
    tiles.append({"id": "custom_in", "kind": "custom_in", "name": "Let my app send events here", "blurb": "An address your app, Zapier or Make can post to", "added": False})
    return tiles


def status_cards(agent):
    return [{"name": n} for n in CARDS]
