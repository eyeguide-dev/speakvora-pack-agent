"""A tiny dashboard for ONE agent, served by the agent itself (standard library, no external files, nothing leaves your machine): what it is waiting to send, what needs you, how complete the bundle is,
and a form to ask Speakvora for more lines. Open the address printed at start-up; the access token is in the part after # so it is never sent to a server and never logged.
Routes: GET /dashboard (the page), GET /dash/api/summary, GET /dash/api/jobs?status=, POST /dash/api/jobs/<id>/<cancel|retry|mark-sent>, POST /dash/api/pause {"on": true|false}, POST /dash/api/phrases {"slots": [...]} or {"custom": {...}}.
Every /dash/api call needs the header x-dashboard-token (env SV_DASHBOARD_TOKEN, or the random token kept in agent-state/dashboard-token). Pause = the kill switch file STOP."""
import hmac, json, os, re, secrets, time, urllib.request
from urllib.parse import parse_qs, urlparse

from . import brain as BR, connect as SU, guardrails as GR, locations as LC, recipes, sharing, slots as SL

CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
ATTENTION = ("needs_approval", "proposed", "needs_review", "failed", "expired", "undelivered")


def token(agent):
    env = os.environ.get("SV_DASHBOARD_TOKEN", "").strip()
    if env:
        return env
    p = os.path.join(agent.state.dir, "dashboard-token")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    t = secrets.token_hex(16)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t)
    return t


def _gaps(agent):
    """Lines the workflows use that the pack cannot say yet: [{'slot','intent','example'}]."""
    reg = SL.registry(agent.profile)
    want = SL.needed_by(json.load(open(agent.cfg["workflows"], encoding="utf-8"))) if agent.cfg.get("workflows") else set()
    return [{"slot": k, **reg[k]} for k in sorted(want) if k in reg and k not in agent.pack.slots]


def _requests_path(agent):
    return os.path.join(agent.state.dir, "phrase-requests.json")


def _requests(agent):
    try:
        return json.load(open(_requests_path(agent), encoding="utf-8"))
    except (OSError, ValueError):
        return []


KIND_LABEL = {"sms": "Text message", "call": "Phone call", "slack": "Slack message", "teams": "Teams message", "email": "Email", "calendar_create": "Calendar entry", "webhook": "Message to your app", "http": "Message to your app", "reason": "Suggestion from your AI"}
STATUS_LABEL = {"sent": "Sent", "delivered": "Delivered", "undelivered": "Not delivered", "queued": "Waiting for internet", "pending": "Sending", "sending": "Sending", "needs_approval": "Waiting for you", "proposed": "Waiting for you",
                "needs_review": "Please check", "failed": "Did not send", "blocked": "Held back by a safety rule", "expired": "Too old, not sent", "cancelled": "Stopped", "approved": "Approved", "answered": "Answered", "rejected": "Declined"}
TONE = {"sent": "good", "delivered": "good", "answered": "good", "approved": "good", "queued": "wait", "pending": "wait", "sending": "wait", "needs_approval": "you", "proposed": "you", "needs_review": "you", "failed": "bad", "undelivered": "bad", "blocked": "warn", "expired": "warn", "cancelled": "mute", "rejected": "mute"}
WHY = {"no_consent": "this person has not agreed to texts", "opted_out": "they replied STOP", "quiet_hours": "it is outside the allowed hours", "kill_switch": "sending is paused", "hourly_limit": "the hourly limit was reached", "recipient_daily_limit": "this person already got the daily maximum",
       "no_recipient": "there is no phone number or address", "reason_limit": "the AI limit for this hour was reached"}


def _person(j):
    a = j.get("a") or {}; c = (j.get("ctx") or {}).get("customer") or {}
    return str(c.get("name") or a.get("name") or a.get("to") or a.get("channel") or "").strip()


def _plain_error(e):
    e = str(e or "")
    if "HTTP 400" in e or "HTTP 4" in e:
        return "The service refused it. Check the connection in the Connect tab."
    if "HTTP 5" in e or "timed out" in e.lower():
        return "The service did not answer properly, so it may or may not have arrived."
    if "not set up" in e:
        return e
    return e[:160]


