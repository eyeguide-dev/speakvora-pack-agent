"""Announce a sale (shops, restaurants, salons, laundries and car businesses only; never a clinic, pharmacy, dispensary, legal, finance, public, school, corrections or collections business).

What it does, in this order, and what it will never do:
  1. Watches the web pages (and, if you give one, the product list) that you list, once a day or when you press "Check now".
  2. When it finds a NEW sale or promotion that was not on the page before, it writes a short announcement from the words on that page and keeps it as a DRAFT. It never makes up a price or a date: every number in the draft comes from the page.
  3. You see the draft on your dashboard. You can change the words, send yourself a test, and see exactly who would get it. Nothing is sent to a customer until you press Approve.
  4. After you approve, the text goes ONLY to people on your consent list: people who agreed to sale texts, with the source and the time they agreed written down. Everyone who ever replied STOP is left out for good.
     The text always says how to stop. It is sent only inside the sending hours you set (default 9 a.m. to 8 p.m. in your time zone), in small batches within your hourly limit, and at most a few sale texts per person per month.
  5. In Practice mode (the default) the whole run is rehearsed: nothing is sent, and you see who would have received it.
This is a tool, not legal advice. In the United States, sale texts generally need the person's prior written agreement (the TCPA and state laws, and mobile carrier rules). Rules differ by country and state.
Speakvora does not check that your consent list is real: it only refuses to text anyone who is not on it, and anyone who said STOP.
"""
import csv, hashlib, io, json, os, re, time, urllib.parse
from zoneinfo import ZoneInfo
import datetime as dt

from . import kits, safety as S

MAX_URLS, MAX_TEXT, MAX_DRAFTS = 5, 320, 5
SALE_RX = re.compile(r"(?i)(\b\d{1,2}\s?%\s?off\b|\bpercent off\b|\bsale\b|\bclearance\b|\bdiscount(?:ed)?\b|\bbuy (?:one|1),? get (?:one|1)\b|\bbogo\b|\bhalf[- ]price\b|\blimited[- ]time\b|\bpromo(?:tion)?\b|\bspecial offer\b|\bsave \$?\d+|\b\d+\s?% savings\b|\bdeals?\b)")
OPTIN_WORDS = ("deals",)
DEFAULTS = {"window_start": "09:00", "window_end": "20:00", "max_per_month": 4, "batch_per_run": 20, "owner_phone": ""}

CONSENT_NOTE = ("Only text people who agreed to receive sale texts from you, and keep how and when they agreed. In the United States, sale texts generally need the person's prior written agreement "
                "(the TCPA, state laws and mobile carrier rules), and every text must say how to stop. Rules differ by country and state. This is not legal advice: ask your own counsel. "
                "Speakvora cannot check that your list is real. It will only text people on this list, never anyone who replied STOP, only in your sending hours, and only after you approve.")


class SaleError(ValueError):
    pass


def allowed(agent):
    return kits.sale_allowed(getattr(agent, "profile", "generic"))


def _need_allowed(agent):
    if not allowed(agent):
        raise SaleError("Announce a sale is only for shops and other businesses that sell to the public. It is not available for this kind of business.")


def workflow():
    return {"name": "announce_a_sale", "title": "Announces your sales to customers who agreed to sale texts", "what": "watches the pages you list for a new sale, writes the text for you, and sends it only after you approve it, only to people on your consent list",
            "kit": True, "sale": True, "enabled": False, "approved": False, "on": {"schedule": {"at": "10:00"}}, "do": [{"action": "sale_watch"}]}


# ---- stored state -------------------------------------------------------------------------------------------------------------------------------------

def _path(agent):
    return os.path.join(agent.cfg["state_dir"], "sales.json")


