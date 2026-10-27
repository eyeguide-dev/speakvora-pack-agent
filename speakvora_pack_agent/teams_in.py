"""Two-way Microsoft Teams through an Outgoing Webhook: the team @mentions the bot in a channel, Teams posts the message (signed) to POST /teams/messages, and the answer is the JSON we return.

Teams signs the raw body with HMAC-SHA256 using the base64 security token it showed the owner once, and sends `Authorization: HMAC <base64 digest>`.
What people write goes through the same bug-desk logic the Slack replies use (bugdesk.handle), so notes, status moves, approval and the close rules behave identically:
close and reopen still wait for approval unless guardrails.bug_close says otherwise, and private details are redacted before anything reaches Jira.
Who may talk: teams.allow (display names or emails, any case). An empty list means anyone who can @mention the bot in that channel.
Secrets and message bodies are never written to the log.
"""
import base64, hashlib, hmac, html, re, time
from datetime import datetime

from . import bugdesk

KEY = bugdesk.KEY
MAX_AGE = 900                                      # a signed message older than this is a replay
HELP = "Tell me which ticket: write its key, for example KAN-17 fixed: the key was renewed. Once you name a ticket in a thread, later messages in that thread need no key."


def sign(secret, raw):
    """The Authorization header value Teams would send for this body (also used by the self-test and the tests)."""
    return "HMAC " + base64.b64encode(hmac.new(_key(secret), raw, hashlib.sha256).digest()).decode()


def _key(secret):
    try:
        return base64.b64decode(str(secret), validate=True)
    except ValueError:
        return str(secret).encode()


def verify(secret, raw, header):
    """True only for a non-empty secret and an exact HMAC match (constant-time compare)."""
    h = str(header or "").strip()
    if not secret or not h[:5].upper() == "HMAC ":
        return False
    return hmac.compare_digest(sign(secret, raw).encode(), ("HMAC " + h[5:].strip()).encode())


