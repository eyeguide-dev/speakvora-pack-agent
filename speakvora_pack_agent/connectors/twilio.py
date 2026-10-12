"""Twilio: send a text, place a call that plays pack audio, answer inbound calls and texts (TwiML), and check Twilio's request signature."""
import base64, hashlib, hmac
from xml.sax.saxutils import escape, quoteattr

from .. import web as http


class Twilio:
    def __init__(self, cfg):
        self.sid, self.token, self.from_number = cfg.get("account_sid", ""), cfg.get("auth_token", ""), cfg.get("from_number", "")
        self.base = cfg.get("api_base", "https://api.twilio.com").rstrip("/")
        self.configured = bool(self.sid and self.token and self.from_number)
        self.status_url = ""

    def _auth(self, idem=None):
        h = {"authorization": "Basic " + base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()}
        if idem:                                                          # best effort: Twilio's idempotency token header. Our own guarantee is the job journal, not this header.
            h["I-Twilio-Idempotency-Token"] = idem
        return h

    def sms(self, to, body, media_url=None, from_=None, idem=None):
        form = {"To": to, "From": from_ or self.from_number, "Body": body[:1500]}
        if media_url:
            form["MediaUrl"] = media_url
        if self.status_url:
            form["StatusCallback"] = self.status_url
        return http.request("POST", f"{self.base}/2010-04-01/Accounts/{self.sid}/Messages.json", self._auth(idem), form=form)[1]

    def call(self, to, twiml, idem=None):
        return http.request("POST", f"{self.base}/2010-04-01/Accounts/{self.sid}/Calls.json", self._auth(idem), form={"To": to, "From": self.from_number, "Twiml": twiml, **({"StatusCallback": self.status_url, "StatusCallbackEvent": "completed"} if self.status_url else {})})[1]

    def check_signature(self, url, params, signature):
        data = url + "".join(k + str(params[k]) for k in sorted(params))
        want = base64.b64encode(hmac.new(self.token.encode(), data.encode(), hashlib.sha1).digest()).decode()
        return bool(signature) and hmac.compare_digest(want, signature)


def twiml_play(urls, then_hangup=True):
    return "<Response>" + "".join(f"<Play>{escape(u)}</Play>" for u in urls) + ("<Hangup/>" if then_hangup else "") + "</Response>"


def twiml_menu(prompt_urls, action_url, say_fallback="", digits=1, pre=()):
    lead = "".join(f"<Play>{escape(v)}</Play>" if k == "play" else f"<Say>{escape(v)}</Say>" for k, v in pre)
    inner = "".join(f"<Play>{escape(u)}</Play>" for u in prompt_urls) or (f"<Say>{escape(say_fallback)}</Say>" if say_fallback else "")
    return f'<Response>{lead}<Gather input="dtmf" numDigits="{digits}" action={quoteattr(action_url)} method="POST" timeout="6">{inner}</Gather></Response>'


def twiml_message(text):
    return f"<Response><Message>{escape(text)}</Message></Response>"


def twiml_parts(parts, hangup=True):
    """parts: [('play', url) | ('say', text)] spoken in order. A required notice that has no audio yet is spoken with the provider's own voice so it is never skipped."""
    return "<Response>" + "".join(f"<Play>{escape(v)}</Play>" if k == "play" else f"<Say>{escape(v)}</Say>" for k, v in parts) + ("<Hangup/>" if hangup else "") + "</Response>"