def load(agent):
    try:
        d = json.load(open(_path(agent), encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d.setdefault("urls", []); d.setdefault("feed", ""); d.setdefault("consent", {}); d.setdefault("snapshots", {}); d.setdefault("drafts", {}); d.setdefault("campaigns", {}); d.setdefault("sent_log", {}); d.setdefault("tests", [])
    d["settings"] = {**DEFAULTS, **(d.get("settings") or {})}
    return d


def _save(agent, d):
    os.makedirs(agent.cfg["state_dir"], exist_ok=True)
    tmp = _path(agent) + ".tmp"; json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, _path(agent))


def _now(agent):
    return int(agent.now())


def _local(agent):
    return dt.datetime.fromtimestamp(agent.now(), ZoneInfo(agent.cfg["timezone"]))


# ---- consent list ---------------------------------------------------------------------------------------------------------------------------------------

def add_consent(agent, phone, source, at=None, name=""):
    """One person who agreed to sale texts. Both the source (how they agreed: a form, a sign-up sheet at the counter, a text of DEALS...) and the time are required: a person with neither is not added."""
    _need_allowed(agent)
    who = S.norm_phone(phone)
    if not re.fullmatch(r"\+\d{10,15}", who or ""):
        raise SaleError("That is not a phone number.")
    source = re.sub(r"\s+", " ", str(source or "")).strip()
    if len(source) < 4:
        raise SaleError("Write how they agreed (for example “web form on our site” or “counter sign-up sheet”). A person without a source is not added.")
    now = _now(agent); at = int(at) if at else now
    if at > now + 60 or at < 1420070400:
        raise SaleError("The time they agreed must be a real date in the past.")
    d = load(agent)
    if agent.state.is_opted_out(who):
        raise SaleError("This person replied STOP. They can only rejoin by texting DEALS themselves.")
    d["consent"][who] = {"source": source[:120], "at": at, "name": str(name or "")[:60], "added": now}
    _save(agent, d)
    return {"phone": who}


def import_csv(agent, text):
    """CSV with a header row: phone, source, date (YYYY-MM-DD or a number of seconds), optional name. Returns how many were added and which rows were refused and why."""
    _need_allowed(agent)
    rows = list(csv.DictReader(io.StringIO(str(text).strip())))
    added, refused = 0, []
    for n, r in enumerate(rows, 2):
        r = {str(k).strip().lower(): (v or "").strip() for k, v in r.items() if k}
        raw = r.get("date") or r.get("at") or r.get("time") or ""
        try:
            at = int(raw) if raw.isdigit() else int(dt.datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=ZoneInfo(agent.cfg["timezone"])).timestamp())
        except ValueError:
            refused.append([n, "no date they agreed"]); continue
        try:
            add_consent(agent, r.get("phone", ""), r.get("source", ""), at, r.get("name", "")); added += 1
        except SaleError as e:
            refused.append([n, str(e)])
    return {"added": added, "refused": refused[:50], "refused_count": len(refused)}


def remove_consent(agent, phone):
    d = load(agent); who = S.norm_phone(phone); gone = d["consent"].pop(who, None) is not None; _save(agent, d); return gone


def revoke(agent, who):
    """Someone replied STOP: they leave the consent list now, and rejoining needs a new DEALS from them."""
    try:
        d = load(agent)
        if d["consent"].pop(S.norm_phone(who), None) is not None:
            _save(agent, d)
    except Exception:  # noqa: BLE001 - STOP itself is already recorded in the agent's opt-out list, which is what counts
        pass


def inbound(agent, who, low):
    """A customer texted DEALS: they agree to sale texts. The source and time are written down. Returns the confirmation to text back, or '' when this does not apply."""
    if low not in OPTIN_WORDS or not allowed(agent):
        return ""
    if agent.state.is_opted_out(who):
        agent.state.opt_in(who)                                         # they texted DEALS themselves: that is a fresh choice
    d = load(agent); had = who in d["consent"]
    d["consent"][who] = d["consent"].get(who) or {"source": "texted DEALS to our number", "at": _now(agent), "name": "", "added": _now(agent)}
    _save(agent, d)
    return agent._line_text("sale_already_optin" if had else "sale_optin_confirm") or ""


