"""The universal connector. Any system that can send a webhook (Shopify, Calendly, Square, Toast, a booking tool, your own app) is connected by writing a small mapping in agent.json, no code:

  "sources": [{"name": "shopify", "path": "/hook/shopify",
               "auth": {"type": "hmac", "header": "X-Shopify-Hmac-Sha256", "secret": "env:SHOPIFY_SECRET", "encoding": "base64"},
               "map": {"event": {"from": "headers.x-shopify-topic", "values": {"orders/fulfilled": "order.ready"}},
                       "id": "payload.id", "customer.name": "payload.customer.first_name", "customer.phone": "payload.customer.phone",
                       "customer.sms_consent": {"from": "payload.customer.sms_marketing_consent.state", "values": {"subscribed": true}, "default": false},
                       "order.number": "payload.order_number"}}]

Every target is a path in the event the agent understands (event, id, customer.*, order.*, ...). A source is a path into the incoming request: payload.x.y (the JSON body), headers.name, query.name,
or {"const": value}; {"from": ..., "values": {...}, "default": ...} translates values. Auth types: sv_hmac (our own signature), hmac (a header with an HMAC of the body, hex or base64), stripe_style (t=..,v1=.. like Stripe and Calendly),
bearer (Authorization: Bearer ...). A source with no auth is refused unless the agent is in dry-run."""
import base64, hashlib, hmac, time

from .connectors import signing


def get_path(root, path):
    cur = root
    for part in str(path).split("."):
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
            elif part.lower() in cur:
                cur = cur[part.lower()]
            else:
                return None
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


def pick(spec, req):
    if isinstance(spec, str):
        return get_path(req, spec)
    if "const" in spec:
        return spec["const"]
    if "template" in spec:                                   # build one value from several: "{{headers.x-github-event}}.{{payload.action}}"
        from . import templating
        v = templating.render(spec["template"], req)
    else:
        v = get_path(req, spec.get("from", ""))
    if v is None or v == "":
        return spec.get("default")
    vals = spec.get("values")
    if vals is not None:
        k = str(v)
        if k not in vals and "template" in spec:                       # a part the sender left out (GitHub's workflow_run conclusion on an issue) leaves a dangling dot: try without it
            k = k.strip(".")
        return vals.get(k, vals.get(v, spec.get("default")))
    return v


def set_path(out, path, value):
    parts = path.split("."); cur = out
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def map_request(source, req):
    """req = {'payload': json body, 'headers': {lowercased}, 'query': {...}} -> the agent's event dict (or None if the source says 'ignore this one')."""
    out = {}
    for target, spec in (source.get("map") or {}).items():
        v = pick(spec, req)
        if v is not None:
            set_path(out, target, v)
    if not out.get("event") and source.get("as") != "sms":
        return None
    out.setdefault("id", f"{source['name']}-{hashlib.sha256(repr(req['payload']).encode()).hexdigest()[:16]}")
    out["id"] = str(out["id"]); out["source"] = source["name"]
    return out


def authorised(source, raw, headers, now=None):
    a = source.get("auth") or {}
    t, secret = a.get("type", ""), a.get("secret") or a.get("token") or ""
    h = {k.lower(): v for k, v in headers.items()}
    if t == "sv_hmac":
        return signing.verify(secret, raw, h, now)
    if not secret:
        return False
    if t == "bearer":
        return hmac.compare_digest(h.get("authorization", ""), "Bearer " + secret)
    if t == "token_header":                                   # GitLab: the header carries the shared secret itself
        return hmac.compare_digest(h.get(a.get("header", "").lower(), ""), secret)
    if t == "hmac":
        digest = hmac.new(secret.encode(), raw, getattr(hashlib, a.get("algo", "sha256"))).digest()
        want = a.get("prefix", "") + (base64.b64encode(digest).decode() if a.get("encoding", "hex") == "base64" else digest.hex())
        return any(hmac.compare_digest(want, c.strip()) for c in h.get(a.get("header", "").lower(), "").split(","))
    if t == "stripe_style":
        parts = dict(p.split("=", 1) for p in h.get(a.get("header", "").lower(), "").split(",") if "=" in p)
        ts, sig = parts.get("t", ""), parts.get(a.get("sig_key", "v1"), "")
        if not ts.isdigit() or abs((now or time.time()) - int(ts)) > int(a.get("tolerance", 300)):
            return False
        return hmac.compare_digest(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest(), sig)
    return False
