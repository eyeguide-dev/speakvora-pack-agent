"""Several business locations in ONE dashboard (for commercial bundles).
Every location runs its own agent: its own bundle copy and licence, its own phone number, settings and data, so one branch's opt-outs, limits and keys never leak into another. This agent keeps a short list of the other locations
and gives the dashboard a drop-down at the top: pick a location and its own dashboard opens through THIS one (the browser only ever talks to this agent). Nothing is shared between locations except what you look at.
Each business location needs its own licence (see https://speakvora.com/pack-license). The agent cannot check licences offline: this is an honour-system reminder, shown in Settings.
Config in agent.json: "locations": {"enabled": false, "this_name": "Downtown", "others": [{"id": "uptown", "name": "Uptown", "url": "http://192.168.1.20:8788"}]}. Access tokens live in agent-state/secrets.json (mode 600), never in agent.json."""
import concurrent.futures as cf, hmac, hashlib, json, re, urllib.error, urllib.request
from urllib.parse import urlparse

from . import connect as SU, licence as LIC, secrets_store

MAX_LOCATIONS = 60
ATTENTION = ("needs_approval", "proposed", "needs_review", "failed", "expired", "undelivered")


class LocationError(ValueError):
    pass


def _cfg(agent):
    return (agent.cfg.get("locations") or {})


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:30]
    if not s:
        raise LocationError("Give the location a name.")
    return s


def _secret_name(lid):
    return "LOC_" + re.sub(r"[^A-Z0-9]+", "_", lid.upper()) + "_TOKEN"


def _token(agent, lid):
    import os
    n = _secret_name(lid)
    return os.environ.get(n) or secrets_store.read(agent.state.dir).get(n, "")


def licence_status(agent):
    return LIC.check((agent.cfg.get("licence") or {}).get("code"), str(agent.pack.meta.get("pack", "")), agent.now())


def _need_licence(agent):
    st = licence_status(agent)
    if not st["valid"]:
        raise LocationError("The location menu is part of the commercial licence (two or more business locations). " + st["message"])
    return st


def set_licence(agent, code):
    """Saves a commercial licence code after checking it offline. An empty code removes it."""
    code = str(code or "").strip()
    st = LIC.check(code, str(agent.pack.meta.get("pack", "")), agent.now()) if code else None
    if code and not st["valid"]:
        raise LocationError(st["message"])
    raw = SU._raw(agent); raw["licence"] = {"code": code} if code else {}
    if not code:
        raw.setdefault("locations", {})["enabled"] = False
    SU._write_raw(agent, raw); SU._reload(agent)
    return view(agent)


def view(agent):
    """What the page needs to draw the drop-down before any location is contacted."""
    c = _cfg(agent); lic = licence_status(agent)
    return {"licence": {"state": lic["state"], "locations": lic["locations"], "until": lic["until"], "message": lic["message"], "valid": lic["valid"]}, "enabled": bool(c.get("enabled")) and lic["valid"], "this_name": str(c.get("this_name") or agent.cfg.get("business") or "This location"),
            "others": [{"id": o["id"], "name": o["name"], "url": o["url"]} for o in c.get("others", [])]}


def _fetch(url, token, path, timeout=4):
    rq = urllib.request.Request(url.rstrip("/") + path, headers={"x-dashboard-token": token, "accept": "application/json"})
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, OSError, ValueError):
        return 0, {}


def _digest(s, name=None):
    """The short facts about one agent that the drop-down and the overview show."""
    counts = s.get("counts") or {}
    att = s.get("attention") or []
    return {"name": name, "online": True, "live": s.get("mode") == "live", "paused": bool(s.get("paused")), "needs_you": sum(1 for j in att if j.get("needs_you")), "problems": sum(1 for j in att if not j.get("needs_you")),
            "waiting": int(counts.get("queued", 0)), "sent": int(counts.get("sent", 0)) + int(counts.get("delivered", 0)), "pack": (s.get("pack") or {}).get("title", ""), "needs_setup": not (s.get("setup") or {}).get("business_complete", True)}


def status_all(agent):
    """[{id, name, self, online, live, paused, needs_you, problems, waiting, ...}] for this agent and the others (contacted in parallel, 4 seconds each)."""
    from . import dashboard
    _need_licence(agent)
    me = view(agent)
    mine = _digest(dashboard.summary(agent), me["this_name"]); out = [{"id": "this", "self": True, **mine}]
    def one(o):
        code, s = _fetch(o["url"], _token(agent, o["id"]), "/dash/api/summary")
        if code == 200:
            return {"id": o["id"], "self": False, **_digest(s, o["name"]), "url": o["url"]}
        why = {0: "Cannot reach it. Is its agent running?", 401: "Its access token was not accepted.", 403: "It only opens on its own computer. On that agent set dashboard.allow_remote to true."}.get(code, f"It answered with an error ({code}).")
        return {"id": o["id"], "self": False, "name": o["name"], "online": False, "live": False, "paused": False, "needs_you": 0, "problems": 0, "waiting": 0, "sent": 0, "pack": "", "needs_setup": False, "url": o["url"], "error": why}
    others = me["others"]
    if others:
        with cf.ThreadPoolExecutor(min(8, len(others))) as ex:
            out += list(ex.map(one, others))
    return {"enabled": me["enabled"], "locations": out, "licence_note": "Each business location needs its own licence: https://speakvora.com/pack-license", "count": len(out)}