# ---- what to watch ---------------------------------------------------------------------------------------------------------------------------------------

def _public_url(u):
    p = urllib.parse.urlparse(str(u).strip())
    h = (p.hostname or "").lower()
    if p.scheme not in ("http", "https") or not h or h in ("localhost",) or h.endswith(".local") or h.endswith(".internal"):
        return False
    if re.fullmatch(r"[\d.]+", h) or ":" in h:                              # an address typed as numbers could be your own network
        return False
    return True


def set_sources(agent, urls, feed="", settings=None):
    _need_allowed(agent)
    urls = [str(u).strip() for u in (urls if isinstance(urls, list) else str(urls).splitlines()) if str(u).strip()]
    if len(urls) > MAX_URLS:
        raise SaleError(f"List at most {MAX_URLS} pages.")
    for u in urls + ([feed] if feed else []):
        if not _public_url(u):
            raise SaleError("“" + u[:60] + "” is not a public website address (it should start with https:// and name a website).")
    d = load(agent); d["urls"] = urls; d["feed"] = feed.strip()
    if settings:
        s = d["settings"]
        for k in ("window_start", "window_end"):
            if k in settings:
                if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(settings[k])):
                    raise SaleError("Use a time like 09:00.")
                s[k] = settings[k]
        if s["window_start"] < "08:00" or s["window_end"] > "21:00" or s["window_start"] >= s["window_end"]:
            raise SaleError("Sale texts go out between 08:00 and 21:00 at the earliest and latest, and the start must be before the end.")
        if "max_per_month" in settings:
            s["max_per_month"] = max(1, min(8, int(settings["max_per_month"])))
        if "batch_per_run" in settings:
            s["batch_per_run"] = max(1, min(100, int(settings["batch_per_run"])))
        if "owner_phone" in settings:
            op = S.norm_phone(settings["owner_phone"]) if settings["owner_phone"] else ""
            if op and not re.fullmatch(r"\+\d{10,15}", op):
                raise SaleError("That is not a phone number.")
            s["owner_phone"] = op
    _save(agent, d)
    return view(agent)


def _fetch(url):
    from . import scan
    raw, ct = scan._get(url, limit=400_000)
    return raw.decode("utf-8", "replace"), ct


def _segments(html, ct=""):
    from . import knowledge as KN
    text = KN._html(html) if "<" in html[:2000] else html
    out = []
    for seg in re.split(r"(?<=[.!?])\s+|\n+| {3,}|\s[|•·]\s", text):
        seg = re.sub(r"\s+", " ", seg).strip(" -–—:;")
        if 12 <= len(seg) <= 140 and SALE_RX.search(seg):
            out.append(seg)
    seen, uniq = set(), []
    for s in out:
        k = re.sub(r"\W+", " ", s.lower()).strip()
        if k not in seen:
            seen.add(k); uniq.append(s)
    return uniq[:20]


def _feed_items(raw):
    """Products on sale from a JSON list (or {"products": [...]}) or CSV: an item whose sale price is below its normal price. Returns segments like “Blue jacket now $40, was $60”."""
    items = []
    try:
        j = json.loads(raw)
        items = j if isinstance(j, list) else (j.get("products") or j.get("items") or [])
    except ValueError:
        items = list(csv.DictReader(io.StringIO(raw)))
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        it = {str(k).lower(): v for k, v in it.items()}
        name = str(it.get("name") or it.get("title") or "").strip()
        def num(*keys):
            for k in keys:
                try:
                    return float(str(it.get(k)).replace("$", "").replace(",", "").strip())
                except (TypeError, ValueError):
                    pass
            return None
        sale, was = num("sale_price", "sale", "price_sale"), num("price", "regular_price", "compare_at_price", "compare_price", "was")
        if "compare_at_price" in it and num("compare_at_price"):
            was, sale = num("compare_at_price"), num("price")
        if name and sale is not None and was is not None and 0 < sale < was:
            f = lambda x: ("$%d" % x) if float(x).is_integer() else "$%.2f" % x       # noqa: E731
            out.append(f"{name[:60]} now {f(sale)}, was {f(was)}")
    return out[:30]