def _job(j):
    a = j.get("a") or {}
    kind = j["kind"]; who = _person(j); wfn = j["wf"]
    title = KIND_LABEL.get(kind, kind.replace("_", " ").capitalize()) + (f" to {who}" if who and kind in ("sms", "call", "email") else f" in {who}" if who and kind in ("slack", "teams") else "")
    detail = str(a.get("text") or a.get("subject") or a.get("title") or ("" if kind == "call" else ""))[:300]
    if kind == "call" and not detail:
        detail = "A call that plays your recording."
    why = WHY.get(j.get("reason") or "", "")
    friendly = {"title": title, "quote": detail, "label": STATUS_LABEL.get(j["status"], j["status"]) + (f": {why}" if j["status"] == "blocked" and why else ""), "tone": TONE.get(j["status"], "mute"),
                "what": recipes.NICE.get(wfn, ""), "workflow_title": wfn.replace("_", " ").capitalize(), "problem": _plain_error(j.get("error")) if j["status"] in ("failed", "needs_review", "undelivered") else "",
                "needs_you": j["status"] in ("needs_approval", "proposed", "needs_review", "failed", "expired", "undelivered")}
    extra = dict(friendly)
    if j["kind"] == "reason" and j.get("result"):
        r = j["result"]
        extra.update({"summary": r.get("summary", ""), "reasoning": r.get("reasoning", ""), "model": r.get("model", ""), "sent_chars": r.get("sent_chars", 0), "sent_to_model": r.get("sent_to_model", "")[:1500], "dropped": r.get("dropped", []),
                 "proposals": [{"i": i, "action": p["action"], "to": (p["args"].get("name") or p["args"].get("channel") or p["args"].get("url") or p["args"].get("title") or ""), "text": str(p["args"].get("text") or p["args"].get("json") or p["args"].get("subject") or "")[:400],
                                "why": p.get("why", ""), "state": p["state"], "status": p.get("status") or ""} for i, p in enumerate(r.get("proposals", []))]})
    return {**extra, "id": j["id"], "status": j["status"], "kind": j["kind"], "workflow": j["wf"], "to": str(a.get("to") or a.get("channel") or a.get("url") or "")[:60], "text": str(a.get("text") or a.get("subject") or a.get("title") or "")[:140],
            "created": j["created"], "updated": j["updated"], "attempts": j.get("attempts", 0), "error": (j.get("error") or "")[:200], "note": (j["history"][-1][2] if j.get("history") else "")}


def summary(agent):
    st = agent.state; gaps = _gaps(agent); jobs = st.jobs()
    att = [j for j in jobs if j["status"] in ATTENTION][-30:][::-1]
    svc = [n for n in ("twilio", "slack", "teams", "email", "calendar") if SU.connected(agent, n)]
    return {"setup": {"business": SU.connected(agent, "business"), "business_complete": bool(SU._real(agent.cfg.get("business")) and all(SU._real((agent.cfg.get("facts") or {}).get(k)) for k in ("hours", "address"))), "connected": len(svc), "services": svc, "ready": SU.readiness(agent)["ok"], "live": not agent.dry}, "update": sharing.update_info(agent), "now": int(agent.now()), "pack": {"title": agent.pack.meta.get("title"), "id": agent.pack.meta.get("pack"), "language": agent.pack.language, "lines": len(agent.pack.items), "profile": agent.profile, "version": agent.pack.meta.get("version")},
            "mode": "dry_run" if agent.dry else "live", "paused": agent.safe.killed(), "counts": st.job_counts(), "workflows": len(agent.workflows),
            "attention": [_job(j) for j in att], "recent": [_job(j) for j in jobs[-40:][::-1]],
            "coverage": {"needed": len(SL.needed_by(json.load(open(agent.cfg["workflows"], encoding="utf-8")))) if agent.cfg.get("workflows") else 0, "missing": gaps},
            "requests": _requests(agent)[-10:][::-1], "can_send_requests": bool(os.environ.get("SPEAKVORA_KEY")), "locations": LC.view(agent)}


CUSTOM_BAD = re.compile(r"https?://|@|\d{6,}")


