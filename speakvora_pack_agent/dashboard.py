"""A tiny dashboard for ONE agent, served by the agent itself (standard library, no external files, nothing leaves your machine): what it is waiting to send, what needs you, how complete the bundle is,
and a form to ask Speakvora for more lines. Open the address printed at start-up; the access token is in the part after # so it is never sent to a server and never logged.
Routes: GET /dashboard (the page), GET /dash/api/summary, GET /dash/api/jobs?status=, POST /dash/api/jobs/<id>/<cancel|retry|mark-sent>, POST /dash/api/pause {"on": true|false}, POST /dash/api/phrases {"slots": [...]} or {"custom": {...}}.
Every /dash/api call needs the header x-dashboard-token (env SV_DASHBOARD_TOKEN, or the random token kept in agent-state/dashboard-token). Pause = the kill switch file STOP."""
import hmac, json, os, re, secrets, time, urllib.request
from urllib.parse import parse_qs, urlparse

from . import slots as SL

CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
ATTENTION = ("needs_review", "failed", "expired", "undelivered")


def token(agent):
    env = os.environ.get("SV_DASHBOARD_TOKEN", "").strip()
    if env:
        return env
    p = os.path.join(agent.state.dir, "dashboard-token")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    t = secrets.token_hex(16)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t)
    return t


def _gaps(agent):
    """Lines the workflows use that the pack cannot say yet: [{'slot','intent','example'}]."""
    reg = SL.registry(agent.profile)
    want = SL.needed_by(json.load(open(agent.cfg["workflows"], encoding="utf-8"))) if agent.cfg.get("workflows") else set()
    return [{"slot": k, **reg[k]} for k in sorted(want) if k in reg and k not in agent.pack.slots]


def _requests_path(agent):
    return os.path.join(agent.state.dir, "phrase-requests.json")


def _requests(agent):
    try:
        return json.load(open(_requests_path(agent), encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _job(j):
    a = j.get("a") or {}
    return {"id": j["id"], "status": j["status"], "kind": j["kind"], "workflow": j["wf"], "to": str(a.get("to") or a.get("channel") or a.get("url") or "")[:60], "text": str(a.get("text") or a.get("subject") or a.get("title") or "")[:140],
            "created": j["created"], "updated": j["updated"], "attempts": j.get("attempts", 0), "error": (j.get("error") or "")[:200], "note": (j["history"][-1][2] if j.get("history") else "")}


def summary(agent):
    st = agent.state; gaps = _gaps(agent); jobs = st.jobs()
    att = [j for j in jobs if j["status"] in ATTENTION][-30:][::-1]
    return {"now": int(agent.now()), "pack": {"title": agent.pack.meta.get("title"), "id": agent.pack.meta.get("pack"), "language": agent.pack.language, "lines": len(agent.pack.items), "profile": agent.profile, "version": agent.pack.meta.get("version")},
            "mode": "dry_run" if agent.dry else "live", "paused": agent.safe.killed(), "counts": st.job_counts(), "workflows": len(agent.workflows),
            "attention": [_job(j) for j in att], "recent": [_job(j) for j in jobs[-40:][::-1]],
            "coverage": {"needed": len(SL.needed_by(json.load(open(agent.cfg["workflows"], encoding="utf-8")))) if agent.cfg.get("workflows") else 0, "missing": gaps},
            "requests": _requests(agent)[-10:][::-1], "can_send_requests": bool(os.environ.get("SPEAKVORA_KEY"))}


CUSTOM_BAD = re.compile(r"https?://|@|\d{6,}")


def request_phrases(agent, body):
    """Writes the request file and, when SPEAKVORA_KEY is set, sends it to Speakvora (the same call as `slots --send`). A custom line is a slot of your own: the moment it is said, and the sentence."""
    gaps = {g["slot"]: g for g in _gaps(agent)}
    if body.get("custom"):
        c = body["custom"]; intent, text = re.sub(r"\s+", " ", str(c.get("when", ""))).strip()[:160], re.sub(r"\s+", " ", str(c.get("text", ""))).strip()[:200]
        if len(intent) < 8 or len(text) < 8 or CUSTOM_BAD.search(intent + text):
            raise ValueError("Say when the line is used (at least 8 characters) and write the sentence you want (at least 8 characters, no links, emails or long numbers).")
        slot = "custom_" + re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:28].rstrip("_")
        picked = [{"slot": slot, "intent": intent, "example": text}]
    else:
        names = [str(s) for s in (body.get("slots") or [])]
        picked = [gaps[s] for s in names if s in gaps]
        if not picked:
            raise ValueError("Choose at least one missing line.")
    path = os.path.join(agent.state.dir, "slot-requests.json"); doc = SL.request_file(agent.pack, agent.profile, picked, path)
    sent, msg = False, "Saved. Set SPEAKVORA_KEY (an API key from your Speakvora dashboard) and ask again to send it."
    key = os.environ.get("SPEAKVORA_KEY")
    if key:
        req = urllib.request.Request(os.environ.get("SPEAKVORA_HOST", "https://speakvora.com") + "/api/v1/packs/slot-requests", data=json.dumps(doc).encode(), method="POST", headers={"x-api-key": key, "content-type": "application/json"})
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=20).read().decode()); sent, msg = True, r.get("note") or "Sent to Speakvora."
        except Exception as e:  # noqa: BLE001
            msg = "Could not send it now (" + str(getattr(e, "reason", e))[:80] + "). The request is saved in agent-state/slot-requests.json; try again, or run `slots --send`."
    log = _requests(agent) + [{"t": int(agent.now()), "slots": [p["slot"] for p in picked], "sent": sent, "text": picked[0]["example"] if body.get("custom") else ""}]
    json.dump(log[-100:], open(_requests_path(agent), "w", encoding="utf-8"))
    return {"sent": sent, "message": msg, "slots": [p["slot"] for p in picked]}


