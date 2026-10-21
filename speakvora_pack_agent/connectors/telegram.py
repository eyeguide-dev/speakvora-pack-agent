"""Telegram bot: customers message your bot, the agent answers. Free and instant (Telegram's Bot API). A bot can only reply to people who messaged it first, and it cannot place or answer voice calls: Telegram does not offer that to bots."""
import hmac

from .. import web as http


class Telegram:
    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.token, self.secret = self.cfg.get("bot_token", ""), self.cfg.get("webhook_secret", "")
        self.base = str(self.cfg.get("api_base") or "https://api.telegram.org").rstrip("/")
        self.configured = bool(self.token) and not str(self.token).startswith("env:")

    def _call(self, method, body=None, timeout=15):
        st, r = http.request("POST", f"{self.base}/bot{self.token}/{method}", body=body or {}, timeout=timeout)
        if not (isinstance(r, dict) and r.get("ok")):
            raise http.HttpError(st, r)
        return r["result"]

    def me(self):
        return self._call("getMe")

    def send(self, chat_id, text, idem=None):
        r = self._call("sendMessage", {"chat_id": chat_id, "text": text[:4000]})
        return {"sid": str(r.get("message_id", ""))}

    def updates(self, offset, wait=25):
        """New messages, waiting up to `wait` seconds for one (long polling): how the agent hears customers without a public web address."""
        return self._call("getUpdates", {"offset": offset, "timeout": wait, "allowed_updates": ["message"]}, timeout=wait + 10)

    def delete_webhook(self):
        return self._call("deleteWebhook", {"drop_pending_updates": False})

    def set_webhook(self, url, secret):
        return self._call("setWebhook", {"url": url, "secret_token": secret, "allowed_updates": ["message"], "drop_pending_updates": False})

    def verify(self, header):
        return bool(self.secret) and hmac.compare_digest(self.secret, header or "")

    def parse(self, update):
        """-> {'from': 'tg:<chat id>', 'body', 'name'} for a private text message, else None (groups, stickers and edits are ignored)."""
        m = (update or {}).get("message") or {}
        chat = m.get("chat") or {}
        if chat.get("type") != "private" or not m.get("text") or (m.get("from") or {}).get("is_bot"):
            return None
        return {"from": f"tg:{chat['id']}", "body": m["text"], "name": (m.get("from") or {}).get("first_name", "")}
