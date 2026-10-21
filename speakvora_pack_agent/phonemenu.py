"""The phone menu you build in the dashboard ("press 1 for hours, 2 to book, 3 for Luli, 0 for a person").
Saved in agent-state/phone_menu.json (so a bundle update never overwrites it). When it is switched on, the agent's call menu uses these options instead of the bundle's standard four, through exactly the same call logic and safety checks:
a caller can always press or say their way to a person, nothing is said that you did not write, a transfer only goes to a number you typed, and practice mode still stops real transfers and messages.
Each option does one thing: tell the opening hours, say a message you write, take a callback request (your team is told), connect the caller to your staff phone, or connect them to another number you choose (a person or a department)."""
import json, os, re

ACTIONS = {"hours": "Tell them our opening hours", "message": "Say a message I write", "callback": "Take a callback request and tell my team", "person": "Connect them to my staff phone", "transfer": "Connect them to a number I choose", "status": "Give a status update"}
SECRET = re.compile(r"\b(?:\d[ -]?){13,19}\b|\b\d{3}-\d{2}-\d{4}\b|\b(?:password|passcode|pin|api[_ -]?key|token)\s*[:=]", re.I)
STOP = {"for", "to", "the", "a", "an", "of", "and", "or", "my", "our", "your", "about", "with", "me", "us", "please", "speak", "talk", "press", "hear", "get", "know", "check", "on", "is", "in", "at", "it"}
WORDS = {"hours": ("hours", "open", "close", "closing", "address", "where", "location", "directions"), "callback": ("book", "booking", "appointment", "schedule", "reschedule", "cancel", "quote", "estimate", "callback"),
         "status": ("status", "order", "ready", "late", "update", "progress", "arrive"), "person": ("person", "human", "manager", "operator", "someone", "representative")}
MAX_OPTIONS = 9


class MenuError(ValueError):
    pass


def _path(agent):
    return os.path.join(agent.state.dir, "phone_menu.json")


