"""One small helper for every outgoing web call (standard library only). Sends are never retried automatically, so a timeout can never turn into a double text."""
import json, urllib.error, urllib.parse, urllib.request


class HttpError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {str(body)[:200]}")
        self.status, self.body = status, body


def request(method, url, headers=None, form=None, body=None, raw=None, timeout=15):
    data, h = None, dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form, doseq=True).encode(); h.setdefault("content-type", "application/x-www-form-urlencoded")
    elif body is not None:
        data = json.dumps(body).encode(); h.setdefault("content-type", "application/json")
    elif raw is not None:
        data = raw
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", "replace"); st = r.status
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode("utf-8", "replace"))
    except urllib.error.URLError as e:
        raise HttpError(0, str(e.reason))
    try:
        return st, json.loads(txt) if txt.strip().startswith(("{", "[")) else txt
    except ValueError:
        return st, txt
