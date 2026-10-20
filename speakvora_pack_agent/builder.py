"""The workflow builder: "when this happens, do this", made in the dashboard without touching a file.
A workflow you make is saved in agent-state/custom_workflows.json (so a bundle update never overwrites it), turned into the same workflow format the ready-made ones use, and runs through exactly the same safety checks:
consent, STOP, quiet hours, limits, 'ask before sending' and practice mode. Your texts to customers always go through the sms action; nothing here can skip a check.
Triggers: a customer texts a word, something happens in your app (an event), a booking is coming up, or a time of day. Steps: reply to the text, text the customer, tell your team, email someone."""
import json, os, re, time

MAX_WORKFLOWS, MAX_STEPS, MAX_TEXT = 30, 5, 500
EVENTS = {
    "order.received": "A new order arrives", "order.preparing": "An order is being prepared", "order.ready": "An order is ready", "order.delayed": "An order is delayed", "order.picked_up": "An order is picked up",
    "order.out_for_delivery": "An order is out for delivery", "order.delivered": "An order is delivered", "order.cancelled": "An order is cancelled", "table.ready": "A table is ready",
    "reservation.created": "A reservation is made", "reservation.no_show": "A guest does not show up", "visit.completed": "A visit is finished", "appointment.created": "Someone books an appointment",
    "appointment.cancelled": "Someone cancels", "payment.failed": "A payment fails", "payment.received": "A payment comes in", "payment.refunded": "A payment is refunded", "payment.due": "A payment is coming up",
    "pipeline.failed": "A build fails", "pipeline.succeeded": "A build passes", "incident.triggered": "An incident is triggered", "incident.resolved": "An incident is resolved", "release.published": "A release is published"}
TRIGGERS = {"sms_keywords": "SMS Person", "event": "App Event", "before_booking": "Booking", "daily": "Daily"}
STEPS = {"reply": "Reply to their text", "sms": "Text the customer", "notify": "Tell my team (Slack or Teams)", "email": "Email someone"}
BEFORE = {15: "15 minutes", 60: "1 hour", 120: "2 hours", 240: "4 hours", 1440: "1 day", 2880: "2 days"}
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
VARS = {"all": ["business", "fact:hours", "fact:address", "fact:phone"], "sms_keywords": ["sms.body", "sms.from"], "event": ["customer.name", "order.number"], "before_booking": ["customer.name", "start_local"], "daily": ["today_text", "summary"]}
VAR_HELP = {"business": "your business name", "fact:hours": "your opening hours", "fact:address": "your address", "fact:phone": "your phone number", "sms.body": "what they texted", "sms.from": "their number",
            "customer.name": "the customer's name", "order.number": "the order number", "start_local": "the booking time", "today_text": "today's bookings", "summary": "yesterday's summary"}
SAMPLE = {"business": "Bell & Basil", "fact:hours": "Tue to Sun, 5 to 10 PM", "fact:address": "12 Main Street", "fact:phone": "+1 929 581 6269", "sms.body": "menu please", "sms.from": "+1 646 555 0101",
          "customer.name": "Ann", "order.number": "1049", "start_local": "Friday 7:00 PM", "today_text": "7:00 PM Ann (4); 8:30 PM Raj (2)", "summary": "Yesterday: 12 conversations (8 texts, 4 calls). Your AI answered 8 texts. 2 needed a person. Nothing is waiting for you."}
SECRET = re.compile(r"\b(?:\d[ -]?){13,19}\b|\b\d{3}-\d{2}-\d{4}\b|\b(?:password|passcode|pin|api[_ -]?key|token)\s*[:=]", re.I)


class BuildError(ValueError):
    pass


def _path(agent):
    return os.path.join(agent.state.dir, "custom_workflows.json")