def load(agent):
    try:
        with open(_path(agent), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _phone(v):
    """(number, is_extension). 2 to 6 digits is an extension on your office phone system; 8 to 15 digits is a full phone number."""
    t = str(v or "").strip(); d = re.sub(r"\D", "", t)
    if 2 <= len(d) <= 6 and not t.startswith("+"):
        return d, True
    if not 8 <= len(d) <= 15:
        raise MenuError("Type the full phone number to connect to, with area code (for example 646 555 0101), or an extension on your office phone system (for example 202).")
    return (("+" + d) if t.startswith("+") or len(d) > 10 else ("+1" + d if len(d) == 10 else "+" + d)), False


def validate(spec):
    """The cleaned menu, or a MenuError that says in plain words what to fix. A way to reach a person is always kept: if none of your options connects one, option 0 is added."""
    g = re.sub(r"\s+", " ", str(spec.get("greeting") or "")).strip()[:200]
    seen, out = set(), []
    for o in (spec.get("options") or []):
        dg = str(o.get("digit", "")).strip()
        if not re.fullmatch(r"[0-9]", dg):
            raise MenuError("Each option needs one key from 0 to 9.")
        if dg in seen:
            raise MenuError(f"Key {dg} is used twice. Each key can do only one thing.")
        seen.add(dg)
        label = re.sub(r"\s+", " ", str(o.get("say") or "")).strip().strip(".,")[:60]
        if not label:
            raise MenuError(f"Say what key {dg} is for, for example: for opening hours.")
        do = str(o.get("do") or "")
        if do not in ACTIONS:
            raise MenuError(f"Choose what key {dg} does.")
        item = {"digit": dg, "say": label, "do": do}
        if do == "message":
            t = re.sub(r"\s+", " ", str(o.get("text") or "")).strip()[:300]
            if not t:
                raise MenuError(f"Type the message callers hear when they press {dg}.")
            item["text"] = t
        if do == "transfer":
            item["to"], ext = _phone(o.get("to"))
            if ext:
                item["ext"] = True
        for t in (label, item.get("text", ""), g):
            if SECRET.search(t):
                raise MenuError("Do not put card numbers, passwords or codes in the menu.")
        out.append(item)
    if not out:
        raise MenuError("Add at least one option.")
    if len(out) > MAX_OPTIONS:
        raise MenuError(f"That is more than {MAX_OPTIONS} options. Callers cannot remember that many.")
    added = False
    zero = next((o for o in out if o["digit"] == "0"), None)
    if zero is None:                                                                    # fail closed to a human: key 0 (and saying "person") always reaches one
        out.append({"digit": "0", "say": "to speak to a person", "do": "person"}); added = True
    elif zero["do"] not in ("person", "transfer"):
        raise MenuError("Key 0 is kept for reaching a person. Move that option to another key, or make key 0 connect a person.")
    out.sort(key=lambda o: (o["digit"] == "0", o["digit"]))
    return {"enabled": bool(spec.get("enabled", True)), "greeting": g or "Thanks for calling {{business}}.", "options": out, "added_person": added}


def save(agent, spec):
    clean = validate(spec); clean.pop("added_person", None)
    p = _path(agent); tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return clean


def reset(agent):
    try:
        os.remove(_path(agent))
    except OSError:
        pass


def _num(n):
    return {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"}[n]


def spoken(menu, business="", digits_as_words=False):
    """What the caller hears: the greeting, then 'Press 1 for opening hours, 2 to book, or 0 to speak to a person.'"""
    g = str(menu.get("greeting") or "").replace("{{business}}", business or "us")
    parts = [f"{_num(o['digit']) if digits_as_words else o['digit']} {o['say']}" for o in menu["options"]]
    if len(parts) == 1:
        tail = "Press " + parts[0] + "."
    else:
        tail = "Press " + ", ".join(parts[:-1]) + ", or " + parts[-1] + "."
    return (g + " " + tail).strip()


def speech_words(o):
    w = set(WORDS.get(o["do"], ()))
    w |= {x for x in re.findall(r"[a-z']+", o["say"].lower()) if x not in STOP and len(x) > 2}
    return tuple(sorted(w))


def actions(o):
    """The agent's own action list for one option (the same format the bundle's standard menu uses)."""
    do = o["do"]
    if do == "hours":
        return [{"action": "reply", "text": "{{fact:hours}}"}]
    if do == "message":
        return [{"action": "reply", "text": o["text"]}]
    if do == "callback":
        return [{"action": "notify", "text": "Caller {{call.from}} wants a callback: " + o["say"]}, {"action": "reply", "text": "Thanks, the team will call you back."}]
    if do == "status":
        return [{"action": "notify", "text": "Caller {{call.from}} asked for a status update."}, {"action": "reply", "text": "Thanks, your request is noted and the team will update you."}]
    if do == "person":
        return [{"action": "notify", "text": "Caller {{call.from}} wants a person."}, {"action": "transfer", "to": "{{fact:oncall_phone}}"}]
    return [{"action": "notify", "text": "Caller {{call.from}} chose: " + o["say"]}, {"action": "transfer", "to": o["to"], **({"extension": True} if o.get("ext") else {})}]


def apply(agent, menu):
    """The bundle's menu, replaced by yours when you switched yours on. Returns the menu dict the call logic reads."""
    d = load(agent)
    if not d.get("enabled") or not d.get("options"):
        return menu
    business = str((agent.cfg.get("business") or "")) if "YOUR-" not in str(agent.cfg.get("business") or "") else ""
    m = dict(menu); m["custom"] = True; m["prompt"] = "__custom_menu__"
    m["options"] = {o["digit"]: actions(o) for o in d["options"]}
    m["words"] = {o["digit"]: speech_words(o) for o in d["options"] if o["digit"] != "0" and o["do"] not in ("person",)}
    m["fallback_say"] = spoken(d, business)
    sp = spoken(d, business)
    m["speech_say"] = sp.replace("Press ", "You can speak, or use your keypad. Say or press ", 1) if " Press " not in sp and not sp.startswith("Press ") else sp.replace(" Press ", " You can speak, or use your keypad. Say or press ", 1)
    m["speech_ask"] = "You can speak, or use your keypad. Say or press " + ", ".join(f"{o['digit']} {o['say']}" for o in d["options"]) + "."
    tl = getattr(agent, "_tl", None)
    if tl is not None and getattr(tl, "sip_call", False) and not getattr(tl, "sip_tts", True):         # an office phone call on a computer with no voice of its own: unless your greeting has been voiced, play the bundle's recorded menu rather than silence
        text = m["speech_say"] if agent._speech_on() else m["fallback_say"]
        if not agent.audio.cached_dynamic(text, True):
            agent.state.log(workflow="phone_menu", status="custom_menu_unvoiced", dry_run=False)
            return menu
    m["again_say"] = "Is there anything else I can help with? " + "Press " + ", ".join(f"{o['digit']} {o['say']}" for o in d["options"]) + "."
    return m


def view(agent):
    d = load(agent); business = str(agent.cfg.get("business") or "")
    business = "" if "YOUR-" in business else business
    cur = {"enabled": bool(d.get("enabled")), "greeting": d.get("greeting") or "Thanks for calling {{business}}.", "options": d.get("options") or [
        {"digit": "1", "say": "for opening hours", "do": "hours"}, {"digit": "2", "say": "to book or change a booking", "do": "callback"}, {"digit": "3", "say": "for a status update", "do": "status"}, {"digit": "0", "say": "to speak to a person", "do": "person"}]}
    return {**cur, "business": business or "us", "saved": bool(d), "spoken": spoken(cur, business), "actions": ACTIONS, "max": MAX_OPTIONS,
            "staff_phone_set": bool(str(((agent.cfg.get("facts") or {}).get("oncall_phone")) or "").strip()) and "YOUR-" not in str((agent.cfg.get("facts") or {}).get("oncall_phone", ""))}
