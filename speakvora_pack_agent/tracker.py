"""Order tracking links, like the ones pizza chains send. By default Speakvora hosts the pages (https://speakvora.com/o/<code>): the agent only pushes the order number, its step and the business's own public details, so the business sets nothing up and customers never depend on its computer being reachable. The customer gets ONE text with a private link; the page behind it shows the order moving through its steps (received, preparing, ready, picked up; or on its way, delivered) and refreshes by itself. No further texts are needed.
The page shows the business name, the order number you give it and the step. Nothing about the customer or what was ordered. The link holds a long random code that cannot be guessed. Every link is saved in agent-state/orders.db when it is made and keeps working (showing the final step) for as long as the agent runs; set tracking.keep_days in agent.json only if you want old ones cleared. Nothing about the customer is saved there: just the order number, the steps and the times.
Without a Speakvora API key the agent can still serve the page itself at public_base_url + /track/<code> (self-hosted mode)."""
import hashlib, html, json, os, secrets, sqlite3, threading, time

from . import sharing

from .trackview import *  # noqa: F401,F403  (the labels, steps and page, shared with the hosted order pages)
from . import trackview as TV


_conns, _lock = {}, threading.RLock()


def _conn(agent):
    """The permanent order list (SQLite, standard library). Created on first use; tracker links from earlier versions are moved in."""
    path = os.path.join(agent.state.dir, "orders.db")
    with _lock:
        c = _conns.get(path)
        if c is None:
            os.makedirs(agent.state.dir, exist_ok=True)
            c = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            c.execute("pragma journal_mode=wal")
            c.execute("create table if not exists orders (token text primary key, order_no text not null, steps text not null, status text not null, created integer not null, updated integer not null, eta text default '', delayed integer default 0, base text default '', history text default '[]')")
            c.execute("create index if not exists orders_no on orders(order_no)"); c.execute("create index if not exists orders_updated on orders(updated)")
            for col in ("pushed integer default 1", "flow text default 'order'"):
                try:
                    c.execute("alter table orders add column " + col)
                except sqlite3.OperationalError:
                    pass
            _conns[path] = c
            old = agent.state.data.get("tracks") or {}
            for tok, r in old.items():
                c.execute("insert or ignore into orders (token,order_no,steps,status,created,updated,eta,delayed,base,history) values (?,?,?,?,?,?,?,?,?,?)", (tok, r["order"], json.dumps(r["steps"]), r["status"], r.get("created", 0), r.get("updated", 0), r.get("eta", ""), int(bool(r.get("delayed"))), "", json.dumps(r.get("history", []))))
            if old:
                with agent.state.lock:
                    agent.state.data.pop("tracks", None); agent.state.save()
        return c


def _row(r):
    return {"token": r[0], "order": r[1], "steps": json.loads(r[2]), "status": r[3], "created": r[4], "updated": r[5], "eta": r[6] or "", "delayed": bool(r[7]), "base": r[8] or "", "history": json.loads(r[9] or "[]")}


def _find(agent, token=None, order=None):
    c = _conn(agent)
    r = c.execute("select * from orders where token=?", (str(token),)).fetchone() if token is not None else c.execute("select * from orders where order_no=? order by created desc limit 1", (str(order),)).fetchone()
    return _row(r) if r else None


def mode(agent):
    """'hosted' (Speakvora serves the page; needs your Speakvora API key) or 'self' (this agent serves it at public_base_url). tracking.mode in agent.json can force one; by default a key means hosted."""
    forced = (agent.cfg.get("tracking") or {}).get("mode")
    if forced in ("hosted", "self"):
        return forced
    base = str(agent.cfg.get("public_base_url", ""))
    return "hosted" if sharing._key(agent) or not base or "YOUR-" in base else "self"