def load(agent):
    try:
        with open(_path(agent), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and isinstance(d.get("workflows"), list) else {"workflows": []}
    except (OSError, ValueError):
        return {"workflows": []}


def _save(agent, d):
    p = _path(agent); tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def _vars_ok(text, trig):
    allowed = set(VARS["all"]) | set(VARS.get(trig, []))
    for v in re.findall(r"\{\{\s*([^{}]*?)\s*\}\}", text):
        if v not in allowed:
            raise BuildError("“{{" + v + "}}” cannot be used here. You can use: " + ", ".join("{{" + a + "}}" for a in sorted(allowed)) + ".")


def validate(spec):
    """The cleaned spec, or a BuildError saying in plain words what to fix."""
    name = re.sub(r"\s+", " ", str(spec.get("name") or "")).strip()[:60]
    if not name:
        kind = str((spec.get("trigger") or {}).get("type") or "")
        name = {"sms_keywords": "Text reply", "event": "App event", "before_booking": "Booking reminder", "daily": "Daily message"}.get(kind, "My workflow")
    if len(name) < 2:
        raise BuildError("Give the workflow a name (at least 2 letters).")
    t = spec.get("trigger") or {}; kind = t.get("type")
    if kind not in TRIGGERS:
        raise BuildError("Choose when it should start.")
    trig = {"type": kind}
    if kind == "sms_keywords":
        words = [re.sub(r"[^\w' -]", "", w).strip().lower()[:30] for w in (t.get("keywords") if isinstance(t.get("keywords"), list) else re.split(r"[,\n]+", str(t.get("keywords") or ""))) or []]
        words = [w for w in words if w][:12]
        if not words:
            raise BuildError("Type at least one word customers will text, for example: menu.")
        if {"stop", "start", "help", "unstop"} & set(words):
            raise BuildError("STOP, START and HELP are handled for you by law; choose other words.")
        trig["keywords"] = words
    elif kind == "event":
        ev = str(t.get("event") or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9_]+(\.[a-z0-9_]+){0,3}", ev):
            raise BuildError("Choose what happens in your app, or type the event name your app sends (like order.ready).")
        trig["event"] = ev
    elif kind == "before_booking":
        try:
            mins = int(t.get("minutes"))
        except (TypeError, ValueError):
            mins = 0
        if mins not in BEFORE:
            raise BuildError("Choose how long before the booking.")
        trig["minutes"] = mins; trig["title_contains"] = re.sub(r"\s+", " ", str(t.get("title_contains") or "")).strip()[:40]
    else:
        at = str(t.get("at") or "")
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
            raise BuildError("Choose a time of day, like 09:30.")
        days = [d for d in (t.get("days") or DAYS) if d in DAYS] or DAYS
        trig["at"] = at; trig["days"] = days
    steps = []
    for st in (spec.get("steps") or [])[:MAX_STEPS]:
        k = st.get("type")
        if k not in STEPS:
            continue
        if k == "reply" and kind != "sms_keywords":
            raise BuildError("“Reply to their text” only works when a customer texts you.")
        if k == "sms" and kind == "daily":
            raise BuildError("A daily workflow can tell your team or email you, not text customers.")
        text = str(st.get("text") or "").strip()[:MAX_TEXT]
        if len(text) < 3:
            raise BuildError(STEPS[k] + ": write the message.")
        if SECRET.search(text):
            raise BuildError("The message looks like it contains a card number or password. Remove it.")
        _vars_ok(text, kind)
        item = {"type": k, "text": text}
        if k == "notify":
            ch = re.sub(r"\s+", "", str(st.get("channel") or "")).lstrip("#").lower()
            if ch:
                if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}|[CG][A-Z0-9]{8,12}", ch, re.I):
                    raise BuildError("Slack channel: use the channel's name, like bugs or billing.")
                item["channel"] = ch if re.fullmatch(r"[CG][A-Z0-9]{8,12}", ch, re.I) else "#" + ch
        if k == "email":
            to = str(st.get("to") or "").strip()
            if kind in ("daily", "sms_keywords") or (to and to != "customer"):
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to):
                    raise BuildError("Type the email address to send to.")
            item["to"] = to or "customer"; item["subject"] = re.sub(r"\s+", " ", str(st.get("subject") or name)).strip()[:90]
        steps.append(item)
    if not steps:
        raise BuildError("Add at least one step: what should happen?")
    return {"name": name, "trigger": trig, "steps": steps, "enabled": bool(spec.get("enabled", True))}


