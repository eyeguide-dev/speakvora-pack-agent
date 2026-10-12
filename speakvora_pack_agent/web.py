"""One small helper for every outgoing web call (standard library only). Sends are never retried automatically, so a timeout can never turn into a double text."""
import errno, json, socket, urllib.error, urllib.parse, urllib.request

NOT_SENT_ERRNOS = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN, errno.ECONNREFUSED, errno.EADDRNOTAVAIL}


class HttpError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {str(body)[:200]}")
        self.status, self.body = status, body


class NetworkDown(HttpError):
    """The request provably never left this machine (no route, DNS failed, connection refused), so it is safe to try again later. A timeout is NOT this: the other side may have received it."""
    def __init__(self, reason):
        super().__init__(0, str(reason))


def is_offline(exc):
    """True only when the failure proves nothing was sent (works for urllib, smtplib and raw sockets)."""
    if isinstance(exc, NetworkDown):
        return True
    if isinstance(exc, urllib.error.URLError) and not isinstance(exc, urllib.error.HTTPError):
        exc = exc.reason if isinstance(exc.reason, BaseException) else exc
    if isinstance(exc, socket.timeout):
        return False
    return isinstance(exc, socket.gaierror) or isinstance(exc, ConnectionRefusedError) or (isinstance(exc, OSError) and exc.errno in NOT_SENT_ERRNOS)


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
        if is_offline(e):
            raise NetworkDown(e.reason)
        raise HttpError(0, str(e.reason))
    try:
        return st, json.loads(txt) if txt.strip().startswith(("{", "[")) else txt
    except ValueError:
        return st, txt