def set_status(agent, order, status, delivery=False, delayed=None, eta=None, flow="order"):
    """Creates the tracker on first use, sets the step, returns {'token','url'}. status is one of LABEL."""
    if status not in LABEL:
        raise ValueError(f"Unknown order step '{status}'. Use: " + ", ".join(LABEL))
    if flow not in FLOW_WORD:
        raise ValueError("Unknown tracker type '" + str(flow) + "'. Use order, job, repair or ticket.")
    hosted = mode(agent) == "hosted"
    if hosted:
        if not sharing._key(agent):
            raise ValueError("Connect your Speakvora account (Connect, Your Speakvora account) so your order pages can be created.")
        base = sharing.host() + "/o"
    else:
        base = str(agent.cfg.get("public_base_url", "")).rstrip("/")
        if not base or "YOUR-" in base:
            raise ValueError("Set public_base_url in agent.json so customers can open the tracking link.")
    order = str(order or "").strip()[:40]
    if not order:
        raise ValueError("The tracker needs an order number.")
    now = int(agent.now())
    with _lock:
        c = _conn(agent); r = _find(agent, order=order)
        if not r:
            tok = secrets.token_urlsafe(16)
            c.execute("insert into orders (token,order_no,steps,status,created,updated,eta,delayed,base,history,pushed,flow) values (?,?,?,?,?,?,?,?,?,?,?,?)", (tok, order, json.dumps(FLOWS.get(flow) or (DELIVERY if delivery else PICKUP)), "received", now, now, "", 0, base, "[]", 0, flow)); r = _find(agent, token=tok)
        steps = DELIVERY if (delivery and status in DELIVERY and r["steps"] in (PICKUP, DELIVERY)) else r["steps"]
        hist = (r["history"] + [[now, status]])[-12:]
        d = (r["delayed"] and status == r["status"]) if delayed is None else bool(delayed)            # "running late" ends when the order moves to its next step
        e = r["eta"] if eta is None else " ".join(str(eta).split())[:40]            # the business's own estimate; an empty value clears it
        c.execute("update orders set steps=?, status=?, updated=?, eta=?, delayed=?, history=?, pushed=0 where token=?", (json.dumps(steps), status, now, e, int(d), json.dumps(hist), r["token"]))
    if hosted:
        threading.Thread(target=sync, args=(agent,), daemon=True).start()                 # the page catches up in a moment; if offline it is retried every minute
    return {"token": r["token"], "url": link(agent, r)}


def link(agent, r):
    """The customer's link for a saved order. A hosted link is speakvora.com/o/<code>; a self-hosted one starts with the address it was made with."""
    base = r.get("base") or ""
    if base.endswith("/o"):
        return f"{base}/{r['token']}"
    return f"{base or str(agent.cfg.get('public_base_url', '')).rstrip('/')}/track/{r['token']}"


def sync(agent):
    """Sends every order that Speakvora has not seen in its latest state (full state, idempotent). Offline or refused: left for the next minute. Returns how many were sent."""
    key = sharing._key(agent)
    if not key or mode(agent) != "hosted":
        return 0
    n = 0
    with _lock:
        rows = [r for r in _conn(agent).execute("select * from orders where pushed=0 order by updated limit 100").fetchall()]
    for raw in rows:
        r = _row(raw); flow = raw[11] if len(raw) > 11 else "order"
        body = {"token": r["token"], "order": r["order"], "flow": flow or "order", "delivery": r["steps"] == DELIVERY, "status": r["status"], "history": r["history"], "eta": r["eta"], "delayed": r["delayed"], "created": r["created"], "updated": r["updated"]}
        try:
            sharing.web.request("POST", sharing.host() + "/api/v1/track/push", {"x-api-key": key}, body=body, timeout=10)
        except Exception:  # noqa: BLE001 - offline or refused: try again next minute
            break
        with _lock:
            _conn(agent).execute("update orders set pushed=1 where token=? and updated=?", (r["token"], r["updated"])); n += 1
    return n


def business_details(agent):
    f = agent.cfg.get("facts") or {}; trk = agent.cfg.get("tracking") or {}
    return {"name": agent.cfg.get("business"), "phone": trk.get("contact_phone") or f.get("phone"), "sms_number": (agent.cfg.get("twilio") or {}).get("from_number"), "website": f.get("website"), "hours": f.get("hours"), "address": f.get("address"), "profile": getattr(agent, "profile", "generic")}


def _clean_details(agent):
    """The business details as Speakvora will take them: placeholders dropped, phone numbers only if they carry a country code."""
    import re
    b = {k: (str(v).strip() if v and "YOUR-" not in str(v) and not str(v).startswith("env:") else "") for k, v in business_details(agent).items()}
    for k in ("phone", "sms_number"):
        if b[k] and not re.fullmatch(r"\+\d{8,15}", b[k].replace(" ", "")):
            b[k] = ""
    if b["website"] and not b["website"].startswith("https://"):
        b["website"] = ""
    return b