def handle(agent, method, path, headers, raw):
    """Returns (status, body bytes, content type, extra headers)."""
    u = urlparse(path); p = u.path
    hdr = {"content-security-policy": CSP, "x-content-type-options": "nosniff", "referrer-policy": "no-referrer", "cache-control": "no-store"}
    if p == "/dashboard" and method == "GET":
        return 200, PAGE.encode(), "text/html; charset=utf-8", hdr
    given = {k.lower(): v for k, v in headers.items()}.get("x-dashboard-token", "")
    if not hmac.compare_digest(given.encode(), token(agent).encode()):
        return 401, b'{"error":"bad_token"}', "application/json", hdr
    try:
        if p == "/dash/api/summary" and method == "GET":
            out = summary(agent)
        elif p == "/dash/api/jobs" and method == "GET":
            qs = parse_qs(u.query); s, k, q = (qs.get("status") or [""])[0], (qs.get("kind") or [""])[0], (qs.get("q") or [""])[0].lower()
            rows = [_job(j) for j in agent.state.jobs(s or None) if (not k or j["kind"] == k)]
            out = {"jobs": [j for j in rows if not q or q in (j["to"] + " " + j["workflow"] + " " + j["text"] + " " + j["kind"]).lower()][-300:][::-1]}
        elif method == "POST" and (m := re.match(r"^/dash/api/jobs/([\w:.\-]+)/(cancel|retry|mark-sent)$", p)):
            body = json.loads(raw or b"{}"); jid, act = m.group(1), m.group(2)
            j = agent.cancel_job(jid) if act == "cancel" else agent.retry_job(jid, bool(body.get("confirm_not_sent"))) if act == "retry" else agent.mark_job_sent(jid)
            if act == "retry":
                agent.flush_outbox()
            out = {"job": _job(agent.state.job_get(jid))}
        elif p == "/dash/api/pause" and method == "POST":
            on = bool(json.loads(raw or b"{}").get("on")); f = os.path.join(agent.state.dir, "STOP")
            if on:
                open(f, "w").close()
            elif os.path.exists(f):
                os.remove(f)
            out = {"paused": agent.safe.killed()}
        elif p == "/dash/api/phrases" and method == "POST":
            out = request_phrases(agent, json.loads(raw or b"{}"))
        else:
            return 404, b'{"error":"not_found"}', "application/json", hdr
    except PermissionError as e:
        return 409, json.dumps({"error": "not_allowed", "message": str(e)}).encode(), "application/json", hdr
    except (ValueError, KeyError) as e:
        return 400, json.dumps({"error": "bad_request", "message": str(e)}).encode(), "application/json", hdr
    return 200, json.dumps(out).encode(), "application/json", hdr


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pack agent</title>
<style>
:root{--bg:#f6f4ef;--card:#fff;--ink:#1d1b18;--mut:#6b655c;--line:#e3ded5;--acc:#1f6f5c;--warn:#a85b00;--bad:#b3261e}
@media(prefers-color-scheme:dark){:root{--bg:#14130f;--card:#1d1b17;--ink:#f1ede4;--mut:#a39c90;--line:#33302a;--acc:#58c4a8;--warn:#e0a24a;--bad:#ff8a80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:940px;margin:0 auto;padding:18px 16px 60px}h1{font-size:19px;margin:0}.sub{color:var(--mut);font-size:13px}.top{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.badge{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid var(--line)}.live{color:var(--bad);border-color:var(--bad)}.dry{color:var(--acc);border-color:var(--acc)}.paused{color:var(--warn);border-color:var(--warn)}
.tabs{display:flex;gap:4px;margin:16px 0 10px;border-bottom:1px solid var(--line)}.tab{border:0;background:none;color:var(--mut);padding:8px 14px;border-bottom:2px solid transparent;font:inherit;cursor:pointer;margin-bottom:-1px}.tab.on{color:var(--ink);border-color:var(--acc);font-weight:600}
.chips{display:flex;gap:6px;flex-wrap:wrap}.chip{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:99px;padding:4px 12px;font:inherit;cursor:pointer}.chip b{font-variant-numeric:tabular-nums;margin-left:5px;color:var(--mut)}.chip.on{background:var(--acc);border-color:var(--acc);color:#fff}.chip.on b{color:#fff}.chip.alert b{color:var(--warn)}.chip.alert.on b{color:#fff}
.bar{display:flex;gap:8px;margin:10px 0;flex-wrap:wrap}.bar input,.bar select{font:inherit;border:1px solid var(--line);border-radius:8px;padding:6px 9px;background:var(--card);color:var(--ink)}.bar input{flex:1;min-width:160px}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--mut);font-weight:600;font-size:12px}tr:last-child td{border-bottom:0}
.st{font-weight:600}.st.needs_review,.st.expired,.st.undelivered{color:var(--warn)}.st.failed,.st.blocked{color:var(--bad)}.st.delivered,.st.sent{color:var(--acc)}.mut{color:var(--mut)}
button.b{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:3px 9px;cursor:pointer;margin:1px 2px 1px 0}button.b:hover{border-color:var(--acc)}button.p{font:inherit;border:1px solid var(--acc);background:var(--acc);color:#fff;border-radius:8px;padding:6px 14px;cursor:pointer}button:disabled{opacity:.5}
.empty{padding:16px;color:var(--mut)}.pad{padding:12px 14px}label{display:block;font-size:12px;color:var(--mut);margin:8px 0 3px}textarea,.pad input[type=text]{font:inherit;width:100%;border:1px solid var(--line);border-radius:8px;padding:7px 9px;background:var(--bg);color:var(--ink)}.msg{margin-top:8px;font-size:13px}
.meter{height:8px;border-radius:99px;background:var(--line);overflow:hidden;margin:6px 0}.meter i{display:block;height:100%;background:var(--acc)}
@media(max-width:560px){th:nth-child(3),td:nth-child(3){display:none}}
</style></head><body><main>
<div class="top"><div><h1 id="title">Pack agent</h1><div class="sub" id="sub">Loading...</div></div><div><span class="badge" id="mode"></span> <button class="b" id="pause"></button></div></div>
<div class="tabs"><button class="tab on" id="t1">Activity</button><button class="tab" id="t2">Lines</button></div>
<section id="v1"><div class="chips" id="chips"></div>
<div class="bar"><input id="q" type="search" placeholder="Search a name, number, channel or workflow"><select id="kind"><option value="">All types</option><option value="sms">Texts</option><option value="call">Calls</option><option value="slack">Slack</option><option value="teams">Teams</option><option value="email">Email</option><option value="calendar_create">Calendar</option><option value="webhook">Webhooks and APIs</option></select></div>
<div class="box" id="list"></div></section>
<section id="v2" hidden><div class="box pad" id="coverage"></div>
<div class="box pad" style="margin-top:12px"><b>Ask for another line</b><div class="sub">Sent to Speakvora with your API key (or saved if no key is set). New lines are written, checked and voiced, then arrive in the next version of your pack. No delivery date is promised.</div>
<label for="when">When is it said?</label><input type="text" id="when" maxlength="160" placeholder="For example: when a customer asks for a refund of a late delivery">
<label for="text">The sentence you want</label><textarea id="text" rows="2" maxlength="200" placeholder="For example: I am sorry your delivery was late, and I have asked for a refund."></textarea>
<div style="margin-top:10px"><button class="p" id="ask">Request this line</button></div><div class="msg" id="askmsg"></div><div class="sub" id="past" style="margin-top:10px"></div></div></section>
<p class="sub" style="margin-top:18px">Runs only on your machine, next to your agent. Pause stops every send until you resume.</p>
</main><script>
const T=(location.hash.match(/token=([\\w-]+)/)||[])[1]||sessionStorage.getItem('t')||'';if(T)sessionStorage.setItem('t',T);history.replaceState(null,'',location.pathname);
const $=id=>document.getElementById(id);let S=null,JOBS=[],FILTER='all';
const GROUPS={all:null,need:['needs_review','failed','undelivered','expired'],wait:['pending','queued','sending'],sent:['sent','delivered'],delivered:['delivered'],stopped:['blocked','cancelled','failed','expired']};
const LABELS=[['all','All'],['need','Needs you'],['wait','Waiting'],['sent','Sent'],['delivered','Delivered']];
async function api(p,o){o=o||{};o.headers=Object.assign({'x-dashboard-token':T,'content-type':'application/json'},o.headers||{});const r=await fetch(p,o);const j=await r.json().catch(()=>({}));if(!r.ok)throw Object.assign(new Error(j.message||j.error||r.status),{status:r.status});return j}
const ago=(s,n)=>{const d=n-s;return d<90?d+' s ago':d<5400?Math.round(d/60)+' min ago':d<172800?Math.round(d/3600)+' h ago':Math.round(d/86400)+' days ago'};
function td(t,c){const x=document.createElement('td');if(c)x.className=c;x.textContent=t;return x}
function bt(label,fn){const b=document.createElement('button');b.className='b';b.textContent=label;b.onclick=async()=>{b.disabled=true;try{await fn()}catch(e){alert(e.message)}load()};return b}
const inGroup=(j,g)=>!GROUPS[g]||GROUPS[g].includes(j.status);
function render(){const now=S.now,q=$('q').value.trim().toLowerCase(),k=$('kind').value;
const chips=$('chips');chips.textContent='';LABELS.forEach(([g,l])=>{const n=JOBS.filter(j=>inGroup(j,g)).length;const c=document.createElement('button');c.className='chip'+(FILTER===g?' on':'')+(g==='need'&&n?' alert':'');c.textContent=l;const b=document.createElement('b');b.textContent=n;c.appendChild(b);c.onclick=()=>{FILTER=g;render()};chips.appendChild(c)});
const list=JOBS.filter(j=>inGroup(j,FILTER)&&(!k||j.kind===k)&&(!q||(j.to+' '+j.workflow+' '+j.text+' '+j.kind).toLowerCase().includes(q)));const box=$('list');box.textContent='';
if(!list.length){const d=document.createElement('div');d.className='empty';d.textContent=JOBS.length?'Nothing matches this filter.':'Nothing sent yet.';box.appendChild(d);return}
const t=document.createElement('table'),h=t.insertRow();['Status','What','To','When',''].forEach(x=>{const th=document.createElement('th');th.textContent=x;h.appendChild(th)});
list.forEach(j=>{const r=t.insertRow();r.appendChild(td(j.status.replace('_',' '),'st '+j.status));const w=td(j.kind+' / '+j.workflow);if(j.error||j.note){const s=document.createElement('div');s.className='mut';s.textContent=(j.error||j.note).slice(0,110);w.appendChild(s)}r.appendChild(w);r.appendChild(td(j.to));r.appendChild(td(ago(j.updated,now),'mut'));
const a=document.createElement('td');a.style.whiteSpace='nowrap';
if(['pending','queued'].includes(j.status))a.appendChild(bt('Cancel',()=>api('/dash/api/jobs/'+j.id+'/cancel',{method:'POST',body:'{}'})));
if(j.status==='needs_review'){a.appendChild(bt('It arrived',()=>api('/dash/api/jobs/'+j.id+'/mark-sent',{method:'POST',body:'{}'})));a.appendChild(bt('Did not arrive: send again',()=>{if(confirm('Only if you checked with the provider and it did NOT arrive. Send again?'))return api('/dash/api/jobs/'+j.id+'/retry',{method:'POST',body:JSON.stringify({confirm_not_sent:true})})}))}
if(['failed','expired'].includes(j.status))a.appendChild(bt('Try again',()=>api('/dash/api/jobs/'+j.id+'/retry',{method:'POST',body:'{}'})));
r.appendChild(a)});box.appendChild(t)}
function lines(){const cov=S.coverage,have=cov.needed-cov.missing.length,box=$('coverage');box.textContent='';const p=document.createElement('div');p.textContent=cov.needed?have+' of '+cov.needed+' spoken lines your workflows use are in this pack.':'Your workflows use no named lines.';box.appendChild(p);
const m=document.createElement('div');m.className='meter';const i=document.createElement('i');i.style.width=(cov.needed?Math.round(100*have/cov.needed):100)+'%';m.appendChild(i);box.appendChild(m);
if(cov.missing.length){const ul=document.createElement('div');cov.missing.forEach(x=>{const lab=document.createElement('label');lab.style.cssText='margin:6px 0;font-size:13px;color:var(--ink)';const cb=document.createElement('input');cb.type='checkbox';cb.checked=true;cb.style.marginRight='8px';cb.dataset.slot=x.slot;lab.append(cb,document.createTextNode(x.slot+': '+x.example));ul.appendChild(lab)});box.appendChild(ul);
const b=document.createElement('button');b.className='p';b.textContent='Request the checked lines';b.onclick=async()=>{const slots=[...ul.querySelectorAll('input:checked')].map(x=>x.dataset.slot);try{const r=await api('/dash/api/phrases',{method:'POST',body:JSON.stringify({slots})});$('askmsg').textContent=r.message}catch(e){$('askmsg').textContent=e.message}load()};box.appendChild(b)}
$('past').textContent=S.requests.length?'Requested before: '+S.requests.map(r=>(r.sent?'sent ':'saved ')+r.slots.join(', ')+' ('+ago(r.t,S.now)+')').join('; '):''}
async function load(){try{S=await api('/dash/api/summary');JOBS=(await api('/dash/api/jobs')).jobs}catch(e){$('sub').textContent=e.status===401?'Open the address printed when the agent started (it ends with #token=...).':'Could not load: '+e.message;return}
$('title').textContent=S.pack.title||'Pack agent';$('sub').textContent=(S.pack.lines||0).toLocaleString()+' lines, language '+S.pack.language+', '+S.workflows+' workflows';
$('mode').textContent=S.paused?'PAUSED':S.mode==='live'?'LIVE: sending for real':'DRY RUN: nothing is sent';$('mode').className='badge '+(S.paused?'paused':S.mode==='live'?'live':'dry');
$('pause').textContent=S.paused?'Resume sending':'Pause all sending';$('pause').onclick=()=>api('/dash/api/pause',{method:'POST',body:JSON.stringify({on:!S.paused})}).then(load);
render();lines()}
$('t1').onclick=()=>{$('v1').hidden=false;$('v2').hidden=true;$('t1').className='tab on';$('t2').className='tab'};$('t2').onclick=()=>{$('v1').hidden=true;$('v2').hidden=false;$('t2').className='tab on';$('t1').className='tab'};
$('q').oninput=()=>S&&render();$('kind').onchange=()=>S&&render();
$('ask').onclick=async()=>{$('ask').disabled=true;try{const r=await api('/dash/api/phrases',{method:'POST',body:JSON.stringify({custom:{when:$('when').value,text:$('text').value}})});$('askmsg').textContent=r.message;if(r.sent){$('when').value='';$('text').value=''}}catch(e){$('askmsg').textContent=e.message}$('ask').disabled=false;load()};
load();setInterval(load,15000);
</script></body></html>"""