def _norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


def watch(agent, force=False, fetch=None):
    """Looks at every page you listed (and the product list). A sale that was not there last time becomes a DRAFT; nothing is sent. force=True drafts from what is on the pages now (the “Check now” button)."""
    if not allowed(agent):
        return {"status": "not_available"}
    fetch = fetch or _fetch; d = load(agent)
    if not d["urls"] and not d["feed"]:
        return {"status": "no_sources"}
    now = _now(agent); found = []; errors = []
    for src in d["urls"] + ([d["feed"]] if d["feed"] else []):
        try:
            body, ct = fetch(src)
        except Exception as ex:  # noqa: BLE001 - a page that will not load is reported, and nothing is drafted from it
            errors.append(src[:80] + ": " + type(ex).__name__); continue
        segs = _feed_items(body) if src == d["feed"] else _segments(body, ct)
        snap = d["snapshots"].get(src)
        known = set(snap["seen"]) if snap else set()
        new = [s for s in segs if _norm(s) not in known] if (snap or force) else []
        d["snapshots"][src] = {"at": now, "seen": sorted(known | {_norm(s) for s in segs})[-200:]}
        if new:
            found.append((src, new))
    made = ""
    live = [x for x in d["drafts"].values() if x["status"] == "draft"]
    for src, new in found:
        if len(live) >= MAX_DRAFTS:
            break
        head = new[0]; more = new[1] if len(new) > 1 and len(new[0]) + len(new[1]) < 150 else ""
        text = (head.rstrip(".!") + ("." if not head.endswith(("!", "?")) else "") + (" " + more if more else "") + " " + src).strip()
        if len(text) > MAX_TEXT - 60:
            text = (head[: MAX_TEXT - 70].rstrip() + " " + src).strip()
        did = "d" + hashlib.sha1((src + head + str(now)).encode()).hexdigest()[:8]
        d["drafts"][did] = {"id": did, "created": now, "source": src, "found": new[:4], "text": text, "status": "draft", "tests": 0}
        made = made or did; live.append(d["drafts"][did])
        try:
            agent.run_actions("announce_a_sale", [{"action": "notify", "text": "A new sale was found on " + src[:80] + ". Open Announce a sale on your dashboard to read it and approve it. Nothing was sent."}], agent.ctx())
        except Exception:  # noqa: BLE001
            pass
    for x in d["drafts"].values():                                       # an old draft is stale: a sale may be over
        if x["status"] == "draft" and now - x["created"] > 7 * 86400:
            x["status"] = "expired"
    _save(agent, d)
    return {"status": "draft" if made else ("errors" if errors else "nothing_new"), "draft": made, "errors": errors}


# ---- the draft, the preview, the test, the approval --------------------------------------------------------------------------------------------------------

def compose(agent, text):
    """The exact words a customer receives: your business, the approved text, and the STOP line."""
    t = re.sub(r"\s+", " ", str(text)).strip()
    biz = agent.cfg.get("business", "")
    head = f"{biz}: " if biz and "YOUR-" not in biz and not t.lower().startswith(biz.lower()) else ""
    foot = agent._line_text("sale_stop_footer") or "Reply STOP to opt out."
    return (head + t + ("" if foot.lower() in t.lower() else " " + foot)).strip()


def _check(text):
    t = str(text or "").strip()
    if not t:
        raise SaleError("The text cannot be empty.")
    if len(t) > MAX_TEXT:
        raise SaleError(f"Keep it under {MAX_TEXT} characters so it does not cost your customers several messages.")
    if "{{" in t or "YOUR-" in t:
        raise SaleError("Fill in or remove the placeholder in the text.")
    from . import builder
    if builder.SECRET.search(t):
        raise SaleError("That looks like it contains a card number, password or key. Never put those in a text.")
    return t