def strip_mentions(text):
    """The message without the <at>BotName</at> mention, other markup and extra spaces."""
    t = re.sub(r"<at>.*?</at>", " ", str(text or ""), flags=re.I | re.S)
    t = re.sub(r"<br\s*/?>|</p>|</div>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t).replace("\xa0", " ")).strip()


def _fresh(ts):
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return True
    return abs(time.time() - t) <= MAX_AGE


def _reply(text):
    return 200, {"type": "message", "text": text}


class _Reply:
    """Stands in for the Slack client while the bug desk runs, collecting what it would have posted in the thread."""
    token = "teams"

    def __init__(self):
        self.said = []

    def post(self, text, channel=None, thread=None):
        self.said.append(text)
        return {}


class _Desk:
    """The agent as bugdesk.handle sees it: everything real, except that `slack` collects the answer to send back to Teams."""
    def __init__(self, agent, slack):
        self.__dict__["_a"], self.__dict__["slack"] = agent, slack

    def __getattr__(self, n):
        return getattr(self._a, n)


def allowed(agent, sender):
    allow = agent.teams.allow
    if not allow:
        return True
    return any(str(v or "").strip().lower() in allow for v in (sender.get("name"), sender.get("email"), sender.get("userPrincipalName")))


def _remember(agent, conv, key):
    if not (conv and key):
        return
    with agent.state.lock:
        t = agent.state.data.setdefault("bug_threads", {}); t[f"teams:{conv}"] = key
        while len(t) > 300:
            t.pop(next(iter(t)))
        agent.state.save()


def handle(agent, raw, header):
    """One request from Teams. Returns (http status, json body). 401 only for a missing or wrong signature; anything else is answered as a Teams message."""
    secret = agent.teams.outgoing_secret
    if not verify(secret, raw, header):
        agent.state.log(workflow="inbound_teams", status="rejected", reason="bad_signature" if header else "no_signature")
        return 401, {"error": "bad_signature"}
    try:
        act = __import__("json").loads(raw or b"{}")
        if not isinstance(act, dict) or act.get("type", "message") != "message":
            return _reply("I only read messages.")
        if act.get("timestamp") and not _fresh(act["timestamp"]):
            agent.state.log(workflow="inbound_teams", status="rejected", reason="too_old"); return 401, {"error": "too_old"}
        sender = act.get("from") or {}; conv = str((act.get("conversation") or {}).get("id") or "")
        text = strip_mentions(act.get("text"))
        if text.lower().strip(" .!") == "ping":
            return _reply("Pong. Speakvora is listening.")
        if not allowed(agent, sender):
            agent.state.log(workflow="inbound_teams", status="rejected", reason="not_allowed")
            return _reply("Sorry, you are not on the list of people who may change tickets from Teams. Ask the owner to add you (teams.allow in agent.json).")
        if not text:
            return _reply(HELP)
        mid = str(act.get("id") or act.get("replyToId") or hashlib.sha256(raw).hexdigest())
        bugs = agent.state.data.get("jira_bugs") or {}; known = {v.get("key") for v in bugs.values() if v.get("key")}
        named = next((k for k in KEY.findall(text) if k in known), None)
        if named:
            _remember(agent, conv, named)                                   # the thread now belongs to that ticket, so "approve" and notes need no key
        out = _Reply()
        payload = {"type": "event_callback", "event_id": "teams:" + mid,
                   "event": {"type": "message", "channel": "teams", "user": str(sender.get("id") or ""), "text": text, "ts": mid, **({"thread_ts": conv} if conv else {})}}
        res = bugdesk.handle(_Desk(agent, out), payload)
        agent.state.log(workflow="inbound_teams", status="handled", ticket=res.get("ticket", ""), result=res.get("action") or res.get("ignored") or "")
        return _reply(_words(agent, res, out.said))
    except Exception as e:  # noqa: BLE001 - a bad message must not break the server or leak internals
        agent.state.log(workflow="inbound_teams", status="error", error=type(e).__name__)
        return _reply("Something went wrong on my side; nothing was changed.")


def _words(agent, res, said):
    ign = res.get("ignored")
    if ign == "no_bug":
        return HELP
    if ign == "jira_not_connected":
        return "Jira is not connected to this agent yet, so I cannot update tickets."
    if ign == "seen":
        return "Already handled that message."
    if res.get("error"):
        return "Something went wrong on my side; nothing was changed."
    if said:
        return " ".join(said) + (" (Answer with @mention.)" if "Reply approve" in " ".join(said) else "")
    k, a = res.get("ticket", ""), res.get("action", "")
    if agent.dry:
        return f"Practice mode: I understood this for {k} ({a}) but changed nothing."
    return {"note": f"Added your note to {k}."}.get(a, f"Done for {k}.")


def selftest(agent):
    """Signs a sample with the saved token and sends it to this agent's own handler (no network). Proves the token is saved and the route answers; changes nothing."""
    if not agent.teams.outgoing_secret:
        return {"ok": False, "message": "Paste the outgoing webhook security token first and press Save."}
    raw = __import__("json").dumps({"type": "message", "id": "selftest-" + str(int(time.time() * 1000)), "text": "<at>Speakvora</at> ping", "from": {"name": "Speakvora self-test"}, "conversation": {"id": "selftest"}}).encode()
    code, body = handle(agent, raw, sign(agent.teams.outgoing_secret, raw))
    refuses = not verify(agent.teams.outgoing_secret, raw, sign(agent.teams.outgoing_secret + "x", raw))
    base = str(agent.cfg.get("public_base_url") or "").rstrip("/")
    where = f"Teams must call {base}/teams/messages." if base.startswith("https://") and "YOUR-PUBLIC" not in base else "Set a permanent public https address first (Connect, Permanent address), then use it plus /teams/messages."
    if code == 200 and "Pong" in str(body.get("text")) and refuses:
        return {"ok": True, "message": "The agent accepted a correctly signed sample and refused a wrong one. " + where}
    return {"ok": False, "message": "The self-test did not pass. Save the token again."}
