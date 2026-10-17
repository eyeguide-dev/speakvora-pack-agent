"""Order tracking links, like the ones pizza chains send. The customer gets ONE text with a private link; the page behind it shows the order moving through its steps (received, preparing, ready, picked up; or on its way, delivered) and refreshes by itself. No further texts are needed.
The page shows the business name, the order number you give it and the step. Nothing about the customer or what was ordered. The link holds a long random code that cannot be guessed, and it stops working a few days after the order is finished.
The page is served by this agent at public_base_url + /track/<code> (the same public address Twilio already uses for audio)."""
import html, json, secrets

KIND = {"food": ("Restaurant", "restaurant"), "retail": ("Retail", "store"), "laundry": ("Laundry", "laundry"), "pharmacy": ("Pharmacy", "pharmacy")}
SHORT = {"received": "Received", "preparing": "Preparing", "ready": "Ready", "picked_up": "Collected", "out_for_delivery": "On the way", "delivered": "Delivered", "cancelled": "Cancelled"}
STEP_WORDS = {"retail": {"received": "Confirmed", "preparing": "Packed", "ready": "Ready", "picked_up": "Collected"}, "laundry": {"received": "Received", "preparing": "Cleaning", "ready": "Ready", "picked_up": "Collected"}}
HEAD = {"food": {"received": "We have your order.", "preparing": "In the kitchen.", "ready": "Ready for pickup.", "picked_up": "Enjoy your meal.", "out_for_delivery": "On its way to you.", "delivered": "Delivered. Enjoy."},
        "retail": {"received": "Order confirmed.", "preparing": "Getting it ready.", "ready": "Ready for pickup.", "picked_up": "All yours.", "out_for_delivery": "On its way to you.", "delivered": "Delivered."},
        "laundry": {"received": "We have your items.", "preparing": "Being cleaned.", "ready": "Fresh. Folded. Ready.", "picked_up": "All collected.", "out_for_delivery": "On its way back to you.", "delivered": "Delivered."},
        "pharmacy": {"received": "We have your order.", "preparing": "Being prepared.", "ready": "Ready for pickup.", "picked_up": "Picked up.", "out_for_delivery": "On its way.", "delivered": "Delivered."}}
HEAD_DEFAULT = {"received": "We have your order.", "preparing": "Being prepared.", "ready": "Ready for pickup.", "picked_up": "Picked up.", "out_for_delivery": "On its way to you.", "delivered": "Delivered.", "cancelled": "This order was cancelled."}
PICKUP = ["received", "preparing", "ready", "picked_up"]
DELIVERY = ["received", "preparing", "out_for_delivery", "delivered"]
LABEL = {"received": "Order received", "preparing": "Being prepared", "ready": "Ready for pickup", "picked_up": "Picked up", "out_for_delivery": "Out for delivery", "delivered": "Delivered", "cancelled": "Cancelled"}
FINAL = ("picked_up", "delivered", "cancelled")
KEEP_DAYS_AFTER_FINISH, KEEP_DAYS_MAX = 3, 14


def _db(agent):
    return agent.state.data.setdefault("tracks", {})


def set_status(agent, order, status, delivery=False, delayed=None, eta=None):
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
        if eta is not None:                                                         # the business's own estimate, shown as "provided by the business"; an empty value clears it
            r["eta"] = " ".join(str(eta).split())[:40]
        r["history"].append([now, status]); r["history"] = r["history"][-12:]
        agent.state.save()
    return {"token": tok, "url": f"{base}/track/{tok}"}


def _contact(agent):
    """How a customer reaches the business from the page: its public phone (facts.phone or tracking.contact_phone) to call, and the number the agent texts from, so a text goes to staff through the agent."""
    cfg = agent.cfg; trk = cfg.get("tracking") or {}; facts = cfg.get("facts") or {}
    ok = lambda v: bool(v) and "YOUR-" not in str(v) and not str(v).startswith("env:")   # noqa: E731
    call = trk.get("contact_phone") or facts.get("phone")
    text = (cfg.get("twilio") or {}).get("from_number")
    return {"call": str(call) if ok(call) else "", "text": str(text) if ok(text) and str(text).startswith("+") else ""}


def get(agent, token):
    r = _db(agent).get(str(token or ""))
    if not r:
        return None
    prof = getattr(agent, "profile", "generic"); kind, noun = KIND.get(prof, ("", "business"))
    words = {**SHORT, **STEP_WORDS.get(prof, {})}; heads = {**HEAD_DEFAULT, **HEAD.get(prof, {})}
    label = lambda s: words.get(s) or LABEL.get(s, s)   # noqa: E731
    delivery = r["steps"] == DELIVERY
    biz = agent.cfg.get("business") if "YOUR-" not in str(agent.cfg.get("business", "YOUR-")) else "Your order"
    return {"business": biz, "kind": (kind + " \u00b7 " if kind else "") + ("Delivery" if delivery else "Pickup"), "noun": noun, "order": r["order"], "status": r["status"], "label": LABEL.get(r["status"], r["status"]), "headline": heads.get(r["status"], LABEL.get(r["status"], "")),
            "steps": [{"key": s, "label": label(s)} for s in r["steps"]], "delayed": bool(r.get("delayed")), "eta": r.get("eta", ""), "updated": r.get("updated"), "cancelled": r["status"] == "cancelled", "contact": _contact(agent)}


