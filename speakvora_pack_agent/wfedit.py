"""Open a ready-made workflow, read it in plain words, change its wording and its timing, and approve or switch it off.

Your changes are kept in agent-state/workflow_edits.json, not in workflows.json, so a bundle update never overwrites them. They are applied to the workflow when the agent loads it.
A kit workflow (the ready-made set for your industry, see kits.py) does nothing until you have opened it and pressed "Approve and turn on". Turning it off, or editing it, keeps the approval you gave only if the new wording passes
the same checks (no promotion or health detail in a business that must not send them). Nothing here can skip consent, STOP, quiet hours, limits or Practice mode: they act on every message afterwards.
"""
import copy, json, os, re

from . import builder, kits, slots as SL

MAX_TEXT = 480
VAR_OK = re.compile(r"^\{\{\s*(?:business|customer\.name|customer\.phone|start_local|start_text|order\.number|order\.extra_minutes|track\.line|today_text|summary|sms\.body|sms\.from|call\.from|fact:[\w]+|slot:[\w]+|slotvar:[\w.]+|t:[\w]+|appointment\.id|ticket\.summary|reminder\.slot|last\.sms)\s*\}\}$")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_NAMES = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}


class EditError(ValueError):
    pass


def _path(agent):
    return os.path.join(agent.cfg["state_dir"], "workflow_edits.json")


