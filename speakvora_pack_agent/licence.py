"""Commercial licence codes for the multi-location dashboard. Buying a licence for two or more business locations gives you a code in your Speakvora account (My packs). Paste it in Settings, Locations.
The agent checks the code OFFLINE with Speakvora's public key (Ed25519): nothing is sent anywhere. Only the location menu depends on it: your bundle, its audio and every workflow keep working without a code, and after your 12-month term
ends the menu stays for 30 more days so you have time to renew. A code names the bundle it was bought for, the number of locations and the day the term ends. (The agent is open source, so this is an honest-use reminder, not copy protection.)"""
import base64, binascii, json, time

from . import ed25519

PUBLIC_KEY = binascii.unhexlify("ac4d46344f8081c40c2917a657f246629ff3a4907f948995d5c5bc812b39fd9c")
GRACE_DAYS = 30
PREFIX = "SVL1"


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64e(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_code(secret, payload):
    """Used by the account server and the tests; the private key never leaves Speakvora's server."""
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"{PREFIX}.{b64e(body)}.{b64e(ed25519.sign(secret, PREFIX.encode() + b'.' + body))}"


def check(code, pack_id="", now=None, public=None):
    """{'valid': bool, 'state': 'valid'|'grace'|'expired'|'wrong_bundle'|'invalid'|'none', 'locations': n, 'until': epoch, 'message': text}"""
    public = public or PUBLIC_KEY
    code = str(code or "").strip()
    if not code:
        return {"valid": False, "state": "none", "locations": 0, "until": 0, "message": "No licence code entered."}
    try:
        pre, b, sg = code.split(".")
        body, sig = _b64d(b), _b64d(sg)
        if pre != PREFIX or not ed25519.verify(public, PREFIX.encode() + b"." + body, sig):
            raise ValueError
        pl = json.loads(body)
        n, until, pk = int(pl["n"]), int(pl["until"]), str(pl.get("pack") or "")
    except (ValueError, KeyError, TypeError, binascii.Error):
        return {"valid": False, "state": "invalid", "locations": 0, "until": 0, "message": "That code is not valid. Copy it again from My packs in your Speakvora account."}
    if pk not in ("", "*") and pack_id and pk != pack_id:
        return {"valid": False, "state": "wrong_bundle", "locations": n, "until": until, "message": f"That code is for a different bundle ({pk})."}
    t = int(now or time.time())
    if t <= until:
        return {"valid": True, "state": "valid", "locations": n, "until": until, "message": f"Licensed for {n} locations until {time.strftime('%B %d, %Y', time.gmtime(until))}."}
    if t <= until + GRACE_DAYS * 86400:
        return {"valid": True, "state": "grace", "locations": n, "until": until, "message": "Your 12-month licence has ended. The location menu keeps working for a few more days: renew in your Speakvora account."}
    return {"valid": False, "state": "expired", "locations": n, "until": until, "message": "Your 12-month licence has ended, so the location menu is hidden. Your bundle and its audio keep working. Renew in your Speakvora account and paste the new code."}
