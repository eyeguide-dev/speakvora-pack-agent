"""A tiny dashboard for ONE agent, served by the agent itself (standard library, no external files, nothing leaves your machine): what it is waiting to send, what needs you, how complete the bundle is,
and a form to ask Speakvora for more lines. Open the address printed at start-up; the access token is in the part after # so it is never sent to a server and never logged.
Routes: GET /dashboard (the page), GET /dash/api/summary, GET /dash/api/jobs?status=, POST /dash/api/jobs/<id>/<cancel|retry|mark-sent>, POST /dash/api/pause {"on": true|false}, POST /dash/api/phrases {"slots": [...]} or {"custom": {...}}.
Every /dash/api call needs the header x-dashboard-token (env SV_DASHBOARD_TOKEN, or the random token kept in agent-state/dashboard-token). Pause = the kill switch file STOP."""
import hmac, json, os, re, secrets, time, urllib.request
from urllib.parse import parse_qs, urlparse

from . import audit as AU, simulate as SIM, builder as BD, activity as AC, knowledge as KN, converse as CVN, brain as BR, chat as CH, conversations as CVS, tracker as TK, controls as CT, learned as LN, connect as SU, guardrails as GR, locations as LC, recipes, sharing, slots as SL, phonemenu as PM, address as AD, wfedit as WE, sales as SA

CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; media-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
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


def remember_cookie(agent):
    return hmac.new(token(agent).encode(), b"svdash-remember", "sha256").hexdigest()


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


KIND_LABEL = {"sms": "Text message", "call": "Phone call", "slack": "Slack message", "teams": "Teams message", "jira_bug": "Jira bug", "confluence_log": "Confluence page", "email": "Email", "calendar_create": "Calendar entry", "calendar_reschedule": "Calendar entry moved", "calendar_cancel": "Calendar entry cancelled", "calendar_delete": "Calendar entry removed", "webhook": "Message to your app", "http": "Message to your app", "reason": "Suggestion from your AI"}
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


def _set_up_text(agent):
    from . import setuplog
    return setuplog.set_up_text(setuplog.timeline(agent))


def summary(agent):
    st = agent.state; gaps = _gaps(agent); jobs = st.jobs()
    att = [j for j in jobs if j["status"] in ATTENTION][-30:][::-1]
    svc = [n for n in ("twilio", "slack", "teams", "email", "calendar") if SU.connected(agent, n)]
    return {"setup": {"business": SU.connected(agent, "business"), "business_complete": bool(SU._real(agent.cfg.get("business")) and all(SU._real((agent.cfg.get("facts") or {}).get(k)) for k in ("hours", "address"))), "connected": len(svc), "services": svc, "account": SU.connected(agent, "account"), "ready": SU.readiness(agent)["ok"], "live": not agent.dry, "order_pages": SU.order_pages(agent)}, "update": sharing.update_info(agent), "now": int(agent.now()), "pack": {"title": agent.pack.meta.get("title"), "id": agent.pack.meta.get("pack"), "language": agent.pack.language, "lines": len(agent.pack.items), "profile": agent.profile, "version": agent.pack.meta.get("version")},
            "mode": "dry_run" if agent.dry else "live", "paused": agent.safe.killed(), "counts": st.job_counts(), "workflows": len(agent.workflows),
            "attention": [_job(j) for j in att], "recent": [_job(j) for j in jobs[-40:][::-1]],
            "coverage": {"needed": len(SL.needed_by(json.load(open(agent.cfg["workflows"], encoding="utf-8")))) if agent.cfg.get("workflows") else 0, "missing": gaps},
            "set_up_text": _set_up_text(agent),
            "requests": _requests(agent)[-10:][::-1], "can_send_requests": bool(sharing._key(agent)), "locations": LC.view(agent)}


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
    return {"sent": r["sent"], "message": r["message"], "slots": [p["slot"] for p in picked], "ready": r.get("ready", [])}


def jobs_for_display(agent):
    return [_job(j) for j in agent.state.jobs(None)][-300:][::-1]


VIEW_OK = ("/dash/api/quickstart", "/dash/api/summary", "/dash/api/setup/timeline", "/dash/api/jobs", "/dash/api/activity", "/dash/api/insights", "/dash/api/library", "/dash/api/learned", "/dash/api/phrases")


