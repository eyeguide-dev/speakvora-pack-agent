"""Email through your own SMTP account (Gmail needs an app password). Can attach a pack clip."""
import os, smtplib
from email.message import EmailMessage


class Email:
    def __init__(self, cfg):
        self.cfg = cfg
        self.configured = all(cfg.get(k) for k in ("host", "username", "password", "from"))

    def send(self, to, subject, text, attach=None):
        m = EmailMessage(); m["From"], m["To"], m["Subject"] = self.cfg["from"], to, subject.replace("\n", " ")[:200]
        m.set_content(text)
        if attach:
            sub = "mpeg" if attach.endswith(".mp3") else "mp4" if attach.endswith(".m4a") else "wav"
            m.add_attachment(open(attach, "rb").read(), maintype="audio", subtype=sub, filename=os.path.basename(attach))
        port = int(self.cfg.get("port", 465))
        s = smtplib.SMTP_SSL(self.cfg["host"], port, timeout=20) if port == 465 else smtplib.SMTP(self.cfg["host"], port, timeout=20)
        try:
            if port != 465:
                s.starttls()
            s.login(self.cfg["username"], self.cfg["password"]); s.send_message(m)
        finally:
            s.quit()
        return {"ok": True}
