"""Order tracking links, like the ones pizza chains send. The customer gets ONE text with a private link; the page behind it shows the order moving through its steps (received, preparing, ready, picked up; or on its way, delivered) and refreshes by itself. No further texts are needed.
The page shows the business name, the order number you give it and the step. Nothing about the customer or what was ordered. The link holds a long random code that cannot be guessed, and it stops working a few days after the order is finished.
The page is served by this agent at public_base_url + /track/<code> (the same public address Twilio already uses for audio)."""
import html, json, secrets

PICKUP = ["received", "preparing", "ready", "picked_up"]
DELIVERY = ["received", "preparing", "out_for_delivery", "delivered"]
LABEL = {"received": "Order received", "preparing": "Being prepared", "ready": "Ready for pickup", "picked_up": "Picked up", "out_for_delivery": "On its way", "delivered": "Delivered", "cancelled": "Cancelled"}
FINAL = ("picked_up", "delivered", "cancelled")
KEEP_DAYS_AFTER_FINISH, KEEP_DAYS_MAX = 3, 14


def _db(agent):
    return agent.state.data.setdefault("tracks", {})


def set_status(agent, order, status, delivery=False, delayed=None):
    """Creates the tracker on first use, sets the step, returns {'token','url'}. status is one of LABEL."""
    if status not in LABEL:
        raise ValueError(f"Unknown order step '{status}'. Use: " + ", ".join(LABEL))
    base = str(agent.cfg.get("public_base_url", "")).rstrip("/")
    if not base or "YOUR-" in base:
        raise ValueError("Set public_base_url in agent.json so customers can open the tracking link.")
    order = str(order or "").strip()[:40]
    if not order:
        raise ValueError("The tracker needs an order number.")
    db = _db(agent); now = int(agent.now())
    with agent.state.lock:
        tok = next((t for t, r in db.items() if r["order"] == order), None)
        if not tok:
            tok = secrets.token_urlsafe(16)
            db[tok] = {"order": order, "steps": DELIVERY if delivery else PICKUP, "status": "received", "created": now, "history": []}
        r = db[tok]
        if delivery and r["steps"] != DELIVERY and status in DELIVERY:
            r["steps"] = DELIVERY
        r.update(status=status, updated=now)
        if delayed is not None:
            r["delayed"] = bool(delayed)
        r["history"].append([now, status]); r["history"] = r["history"][-12:]
        agent.state.save()
    return {"token": tok, "url": f"{base}/track/{tok}"}


def get(agent, token):
    r = _db(agent).get(str(token or ""))
    if not r:
        return None
    return {"business": agent.cfg.get("business") if "YOUR-" not in str(agent.cfg.get("business", "YOUR-")) else "Your order", "order": r["order"], "status": r["status"], "label": LABEL.get(r["status"], r["status"]),
            "steps": [{"key": s, "label": LABEL[s]} for s in r["steps"]], "delayed": bool(r.get("delayed")), "updated": r.get("updated"), "cancelled": r["status"] == "cancelled"}


def purge(agent):
    db, now = _db(agent), agent.now(); n = 0
    with agent.state.lock:
        for t in [t for t, r in db.items() if (r["status"] in FINAL and now - r.get("updated", 0) > KEEP_DAYS_AFTER_FINISH * 86400) or now - r.get("created", 0) > KEEP_DAYS_MAX * 86400]:
            del db[t]; n += 1
        if n:
            agent.state.save()
    return n


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>__BIZ__ order __ORDER__</title>
<style>:root{--bg:#faf7f2;--fg:#1c1a17;--mut:#6d675f;--line:#e4ddd2;--ok:#e8710a;--card:#fff}@media(prefers-color-scheme:dark){:root{--bg:#161412;--fg:#f4efe8;--mut:#a39b90;--line:#332f2a;--card:#1f1c19}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}main{max-width:480px;margin:0 auto;padding:28px 18px}h1{font-size:22px;margin:0 0 2px}.sub{color:var(--mut);margin:0 0 22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px}.now{font-size:26px;font-weight:700;margin:0 0 4px}ol{list-style:none;margin:20px 0 0;padding:0}li{display:flex;gap:12px;align-items:center;padding:9px 0;color:var(--mut)}
li i{width:14px;height:14px;border-radius:50%;border:2px solid var(--line);flex:none}li.done{color:var(--fg)}li.done i{background:var(--ok);border-color:var(--ok)}li.cur{color:var(--fg);font-weight:700}li.cur i{border-color:var(--ok);box-shadow:0 0 0 4px rgba(232,113,10,.2)}
.late{margin-top:14px;color:var(--ok)}small{display:block;margin-top:16px;color:var(--mut)}</style></head><body><main><h1 id="b">__BIZ__</h1><p class="sub" id="o">Order __ORDER__</p><div class="card"><p class="now" id="now"></p><div id="late" class="late"></div><ol id="steps"></ol><small id="upd"></small></div></main>
<script>const T=__TOKEN__;async function load(){try{const r=await fetch('/track/'+T+'.json',{cache:'no-store'});if(!r.ok)throw 0;const d=await r.json();document.getElementById('now').textContent=d.label;document.getElementById('late').textContent=d.delayed?'Running a little late. Thank you for your patience.':'';
const keys=d.steps.map(s=>s.key);const at=keys.indexOf(d.status);const ol=document.getElementById('steps');ol.textContent='';d.steps.forEach((s,i)=>{const li=document.createElement('li');li.className=d.cancelled?'':(i<at?'done':i===at?'cur':'');const b=document.createElement('i');li.appendChild(b);li.appendChild(document.createTextNode(s.label));ol.appendChild(li)});
document.getElementById('upd').textContent=d.cancelled?'This order was cancelled.':'This page updates by itself.'}catch(e){document.getElementById('now').textContent='This link has expired.';document.getElementById('steps').textContent=''}}load();setInterval(load,10000);</script></body></html>"""


def page(agent, token):
    d = get(agent, token)
    if not d:
        return None
    return (PAGE.replace("__BIZ__", html.escape(str(d["business"]))).replace("__ORDER__", html.escape(str(d["order"]))).replace("__TOKEN__", json.dumps(str(token)))).encode()