def policy_view(agent):
    pol = agent.policy(); names = {"sms": "texts to customers", "call": "phone calls", "email": "emails", "slack": "Slack messages", "teams": "Teams messages", "http": "messages to your app", "calendar_create": "calendar entries"}
    dec = []
    for k, v in sorted(pol["decisions"].items()):
        wfn, _, act = k.partition(":")
        dec.append({"key": k, "workflow": wfn.replace("_", " ").capitalize(), "action": names.get(act, act), "choice": v})
    return {"ask_before": pol["ask_before"], "kinds": [{"kind": k, "label": n} for k, n in names.items() if k in ("sms", "call", "email")], "decisions": dec, "share_phrases": sharing.enabled(agent)}


def library_view(agent):
    s = summary(agent); pend = sharing.pending(agent); req = sharing.requested(agent)
    return {"coverage": s["coverage"], "pending": pend, "requested": [{"slot": k, "t": v} for k, v in sorted(req.items(), key=lambda x: -x[1])], "share": sharing.enabled(agent), "update": sharing.update_info(agent), "log": _requests(agent)[-8:][::-1], "now": int(agent.now())}


def request_phrases(agent, body):
    """Writes the request file and, when SPEAKVORA_KEY is set, sends it to Speakvora (the same call as `slots --send`). A custom line is a slot of your own: the moment it is said, and the sentence."""
    gaps = {g["slot"]: g for g in _gaps(agent)}
    if body.get("custom"):
        c = body["custom"]; intent, text = re.sub(r"\s+", " ", str(c.get("when", ""))).strip()[:160], re.sub(r"\s+", " ", str(c.get("text", ""))).strip()[:200]
        if len(intent) < 8 or len(text) < 8 or CUSTOM_BAD.search(intent + text):
            raise ValueError("Say when the line is used (at least 8 characters) and write the sentence you want (at least 8 characters, no links, emails or long numbers).")
        slot = "custom_" + re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:28].rstrip("_")
        picked = [{"slot": slot, "intent": intent, "example": text}]
    else:
        names = [str(s) for s in (body.get("slots") or [])]
        picked = [gaps[s] for s in names if s in gaps]
        if not picked:
            raise ValueError("Choose at least one missing line.")
    r = sharing.submit(agent, picked, picked[0]["example"] if body.get("custom") else "")
    return {"sent": r["sent"], "message": r["message"], "slots": [p["slot"] for p in picked]}