def purge(agent):
    db, now = _db(agent), agent.now(); n = 0
    with agent.state.lock:
        for t in [t for t, r in db.items() if (r["status"] in FINAL and now - r.get("updated", 0) > KEEP_DAYS_AFTER_FINISH * 86400) or now - r.get("created", 0) > KEEP_DAYS_MAX * 86400]:
            del db[t]; n += 1
        if n:
            agent.state.save()
    return n


LOGO = ('<svg viewBox="0 0 32 32" aria-hidden="true" width="34" height="34"><defs><linearGradient id="tl" x1="0" y1="0" x2="32" y2="32"><stop stop-color="#ff6a4d"/><stop offset=".55" stop-color="#ffb454"/><stop offset="1" stop-color="#ff4f8b"/></linearGradient></defs>'
        '<rect width="32" height="32" rx="10" fill="url(#tl)"/><path d="M6 17h3v-2H6zM11 21h3V11h-3zM16 25h3V7h-3zM21 21h3V11h-3zM26 17h-3v-2h3z" fill="#1a0c07"/></svg>')

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer"><title>__BIZ__ order __ORDER__</title>
<style>:root{--bg:#fdf5ec;--fg:#1c1814;--mut:#6f665c;--line:#eadfd0;--card:#fffdfa;--acc:#ee6a14;--accsoft:#fde6d3;--done:#ee6a14;--idle:#d9d2c8}
@media(prefers-color-scheme:dark){:root{--bg:#17130f;--fg:#f6efe6;--mut:#a89d90;--line:#352e27;--card:#201b16;--accsoft:#3a2616;--idle:#4a4138}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:460px;margin:0 auto;padding:max(16px,env(safe-area-inset-top)) 16px 28px}
.top{display:flex;align-items:center;gap:10px;padding:6px 2px 16px;font-weight:700;font-size:24px;letter-spacing:-.02em}
.card{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:18px;box-shadow:0 8px 28px rgba(120,70,20,.07)}
.biz{display:flex;gap:14px;align-items:center;padding-bottom:16px;border-bottom:1px solid var(--line)}
.ini{width:58px;height:58px;border-radius:50%;background:var(--accsoft);color:var(--acc);display:grid;place-items:center;font-weight:800;font-size:21px;flex:none}
.bn{font-weight:750;font-size:20px;line-height:1.2}.bk{color:var(--mut);margin-top:2px}
.ord{color:var(--mut);margin:18px 0 4px}h1{font-size:34px;line-height:1.08;letter-spacing:-.03em;margin:0 0 12px;text-wrap:balance}
.pill{display:inline-flex;align-items:center;gap:8px;background:var(--accsoft);color:var(--acc);font-weight:700;padding:8px 16px;border-radius:999px}.pill i{width:12px;height:12px;border-radius:50%;background:var(--acc)}
.help{color:var(--mut);margin:12px 0 0}.late{color:var(--acc);font-weight:600;margin:10px 0 0}
.steps{display:flex;margin:24px 0 6px}.st{flex:1;display:flex;flex-direction:column;align-items:center;position:relative;text-align:center;font-size:13.5px;color:var(--mut)}
.st .dot{width:30px;height:30px;border-radius:50%;background:var(--idle);display:grid;place-items:center;color:#fff;position:relative;z-index:1;margin-bottom:8px}
.st:not(:first-child)::before{content:"";position:absolute;top:14px;right:50%;width:100%;height:3px;background:var(--idle)}
.st.done .dot,.st.cur .dot{background:var(--done)}.st.done:not(:first-child)::before,.st.cur:not(:first-child)::before{background:var(--done)}
.st.cur .dot{box-shadow:0 0 0 4px var(--accsoft);outline:3px solid var(--done);outline-offset:-3px;background:#fff}.st.cur .dot::after{content:"";width:12px;height:12px;border-radius:50%;background:var(--done)}
.st.cur{color:var(--fg);font-weight:700}.st.done{color:var(--fg)}
.box{display:flex;gap:14px;align-items:center;border:1px solid var(--line);border-radius:16px;padding:14px 16px;margin-top:16px}
.ico{width:46px;height:46px;border-radius:50%;background:var(--accsoft);display:grid;place-items:center;flex:none}.ico svg{width:22px;height:22px;stroke:var(--fg);fill:none;stroke-width:1.8}
.box small{display:block;color:var(--mut)}.box b{font-size:20px}
.upd{display:flex;justify-content:space-between;gap:12px;margin-top:16px;padding-top:16px;border-top:1px solid var(--line)}.upd small{display:block;color:var(--mut)}.upd b{font-size:17px}.upd div:last-child{text-align:right}
.btns{display:grid;gap:10px;margin-top:16px}.btn{display:flex;align-items:center;justify-content:center;gap:10px;border:1.5px solid var(--fg);border-radius:14px;padding:15px;color:var(--fg);text-decoration:none;font-weight:700;font-size:17px;background:transparent}
.btn svg{width:20px;height:20px;stroke:currentColor;fill:none;stroke-width:2}
.foot{text-align:center;color:var(--mut);font-size:13px;margin-top:18px}[hidden]{display:none!important}</style></head><body><main>
<div class="top">__LOGO__<span>speakvora</span></div>
<div class="card"><div class="biz"><div class="ini" id="ini"></div><div><div class="bn" id="bn">__BIZ__</div><div class="bk" id="bk"></div></div></div>
<div class="ord" id="ord">Order __ORDER__</div><h1 id="hd"></h1><div class="pill" id="pill"><i></i><span id="pl"></span></div><div class="late" id="late" hidden></div><p class="help" id="help"></p>
<div class="steps" id="steps"></div>
<div class="box" id="etab" hidden><div class="ico"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></div><div><small id="etal"></small><b id="et"></b><small id="ets"></small></div></div>
<div class="upd"><div><small>Latest update</small><b id="lu"></b></div><div><small>Last updated</small><span id="lt"></span></div></div>
<div class="btns" id="btns" hidden></div></div><div class="foot">Branded order tracking by Speakvora</div></main>
<script>const T=__TOKEN__;
function tm(s){try{return new Date(s*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}catch(e){return ''}}
function el(t,c,x){const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
async function load(){try{const r=await fetch('/track/'+T+'.json',{cache:'no-store'});if(!r.ok)throw 0;const d=await r.json();
document.getElementById('bn').textContent=d.business;document.getElementById('ini').textContent=d.business.split(/\\s+/).filter(Boolean).slice(0,2).map(w=>w[0].toUpperCase()).join('');document.getElementById('bk').textContent=d.kind;
document.getElementById('ord').textContent='Order #'+d.order;document.getElementById('hd').textContent=d.headline;document.getElementById('pl').textContent=d.label;
const late=document.getElementById('late');late.hidden=!d.delayed;late.textContent=d.delayed?'Running a little late. Thank you for your patience.':'';
document.getElementById('help').textContent=d.cancelled?'This order was cancelled. Please contact us if you have questions.':'This page updates by itself when your '+d.noun+' sends a new step.';
const keys=d.steps.map(s=>s.key),at=keys.indexOf(d.status),box=document.getElementById('steps');box.textContent='';
d.steps.forEach((s,i)=>{const c=el('div','st'+(d.cancelled?'':(i<at?' done':i===at?' cur':'')));const dot=el('div','dot');if(!d.cancelled&&i<at){dot.innerHTML='<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#fff" stroke-width="3"><path d="M5 12l5 5 9-10"/></svg>'}c.appendChild(dot);c.appendChild(document.createTextNode(s.label));box.appendChild(c)});
const eb=document.getElementById('etab');eb.hidden=!d.eta||d.cancelled;if(d.eta){document.getElementById('etal').textContent=(keys.indexOf('delivered')>=0?'Delivery':'Pickup')+' estimate';document.getElementById('et').textContent=d.eta;document.getElementById('ets').textContent='Provided by the '+d.noun}
document.getElementById('lu').textContent=d.label+(d.updated?' \u00b7 '+tm(d.updated):'');document.getElementById('lt').textContent=tm(d.updated);
const bt=document.getElementById('btns');bt.textContent='';const ph='<svg viewBox="0 0 24 24"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/></svg>';
if(d.contact.call){const a=el('a','btn');a.href='tel:'+d.contact.call;a.innerHTML=ph;a.appendChild(document.createTextNode('Call '+d.noun));bt.appendChild(a)}
if(d.contact.text){const a=el('a','btn');a.href='sms:'+d.contact.text+'?&body='+encodeURIComponent('Question about order #'+d.order);a.innerHTML='<svg viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4z"/></svg>';a.appendChild(document.createTextNode('Text '+d.noun));bt.appendChild(a)}
bt.hidden=!bt.children.length}catch(e){document.getElementById('hd').textContent='This link has expired.';document.getElementById('pl').textContent='Expired';document.getElementById('steps').textContent='';document.getElementById('btns').hidden=true}}
load();setInterval(load,10000);</script></body></html>"""


def page(agent, token):
    d = get(agent, token)
    if not d:
        return None
    return (PAGE.replace("__LOGO__", LOGO).replace("__BIZ__", html.escape(str(d["business"]))).replace("__ORDER__", html.escape(str(d["order"]))).replace("__TOKEN__", json.dumps(str(token)))).encode()