def load(agent):
    try:
        d = json.load(open(_path(agent), encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return d if isinstance(d, dict) else {}


def _save(agent, d):
    os.makedirs(os.path.dirname(_path(agent)), exist_ok=True)
    tmp = _path(agent) + ".tmp"; json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, _path(agent))


def reminder_setting(agent):
    r = load(agent).get("smart_reminder", {}).get("reminder") or {}
    return {"before": [k for k in (r.get("before") or kits.REMINDER_DEFAULT) if k in kits.REMINDER_CHOICES], "morning_at": r.get("morning_at") or kits.MORNING_AT}


def hours(agent):
    h = (load(agent).get("_hours") or {})
    return h if h.get("days") and h.get("open") and h.get("close") else {}


def approved(agent, name):
    return bool((load(agent).get(name) or {}).get("approved"))


def apply(agent, workflows):
    """The workflows the agent should run: your wording and timing applied, and kit workflows kept out until they are approved. Returns new copies; the file on disk is not changed."""
    ed = load(agent); out = []
    for w in workflows:
        if w.get("kit") and not (ed.get(w["name"]) or {}).get("approved"):
            continue
        e = ed.get(w["name"])
        if e:
            w = copy.deepcopy(w)
            for i, t in (e.get("texts") or {}).items():
                try:
                    step = w["do"][int(i)]
                except (IndexError, ValueError):
                    continue
                if "text" in step and isinstance(t, str) and t.strip():
                    step["text"] = t
            on = w.get("on") or {}
            if e.get("keywords") and isinstance(on.get("sms"), dict):
                on["sms"] = dict(on["sms"], keywords=list(e["keywords"])); on["sms"].pop("topic", None)
            if e.get("daily_at") and isinstance(on.get("schedule"), dict):
                on["schedule"] = dict(on["schedule"], at=e["daily_at"])
            if e.get("title_contains") is not None and isinstance(on.get("calendar"), dict):
                on["calendar"] = dict(on["calendar"], title_contains=e["title_contains"])
            if e.get("lead") and isinstance(on.get("calendar"), dict) and not on["calendar"].get("smart"):
                on["calendar"] = dict(on["calendar"], starts_in_minutes=int(e["lead"]))
        out.append(w)
    return out


# ---- reading a workflow in plain words ---------------------------------------------------------------------------------------------------------------------

def _find(agent, name):
    from . import connect
    for w in connect._workflow_file(agent).get("workflows", []):
        if w["name"] == name:
            return w
    raise EditError("No such workflow.")


def shown(template, profile):
    """The template as a customer would read it: recorded lines written out as their English sentence, so you can read and change the words."""
    def sub(m):
        key = m.group(1)
        if key.startswith("slot:"):
            return SL.fallback_text(key[5:]) or m.group(0)
        return m.group(0)
    return re.sub(r"\{\{\s*([\w.:\-]+)\s*\}\}", sub, template)


def _label(step):
    return {"sms": "Text to the customer", "reply": "Reply to the customer's text", "email": "Email to the customer", "notify": "Message to your team (Slack or Teams)"}.get(step.get("action"), "")


def trigger_words(w):
    on = w.get("on") or {}
    if "event" in on:
        return "when " + builder.EVENTS.get(on["event"], "your app sends “" + on["event"] + "”").lower() if on["event"] in builder.EVENTS else "when your app sends “" + on["event"] + "”"
    if "sms" in on:
        if on["sms"].get("when_closed"):
            return "when a customer texts while you are closed"
        return "when a customer texts one of these words"
    if "calendar" in on:
        return "before a booking in your calendar" if on["calendar"].get("smart") else "when a booking is coming up in your calendar"
    if "schedule" in on:
        return "every day at a set time"
    if "email" in on:
        return "when a customer emails you"
    if "call" in on:
        return "when someone calls"
    if "slack_command" in on:
        return "when your staff types a Slack command"
    return ""


def detail(agent, name):
    """Everything the edit screen shows for one workflow."""
    from . import connect
    w = _find(agent, name); ed = load(agent).get(name) or {}; prof = getattr(agent, "profile", "generic")
    eff = apply_one(agent, w)
    texts = []
    for i, step in enumerate(w.get("do", [])):
        if "text" in step and _label(step) and isinstance(step["text"], str):
            cur = (ed.get("texts") or {}).get(str(i))
            texts.append({"i": i, "label": _label(step), "text": cur if cur else shown(step["text"], prof), "original": shown(step["text"], prof), "changed": bool(cur), "team": step.get("action") == "notify"})
    on = w.get("on") or {}; timing = {}
    if on.get("calendar", {}).get("smart"):
        s = reminder_setting(agent)
        timing = {"kind": "reminder", "choices": [{"key": k, "label": v[0], "on": k in s["before"]} for k, v in kits.REMINDER_CHOICES.items()], "morning_at": s["morning_at"],
                  "title_contains": ((eff.get("on") or {}).get("calendar") or {}).get("title_contains", ""), "note": "Each time you tick sends a line that fits it: a reminder for the day before, a good-morning line for the morning of, a short “coming up soon” line for the hours before."}
    elif "sms" in on and on["sms"].get("when_closed"):
        timing = {"kind": "hours", "hours": hours(agent) or {"days": ["mon", "tue", "wed", "thu", "fri"], "open": "09:00", "close": "17:00", "set": False}, "days": [{"key": d, "label": DAY_NAMES[d]} for d in DAYS],
                  "note": "This answers only outside the times you set. Until you set your opening times it stays quiet."}
    elif "sms" in on and on["sms"].get("keywords"):
        timing = {"kind": "keywords", "keywords": list(((eff.get("on") or {}).get("sms") or {}).get("keywords") or []), "note": "A customer's text that contains one of these words starts it. Separate words with commas."}
    elif "schedule" in on:
        timing = {"kind": "daily", "at": ((eff.get("on") or {}).get("schedule") or {}).get("at", "09:00")}
    elif "calendar" in on:
        timing = {"kind": "lead", "minutes": ((eff.get("on") or {}).get("calendar") or {}).get("starts_in_minutes", 60), "options": [{"minutes": m, "label": l} for m, l in builder.BEFORE.items()]}
    else:
        timing = {"kind": "fixed", "note": "It starts by itself when this happens. The wording is yours to change."}
    row = next((x for x in connect.workflows(agent) if x["name"] == name), {})
    note = ""
    if prof in kits.REGULATED:
        note = "Written to be safe by design: no promotion, no health, legal or account details in a text, and a person takes anything sensitive. This is not a claim of HIPAA or any other certification; you stay responsible for your own rules."
    return {"name": name, "title": w.get("title") or row.get("title") or name, "what": w.get("what") or row.get("what", ""), "when": trigger_words(w), "kit": bool(w.get("kit")), "approved": bool(ed.get("approved")) or not w.get("kit"),
            "enabled": bool(w.get("enabled", True)) and (bool(ed.get("approved")) or not w.get("kit")), "needs": row.get("needs", []), "missing": row.get("missing", []), "texts": texts, "timing": timing, "sale": bool(w.get("sale")),
            "note": note, "state": state_of(w, ed), "profile": prof}


def state_of(w, ed):
    if w.get("kit") and not (ed or {}).get("approved"):
        return "needs_approval"
    return "on" if w.get("enabled", True) else "off"


def apply_one(agent, w):
    r = apply(agent, [dict(w, kit=False)] if w.get("kit") else [w])
    return r[0] if r else w


# ---- changing a workflow ---------------------------------------------------------------------------------------------------------------------------------

def _check_text(prof, t):
    t = str(t).strip()
    if not t:
        raise EditError("The wording cannot be empty.")
    if len(t) > MAX_TEXT:
        raise EditError(f"Keep it under {MAX_TEXT} characters.")
    for m in re.finditer(r"\{\{[^}]*\}\}", t):
        if not VAR_OK.match(m.group(0)):
            raise EditError("“" + m.group(0) + "” is not a value your agent knows. Remove it or use a name from the list.")
    if builder.SECRET.search(t):
        raise EditError("That looks like it contains a card number, password or key. Never put those in a text.")
    bad = kits.violations(prof, re.sub(r"\{\{[^}]*\}\}", "", t))
    if bad:
        raise EditError("A message from this kind of business cannot use: " + ", ".join(sorted(set(bad))) + ". Take that out, or say it face to face.")
    return t


def save(agent, name, texts=None, keywords=None, daily_at=None, lead=None, reminder=None, hours_=None, title_contains=None, approve=None, enable=None):
    """Applies your changes. approve=True (kit workflows) also switches it on; enable=False switches it off. Returns the fresh detail. Raises EditError with a plain sentence."""
    w = _find(agent, name); prof = getattr(agent, "profile", "generic"); d = load(agent); e = d.setdefault(name, {})
    if texts is not None:
        keep = {}
        for i, t in texts.items():
            try:
                step = w["do"][int(i)]
            except (IndexError, ValueError):
                raise EditError("That step does not exist.")
            if "text" not in step or not _label(step):
                raise EditError("That step has no wording to change.")
            t = str(t).strip()
            if t == shown(step["text"], prof).strip():
                continue                                                           # unchanged: keep the recorded line
            keep[str(i)] = _check_text(prof, t)
        e["texts"] = keep
    if keywords is not None:
        kw = [k.strip().lower() for k in (keywords.split(",") if isinstance(keywords, str) else keywords) if str(k).strip()]
        if not kw or len(kw) > 30 or any(len(k) > 40 for k in kw):
            raise EditError("Give between one and thirty words, each under forty letters.")
        if "sms" not in (w.get("on") or {}) or (w["on"]["sms"] or {}).get("when_closed"):
            raise EditError("This workflow does not start from a customer's words.")
        e["keywords"] = kw
    if daily_at is not None:
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", str(daily_at)) or "schedule" not in (w.get("on") or {}):
            raise EditError("Use a time like 09:30.")
        e["daily_at"] = daily_at
    if lead is not None:
        if int(lead) not in builder.BEFORE or "calendar" not in (w.get("on") or {}):
            raise EditError("Pick one of the times in the list.")
        e["lead"] = int(lead)
    if title_contains is not None:
        if "calendar" not in (w.get("on") or {}) or len(str(title_contains)) > 60:
            raise EditError("That cannot be changed here.")
        e["title_contains"] = str(title_contains).strip()
    if reminder is not None:
        if not (w.get("on") or {}).get("calendar", {}).get("smart"):
            raise EditError("Only the reminder has these times.")
        b = [k for k in (reminder.get("before") or []) if k in kits.REMINDER_CHOICES]
        if not b:
            raise EditError("Pick at least one time, or switch the reminder off.")
        at = reminder.get("morning_at") or kits.MORNING_AT
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", str(at)) or str(at) < "06:00" or str(at) > "11:00":
            raise EditError("The morning reminder goes out between 06:00 and 11:00.")
        e["reminder"] = {"before": b, "morning_at": str(at)}
    if hours_ is not None:
        hd = [x for x in (hours_.get("days") or []) if x in DAYS]
        if not hd or not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", str(hours_.get("open"))) or not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", str(hours_.get("close"))) or str(hours_["open"]) >= str(hours_["close"]):
            raise EditError("Pick your open days and an opening time that is earlier than the closing time.")
        d.setdefault("_hours", {}).update({"days": hd, "open": str(hours_["open"]), "close": str(hours_["close"])})
    if approve:
        if w.get("sale"):
            raise EditError("Announce a sale is approved from its own screen.")
        for i, step in enumerate(w.get("do", [])):                                   # the wording in force is checked again before it can be approved
            t = (e.get("texts") or {}).get(str(i)) or (shown(step["text"], prof) if _label(step) and isinstance(step.get("text"), str) else "")
            if t and _label(step) and step.get("action") != "notify":
                _check_text(prof, t)
        e["approved"] = True
        _set_enabled(agent, name, True)
    if enable is not None and not approve:
        if enable and w.get("kit") and not e.get("approved"):
            raise EditError("Open it, read the wording and press “Approve and turn on” first.")
        _set_enabled(agent, name, bool(enable))
    if not e:
        d.pop(name, None)
    _save(agent, d)
    agent._load_workflows()
    return detail(agent, name)


