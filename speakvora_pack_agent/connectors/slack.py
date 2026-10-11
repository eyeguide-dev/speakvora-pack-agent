"""Slack: post a message, upload a pack clip, and verify slash-command requests. Use a bot token (chat:write, files:write) or an incoming-webhook URL for text only."""
import hashlib, hmac, os, time

from .. import web as http


class Slack:
    def __init__(self, cfg):
        self.token, self.webhook, self.channel = cfg.get("bot_token", ""), cfg.get("webhook_url", ""), cfg.get("channel", "")
        self.signing_secret = cfg.get("signing_secret", "")
        self.base = cfg.get("api_base", "https://slack.com/api").rstrip("/")
        self.configured = bool(self.token or self.webhook)

    def _h(self):
        return {"authorization": "Bearer " + self.token}

    def post(self, text, channel=None, thread_ts=None):
        if self.token:
            body = {"channel": channel or self.channel, "text": text}
            if thread_ts:
                body["thread_ts"] = thread_ts
            st, r = http.request("POST", f"{self.base}/chat.postMessage", self._h(), body=body)
            if not (isinstance(r, dict) and r.get("ok")):
                raise http.HttpError(st, r)
            return r
        return http.request("POST", self.webhook, body={"text": text})[1]

    def upload(self, channel, path, title, comment=""):
        """Slack's current three-step upload: get an upload URL, send the bytes, finish and share to the channel."""
        data = open(path, "rb").read(); name = os.path.basename(path)
        st, r = http.request("POST", f"{self.base}/files.getUploadURLExternal", self._h(), form={"filename": name, "length": len(data)})
        if not (isinstance(r, dict) and r.get("ok")):
            raise http.HttpError(st, r)
        http.request("POST", r["upload_url"], raw=data, headers={"content-type": "application/octet-stream"})
        st, r2 = http.request("POST", f"{self.base}/files.completeUploadExternal", self._h(),
                              body={"files": [{"id": r["file_id"], "title": title}], "channel_id": channel or self.channel, "initial_comment": comment})
        if not (isinstance(r2, dict) and r2.get("ok")):
            raise http.HttpError(st, r2)
        return r2

    def verify(self, body, timestamp, signature, now=None):
        if not self.signing_secret or not timestamp.isdigit() or abs((now or time.time()) - int(timestamp)) > 300:
            return False
        want = "v0=" + hmac.new(self.signing_secret.encode(), f"v0:{timestamp}:".encode() + body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, signature or "")