def handle(agent, method, path, headers, raw):
    """Returns (status, body bytes, content type, extra headers)."""
    u = urlparse(path); p = u.path
    hdr = {"content-security-policy": CSP, "x-content-type-options": "nosniff", "referrer-policy": "no-referrer", "cache-control": "no-store"}
    if p == "/dashboard" and method == "GET":
        return 200, PAGE.encode(), "text/html; charset=utf-8", hdr
    given = {k.lower(): v for k, v in headers.items()}.get("x-dashboard-token", "")
    if not hmac.compare_digest(given.encode(), token(agent).encode()):
        return 401, b'{"error":"bad_token"}', "application/json", hdr
    try:
        if p == "/dash/api/summary" and method == "GET":
            out = summary(agent)
        elif p == "/dash/api/jobs" and method == "GET":
            qs = parse_qs(u.query); s, k, q = (qs.get("status") or [""])[0], (qs.get("kind") or [""])[0], (qs.get("q") or [""])[0].lower()
            rows = [_job(j) for j in agent.state.jobs(s or None) if (not k or j["kind"] == k)]
            out = {"jobs": [j for j in rows if not q or q in (j["to"] + " " + j["workflow"] + " " + j["text"] + " " + j["kind"]).lower()][-300:][::-1]}
        elif method == "POST" and (m := re.match(r"^/dash/api/jobs/([\w:.\-]+)/(cancel|retry|mark-sent|approve|decline)$", p)):
            body = json.loads(raw or b"{}"); jid, act = m.group(1), m.group(2)
            if act == "approve":
                agent.approve_job(jid, bool(body.get("remember"))); agent.flush_outbox()
            elif act == "decline":
                agent.decline_job(jid, bool(body.get("remember")))
            else:
                j = agent.cancel_job(jid) if act == "cancel" else agent.retry_job(jid, bool(body.get("confirm_not_sent"))) if act == "retry" else agent.mark_job_sent(jid)
            if act == "retry":
                agent.flush_outbox()
            out = {"job": _job(agent.state.job_get(jid))}
        elif method == "POST" and (m2 := re.match(r"^/dash/api/proposals/([\w:.\-]+)/(approve|reject)$", p)):
            body = json.loads(raw or b"{}"); jid, act = m2.group(1), m2.group(2); idx = body.get("indexes")
            idx = [int(i) for i in idx] if isinstance(idx, list) else None
            if act == "approve":
                if idx is None:
                    jj = agent.state.job_get(jid); idx = [i for i, pr in enumerate(((jj or {}).get("result") or {}).get("proposals", [])) if pr["state"] == "pending"]
                agent.execute_proposals(jid, idx, bool(body.get("remember"))); agent.flush_outbox()
            else:
                agent.reject_proposals(jid, idx, bool(body.get("remember")))
            out = {"job": _job(agent.state.job_get(jid))}
        elif p == "/dash/api/setup" and method == "GET":
            out = SU.status(agent)
        elif p == "/dash/api/setup/save" and method == "POST":
            b = json.loads(raw or b"{}"); out = {"card": SU.save(agent, str(b.get("card", "")), b.get("values") or {})}
        elif p == "/dash/api/setup/test" and method == "POST":
            b = json.loads(raw or b"{}"); out = SU.test(agent, str(b.get("card", "")), b.get("opts") or {})
        elif p == "/dash/api/setup/workflow" and method == "POST":
            b = json.loads(raw or b"{}"); out = {"workflows": SU.set_workflow(agent, str(b.get("name", "")), bool(b.get("enabled")))}
        elif p == "/dash/api/setup/live" and method == "POST":
            out = SU.go_live(agent, bool(json.loads(raw or b"{}").get("on")))
        elif p == "/dash/api/setup/source" and method == "POST":
            out = SU.add_source(agent, str(json.loads(raw or b"{}").get("name", "")))
        elif p == "/dash/api/setup/catalog" and method == "GET":
            out = {"tiles": SU.catalog(agent), "connections": SU.connections(agent)}
        elif p == "/dash/api/setup/connection" and method == "POST":
            out = SU.add_connection(agent, json.loads(raw or b"{}"))
        elif p == "/dash/api/setup/connection/remove" and method == "POST":
            out = SU.remove_connection(agent, str(json.loads(raw or b"{}").get("id", "")))
        elif p == "/dash/api/setup/connection/test" and method == "POST":
            out = SU.test_connection(agent, str(json.loads(raw or b"{}").get("id", "")))
        elif p == "/dash/api/setup/incoming" and method == "POST":
            out = SU.add_incoming(agent, str(json.loads(raw or b"{}").get("name", "")))
        elif p == "/dash/api/setup/incoming/show" and method == "POST":
            out = SU.incoming_token(agent, str(json.loads(raw or b"{}").get("id", "")))
        elif p == "/dash/api/setup/incoming/remove" and method == "POST":
            out = SU.remove_incoming(agent, str(json.loads(raw or b"{}").get("id", "")))
        elif p == "/dash/api/setup/workflow-targets" and method == "POST":
            b = json.loads(raw or b"{}"); out = {"workflows": SU.set_workflow_targets(agent, str(b.get("name", "")), b.get("ids") or [])}
        elif p == "/dash/api/setup/public-check" and method == "POST":
            out = SU.check_public(agent)
        elif p == "/dash/api/policy" and method == "GET":
            out = policy_view(agent)
        elif p == "/dash/api/policy" and method == "POST":
            b = json.loads(raw or b"{}")
            if "ask_before" in b:
                agent.set_policy(ask_before=[str(x) for x in b["ask_before"]])
            if b.get("reset"):
                agent.set_policy(reset=str(b["reset"]))
            if isinstance(b.get("decision"), list) and len(b["decision"]) == 2:
                agent.set_policy(decision=(str(b["decision"][0]), str(b["decision"][1])))
            if "share_phrases" in b:
                sharing.set_enabled(agent, bool(b["share_phrases"]))
            out = policy_view(agent)
        elif p == "/dash/api/library" and method == "GET":
            out = library_view(agent)
        elif p == "/dash/api/library/share" and method == "POST":
            sharing.set_enabled(agent, bool(json.loads(raw or b"{}").get("on")))
            if sharing.enabled(agent):
                sharing.auto(agent)
            out = library_view(agent)
        elif p == "/dash/api/library/submit" and method == "POST":
            b = json.loads(raw or b"{}"); todo = [g for g in sharing.gaps(agent) if g["slot"] in (b.get("slots") or [])] or sharing.pending(agent)
            if not todo:
                raise ValueError("Nothing is missing.")
            r = sharing.submit(agent, todo[:60]); out = {**r, "library": library_view(agent)}
        elif p == "/dash/api/locations" and method == "GET":
            out = LC.status_all(agent)
        elif p == "/dash/api/licence" and method == "POST":
            out = {"locations": LC.set_licence(agent, json.loads(raw or b"{}").get("code"))}
        elif p == "/dash/api/locations/session" and method == "POST":
            hdr = {**hdr, "set-cookie": f"svloc={LC.session_cookie(token(agent))}; Path=/loc; HttpOnly; SameSite=Strict"}; out = {"ok": True}
        elif p == "/dash/api/locations/test" and method == "POST":
            b = json.loads(raw or b"{}"); out = LC.test(agent, b.get("url"), b.get("token"))
        elif p == "/dash/api/locations/add" and method == "POST":
            b = json.loads(raw or b"{}"); out = LC.add(agent, b.get("name"), b.get("url"), b.get("token"), bool(b.get("force")))
        elif p == "/dash/api/locations/remove" and method == "POST":
            out = {"locations": LC.remove(agent, str(json.loads(raw or b"{}").get("id", "")))}
        elif p == "/dash/api/locations/enable" and method == "POST":
            b = json.loads(raw or b"{}"); out = {"locations": LC.set_enabled(agent, bool(b.get("on")), b.get("this_name"))}
        elif p == "/dash/api/brain" and method == "GET":
            out = BR.load(agent) | {"configured": BR.configured(agent)}
        elif p == "/dash/api/brain/learn" and method == "POST":
            b = json.loads(raw or b"{}"); BR.start_learning_now(agent, str(b.get("website") or ""), str(b.get("notes") or "")); out = BR.load(agent) | {"configured": BR.configured(agent)}
        elif p == "/dash/api/brain/approve" and method == "POST":
            out = BR.approve(agent)
        elif p == "/dash/api/brain/save" and method == "POST":
            out = BR.edit(agent, json.loads(raw or b"{}").get("profile"))
        elif p == "/dash/api/brain/forget" and method == "POST":
            out = BR.forget(agent)
        elif p == "/dash/api/guardrails" and method == "GET":
            out = GR.view(agent)
        elif p == "/dash/api/guardrails" and method == "POST":
            rawc = SU._raw(agent); rawc["guardrails"] = GR.clean(json.loads(raw or b"{}")); SU._write_raw(agent, rawc); SU._reload(agent); out = GR.view(agent)
        elif p == "/dash/api/pause" and method == "POST":
            on = bool(json.loads(raw or b"{}").get("on")); f = os.path.join(agent.state.dir, "STOP")
            if on:
                open(f, "w").close()
            elif os.path.exists(f):
                os.remove(f)
            out = {"paused": agent.safe.killed()}
        elif p == "/dash/api/phrases" and method == "POST":
            out = request_phrases(agent, json.loads(raw or b"{}"))
        else:
            return 404, b'{"error":"not_found"}', "application/json", hdr
    except PermissionError as e:
        return 409, json.dumps({"error": "not_allowed", "message": str(e)}).encode(), "application/json", hdr
    except (ValueError, KeyError) as e:         # LocationError and SetupError are ValueErrors
        return 400, json.dumps({"error": "bad_request", "message": str(e)}).encode(), "application/json", hdr
    return 200, json.dumps(out).encode(), "application/json", hdr


from .ui import PAGE  # noqa: E402  (the page lives in ui.py)