def _validate_url(url):
    u = str(url or "").strip().rstrip("/")
    if u and "://" not in u:
        u = "http://" + u                                             # a bare address such as 192.168.1.20:8787 is fine
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ("", "/"):
        raise LocationError("Type the address of that location's dashboard, for example 192.168.1.20:8787 (no path).")
    return u


def test(agent, url, token):
    url = _validate_url(url)
    code, s = _fetch(url, str(token or "").strip(), "/dash/api/summary", 6)
    if code == 200:
        return {"ok": True, "message": "Connected: " + ((s.get("pack") or {}).get("title") or "that agent") + (" (live)" if s.get("mode") == "live" else " (practice mode).")}
    why = {0: "Cannot reach that address. Check it and that the agent is running there.", 401: "That access token was not accepted. Copy it from the address that agent printed when it started (the part after #token=).",
           403: "That agent only opens on its own computer. On that computer set dashboard.allow_remote to true in its agent.json, restart it, and keep it on your private network."}.get(code, f"It answered with an error ({code}).")
    return {"ok": False, "message": why}


def add(agent, name, url, token, force=False):
    lic = _need_licence(agent)
    name = str(name or "").strip()[:60]
    if not name:
        raise LocationError("Give the location a name.")
    lid = _slug(name)
    if lid in ("this", "main-self"):
        raise LocationError("Choose a different name.")
    r = test(agent, url, token)
    if not r["ok"] and not force:
        raise LocationError(r["message"])
    raw = SU._raw(agent); loc = raw.setdefault("locations", {})
    others = [o for o in loc.get("others", []) if o["id"] != lid]
    if len(others) >= MAX_LOCATIONS:
        raise LocationError("That is the most locations one dashboard lists.")
    if len(others) + 2 > max(2, int(lic["locations"])):
        raise LocationError(f"Your licence covers {lic['locations']} locations (this one plus {int(lic['locations']) - 1}). Add a location licence in your Speakvora account, then paste the new code in Settings.")
    others.append({"id": lid, "name": name, "url": _validate_url(url)}); loc["others"] = others; loc["enabled"] = True
    SU._write_raw(agent, raw); secrets_store.set_value(agent.state.dir, _secret_name(lid), str(token or "").strip()); SU._reload(agent)
    return {"added": lid, "test": r, "locations": view(agent)}


def remove(agent, lid):
    raw = SU._raw(agent); loc = raw.setdefault("locations", {}); loc["others"] = [o for o in loc.get("others", []) if o["id"] != lid]
    SU._write_raw(agent, raw); secrets_store.set_value(agent.state.dir, _secret_name(lid), ""); SU._reload(agent)
    return view(agent)


def set_enabled(agent, on, this_name=None):
    if on:
        _need_licence(agent)
    raw = SU._raw(agent); loc = raw.setdefault("locations", {}); loc["enabled"] = bool(on)
    if this_name is not None:
        loc["this_name"] = str(this_name).strip()[:60]
    SU._write_raw(agent, raw); SU._reload(agent)
    return view(agent)


# ---- opening another location's dashboard through this one --------------------------------------------------------------------------------
def session_cookie(token):
    return hmac.new(token.encode(), b"svloc", hashlib.sha256).hexdigest()[:40]


BAR = ('<div style="position:sticky;top:0;z-index:70;display:flex;gap:12px;align-items:center;justify-content:space-between;padding:10px 16px;background:#1c1a17;color:#fff;font:600 14px system-ui,sans-serif">'
       '<a href="/dashboard" style="color:#ffb454;text-decoration:none">&larr; Back to {home}</a><span>Viewing: {name}</span></div>')


def proxy(agent, lid, method, rest, body=b""):
    """(status, body, content type) from another location's dashboard. Only locations in this agent's own list can be reached. The page's own API calls are pointed back through this agent."""
    if not licence_status(agent)["valid"]:
        return 403, b'{"error":"licence_required"}', "application/json"
    o = next((x for x in _cfg(agent).get("others", []) if x["id"] == lid), None)
    if not o:
        return 404, b'{"error":"unknown_location"}', "application/json"
    if not (rest == "/dashboard" or rest.startswith("/dash/api/")):
        return 404, b'{"error":"not_found"}', "application/json"
    rq = urllib.request.Request(o["url"].rstrip("/") + rest, data=body if method == "POST" else None, method=method,
                                headers={"x-dashboard-token": _token(agent, lid), "content-type": "application/json", "accept": "*/*"})
    try:
        with urllib.request.urlopen(rq, timeout=15) as r:
            code, data, ctype = r.status, r.read(), r.headers.get("content-type", "application/octet-stream")
    except urllib.error.HTTPError as e:
        code, data, ctype = e.code, e.read(), e.headers.get("content-type", "application/json")
    except (urllib.error.URLError, OSError):
        return 502, json.dumps({"error": "unreachable", "message": "That location's agent did not answer. Is it running?"}).encode(), "application/json"
    if rest == "/dashboard" and code == 200:
        page = data.decode("utf-8", "replace").replace("'/dash/api", f"'/loc/{lid}/dash/api").replace('"/dash/api', f'"/loc/{lid}/dash/api')
        page = page.replace("<body>", "<body>" + BAR.format(home=_esc(view(agent)["this_name"]), name=_esc(o["name"])), 1)
        data = page.encode()
    return code, data, ctype


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