def edit_draft(agent, did, text):
    _need_allowed(agent)
    d = load(agent); x = d["drafts"].get(did)
    if not x or x["status"] != "draft":
        raise SaleError("That draft is not waiting for approval.")
    x["text"] = _check(text); x["tests"] = 0; _save(agent, d); return x


def decline(agent, did):
    d = load(agent); x = d["drafts"].get(did)
    if not x or x["status"] not in ("draft", "approved"):
        raise SaleError("Nothing to decline.")
    x["status"] = "declined"
    for c in d["campaigns"].values():
        if c["draft"] == did and c["status"] == "sending":
            c["status"] = "stopped"
    _save(agent, d); return True


def _audience(agent, d, count_only=False):
    """(people who would get it now, {reason: how many left out})."""
    out, left = [], {"replied_stop": 0, "sent_too_many_this_month": 0}
    s = d["settings"]; month = _now(agent) - 30 * 86400
    for who, c in sorted(d["consent"].items()):
        if agent.state.is_opted_out(who):
            left["replied_stop"] += 1; continue
        if len([t for t in d["sent_log"].get(who, []) if t > month]) >= s["max_per_month"]:
            left["sent_too_many_this_month"] += 1; continue
        out.append(who)
    return out, left


def _mask(p):
    return p[:2] + "•" * (len(p) - 6) + p[-4:] if len(p) > 6 else p


def in_window(agent, d=None):
    s = (d or load(agent))["settings"]; t = _local(agent).strftime("%H:%M")
    return s["window_start"] <= t < s["window_end"]


def preview(agent, did):
    d = load(agent); x = d["drafts"].get(did)
    if not x:
        raise SaleError("No such draft.")
    who, left = _audience(agent, d)
    msg = compose(agent, x["text"])
    return {"id": did, "message": msg, "characters": len(msg), "messages_each": 1 if len(msg) <= 160 else (len(msg) + 152) // 153, "will_send_to": len(who), "left_out": left, "example": _mask(who[0]) if who else "",
            "practice": bool(agent.dry), "window": f"{d['settings']['window_start']} to {d['settings']['window_end']}", "inside_window": in_window(agent, d), "needs_owner_phone": not _owner_phone(agent, d),
            "consent_people": len(d["consent"])}


def _owner_phone(agent, d):
    p = d["settings"].get("owner_phone") or str((agent.cfg.get("facts") or {}).get("oncall_phone", ""))
    return S.norm_phone(p) if p and "YOUR-" not in p else ""


def test_send(agent, did):
    """A text of the finished announcement to the owner's own phone only. In Practice mode it is rehearsed and nothing is sent."""
    _need_allowed(agent)
    d = load(agent); x = d["drafts"].get(did)
    if not x or x["status"] not in ("draft", "approved"):
        raise SaleError("That draft is not waiting.")
    to = _owner_phone(agent, d)
    if not to:
        raise SaleError("Add your own mobile number first (Announce a sale, Settings: your number for tests).")
    now = _now(agent); d["tests"] = [t for t in d["tests"] if t > now - 86400]
    if len(d["tests"]) >= 5:
        raise SaleError("You have sent five tests today. That is enough.")
    ctx = agent.ctx(customer={"phone": to, "name": "Owner", "sms_consent": True}); ctx["_approved"] = True
    r = agent.run_actions("announce_a_sale/test", [{"action": "sms", "to": to, "text": "[TEST] " + compose(agent, x["text"]), "raw": True, "urgent": True}], ctx, job_prefix=f"saletest:{did}:{now}")
    st = (r[0] if r else {}).get("status", "")
    if st in ("sent", "dry_run", "queued"):
        d["tests"].append(now); x["tests"] = x.get("tests", 0) + 1; _save(agent, d)
    return {"status": st, "practice": bool(agent.dry), "to": _mask(to), "reason": (r[0] if r else {}).get("reason", "")}


