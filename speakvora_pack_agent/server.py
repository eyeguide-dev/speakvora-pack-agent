"""The agent's web server (standard library). Endpoints: POST /event (from your app, signed), POST /twilio/sms and /twilio/call[/menu] (Twilio, signature checked), POST /slack/command (Slack, signature checked),
GET /audio/<id>.mp3 (so Twilio can play pack audio), GET /health. A background thread runs the calendar and daily schedules about once a minute."""
import json, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import dashboard, sources
from .connectors import signing


def make_handler(agent):
    cfg = agent.cfg

    class H(BaseHTTPRequestHandler):
        server_version = "SpeakvoraPackAgent/0.1"

        def log_message(self, *a):
            pass

        def _send(self, code, body=b"", ctype="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code); self.send_header("content-type", ctype); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def _body(self):
            n = min(int(self.headers.get("content-length") or 0), 200_000)
            return self.rfile.read(n)

        def _public(self):
            return cfg.get("public_base_url", "").rstrip("/") + self.path.split("?")[0]

        def _dash(self, method):
            raw = self._body() if method == "POST" else b""
            origin = self.headers.get("Origin")
            if method == "POST" and origin and urlparse(origin).netloc != self.headers.get("Host", ""):      # a page on another site cannot drive the dashboard
                return self._send(403, {"error": "bad_origin"})
            code, body, ctype, hdr = dashboard.handle(agent, method, self.path, dict(self.headers), raw)
            self.send_response(code); self.send_header("content-type", ctype); self.send_header("content-length", str(len(body)))
            for k, v in hdr.items():
                self.send_header(k, v)
            self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            p = self.path.split("?")[0]
            if p == "/dashboard" or p.startswith("/dash/api/"):
                return self._dash("GET")
            if p == "/health":
                return self._send(200, {"ok": True, "dry_run": agent.dry, "pack": agent.pack.meta.get("pack"), "workflows": len(agent.workflows), "missing_slots": agent.missing_slots, "missing_required_lines": agent.missing_required, "killed": agent.safe.killed(), "queued": len(agent.state.outbox()), "jobs": agent.state.job_counts()})
            if p.startswith("/audio/"):
                got = agent.audio.serve(p[len("/audio/"):].rsplit(".", 1)[0])
                return self._send(200, got[0], got[1]) if got else self._send(404, {"error": "not_found"})
            self._send(404, {"error": "not_found"})

        def do_POST(self):
            if self.path.split("?")[0].startswith("/dash/api/"):
                return self._dash("POST")
            p, raw = self.path.split("?")[0], self._body()
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
                    if ev and src.get("as") == "sms":                              # any provider's inbound text: answered through your sms_provider
                        return self._send(200, {"replied": bool(agent.sms_via_provider(ev.get("from") or (ev.get("customer") or {}).get("phone"), ev.get("body", "")))})
                    return self._send(200, agent.handle_event(ev) if ev else {"ignored": True})
                if p in ("/twilio/sms", "/twilio/call", "/twilio/call/menu", "/twilio/status"):
                    params = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True).items()}
                    if not agent.twilio.check_signature(self._public(), params, self.headers.get("X-Twilio-Signature", "")):
                        return self._send(403, {"error": "bad_signature"})
                    if p == "/twilio/status":
                        return self._send(200, agent.handle_delivery(params))
                    if p == "/twilio/sms":
                        from .connectors.twilio import twiml_message
                        reply = agent.handle_sms(params)
                        return self._send(200, twiml_message(reply) if reply else "<Response></Response>", "text/xml")
                    return self._send(200, agent.handle_call(params, "start" if p == "/twilio/call" else "menu", params.get("Digits", "")), "text/xml")
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
    return srv
