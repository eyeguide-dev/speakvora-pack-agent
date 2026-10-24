"""Fake Twilio, Slack and Google servers on localhost for the tests and the demo. They record every request and answer like the real services."""
import json, re, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs


class Mock:
    def __init__(self):
        self.requests, self.events, self.fail = [], [], {}
        self.cal = {}                                                    # events made through the fake Google Calendar: id -> event
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
                b = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode(); self.send_response(code); self.send_header("content-type", "text/calendar" if isinstance(obj, str) else "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
            do_GET = do_POST = do_PATCH = do_DELETE = handle_any

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
            return 200, {"ok": True, "ts": "1.1", "channel": "C0FRONT"}
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
            return 200, {"incoming_phone_numbers": [] if getattr(self, "no_numbers", False) else [{"sid": "PN1", **getattr(self, "twilio_num", {})}]}
        if re.search(r"/IncomingPhoneNumbers/[^/]+\.json$", p) and r["method"] == "POST":
            f = r.get("form") or {}; st = self.__dict__.setdefault("twilio_num", {})
            st.update({k: v for k, v in (("voice_url", f.get("VoiceUrl")), ("voice_fallback_url", f.get("VoiceFallbackUrl"))) if v is not None})
            return 200, {"sid": "PN1", "voice_url": f.get("VoiceUrl", "")}
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
            want = [x.split("=", 1) for x in __import__("urllib.parse").parse.parse_qs(r.get("query", "")).get("privateExtendedProperty", [])]
            if want:
                return 200, {"items": [e for e in self.cal.values() if all(((e.get("extendedProperties") or {}).get("private") or {}).get(k) == v for k, v in want)]}
            return 200, {"items": self.events + list(self.cal.values())}
        if p.endswith("/events") and r["method"] == "POST":
            ev = dict(r["json"] or {}); ev["id"] = "ev" + str(len(self.cal) + 1); ev["status"] = "confirmed"; self.cal[ev["id"]] = ev; return 200, ev
        m = re.search(r"/events/([^/]+)$", p)
        if m and r["method"] == "PATCH":
            ev = self.cal.get(m.group(1))
            if not ev:
                return 404, {"error": "gone"}
            ev.update(r["json"] or {}); return 200, ev
        if m and r["method"] == "DELETE":
            if self.cal.pop(m.group(1), None) is None:
                return 404, {"error": "gone"}
            return 204, ""
        if p.startswith("/teams-hook"):
            return 200, {"ok": 1}
        if p.endswith("/calendarView"):
            return 200, {"value": getattr(self, "graph_events", [])}
        if p.endswith("/tickets") and r["method"] == "POST":
            return 201, {"id": "T-100"}
        if p.startswith("/ical"):
            return 200, "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
        if p.startswith("/ics"):
            return 200, {}
        if p == "/android/3rdparty/v1/message" and r["method"] == "POST":
            return 202, {"id": "AM" + str(len(self.requests)), "state": "Pending"}
        if p == "/android/3rdparty/v1/devices":
            return 200, getattr(self, "android_devices", [{"id": "dev1"}])
        if p == "/android/3rdparty/v1/webhooks":
            return 201, {"id": "speakvora-sms"}
        if re.fullmatch(r"/bot[^/]+/sendMessage", p):
            return 200, {"ok": True, "result": {"message_id": 7}}
        if re.fullmatch(r"/bot[^/]+/getUpdates", p):
            ups, self.tg_updates = list(getattr(self, "tg_updates", [])), []
            return 200, {"ok": True, "result": ups}
        if re.fullmatch(r"/bot[^/]+/(getMe|setWebhook|deleteWebhook)", p):
            return 200, {"ok": True, "result": {"username": "bella_bot"} if p.endswith("getMe") else True}
        if re.fullmatch(r"/v21\.0/PID1/messages", p):
            return 200, {"messages": [{"id": "wamid.1"}]}
        if re.fullmatch(r"/v21\.0/WABA1/subscribed_apps", p) and r["method"] == "POST":
            return 200, {"success": True}
        if re.fullmatch(r"/v21\.0/PID1", p):
            return 200, {"display_phone_number": "+1 555-000-2222", "verified_name": "Bella"}
        return 404, {"error": "unknown"}

    def calls(self, suffix):
        return [r for r in self.requests if r["path"].endswith(suffix)]

    def close(self):
        self.srv.shutdown()