def compile_spec(spec, wid):
    """The same workflow format the ready-made workflows use."""
    t = spec["trigger"]; k = t["type"]
    if k == "sms_keywords":
        on = {"sms": {"keywords": t["keywords"]}}
    elif k == "event":
        on = {"event": t["event"]}
    elif k == "before_booking":
        cal = {"starts_in_minutes": t["minutes"], "window_minutes": min(30, max(5, t["minutes"] // 2))}
        if t.get("title_contains"):
            cal["title_contains"] = t["title_contains"]
        on = {"calendar": cal}
    else:
        on = {"schedule": {"at": t["at"], "days": t["days"]}}
    do = []
    for s in spec["steps"]:
        if s["type"] == "reply":
            do.append({"action": "reply", "text": s["text"]})
        elif s["type"] == "sms":
            do.append({"action": "sms", "to": "{{sms.from}}" if k == "sms_keywords" else "{{customer.phone}}", "text": s["text"]})
        elif s["type"] == "notify":
            do.append({"action": "notify", "text": s["text"], **({"channel": s["channel"], "direct": True} if s.get("channel") else {})})
        else:
            do.append({"action": "email", "to": ("{{customer.email}}" if s["to"] == "customer" else s["to"]), "subject": s["subject"], "text": s["text"]})
    return {"name": "custom_" + wid, "title": spec["name"], "custom": True, "enabled": spec["enabled"], "on": on, "do": do}


def compiled(agent):
    """The enabled custom workflows, ready to run. Texted keywords come first so your words win over the bundle's."""
    return [compile_spec(w["spec"], w["id"]) for w in load(agent)["workflows"] if w["spec"].get("enabled", True)]


def when_text(spec):
    t = spec["trigger"]; k = t["type"]
    if k == "sms_keywords":
        return "Someone texts " + " or ".join("“" + k + "”" for k in t["keywords"])
    if k == "event":
        return EVENTS.get(t["event"], "Your app sends “" + t["event"] + "”")
    if k == "before_booking":
        return BEFORE[t["minutes"]] + " before a booking" + (" (title has “" + t["title_contains"] + "”)" if t.get("title_contains") else "")
    return "Every " + ("day" if len(t["days"]) == 7 else ", ".join(t["days"])) + " at " + t["at"]


def then_text(spec):
    return "; ".join(STEPS[s["type"]].lower() + (" in " + s["channel"] if s["type"] == "notify" and s.get("channel") else "") for s in spec["steps"])


def view(agent):
    from . import connect as SU
    d = load(agent)
    known = {}
    for w in getattr(agent, "workflows", []):
        e = (w.get("on") or {}).get("event")
        if e:
            known[e] = EVENTS.get(e, e.replace(".", " ").replace("_", " ").capitalize())
    for e, l in EVENTS.items():
        known.setdefault(e, l)
    return {"workflows": [{"id": w["id"], "name": w["spec"]["name"], "when": when_text(w["spec"]), "then": then_text(w["spec"]), "enabled": bool(w["spec"].get("enabled", True)), "spec": w["spec"], "updated": w.get("updated", 0)} for w in d["workflows"]],
            "triggers": TRIGGERS, "steps": STEPS, "events": [{"id": k, "label": v} for k, v in sorted(known.items(), key=lambda x: x[1])], "before": [{"minutes": k, "label": v} for k, v in BEFORE.items()],
            "vars": {k: [{"name": n, "help": VAR_HELP[n]} for n in v] for k, v in VARS.items()}, "days": DAYS, "limit": MAX_WORKFLOWS,
            "connected": {"team": bool(agent.slack.configured or getattr(agent.teams, "configured", False)), "sms": bool(agent.twilio.configured), "email": bool(agent.mail.configured), "calendar": bool(agent.gcal.configured or agent.outlook.configured)}}


def save(agent, spec, wid=None):
    clean = validate(spec); d = load(agent)
    if wid:
        hit = next((w for w in d["workflows"] if w["id"] == wid), None)
        if not hit:
            raise BuildError("That workflow no longer exists.")
        hit["spec"] = clean; hit["updated"] = int(time.time())
    else:
        if len(d["workflows"]) >= MAX_WORKFLOWS:
            raise BuildError(f"That is {MAX_WORKFLOWS} workflows. Delete one you no longer use first.")
        wid = "w" + re.sub(r"[^a-z0-9]", "", clean["name"].lower())[:14] + format(int(time.time() * 1000) % 100000, "05d")
        d["workflows"].append({"id": wid, "spec": clean, "created": int(time.time()), "updated": int(time.time())})
    _save(agent, d); agent._load_workflows()
    return {"id": wid, **next(x for x in view(agent)["workflows"] if x["id"] == wid)}


def delete(agent, wid):
    d = load(agent); n = len(d["workflows"]); d["workflows"] = [w for w in d["workflows"] if w["id"] != wid]
    if len(d["workflows"]) == n:
        raise BuildError("That workflow no longer exists.")
    _save(agent, d); agent._load_workflows()


def toggle(agent, wid, on):
    d = load(agent); hit = next((w for w in d["workflows"] if w["id"] == wid), None)
    if not hit:
        raise BuildError("That workflow no longer exists.")
    hit["spec"]["enabled"] = bool(on); _save(agent, d); agent._load_workflows()


def preview(agent, spec):
    """What each step would say, with sample details filled in (nothing is sent)."""
    clean = validate(spec); out = []; sample = dict(SAMPLE); facts = agent.cfg.get("facts") or {}
    biz = str(agent.cfg.get("business") or "")
    if biz and "YOUR-" not in biz:
        sample["business"] = biz
    for key in ("hours", "address", "phone"):
        if facts.get(key) and "YOUR-" not in str(facts[key]):
            sample["fact:" + key] = str(facts[key])
    for s in clean["steps"]:
        text = re.sub(r"\{\{\s*([^{}]*?)\s*\}\}", lambda m: sample.get(m.group(1), m.group(0)), s["text"])
        out.append({"step": STEPS[s["type"]], "text": text, "to": ("the customer" if s["type"] in ("reply", "sms") or s.get("to") == "customer" else s.get("to", "your team"))})
    return {"when": when_text(clean), "steps": out}