def approve(agent, did, text=None):
    """Your OK. The text can be changed first (a change is checked again). Sending then starts, in batches, on the agent's own schedule; in Practice mode it is only rehearsed."""
    _need_allowed(agent)
    if text is not None:
        edit_draft(agent, did, text)
    d = load(agent); x = d["drafts"].get(did)
    if not x or x["status"] != "draft":
        raise SaleError("That draft is not waiting for approval.")
    if not d["consent"]:
        raise SaleError("Your consent list is empty, so nobody would receive it. Add the people who agreed to sale texts first.")
    x["status"] = "approved"; x["approved_at"] = _now(agent); x["approved_hash"] = hashlib.sha1(compose(agent, x["text"]).encode()).hexdigest()
    who, left = _audience(agent, d)
    cid = "c" + hashlib.sha1((did + str(_now(agent))).encode()).hexdigest()[:8]
    d["campaigns"][cid] = {"id": cid, "draft": did, "started": _now(agent), "practice": bool(agent.dry), "status": "sending", "pending": who, "done": {}, "left_out": left}
    _save(agent, d)
    agent.state.log(workflow="announce_a_sale", action="approve", status="approved", dry_run=bool(agent.dry), draft=did, people=len(who))
    return step(agent, cid)


def step(agent, cid):
    """Sends the next small batch of an approved campaign. Safe to call as often as you like: it stops at the sending-hours window, your hourly limit and the monthly limit per person."""
    if not allowed(agent):
        return {"status": "not_available"}
    d = load(agent); c = d["campaigns"].get(cid)
    if not c or c["status"] != "sending":
        return {"status": (c or {}).get("status", "none")}
    x = d["drafts"].get(c["draft"])
    if not x or x["status"] != "approved":
        c["status"] = "stopped"; _save(agent, d); return {"status": "stopped"}
    msg = compose(agent, x["text"])
    if hashlib.sha1(msg.encode()).hexdigest() != x.get("approved_hash"):
        c["status"] = "stopped"; x["status"] = "draft"; _save(agent, d)                   # the words changed after approval: it needs approving again
        return {"status": "stopped", "reason": "text_changed"}
    if not agent.dry and not in_window(agent, d):
        return {"status": "waiting", "reason": "outside_sending_hours"}
    s = d["settings"]; sent_now = 0; month = _now(agent) - 30 * 86400
    for who in list(c["pending"]):
        if sent_now >= s["batch_per_run"]:
            break
        if who not in d["consent"]:                                                    # removed from the list (or said STOP) since approval
            c["pending"].remove(who); c["done"][who] = "left_the_list"; continue
        if agent.state.is_opted_out(who):
            c["pending"].remove(who); c["done"][who] = "replied_stop"; continue
        if len([t for t in d["sent_log"].get(who, []) if t > month]) >= s["max_per_month"]:
            c["pending"].remove(who); c["done"][who] = "monthly_limit"; continue
        ctx = agent.ctx(customer={"phone": who, "name": d["consent"][who].get("name", ""), "sms_consent": True}); ctx["_approved"] = True      # the owner approved this announcement; consent is on the list; every other safety check still runs
        r = agent.run_actions("announce_a_sale", [{"action": "sms", "to": who, "text": msg, "raw": True}], ctx, job_prefix=f"sale:{c['id']}:{who}")
        st = (r[0] if r else {}).get("status", ""); why = (r[0] if r else {}).get("reason", "")
        if st in ("sent", "queued"):
            c["pending"].remove(who); c["done"][who] = st; sent_now += 1
            if not agent.dry:
                d["sent_log"].setdefault(who, []).append(_now(agent))
        elif st == "dry_run":
            c["pending"].remove(who); c["done"][who] = "practice"; sent_now += 1
        elif st == "blocked" and why in ("quiet_hours", "hourly_limit", "recipient_daily_limit"):
            agent.state.job_delete(f"sale:{c['id']}:{who}:0")                       # nothing was sent: forget the blocked entry so the next round can try this person again
            break                                                                      # timing: try again later, nobody is skipped
        else:
            c["pending"].remove(who); c["done"][who] = st or "failed"
    if not c["pending"]:
        c["status"] = "practiced" if c["practice"] else "sent"; c["finished"] = _now(agent)
        if not c["practice"]:
            x["status"] = "sent"
        else:
            x["status"] = "draft"; x["practiced"] = _now(agent)                       # rehearsed only: still waiting for a real approval in Live
    d["sent_log"] = {k: [t for t in v if t > _now(agent) - 40 * 86400] for k, v in d["sent_log"].items() if any(t > _now(agent) - 40 * 86400 for t in v)}
    _save(agent, d)
    return {"status": c["status"], "sent_now": sent_now, "pending": len(c["pending"])}


