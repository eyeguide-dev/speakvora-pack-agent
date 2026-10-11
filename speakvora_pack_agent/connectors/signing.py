"""Signatures for webhooks between your app and the agent: hex HMAC-SHA256 of '<timestamp>.<body>' with the shared secret, in headers X-SV-Timestamp and X-SV-Signature (as 'sha256=<hex>'). Five minutes of clock skew allowed."""
import hashlib, hmac, time


def sign(secret, body, ts=None):
    ts = str(int(ts or time.time()))
    mac = hmac.new(secret.encode(), ts.encode() + b"." + (body if isinstance(body, bytes) else body.encode()), hashlib.sha256).hexdigest()
    return {"X-SV-Timestamp": ts, "X-SV-Signature": "sha256=" + mac}


def verify(secret, body, headers, now=None, tolerance=300):
    h = {k.lower(): v for k, v in headers.items()}
    ts, sig = h.get("x-sv-timestamp", ""), h.get("x-sv-signature", "")
    if not secret or not ts.isdigit() or abs((now or time.time()) - int(ts)) > tolerance:
        return False
    want = sign(secret, body, ts)["X-SV-Signature"]
    return hmac.compare_digest(want, sig)