def handle(agent, method, path, headers, raw):
    """Returns (status, body bytes, content type, extra headers)."""
    u = urlparse(path); p = u.path
    hdr = {"content-security-policy": CSP, "x-content-type-options": "nosniff", "referrer-policy": "no-referrer", "cache-control": "no-store"}
    if p == "/dashboard" and method == "GET":
        # A browser that has already opened the dashboard once with its private token keeps a cookie (set by POST /dash/api/remember). From then on the page opens with no token in the address,
        # for example from the "Open my dashboard" button on speakvora.com. A browser without the cookie still needs the token.
        page = PAGE; ck = dict(c.strip().split("=", 1) for c in {k.lower(): v for k, v in headers.items()}.get("cookie", "").split(";") if "=" in c)
        if hmac.compare_digest(ck.get("svdash", "").encode(), remember_cookie(agent).encode()):
            page = PAGE.replace("<script>", "<script>try{if(location.hash.indexOf('token=')<0&&!sessionStorage.getItem('t'))sessionStorage.setItem('t'," + json.dumps(token(agent)) + ")}catch(e){}", 1)
        return 200, page.encode(), "text/html; charset=utf-8", hdr
    given = {k.lower(): v for k, v in headers.items()}.get("x-dashboard-token", "")
    role = "owner" if hmac.compare_digest(given.encode(), token(agent).encode()) else None
    vt = AU.viewer_token(agent) if role is None else ""
    if role is None and vt and hmac.compare_digest(given.encode(), vt.encode()):
        role = "viewer"
    if role is None:
        return 401, b'{"error":"bad_token"}', "application/json", hdr
    if role == "viewer" and not (method == "GET" and (p in VIEW_OK or p == "/dash/api/me")):
        return 403, json.dumps({"error": "view_only", "message": "You have view-only access. Ask the owner to make this change."}).encode(), "application/json", hdr
    try:
        if p == "/dash/api/remember" and method == "POST":
            if role != "owner":
                return 403, b'{"error":"owner_only"}', "application/json", hdr
            return 200, b'{"ok":true}', "application/json", {**hdr, "set-cookie": f"svdash={remember_cookie(agent)}; Path=/dashboard; Max-Age=31536000; HttpOnly; SameSite=Lax"}
        if p == "/dash/api/me" and method == "GET":
            return 200, json.dumps({"role": role}).encode(), "application/json", hdr
        if p == "/dash/api/audit" and method == "GET":
            return 200, json.dumps(AU.view(agent)).encode(), "application/json", hdr
        if p == "/dash/api/viewer" and method == "POST":
            b = json.loads(raw or b"{}"); out = AU.set_viewer(agent, bool(b.get("on")), bool(b.get("rotate")))
            AU.record(agent, role, method, p)
            return 200, json.dumps(out).encode(), "application/json", hdr
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
        elif p == "/dash/api/setup/timeline" and method == "GET":
            from . import setuplog
            tl = setuplog.timeline(agent); out = {"timeline": tl, "text": setuplog.set_up_text(tl)}
        elif p == "/dash/api/setup" and method == "GET":
            out = SU.status(agent)
        elif p == "/dash/api/setup/save" and method == "POST":
            b = json.loads(raw or b"{}"); out = {"card": SU.save(agent, str(b.get("card", "")), b.get("values") or {})}
        elif p == "/dash/api/setup/tool" and method == "GET":
            out = SU.tool_view(agent, (parse_qs(u.query).get("name") or [""])[0])
        elif p == "/dash/api/setup/tool/secret" and method == "POST":
            out = SU.tool_secret(agent, str(json.loads(raw or b"{}").get("name", "")))
        elif p == "/dash/api/setup/tool/save" and method == "POST":
            b = json.loads(raw or b"{}"); out = SU.tool_save(agent, str(b.get("name", "")), b.get("secret", ""))
        elif p == "/dash/api/setup/tool/test" and method == "POST":
            out = SU.tool_test(agent, str(json.loads(raw or b"{}").get("name", "")))
        elif p == "/dash/api/setup/tool/remove" and method == "POST":
            out = SU.tool_remove(agent, str(json.loads(raw or b"{}").get("name", "")))
        elif p == "/dash/api/voice/check" and method == "POST":
            out = SU.voice_check(agent)
        elif p == "/dash/api/setup/twilio/numbers" and method == "GET":
            out = SU.twilio_numbers(agent)
        elif p == "/dash/api/setup/twilio/fallback" and method == "GET":
            out = SU.twilio_fallback(agent)
        elif p == "/dash/api/setup/twilio/fallback" and method == "POST":
            out = SU.twilio_fallback_set(agent, json.loads(raw or b"{}").get("url"))
        elif p == "/dash/api/sip/providers" and method == "GET":
            out = {"providers": SU.sip_providers()}
        elif p == "/dash/api/sip/admin-message" and method == "GET":
            out = {"message": SU.sip_admin_message(agent, (parse_qs(u.query).get("provider") or ["other"])[0])}
        elif p == "/dash/api/sip/status" and method == "GET":
            out = SU.sip_status(agent)
        elif p == "/dash/api/support/report" and method == "GET":
            from . import setuplog
            out = {"report": setuplog.report(agent)}
        elif p == "/dash/api/support/send" and method == "POST":
            from . import setuplog
            if not agent.mail.configured:
                raise SU.SetupError("Connect your email first (Connect, Email), or use Download report and email the file to support@speakvora.com.")
            agent.mail.send("support@speakvora.com", f"Setup report from {agent.cfg.get('business') or 'a new agent'}", setuplog.report(agent)); setuplog.record(agent, "support_report_emailed")
            out = {"sent": True}
        elif p.startswith("/dash/api/guide/") and method == "GET":
            out = SU.guide(p.rsplit("/", 1)[1])
        elif p == "/dash/api/setup/channel/connect" and method == "POST":
            out = SU.channel_connect(agent, json.loads(raw or b"{}").get("card"))
        elif p == "/dash/api/setup/twilio/point" and method == "POST":
            out = SU.twilio_point(agent, json.loads(raw or b"{}").get("number"))
        elif p == "/dash/api/setup/pair" and method == "POST":
            out = SU.pair_agent(agent, json.loads(raw or b"{}").get("code"))
        elif p == "/dash/api/setup/disconnect" and method == "POST":
            out = SU.disconnect(agent, str(json.loads(raw or b"{}").get("card", "")))
        elif p == "/dash/api/setup/test" and method == "POST":
            b = json.loads(raw or b"{}"); out = SU.test(agent, str(b.get("card", "")), b.get("opts") or {})
        elif p == "/dash/api/setup/workflow" and method == "POST":
            b = json.loads(raw or b"{}"); out = {"workflows": SU.set_workflow(agent, str(b.get("name", "")), bool(b.get("enabled")))}
            if b.get("enabled"):
                from . import setuplog
                setuplog.record(agent, "workflow_on", workflow=str(b.get("name", ""))[:60])
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
            b = json.loads(raw or b"{}"); out = SU.add_incoming(agent, str(b.get("name", "")), str(b.get("origin", "")))
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
        elif p == "/dash/api/quickstart" and method == "GET":
            from . import quickstart as QS
            out = {**QS.prefill(agent), "pending": QS.pending(agent)}
        elif p == "/dash/api/quickstart" and method == "POST":
            from . import quickstart as QS
            out = QS.apply(agent, json.loads(raw or b"{}"))
        elif p == "/dash/api/quickstart/transcripts" and method == "POST":
            from . import quickstart as QS
            b = json.loads(raw or b"{}"); out = {**QS.import_transcripts(agent, b.get("name"), b.get("data")), "items": QS.pending(agent)}
        elif p == "/dash/api/quickstart/approve" and method == "POST":
            from . import quickstart as QS
            b = json.loads(raw or b"{}"); texts = {i["id"]: i["a"] for i in QS.pending(agent)}; out = QS.approve(agent, b.get("ids"), b.get("edits"))
            import threading; threading.Thread(target=lambda: [agent._ai_voice(str((b.get("edits") or {}).get(i) or texts.get(i, ""))) for i in (b.get("ids") or [])[:10] if texts.get(i)], daemon=True).start()          # voiced now, so a call plays it instantly
            out["items"] = QS.pending(agent)
        elif p == "/dash/api/quickstart/dismiss" and method == "POST":
            from . import quickstart as QS
            out = QS.dismiss(agent, json.loads(raw or b"{}").get("ids")); out["items"] = QS.pending(agent)
        elif p == "/dash/api/knowledge" and method == "GET":
            out = KN.view(agent)
        elif p == "/dash/api/knowledge/source" and method == "GET":
            out = KN.preview(agent, (parse_qs(u.query).get("id") or [""])[0])
        elif p == "/dash/api/knowledge/text" and method == "POST":
            b = json.loads(raw or b"{}"); out = {"added": KN.add_text(agent, b.get("title"), b.get("text"), "note"), "view": KN.view(agent)}
        elif p == "/dash/api/knowledge/qa" and method == "POST":
            b = json.loads(raw or b"{}"); added = KN.add_qa(agent, b.get("question"), b.get("answer"))
            import threading; threading.Thread(target=lambda: agent._ai_voice(added["a"]), daemon=True).start()          # voiced now, so a call plays it instantly
            out = {"added": added, "view": KN.view(agent)}
        elif p == "/dash/api/knowledge/upload" and method == "POST":
            b = json.loads(raw or b"{}"); out = {"added": KN.add_file(agent, b.get("name"), b.get("data")), "view": KN.view(agent)}
        elif p == "/dash/api/knowledge/site" and method == "POST":
            out = {"added": KN.add_site(agent, json.loads(raw or b"{}").get("url")), "view": KN.view(agent)}
        elif p == "/dash/api/knowledge/remove" and method == "POST":
            KN.remove(agent, str(json.loads(raw or b"{}").get("id", ""))); out = KN.view(agent)
        elif p == "/dash/api/knowledge/gap" and method == "POST":
            KN.dismiss_gap(agent, str(json.loads(raw or b"{}").get("k", ""))); out = KN.view(agent)
        elif p == "/dash/api/knowledge/try" and method == "POST":
            out = CVN.try_it(agent, json.loads(raw or b"{}").get("question"))
        elif p == "/dash/api/scan" and method == "GET":
            from . import scan as SC
            out = SC.view(agent)
        elif p.startswith("/dash/api/scan/") and method == "POST":
            from . import scan as SC
            b = json.loads(raw or b"{}"); act = p[len("/dash/api/scan/"):]
            if act in ("search", "read", "phrases", "phrases/add", "check/ask", "anticipate") and b.get("ok") is not True:
                raise ValueError("Nothing happens until you say OK.")                      # every step that reads the web, sends text to your AI or spends your allowance asks first
            if act == "anticipate":
                SC.start_anticipating(agent, force=True)
            elif act == "search":
                SC.search(agent)
            elif act == "site":
                SC.set_site(agent, b.get("url"))
            elif act == "read":
                SC.read_site(agent, max(5, min(int(b.get("max_pages") or 40), 60)))
            elif act == "apply":
                SC.apply(agent, b.get("facts") or [], bool(b.get("profile", True)), bool(b.get("menu", True)), bool(b.get("faqs", True)), bool(b.get("daily")))
            elif act == "phrases":
                SC.suggest_phrases(agent)
            elif act == "phrases/add":
                added = SC.add_phrases(agent, b.get("lines") or [])["result"]
            elif act == "checks":
                SC.make_checks(agent)
            elif act == "daily":
                SC.set_daily(agent, bool(b.get("on")))
            elif act == "updates/apply":
                SC.apply_updates(agent, b.get("facts") or [])
            elif act == "updates/dismiss":
                SC.dismiss_updates(agent)
            elif act == "stale/remove":
                SC.remove_stale(agent, b.get("ids") or [])
            elif act == "check/ask":
                SC.check_ask(agent, b.get("i"))
            elif act == "check/mark":
                SC.check_mark(agent, b.get("i"), bool(b.get("ok")), b.get("fix") or "")
            elif act == "reset":
                SC.reset(agent)
            else:
                return 404, b'{"error":"not_found"}', "application/json", hdr
            out = SC.view(agent)
            if act == "phrases/add":
                out["result"] = added                                          # what was recorded and what was skipped (and why), so the sheet can say so
        elif p == "/dash/api/bookings" and method == "GET":
            from . import bookings as BK
            out = BK.view(agent)
        elif p == "/dash/api/bookings/save" and method == "POST":
            from . import bookings as BK
            out = BK.save(agent, json.loads(raw or b"{}"))
        elif p == "/dash/api/bookings/cancel" and method == "POST":
            from . import bookings as BK
            out = {"cancelled": BK.cancel(agent, str(json.loads(raw or b"{}").get("code", ""))), **BK.view(agent)}
        elif p == "/dash/api/simulate" and method == "GET":
            out = SIM.view(agent)
        elif p == "/dash/api/simulate" and method == "POST":
            b = json.loads(raw or b"{}")
            if b.get("call") is not None:
                c = b["call"] or {}; out = SIM.call(agent, c.get("digits", ""), c.get("said", ""), bool(c.get("new")))
            else:
                out = SIM.event(agent, b.get("event")) if b.get("event") else SIM.text(agent, b.get("text"), bool(b.get("new")))
            for x in out.get("did", []):
                if x.get("reason") in WHY:
                    x["why"] = WHY[x["reason"]]
        elif p == "/dash/api/workflows" and method == "GET":
            out = BD.view(agent)
        elif p == "/dash/api/workflows/save" and method == "POST":
            b = json.loads(raw or b"{}"); out = BD.save(agent, b.get("spec") or {}, b.get("id") or None)
        elif p == "/dash/api/workflows/delete" and method == "POST":
            BD.delete(agent, str(json.loads(raw or b"{}").get("id", ""))); out = BD.view(agent)
        elif p == "/dash/api/workflows/toggle" and method == "POST":
            b = json.loads(raw or b"{}"); BD.toggle(agent, str(b.get("id", "")), bool(b.get("on"))); out = BD.view(agent)
        elif p == "/dash/api/workflows/preview" and method == "POST":
            out = BD.preview(agent, json.loads(raw or b"{}").get("spec") or {})
        elif p == "/dash/api/workflows/page" and method == "GET":
            qs = parse_qs(u.query); out = WE.page(agent, int((qs.get("offset") or ["0"])[0] or 0), max(1, min(50, int((qs.get("limit") or ["10"])[0] or 10))), (qs.get("state") or [""])[0] or None)
        elif p == "/dash/api/workflows/detail" and method == "GET":
            out = WE.detail(agent, (parse_qs(u.query).get("name") or [""])[0])
        elif p == "/dash/api/workflows/edit" and method == "POST":
            b = json.loads(raw or b"{}")
            out = WE.save(agent, str(b.get("name", "")), texts=b.get("texts"), keywords=b.get("keywords"), daily_at=b.get("daily_at"), lead=b.get("lead"), reminder=b.get("reminder"), hours_=b.get("hours"),
                          title_contains=b.get("title_contains"), approve=b.get("approve"), enable=b.get("enable"))
        elif p == "/dash/api/workflows/reset" and method == "POST":
            out = WE.reset(agent, str(json.loads(raw or b"{}").get("name", "")))
        elif p == "/dash/api/sales" and method == "GET":
            out = SA.view(agent)
        elif p == "/dash/api/sales/sources" and method == "POST":
            b = json.loads(raw or b"{}"); out = SA.set_sources(agent, b.get("urls") or [], str(b.get("feed") or ""), b.get("settings"))
        elif p == "/dash/api/sales/enable" and method == "POST":
            out = SA.enable(agent, bool(json.loads(raw or b"{}").get("on")))
        elif p == "/dash/api/sales/check" and method == "POST":
            r = SA.watch(agent, force=bool(json.loads(raw or b"{}").get("force"))); out = {**SA.view(agent), "result": r}
        elif p == "/dash/api/sales/consent" and method == "POST":
            b = json.loads(raw or b"{}")
            if b.get("csv"):
                r = SA.import_csv(agent, str(b["csv"]))
            elif b.get("remove"):
                r = {"removed": SA.remove_consent(agent, str(b["remove"]))}
            else:
                r = SA.add_consent(agent, b.get("phone"), b.get("source"), b.get("at"), b.get("name", ""))
            out = {**SA.view(agent), "result": r}
        elif p == "/dash/api/sales/draft" and method == "POST":
            b = json.loads(raw or b"{}"); did = str(b.get("id", "")); act = b.get("action")
            if act == "edit":
                SA.edit_draft(agent, did, b.get("text")); out = SA.view(agent)
            elif act == "preview":
                out = SA.preview(agent, did)
            elif act == "test":
                out = SA.test_send(agent, did)
            elif act == "approve":
                out = {**SA.view(agent), "result": SA.approve(agent, did, b.get("text"))}
            elif act == "decline":
                SA.decline(agent, did); out = SA.view(agent)
            else:
                raise ValueError("Unknown action.")
        elif p == "/dash/api/address" and method == "GET":
            out = AD.view(agent)
        elif p == "/dash/api/address/save" and method == "POST":
            out = AD.save(agent, json.loads(raw or b"{}"))
        elif p == "/dash/api/address/check" and method == "POST":
            out = AD.check(agent)
        elif p == "/dash/api/address/install" and method == "POST":
            AD.install_cloudflared(agent); AD.sync(agent); out = AD.view(agent)
        elif p == "/dash/api/address/funnel" and method == "POST":
            ok, msg = AD.tailscale_funnel(agent.cfg["listen"]["port"]); out = {"ok": ok, "message": msg, **AD.check(agent)}
        elif p == "/dash/api/accessibility" and method == "GET":
            from . import access as AX
            out = AX.view(agent)
        elif p == "/dash/api/accessibility" and method == "POST":
            from . import access as AX
            b = json.loads(raw or b"{}")
            out = AX.suggest(agent) if b.get("ask_ai") else AX.save(agent, b.get("preset"))
        elif p == "/dash/api/address/private-dashboard" and method == "POST":
            on = bool(json.loads(raw or b"{}").get("on")); ok, msg = AD.tailscale_private_dashboard(agent.cfg["listen"]["port"], on)
            if ok:
                AD.save(agent, {"private_dashboard": on})
                from . import server as SRV
                SRV.ensure_private(agent)
            out = {"ok": ok, "message": msg, **AD.view(agent)}
        elif p == "/dash/api/address/use" and method == "POST":
            out = AD.use_everywhere(agent, bool(json.loads(raw or b"{}").get("force")))
        elif p == "/dash/api/address/remove" and method == "POST":
            out = AD.remove(agent)
        elif p == "/dash/api/phonemenu" and method == "GET":
            out = PM.view(agent)
        elif p == "/dash/api/phonemenu" and method == "POST":
            PM.save(agent, json.loads(raw or b"{}")); out = PM.view(agent)
        elif p == "/dash/api/phonemenu/reset" and method == "POST":
            PM.reset(agent); out = PM.view(agent)
        elif p == "/dash/api/phonemenu/voice" and method == "POST":
            m = PM.apply(agent, {}); n = 0
            if not m.get("custom"):
                raise ValueError("Switch your menu on and save it first.")
            if not sharing._key(agent):
                raise ValueError("Voicing needs your Speakvora key (Connect, Speakvora agent). Until then callers hear your words in the phone provider's voice.")
            for t in dict.fromkeys([m["speech_say"], m["fallback_say"], m["speech_ask"], m["again_say"]]):
                if not agent.audio.cached_dynamic(t, True) and "<Play>" in agent._ai_voice(t, True, True):
                    n += 1
            out = {"voiced": n, "message": f"Voiced {n} new line{'s' if n != 1 else ''} in your bundle's voice." if n else "Nothing new to voice: every line is already voiced, or the voice service did not answer (callers hear the phone provider's voice meanwhile)."}
        elif p == "/dash/api/insights" and method == "GET":
            out = AC.insights(agent, int((parse_qs(u.query).get("days") or ["7"])[0] or 7))
        elif p == "/dash/api/activity" and method == "GET":
            qs = parse_qs(u.query); out = AC.activity(agent, jobs_for_display(agent), (qs.get("kind") or [""])[0], int((qs.get("offset") or ["0"])[0] or 0))
        elif p == "/dash/api/phrases" and method == "GET":
            qs = parse_qs(u.query); out = AC.phrases(agent, (qs.get("q") or [""])[0], int((qs.get("offset") or ["0"])[0] or 0), cat=(qs.get("cat") or [""])[0])
        elif p == "/dash/api/chat" and method == "GET":
            out = {"history": CH.history(agent), "configured": BR.configured(agent)}
        elif p == "/dash/api/chat" and method == "POST":
            out = CH.ask(agent, json.loads(raw or b"{}").get("message"))
        elif p == "/dash/api/chat/clear" and method == "POST":
            out = CH.clear(agent)
        elif p == "/dash/api/conversations" and method == "GET":
            qs = parse_qs(u.query); out = CVS.list_(agent, (qs.get("q") or [""])[0], (qs.get("kind") or [""])[0], int((qs.get("offset") or ["0"])[0] or 0))
        elif re.fullmatch(r"/dash/api/conversations/\d+", p) and method == "GET":
            out = CVS.get(agent, int(p.rsplit("/", 1)[1])); out = out if out is not None else (_ for _ in ()).throw(ValueError("That conversation was not found."))
        elif p == "/dash/api/conversations/switch" and method == "POST":
            out = CVS.set_enabled(agent, bool(json.loads(raw or b"{}").get("on")))
        elif p == "/dash/api/conversations/summary" and method == "POST":
            out = CVS.ai_summary(agent, int(json.loads(raw or b"{}").get("id") or 0))
        elif p == "/dash/api/conversations/delete" and method == "POST":
            b = json.loads(raw or b"{}"); out = {"deleted": CVS.delete(agent, None if b.get("all") else int(b.get("id") or 0))}
        elif p == "/dash/api/orderpages" and method == "GET":
            out = SU.order_pages(agent)
        elif p == "/dash/api/orderpages/switch" and method == "POST":
            out = SU.set_tracking(agent, bool(json.loads(raw or b"{}").get("on")))
        elif p == "/dash/api/orderpages/pair" and method == "POST":
            out = SU.pair_account(agent, json.loads(raw or b"{}").get("code"))
        elif p == "/dash/api/orderpages/setup" and method == "POST":
            out = SU.setup_order_pages(agent, json.loads(raw or b"{}"))
        elif p == "/dash/api/orders" and method == "GET":
            qs = parse_qs(u.query); out = TK.orders(agent, (qs.get("q") or [""])[0], int((qs.get("offset") or ["0"])[0] or 0))
        elif p == "/dash/api/orders/export" and method == "GET":
            out = {"csv": TK.export_csv(agent), "filename": "speakvora-orders.csv"}
        elif p == "/dash/api/controls" and method == "GET":
            out = CT.view(agent)
        elif p == "/dash/api/controls/rules" and method == "GET":
            qs = parse_qs(u.query); out = CT.rules(agent, (qs.get("priority") or [""])[0], (qs.get("q") or [""])[0], int((qs.get("offset") or ["0"])[0] or 0))
        elif p == "/dash/api/controls/policy" and method == "POST":
            out = CT.set_policy(agent, json.loads(raw or b"{}").get("values"))
        elif p == "/dash/api/learned" and method == "GET":
            out = LN.view(agent)
        elif p == "/dash/api/learned/add" and method == "POST":
            LN.add(agent, str(json.loads(raw or b"{}").get("id") or "")); out = LN.view(agent)
        elif p == "/dash/api/learned/lines" and method == "POST":
            out = LN.add_lines(agent, json.loads(raw or b"{}").get("text")) | {"view": LN.view(agent)}
        elif p == "/dash/api/learned/suggest" and method == "POST":
            out = LN.suggest(agent, json.loads(raw or b"{}").get("text"))
        elif p == "/dash/api/learned/write" and method == "POST":
            out = {"options": LN.write(agent, json.loads(raw or b"{}").get("situation"))}
        elif p == "/dash/api/learned/dismiss" and method == "POST":
            out = LN.dismiss(agent, str(json.loads(raw or b"{}").get("id") or ""))
        elif p == "/dash/api/learned/remove" and method == "POST":
            out = LN.remove(agent, str(json.loads(raw or b"{}").get("id") or ""))
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
    if method != "GET":
        try:
            AU.record(agent, role, method, p)
        except Exception:  # noqa: BLE001 - the log never stops a change
            pass
    return 200, json.dumps(out).encode(), "application/json", hdr


from .ui import PAGE  # noqa: E402  (the page lives in ui.py)
