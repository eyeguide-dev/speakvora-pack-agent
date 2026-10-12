"""Fake Twilio, Slack and Google servers on localhost for the tests and the demo. They record every request and answer like the real services."""
import json, re, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs


class Mock:
    def __init__(self):
        self.requests, self.events, self.fail = [], [], {}
        mock = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def handle_any(self):
                raw = self.rfile.read(int(self.headers.get("content-length") or 0))
                ctype = self.headers.get("content-type", "")
                data = parse_qs(raw.decode("utf-8", "replace")) if "x-www-form-urlencoded" in ctype else None
                body = json.loads(raw) if "json" in ctype and raw else None
                req = {"method": self.command, "path": self.path.split("?")[0], "query": self.path.partition("?")[2], "form": {k: v[0] for k, v in (data or {}).items()}, "json": body, "auth": self.headers.get("authorization", ""), "headers": {k.lower(): v for k, v in self.headers.items()}, "raw": raw}
                mock.requests.append(req)
                for rx, code in mock.fail.items():
                    if re.search(rx, req["path"]):
                        return self.reply(code, {"error": "forced failure"})
                self.reply(*mock.route(req))

            def reply(self, code, obj):
                b = json.dumps(obj).encode(); self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
            do_GET = do_POST = handle_any

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def route(self, r):
        p = r["path"]
        if p.endswith("/Messages.json"):
            return 201, {"sid": "SM" + str(len(self.requests))}
        if p.endswith("/Calls.json"):
            return 201, {"sid": "CA" + str(len(self.requests))}
        if p.endswith("/chat.postMessage"):
            return 200, {"ok": True, "ts": "1.1"}
        if p.endswith("/files.getUploadURLExternal"):
            return 200, {"ok": True, "upload_url": self.url + "/slack-upload/1", "file_id": "F123"}
        if p.startswith("/slack-upload"):
            return 200, {}
        if p.endswith("/files.completeUploadExternal"):
            return 200, {"ok": True}
        if p.startswith("/my-app"):
            return 200, {"ok": 1}
        if p == "/api/v1/packs" and r["method"] == "GET":
            return 200, {"packs": [{"id": "t", "version": getattr(self, "latest_version", "2026.10.01"), "phrases": 500}]}
        if p.endswith("/IncomingPhoneNumbers.json"):
            return 200, {"incoming_phone_numbers": [] if getattr(self, "no_numbers", False) else [{"sid": "PN1"}]}
        if re.search(r"/Accounts/[^/]+\.json$", p) and r["method"] == "GET":
            return 200, {"friendly_name": "Bella Co", "status": "active"}
        if p.endswith("/auth.test"):
            return 200, {"ok": not getattr(self, "bad_slack", False), "team": "Bella Team"}
        if p.endswith("/chat/completions"):
            return 200, {"choices": [{"message": {"content": getattr(self, "model_text", "{}")}}], "usage": {"prompt_tokens": 10, "completion_tokens": 20}}
        if p.endswith("/v1/messages"):
            return 200, {"content": [{"type": "text", "text": getattr(self, "model_text", "{}")}], "usage": {"input_tokens": 10, "output_tokens": 20}}
        if p.endswith("/packs/slot-requests"):
            return 200, {"queued": len((r["json"] or {}).get("slots", [])), "already_queued_or_built": 0, "note": "Queued. They arrive in the next pack version."}
        if p == "/token":
            return 200, {"access_token": "ya29.test", "expires_in": 3600}
        if p.endswith("/events") and r["method"] == "GET":
            return 200, {"items": self.events}
        if p.endswith("/events") and r["method"] == "POST":
            return 200, {"id": "newev"}
        if p.startswith("/teams-hook"):
            return 200, {"ok": 1}
        if p.endswith("/calendarView"):
            return 200, {"value": getattr(self, "graph_events", [])}
        if p.endswith("/tickets") and r["method"] == "POST":
            return 201, {"id": "T-100"}
        if p.startswith("/ics"):
            return 200, {}
        return 404, {"error": "unknown"}

    def calls(self, suffix):
        return [r for r in self.requests if r["path"].endswith(suffix)]

    def close(self):
        self.srv.shutdown()
