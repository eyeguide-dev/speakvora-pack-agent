"""WhatsApp Business through Meta's own Cloud API (no Twilio). Needs a Meta developer app with a WhatsApp phone number, its access token, and the app secret to check webhook signatures. A business can reply freely for 24 hours after a customer
messages it; starting a conversation outside that window needs an approved template, which this connector does not send. Voice calls are not handled here."""
import hashlib, hmac

from .. import web as http


class WhatsApp:
    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.token, self.phone_id = self.cfg.get("access_token", ""), str(self.cfg.get("phone_number_id", ""))
        self.verify_token, self.app_secret = self.cfg.get("verify_token", ""), self.cfg.get("app_secret", "")
        self.base = str(self.cfg.get("api_base") or "https://graph.facebook.com").rstrip("/") + "/" + (self.cfg.get("api_version") or "v21.0")
        self.configured = bool(self.token and self.phone_id) and not str(self.token).startswith("env:")

    def _h(self):
        return {"authorization": "Bearer " + self.token}

    def me(self):
        st, r = http.request("GET", f"{self.base}/{self.phone_id}?fields=display_phone_number,verified_name", self._h())
        return r

    def subscribe_account(self):
        """Meta only sends an app the messages of a WhatsApp Business Account the app is subscribed to. Without this a published app with a verified webhook still hears nothing."""
        waba = str(self.cfg.get("waba_id") or "")
        if not waba:
            return False
        st, r = http.request("POST", f"{self.base}/{waba}/subscribed_apps", self._h(), body={})
        if st not in (200, 201):
            raise http.HttpError(st, r)
        return True

    @staticmethod
    def token_expired(exc):
        """Meta answers 401 / error code 190 when the access token is expired, revoked or wrong."""
        return isinstance(exc, http.HttpError) and (exc.status == 401 or (exc.status == 400 and '"code":190' in str(exc.body).replace(" ", "")))

    def send(self, to, text, idem=None):
        st, r = http.request("POST", f"{self.base}/{self.phone_id}/messages", self._h(),
                             body={"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text", "text": {"body": text[:4000]}})
        if st not in (200, 201):
            raise http.HttpError(st, r)
        return {"sid": (((r or {}).get("messages") or [{}])[0]).get("id", "") if isinstance(r, dict) else ""}

    def handshake(self, query):
        """Meta's one-time webhook check (a GET): echo hub.challenge when the verify token matches, else None."""
        q = {k: (v[0] if isinstance(v, list) else v) for k, v in query.items()}
        if self.verify_token and q.get("hub.mode") == "subscribe" and hmac.compare_digest(self.verify_token, q.get("hub.verify_token", "")):
            return q.get("hub.challenge", "")
        return None

    def verify(self, raw, header):
        if not (self.app_secret and header and header.startswith("sha256=")):
            return False
        return hmac.compare_digest("sha256=" + hmac.new(self.app_secret.encode(), raw, hashlib.sha256).hexdigest(), header)

    def parse(self, payload):
        """-> list of {'from': '+digits', 'body'} for each text message in the webhook (statuses and media are ignored)."""
        out = []
        for e in (payload or {}).get("entry") or []:
            for ch in e.get("changes") or []:
                v = ch.get("value") or {}
                if str((v.get("metadata") or {}).get("phone_number_id", self.phone_id)) != self.phone_id:
                    continue
                for m in v.get("messages") or []:
                    if m.get("type") == "text" and m.get("from"):
                        out.append({"from": "+" + m["from"], "body": (m.get("text") or {}).get("body", "")})
                    elif m.get("from") and m.get("type") in ("image", "audio", "voice", "video", "document", "sticker", "location", "contacts"):
                        out.append({"from": "+" + m["from"], "body": "", "unsupported": m["type"]})
        return out