def push_business(agent):
    """Creates (or updates) the business's order pages at Speakvora from the details it entered. Returns {'ok', 'preview_url'} or raises ValueError with a plain reason."""
    key = sharing._key(agent)
    if not key:
        raise ValueError("Add your Speakvora API key first.")
    b = _clean_details(agent)
    try:
        st, r = sharing.web.request("PUT", sharing.host() + "/api/v1/track/business", {"x-api-key": key}, body=b, timeout=15)
    except sharing.web.HttpError as e:
        detail = (getattr(e, "body", None) or {}) if isinstance(getattr(e, "body", None), dict) else {}
        raise ValueError(detail.get("detail") or ("Speakvora did not accept the key." if getattr(e, "status", 0) == 401 else "Speakvora could not create the pages just now."))
    except Exception:  # noqa: BLE001
        raise ValueError("No internet connection right now. Try again when you are online.")
    with agent.state.lock:
        agent.state.data["order_pages"] = {"preview_url": (r or {}).get("preview_url", ""), "at": int(agent.now()), "hash": hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest()}
        agent.state.data.setdefault("tested", {})["order_pages"] = int(agent.now()); agent.state.save()
    return {"ok": True, "preview_url": (r or {}).get("preview_url", "")}


def pages_current(agent):
    """True when the business details Speakvora holds are the ones saved here."""
    op = agent.state.data.get("order_pages") or {}
    b = _clean_details(agent)
    return bool(op) and op.get("hash") == hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest()


def orders(agent, q="", offset=0, limit=50):
    """The dashboard's order list, newest first: {'total', 'orders': [{order, status, label, url, created, updated, history, stale}]}. stale = the link was made with an address that is no longer this agent's public address."""
    c = _conn(agent); base = str(agent.cfg.get("public_base_url", "")).rstrip("/"); like = "%" + str(q or "").strip()[:40] + "%"
    total = c.execute("select count(*) from orders where order_no like ?", (like,)).fetchone()[0]
    rows = [_row(r) for r in c.execute("select * from orders where order_no like ? order by updated desc limit ? offset ?", (like, int(limit), int(offset))).fetchall()]
    return {"total": total, "orders": [{"order": r["order"], "status": r["status"], "label": LABEL.get(r["status"], r["status"]), "url": link(agent, r), "created": r["created"], "updated": r["updated"], "history": [[t, LABEL.get(s, s)] for t, s in r["history"]],
                                         "stale": bool(r["base"] and not r["base"].endswith("/o") and base and r["base"] != base)} for r in rows]}


def export_csv(agent):
    c = _conn(agent); base = str(agent.cfg.get("public_base_url", "")).rstrip("/"); out = ["order,status,link,created,updated"]
    for r in c.execute("select * from orders order by created").fetchall():
        r = _row(r); q = lambda v: '"' + str(v).replace('"', '""') + '"'   # noqa: E731
        out.append(",".join([q(r["order"]), q(LABEL.get(r["status"], r["status"])), q(link(agent, r)), q(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(r["created"]))), q(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(r["updated"])))]))
    return "\n".join(out) + "\n"


def _biz(agent):
    cfg = agent.cfg; trk = cfg.get("tracking") or {}; facts = cfg.get("facts") or {}
    return {"name": cfg.get("business"), "phone": trk.get("contact_phone") or facts.get("phone"), "sms_number": (cfg.get("twilio") or {}).get("from_number"), "website": facts.get("website"), "hours": facts.get("hours")}


def get(agent, token):
    r = _find(agent, token=str(token or ""))
    return TV.view(r, _biz(agent), getattr(agent, "profile", "generic")) if r else None


def purge(agent):
    """Links never expire by default. Only with tracking.keep_days in agent.json are finished orders older than that many days removed."""
    days = int((agent.cfg.get("tracking") or {}).get("keep_days") or 0)
    if days <= 0:
        return 0
    c = _conn(agent)
    cur = c.execute("delete from orders where status in ('picked_up','delivered','cancelled') and updated < ?", (int(agent.now()) - days * 86400,))
    return cur.rowcount


def page(agent, token):
    d = get(agent, token)
    if not d:
        return None
    return TV.render(token, d, f"/track/{token}.json")
