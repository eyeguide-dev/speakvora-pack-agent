"""Use the phone and text numbers you already have, with any provider. Twilio is built in. For anything else, describe the provider's web API in agent.json and the agent calls it:

  "sms_provider": {"method": "POST", "url": "https://api.example-carrier.com/v1/messages", "headers": {"Authorization": "Bearer env:CARRIER_TOKEN"},
                   "json": {"from": "+15551234567", "to": "{{to}}", "text": "{{text}}"}, "ok_status": [200, 201, 202]}
  "call_provider": {"method": "POST", "url": "https://api.example-carrier.com/v1/calls", "headers": {...},
                    "json": {"from": "+15551234567", "to": "{{to}}", "twiml": "{{twiml}}"}}

{{to}}, {{text}}, {{twiml}} (TwiML-style call instructions, accepted by Twilio-compatible and TeXML providers), {{audio_urls}} (the list of clips) and {{media_url}} are filled in; the server name must be written out literally."""
import json, re

from . import templating as T, web

HOST_RX = re.compile(r"^https?://[^/{}?#\s]+")


class HttpProvider:
    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.configured = bool(self.cfg.get("url")) and bool(HOST_RX.match(str(self.cfg.get("url", ""))))

    def send(self, **values):
        idem = values.pop("_idem", None)
        c = self.cfg
        def fill(o):
            if isinstance(o, str):
                m = re.fullmatch(r"\{\{\s*(\w+)\s*\}\}", o)
                return values.get(m.group(1), "") if m else T.render(o, values)
            if isinstance(o, dict):
                return {k: fill(v) for k, v in o.items()}
            if isinstance(o, list):
                return [fill(v) for v in o]
            return o
        kw = {"headers": fill(c.get("headers", {}))}
        if idem and c.get("idempotency_header"):                          # providers that document an idempotency header: set "idempotency_header": "Idempotency-Key" in the provider settings
            kw["headers"][c["idempotency_header"]] = idem
        if "json" in c:
            kw["body"] = fill(c["json"])
        elif "form" in c:
            kw["form"] = fill(c["form"])
        st, resp = web.request(c.get("method", "POST").upper(), fill(c["url"]), **kw)
        if st not in c.get("ok_status", [200, 201, 202, 204]):
            raise web.HttpError(st, resp)
        return resp if isinstance(resp, dict) else {"text": resp}
