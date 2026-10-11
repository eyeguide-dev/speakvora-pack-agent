"""Inbound email: reads UNSEEN mail from a folder with IMAP (PEEK, so your mail stays unread) and hands each message to the agent. Gmail/Outlook/iCloud need an app password. Use a dedicated folder or label (for example Support) so personal mail is never read."""
import email as _email, email.policy, imaplib, re, ssl, time
from email.utils import getaddresses


class Inbox:
    def __init__(self, cfg, factory=None):
        self.cfg, self.factory = cfg, factory
        self.configured = all(cfg.get(k) for k in ("host", "username", "password"))

    def fetch(self, limit=10, max_age_days=3):
        out = []
        try:
            m = self.factory(self.cfg) if self.factory else imaplib.IMAP4_SSL(self.cfg["host"], int(self.cfg.get("port", 993)), ssl_context=ssl.create_default_context(), timeout=15)
            m.login(self.cfg["username"], self.cfg["password"])
            if m.select(f'"{self.cfg.get("folder", "INBOX")}"', readonly=True)[0] != "OK":
                return []
            typ, data = m.search(None, "UNSEEN", "SINCE", time.strftime("%d-%b-%Y", time.gmtime(time.time() - max_age_days * 86400)))
            for i in (data[0].split() if typ == "OK" and data and data[0] else [])[-limit:]:
                typ, d = m.fetch(i, "(BODY.PEEK[])")
                if typ != "OK" or not d or not isinstance(d[0], tuple):
                    continue
                msg = _email.message_from_bytes(d[0][1], policy=_email.policy.default)
                frm = getaddresses([str(msg.get("From", ""))]); addr = (frm[0][1] if frm else "").lower()
                if not addr or addr == self.cfg.get("username", "").lower() or msg.get("Auto-Submitted", "no") != "no" or msg.get("Precedence", "") in ("bulk", "list", "junk") or msg.get("List-Unsubscribe"):
                    continue                                                   # never answer our own mail, auto-replies or newsletters
                part = msg.get_body(preferencelist=("plain", "html")); body = part.get_content() if part else ""
                if part is not None and part.get_content_type() == "text/html":
                    body = re.sub(r"<[^>]+>", " ", body)
                out.append({"from": addr, "subject": str(msg.get("Subject", ""))[:200], "body": re.sub(r"\s+", " ", body).strip()[:3000], "message_id": str(msg.get("Message-ID", "")).strip()})
            m.logout()
        except Exception:  # noqa: BLE001
            return out
        return out