def tick(agent):
    """Called about once a minute: carries on with any approved campaign that is still sending."""
    if not allowed(agent):
        return 0
    d = load(agent); n = 0
    for cid, c in d["campaigns"].items():
        if c["status"] == "sending":
            step(agent, cid); n += 1
    return n


# ---- for the dashboard --------------------------------------------------------------------------------------------------------------------------------------

def enable(agent, on):
    """Switch the watching on or off. Turning it on is itself the owner's decision: it needs at least one page or a product list. Nothing is ever sent without approving each announcement."""
    _need_allowed(agent)
    from . import wfedit
    d = load(agent)
    if on and not (d["urls"] or d["feed"]):
        raise SaleError("List at least one page to watch first.")
    ed = wfedit.load(agent); e = ed.setdefault("announce_a_sale", {}); e["approved"] = bool(on); wfedit._save(agent, ed)
    wfedit._set_enabled(agent, "announce_a_sale", bool(on)); agent._load_workflows()
    return view(agent)


def view(agent):
    if not allowed(agent):
        return {"available": False, "why": "Announce a sale is only for shops, restaurants, salons, laundries and car businesses. It is never offered to health, pharmacy, dispensary, legal, finance, public-service, school, prison or collections businesses."}
    from . import wfedit
    d = load(agent); who, left = _audience(agent, d)
    active = [c for c in d["campaigns"].values() if c["status"] == "sending"]
    drafts = sorted(d["drafts"].values(), key=lambda x: -x["created"])[:12]
    return {"available": True, "on": wfedit.approved(agent, "announce_a_sale") and bool(next((w for w in agent.workflows if w["name"] == "announce_a_sale"), None)), "urls": d["urls"], "feed": d["feed"], "settings": d["settings"],
            "consent_note": CONSENT_NOTE, "practice": bool(agent.dry), "consent_count": len(d["consent"]), "would_receive": len(who), "left_out": left,
            "consent": [{"phone": _mask(p), "full": p, "source": c["source"], "at": c["at"], "name": c.get("name", "")} for p, c in sorted(d["consent"].items(), key=lambda kv: -kv[1]["at"])[:200]],
            "drafts": [{"id": x["id"], "status": x["status"], "text": x["text"], "source": x["source"], "created": x["created"], "found": x.get("found", []), "practiced": x.get("practiced")} for x in drafts],
            "sending": [{"id": c["id"], "pending": len(c["pending"]), "done": len(c["done"]), "practice": c["practice"]} for c in active],
            "history": [{"id": c["id"], "status": c["status"], "people": len(c["done"]), "practice": c["practice"], "started": c["started"]} for c in sorted(d["campaigns"].values(), key=lambda c: -c["started"])[:8]],
            "owner_phone_set": bool(_owner_phone(agent, d))}