def reset(agent, name):
    d = load(agent); d.pop(name, None); _save(agent, d); agent._load_workflows()
    return detail(agent, name)


def _set_enabled(agent, name, on):
    from . import connect
    wf = connect._workflow_file(agent)
    for w in wf.get("workflows", []):
        if w["name"] == name:
            w["enabled"] = bool(on)
    p = agent.cfg["workflows"]; open(p + ".bak", "w", encoding="utf-8").write(open(p, encoding="utf-8").read())
    tmp = p + ".tmp"; json.dump(wf, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, p)


# ---- the list, ten at a time ------------------------------------------------------------------------------------------------------------------------------

def page(agent, offset=0, limit=10, state=None):
    """The ready-made workflows in pages of ten for the scrolling list. state: None (all), 'on', 'off' or 'needs_approval'."""
    from . import connect
    ed = load(agent); rows = []
    for r in connect.workflows(agent):
        if r.get("soon"):
            continue
        r = dict(r); r["state"] = r.get("state") or "off"
        rows.append(r)
    order = {"needs_approval": 0, "on": 1, "off": 2}
    rows.sort(key=lambda r: (order.get(r["state"], 3), 0 if r.get("kit") else 1))
    if state:
        rows = [r for r in rows if r["state"] == state]
    counts = {"all": len(rows)}
    return {"total": len(rows), "offset": offset, "limit": limit, "items": rows[offset:offset + limit], "counts": {"": sum(1 for r in connect.workflows(agent) if not r.get("soon")), **{s: sum(1 for r in connect.workflows(agent) if not r.get("soon") and r.get("state") == s) for s in ("on", "off", "needs_approval")}}, **{"edited": sorted(k for k in ed if not k.startswith("_"))}}


def closed_now(agent, now_local):
    """True only when you have told the agent your opening times and it is outside them. Unknown is not closed: with no times set this is False, so nothing is answered as closed by mistake."""
    h = hours(agent)
    if not h:
        return False
    day = DAYS[now_local.weekday()]
    if day not in h["days"]:
        return True
    t = now_local.strftime("%H:%M")
    return not (h["open"] <= t < h["close"])
