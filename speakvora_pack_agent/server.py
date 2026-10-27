"""The agent's web server (standard library). Endpoints: POST /event (from your app, signed), POST /twilio/sms and /twilio/call[/menu] (Twilio, signature checked), POST /slack/command (Slack, signature checked),
GET /audio/<id>.mp3 (so Twilio can play pack audio), GET /health. A background thread runs the calendar and daily schedules about once a minute."""
import hashlib, hmac, json, os, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import dashboard, locations as LC, sources
from .connectors import signing


bad_by = {}


def _locked(who):
    """Eight wrong access tokens from one remote address in ten minutes lock that address out for the rest of the ten minutes."""
    return len([t for t in bad_by.get(who, []) if time.time() - t < 600]) >= 8


def _fail(who):
    now = time.time(); bad_by[who] = [t for t in bad_by.get(who, []) if now - t < 600] + [now]
    if len(bad_by) > 2000:
        bad_by.clear()


def make_handler(agent, private=False):
    """private=True is the second, dashboard-only door that Tailscale Serve (never Funnel) points at: it listens on its own port on this computer, so which door a request used cannot be faked by a header."""
    cfg = agent.cfg

    hits_by = {}

    class H(BaseHTTPRequestHandler):
        server_version = "SpeakvoraPackAgent/0.1"

        def log_message(self, *a):
            pass

        def _cors_origin(self):
            """The website that may post straight from a visitor's browser to this address: only a source that lists it (origins in its settings), and only with its token."""
            p = self.path.split("?")[0]; o = self.headers.get("Origin", "")
            if not (o and p.startswith("/hook/")):
                return ""
            src = next((x for x in cfg.get("sources", []) if x.get("path") == p), None)
            return o if src and o in (src.get("origins") or []) else ""

        def _send(self, code, body=b"", ctype="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code); self.send_header("content-type", ctype); self.send_header("content-length", str(len(body)))
            o = self._cors_origin()
            if o:
                self.send_header("access-control-allow-origin", o); self.send_header("vary", "Origin")
            self.end_headers(); self.wfile.write(body)

        def do_OPTIONS(self):
            o = self._cors_origin()
            if not o:
                return self._send(404, {"error": "not_found"})
            self.send_response(204); self.send_header("access-control-allow-origin", o); self.send_header("vary", "Origin"); self.send_header("access-control-allow-methods", "POST, OPTIONS")
            self.send_header("access-control-allow-headers", "authorization, content-type"); self.send_header("access-control-max-age", "600"); self.send_header("content-length", "0"); self.end_headers()

        def _body(self):
            n = min(int(self.headers.get("content-length") or 0), 4_500_000 if self.path.split("?")[0] == "/dash/api/knowledge/upload" else 200_000)
            return self.rfile.read(n)

        def _public(self):
            return cfg.get("public_base_url", "").rstrip("/") + self.path.split("?")[0]

        def _local_only(self):
            """The dashboard is for the person at this computer. A request that came through a tunnel or reverse proxy (it carries forwarding headers or a public Host name) is refused, so exposing the webhook routes to the internet never exposes the dashboard. Set dashboard.allow_remote to true in agent.json to turn this off on purpose."""
            if (cfg.get("dashboard") or {}).get("allow_remote"):
                return True
            h = {k.lower(): v for k, v in self.headers.items()}
            ad = cfg.get("address") or {}
            if ad.get("remote_dashboard") and ad.get("dashboard_hostname") and h.get("host", "").rsplit(":", 1)[0].lower() == str(ad["dashboard_hostname"]).lower():      # the dashboard has its own address, never the webhook one
                who = h.get("cf-access-authenticated-user-email", "").strip().lower()
                if ad.get("require_access", True) is not False and not who:          # Cloudflare Access (the email login in front of this address) must have let the person in
                    return False
                allowed = [str(x).lower() for x in (ad.get("allowed_emails") or [])]
                return not allowed or who in allowed
            if private:                                                                   # the private door: only through Tailscale Serve, with a signed-in Tailscale user (and the optional list of logins)
                from . import address as _AD
                return _AD.private_login_ok(agent, h)
            if any(k in h for k in ("x-forwarded-for", "x-forwarded-host", "forwarded", "x-real-ip", "cf-connecting-ip", "cf-ray", "x-forwarded-proto")):
                return False
            host = h.get("host", "").rsplit(":", 1)[0].strip("[]").lower() if not h.get("host", "").startswith("[") else h.get("host", "").split("]")[0].strip("[").lower()
            return host in ("127.0.0.1", "localhost", "::1", "") or host.endswith(".localhost")

        def _limited(self):
            """Webhook routes accept at most 240 requests a minute per sender (by the forwarded address when behind a tunnel). Returns True when this request is over the limit."""
            now = time.time(); h = {k.lower(): v for k, v in self.headers.items()}
            who = (h.get("cf-connecting-ip") or h.get("x-forwarded-for", "").split(",")[0].strip() or self.client_address[0])
            hits = [t for t in hits_by.get(who, []) if now - t < 60]; hits.append(now); hits_by[who] = hits
            if len(hits_by) > 5000:
                hits_by.clear()
            return len(hits) > 240

        def _loc(self, method):
            """/loc/<id>/dashboard and /loc/<id>/dash/api/...: another location's dashboard, shown through this agent. Same rules as the dashboard: this computer only, and the access token (header for the page's calls, a cookie the page sets for the first load)."""
            if not self._local_only():
                return self._send(403, {"error": "dashboard_is_local_only"})
            h = {k.lower(): v for k, v in self.headers.items()}; tok = dashboard.token(agent)
            cookie = dict(c.strip().split("=", 1) for c in h.get("cookie", "").split(";") if "=" in c)
            if not (hmac.compare_digest(h.get("x-dashboard-token", "").encode(), tok.encode()) or hmac.compare_digest(cookie.get("svloc", "").encode(), LC.session_cookie(tok).encode())):
                return self._send(401, {"error": "bad_token"})
            m = re.match(r"^/loc/([a-z0-9\-]{1,30})(/.*)$", self.path.split("?")[0])
            if not m:
                return self._send(404, {"error": "not_found"})
            raw = self._body() if method == "POST" else b""
            if method == "POST":
                origin = self.headers.get("Origin")
                if origin and urlparse(origin).netloc != self.headers.get("Host", ""):
                    return self._send(403, {"error": "bad_origin"})
            code, body, ctype = LC.proxy(agent, m.group(1), method, m.group(2), raw)
            self.send_response(code); self.send_header("content-type", ctype); self.send_header("content-length", str(len(body))); self.send_header("cache-control", "no-store")
            self.send_header("content-security-policy", dashboard.CSP.replace("frame-ancestors 'none'", "frame-ancestors 'none'")); self.end_headers(); self.wfile.write(body)

        def _dash(self, method):
            if not self._local_only():
                return self._send(403, {"error": "dashboard_is_local_only", "message": "The dashboard only opens on the computer running the agent. Open http://127.0.0.1:8787/dashboard there."})
            raw = self._body() if method == "POST" else b""
            origin = self.headers.get("Origin")
            if method == "POST" and origin and urlparse(origin).netloc != self.headers.get("Host", ""):      # a page on another site cannot drive the dashboard
                return self._send(403, {"error": "bad_origin"})
            h_ = {k.lower(): v for k, v in self.headers.items()}
            who = (h_.get("x-forwarded-for", "").split(",")[0].strip() or self.client_address[0]) if "x-forwarded-for" in h_ else ""
            if who and _locked(who):
                return self._send(429, {"error": "too_many_wrong_tokens", "message": "Too many wrong access tokens. Try again in 10 minutes."})
            code, body, ctype, hdr = dashboard.handle(agent, method, self.path, dict(self.headers), raw)
            if who and code == 401:
                _fail(who)
            self.send_response(code); self.send_header("content-type", ctype); self.send_header("content-length", str(len(body)))
            for k, v in hdr.items():
                self.send_header(k, v)
            self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            p = self.path.split("?")[0]
            if private and not (p == "/dashboard" or p.startswith("/dash/api/") or p.startswith("/loc/")):
                return self._send(404, {"error": "not_found"})
            if p == "/dashboard" or p.startswith("/dash/api/"):
                return self._dash("GET")
            if p.startswith("/loc/"):
                return self._loc("GET")
            if p == "/health":
                return self._send(200, {"ok": True, "home": hashlib.sha256(os.path.abspath(agent.state.dir).encode()).hexdigest()[:12], "dry_run": agent.dry, "pack": agent.pack.meta.get("pack"), "workflows": len(agent.workflows), "missing_slots": agent.missing_slots, "missing_required_lines": agent.missing_required, "killed": agent.safe.killed(), "queued": len(agent.state.outbox()), "jobs": agent.state.job_counts()})
            if p.startswith("/bookings/") and p.endswith(".ics"):               # the booking book as a calendar feed: public, but only with the long secret in the address
                from . import bookings
                if self._limited():
                    return self._send(429, {"error": "slow_down"})
                if not hmac.compare_digest(p[len("/bookings/"):-4].encode(), bookings.feed_token(agent).encode()):
                    return self._send(404, {"error": "not_found"})
                return self._send(200, bookings.ics(agent), "text/calendar; charset=utf-8")
            if p.startswith("/track/"):                                        # the customer's order page: public, holds only the step, protected by a long random code
                from . import tracker
                if self._limited():
                    return self._send(429, {"error": "slow_down"})
                code = p[len("/track/"):]
                if code.endswith(".json"):
                    d = tracker.get(agent, code[:-5])
                    return self._send(200, d) if d else self._send(404, {"error": "not_found"})
                body = tracker.page(agent, code)
                return self._send(200, body, "text/html; charset=utf-8") if body else self._send(404, {"error": "not_found"})
            if p.startswith("/guide/"):                                            # the full setup guides: public documentation with nothing private in it, so a new browser tab can open it
                from . import connect as _SU
                try:
                    page = _SU.guide_html(p.rsplit("/", 1)[1]).encode()
                except _SU.SetupError:
                    return self._send(404, {"error": "not_found"})
                self.send_response(200); self.send_header("content-type", "text/html; charset=utf-8"); self.send_header("content-length", str(len(page)))
                self.send_header("content-security-policy", "default-src 'none'; img-src data:; style-src 'unsafe-inline'")
                if "download=1" in self.path:
                    self.send_header("content-disposition", f'attachment; filename="speakvora-{p.rsplit("/", 1)[1]}-setup-guide.html"')
                self.end_headers(); self.wfile.write(page); return
            if p == "/whatsapp/webhook":                                       # Meta's one-time check when you save the webhook address
                from urllib.parse import urlparse
                ch = agent.whatsapp.handshake(parse_qs(urlparse(self.path).query))
                return self._send(200, ch, "text/plain") if ch is not None else self._send(403, {"error": "bad_verify_token"})
            if p.startswith("/audio/"):
                got = agent.audio.serve(p[len("/audio/"):].rsplit(".", 1)[0])
                return self._send(200, got[0], got[1]) if got else self._send(404, {"error": "not_found"})
            self._send(404, {"error": "not_found"})

        def do_POST(self):
            if private and not (self.path.split("?")[0].startswith("/dash/api/") or self.path.split("?")[0].startswith("/loc/")):
                return self._send(404, {"error": "not_found"})
            if self.path.split("?")[0].startswith("/dash/api/"):
                return self._dash("POST")
            if self.path.split("?")[0].startswith("/loc/"):
                return self._loc("POST")
            p, raw = self.path.split("?")[0], self._body()
            if self._limited():
                return self._send(429, {"error": "slow_down", "message": "Too many requests from one sender; wait a minute."})
            try:
                if p == "/event":
                    if not signing.verify(cfg["events"].get("secret", ""), raw, dict(self.headers)):
                        return self._send(401, {"error": "bad_signature"})
                    return self._send(200, agent.handle_event(json.loads(raw or b"{}")))
                if p.startswith("/hook/"):
                    src = next((x for x in cfg.get("sources", []) if x.get("path") == p), None)
                    if not src:
                        return self._send(404, {"error": "unknown_source"})
                    if not sources.authorised(src, raw, dict(self.headers)) and not (agent.dry and (src.get("auth") or {}).get("type") in (None, "", "none")):
                        return self._send(401, {"error": "bad_signature"})
                    from urllib.parse import urlparse
                    req = {"payload": json.loads(raw or b"{}") if raw.strip().startswith((b"{", b"[")) else {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace")).items()},
                           "headers": {k.lower(): v for k, v in self.headers.items()}, "query": {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}}
                    ev = sources.map_request(src, req)
                    if src.get("name") and not src.get("name", "").startswith("custom-"):
                        agent.state.data.setdefault("tool_seen", {})[src["name"]] = int(time.time()); agent.state.save()
                    if ev and src.get("as") == "sms":                              # any provider's inbound text: answered through your sms_provider
                        return self._send(200, {"replied": bool(agent.sms_via_provider(ev.get("from") or (ev.get("customer") or {}).get("phone"), ev.get("body", "")))})
                    return self._send(200, agent.handle_event(ev) if ev else {"ignored": True})
                if p.startswith("/twilio/call/whisper/") and re.fullmatch(r"[0-9a-f]{10}", p.rsplit("/", 1)[1]):          # spoken only to the person who picks up a transfer, before the caller is connected
                    params = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True).items()}
                    if not agent.twilio.check_signature(self._public(), params, self.headers.get("X-Twilio-Signature", "")):
                        return self._send(403, {"error": "bad_signature"})
                    return self._send(200, agent.handle_whisper(p.rsplit("/", 1)[1]), "text/xml")
                if p == "/twilio/call/partial":                                                                           # Twilio's first partial speech result: the moment the caller started talking
                    params = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True).items()}
                    if not agent.twilio.check_signature(self._public(), params, self.headers.get("X-Twilio-Signature", "")):
                        return self._send(403, {"error": "bad_signature"})
                    agent.handle_partial(params)
                    return self._send(200, "<Response></Response>", "text/xml")
                if p.startswith("/twilio/call/wait/") and re.fullmatch(r"[0-9a-f]{10}", p.rsplit("/", 1)[1]):
                    params = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True).items()}
                    if not agent.twilio.check_signature(self._public(), params, self.headers.get("X-Twilio-Signature", "")):
                        return self._send(403, {"error": "bad_signature"})
                    return self._send(200, agent.call_wait(p.rsplit("/", 1)[1], params), "text/xml")
                if p in ("/twilio/sms", "/twilio/call", "/twilio/call/menu", "/twilio/call/menu2", "/twilio/call/menu3", "/twilio/call/dialdone", "/twilio/status"):
                    params = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True).items()}
                    if not agent.twilio.check_signature(self._public(), params, self.headers.get("X-Twilio-Signature", "")):
                        return self._send(403, {"error": "bad_signature"})
                    if p == "/twilio/status":
                        return self._send(200, agent.handle_delivery(params))
                    if p == "/twilio/sms":
                        from .connectors.twilio import twiml_message
                        reply = agent.handle_sms(params)
                        return self._send(200, twiml_message(reply) if reply else "<Response></Response>", "text/xml")
                    if p == "/twilio/call/dialdone":
                        return self._send(200, agent.handle_dial_done(params), "text/xml")
                    params["_idem"] = self.headers.get("I-Twilio-Idempotency-Token", "")                       # present only on a retry of the same webhook: answered from memory, never run twice
                    return self._send(200, agent.handle_call(params, "start" if p == "/twilio/call" else ("menu3" if p.endswith("menu3") else "menu2" if p.endswith("menu2") else "menu"), params.get("Digits", "")), "text/xml")
                if p == "/android/sms":                                        # a text your Android phone received (signed by the SMS Gateway app)
                    if not agent.android.verify(raw, self.headers.get("X-Timestamp", ""), self.headers.get("X-Signature", "")):
                        __import__("speakvora_pack_agent.setuplog", fromlist=["x"]).record(agent, "webhook_rejected", channel="android"); agent.state.log(workflow="inbound_android", status="rejected", reason="bad_signature_or_old_timestamp", has_signature=bool(self.headers.get("X-Signature")), hint="re-copy the signing key from the phone app (an apostrophe or space typed differently is enough to fail)")
                        return self._send(401, {"error": "bad_signature"})
                    m = agent.android.parse(json.loads(raw or b"{}"))
                    if not m or not agent.state.once("android:" + (m["id"] or hashlib.sha256(raw).hexdigest())):          # the app retries until it gets a 200: answer each text once
                        return self._send(200, {"ignored": True})
                    return self._send(200, {"replied": bool(agent.handle_chat("android", m["from"], m["body"], m["line"], m.get("own")))})
                if p == "/telegram/webhook":
                    if not agent.telegram.verify(self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")):
                        agent.state.log(workflow="inbound_telegram", status="rejected", reason="bad_secret")
                        return self._send(401, {"error": "bad_secret"})
                    upd = json.loads(raw or b"{}"); m = agent.telegram.parse(upd)
                    if not m or not agent.state.once("telegram:" + str(upd.get("update_id", hashlib.sha256(raw).hexdigest()))):
                        return self._send(200, {"ignored": True})
                    return self._send(200, {"replied": bool(agent.handle_chat("telegram", m["from"], m["body"]))})
                if p == "/whatsapp/webhook":
                    if not agent.whatsapp.verify(raw, self.headers.get("X-Hub-Signature-256", "")):
                        __import__("speakvora_pack_agent.setuplog", fromlist=["x"]).record(agent, "webhook_rejected", channel="whatsapp"); agent.state.log(workflow="inbound_whatsapp", status="rejected", reason="bad_signature", hint="check the App secret (Meta, App settings, Basic) saved in the agent")
                        return self._send(401, {"error": "bad_signature"})
                    try:
                        kinds = [m.get("type") for e in json.loads(raw or b"{}").get("entry", []) for c in e.get("changes", []) for m in (c.get("value") or {}).get("messages", [])]
                    except (ValueError, AttributeError):
                        kinds = []
                    agent.state.log(workflow="inbound_whatsapp", status="received", bytes=len(raw), kinds=kinds or "status")
                    n = 0
                    for m in agent.whatsapp.parse(json.loads(raw or b"{}")):
                        if agent.state.once("whatsapp:" + hashlib.sha256(raw).hexdigest() + m["from"]):
                            n += bool(agent.handle_unsupported("whatsapp", m["from"]) if m.get("unsupported") else agent.handle_chat("whatsapp", m["from"], m["body"]))
                    return self._send(200, {"replied": n})
                if p == "/slack/events":
                    if not agent.slack.verify(raw, self.headers.get("X-Slack-Request-Timestamp", ""), self.headers.get("X-Slack-Signature", "")):
                        return self._send(401, {"error": "bad_signature"})
                    payload = json.loads(raw or b"{}")
                    if payload.get("type") == "url_verification":
                        return self._send(200, {"challenge": payload.get("challenge", "")})
                    if not self.headers.get("X-Slack-Retry-Num"):                 # Slack retries a slow answer; the first delivery is enough
                        threading.Thread(target=agent.handle_slack_event, args=(payload,), daemon=True).start()
                    return self._send(200, {"ok": True})
                if p == "/teams/messages":                                      # Teams Outgoing Webhook (see teams_in.py): HMAC-signed, wrong tries are locked out like the dashboard token
                    who = (self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0])
                    if _locked(who):
                        return self._send(429, {"error": "too_many_wrong_attempts"})
                    code, body = __import__("speakvora_pack_agent.teams_in", fromlist=["x"]).handle(agent, raw, self.headers.get("Authorization", ""))
                    if code == 401:
                        _fail(who)
                    return self._send(code, body)
                if p == "/slack/command":
                    if not agent.slack.verify(raw, self.headers.get("X-Slack-Request-Timestamp", ""), self.headers.get("X-Slack-Signature", "")):
                        return self._send(401, {"error": "bad_signature"})
                    return self._send(200, agent.handle_slack_command({k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace")).items()}))
            except Exception as e:  # noqa: BLE001 - never crash the server, never leak internals
                agent.state.log(workflow="server", status="error", path=p, error=type(e).__name__ + ": " + str(e)[:160])
                return self._send(500, {"error": "agent_error"})
            self._send(404, {"error": "not_found"})

    return H


def serve(agent, host=None, port=None, tick_seconds=60):
    host, port = host or agent.cfg["listen"]["host"], agent.cfg["listen"]["port"] if port is None else port
    srv = ThreadingHTTPServer((host, port), make_handler(agent))
    stop = threading.Event()
    ensure_private(agent, host)

    def loop():
        try:
            agent.recover()                                                   # a send cut off by a crash waits for a person; events accepted but not finished are resumed
            agent.flush_outbox()                                              # anything left in the outbox from before a restart or power cut goes out as soon as the connection allows
        except Exception as e:  # noqa: BLE001
            agent.state.log(workflow="outbox", status="error", error=str(e)[:200])
        while not stop.wait(tick_seconds):
            try:
                agent.tick()
            except Exception as e:  # noqa: BLE001
                agent.state.log(workflow="tick", status="error", error=str(e)[:200])
    threading.Thread(target=loop, daemon=True).start()
    srv.stopper = stop
    agent._serving = True; agent.sip_sync(); agent.telegram_sync(); agent.address_sync()
    _shutdown = srv.shutdown
    srv.shutdown = lambda: (ensure_private(agent, host, stop=True), agent.sip_stop(), getattr(getattr(agent, 'tunnel', None), 'stop', lambda: None)(), _shutdown())
    return srv


def private_port(agent):
    return agent.cfg["listen"]["port"] + 1000


def ensure_private(agent, host=None, stop=False):
    """Starts (or stops) the private dashboard door, a second listener on this computer that only Tailscale Serve points at. It runs only while the owner has switched the private dashboard on."""
    from . import address as _AD
    cur = getattr(agent, "_private_srv", None)
    if stop or not (_AD.settings(agent).get("private_dashboard") and (_AD.settings(agent).get("provider") or "") == "tailscale"):
        if cur:
            threading.Thread(target=cur.shutdown, daemon=True).start(); cur.server_close(); agent._private_srv = None
        return None
    if cur:
        return cur
    try:
        srv = ThreadingHTTPServer((host or agent.cfg["listen"]["host"], private_port(agent)), make_handler(agent, private=True))
    except OSError as e:
        agent.state.log(workflow="server", status="error", path="private-dashboard", error=str(e)[:160]); return None
    threading.Thread(target=srv.serve_forever, daemon=True).start(); agent._private_srv = srv
    return srv
