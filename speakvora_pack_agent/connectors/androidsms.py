"""Texts through your own Android phone and its SIM, using the open-source SMS Gateway for Android app (github.com/capcom6/android-sms-gateway). No carrier registration: the message leaves your phone like one you typed.
Cloud mode (default) reaches the phone through the app's relay at api.sms-gate.app; local mode talks to the phone on your own network (set base_url to http://PHONE-IP:8080). Inbound texts arrive as signed webhooks.
Each phone is one line (Front desk, Billing...): a message to a customer leaves from the line you name, and a reply leaves from the line the customer texted."""
import hashlib, hmac, time
from base64 import b64encode

from .. import web as http

CLOUD = "https://api.sms-gate.app/3rdparty/v1"


class AndroidSms:
    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.base = str(self.cfg.get("base_url") or CLOUD).rstrip("/")
        self.user, self.password, self.signing_key = self.cfg.get("username", ""), self.cfg.get("password", ""), self.cfg.get("signing_key", "")
        self.lines = {str(k): str(v) for k, v in (self.cfg.get("lines") or {}).items() if v}
        for part in str(self.cfg.get("lines_text") or "").replace("\n", ",").split(","):          # "Front desk=DEVICEID, Billing=DEVICEID" typed in the dashboard
            if "=" in part and part.split("=", 1)[1].strip():
                self.lines[part.split("=", 1)[0].strip()] = part.split("=", 1)[1].strip()
        self.configured = bool(self.user and self.password and not str(self.user).startswith("env:") and not str(self.password).startswith("env:"))

    def _h(self):
        return {"authorization": "Basic " + b64encode(f"{self.user}:{self.password}".encode()).decode()}

    def device_for(self, line=None):
        """The phone to send from: the named line, else the default phone, else none (the app then uses its only/first phone)."""
        if line and line in self.lines:
            return self.lines[line]
        d = str(self.cfg.get("device_id") or ""); return d or (next(iter(self.lines.values())) if len(self.lines) == 1 else "")

    def line_for(self, device_id):
        return next((k for k, v in self.lines.items() if v == device_id), "")

    def send(self, to, text, line=None, idem=None):
        body = {"textMessage": {"text": text}, "phoneNumbers": [to]}
        dev = self.device_for(line)
        if dev:
            body["deviceId"] = dev
        if idem:
            body["id"] = str(idem)[:36]
        st, r = http.request("POST", self.base + "/message", self._h(), body=body)
        if st not in (200, 201, 202):
            raise http.HttpError(st, r)
        return {"sid": (r or {}).get("id", "") if isinstance(r, dict) else ""}

    def devices(self):
        st, r = http.request("GET", self.base + ("/devices" if self.base == CLOUD or "/3rdparty/" in self.base else "/health"), self._h())
        return r

    def register_webhook(self, url):
        """Tells the phone app to post every received text to this address (the same id replaces the old one)."""
        st, r = http.request("POST", self.base + "/webhooks", self._h(), body={"id": "speakvora-sms", "url": url, "event": "sms:received"})
        if st not in (200, 201, 202):
            raise http.HttpError(st, r)
        return r

    def verify(self, raw, timestamp, signature, now=None):
        """Signed webhook check: HMAC-SHA256 over the body plus the timestamp, five minutes of slack. No signing key saved means nothing is accepted."""
        if not (self.signing_key and signature and timestamp):
            return False
        try:
            if abs((now or time.time()) - int(timestamp)) > 300:
                return False
        except ValueError:
            return False
        want = hmac.new(self.signing_key.encode(), raw + str(timestamp).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, signature.strip().lower())

    def parse(self, payload):
        """A received-text webhook -> {'from', 'body', 'line'}, or None for any other event."""
        if (payload or {}).get("event") != "sms:received":
            return None
        p = payload.get("payload") or {}
        if not (p.get("sender") and p.get("message")):
            return None
        return {"from": p["sender"], "body": p["message"], "line": self.line_for(payload.get("deviceId", "")), "id": p.get("messageId", ""), "own": p.get("recipient") or ""}
