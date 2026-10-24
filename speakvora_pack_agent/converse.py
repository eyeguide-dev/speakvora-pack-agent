"""Live conversation: the owner's own AI answers a text or a phone call turn by turn, inside hard limits that live in this code.
A turn goes: safety checks on what the person said (emergency, secrets, opt-out and 'a person please' never reach the AI), then the AI picks ONE approved library line to play (instant, free) or writes a short answer, then the answer is checked
(industry blocked terms, invented phone numbers or prices) before anything is said. Anything that fails a check, any cap reached, or any AI problem becomes a polite hand-off to a person. Nothing here needs the AI to be safe: P0 handling stays local.
On a call, an answer that takes the AI more than a moment is covered by a short recorded filler so the line never goes quiet (see Agent._talk). The AI only answers; it cannot send, change or approve anything."""
import hashlib, json, re, threading, time

from . import bookings, brain, controls, guardrails as G, industry_rules, knowledge, learned, reasoner as R

PRIVATE_PROFILES = ("clinic", "pharmacy", "dispensary", "legal", "finance", "education", "lodging", "public", "collections", "corrections")
SYSTEM = ("You are the front-desk voice of a small business, answering one customer message or one phone turn. Speak like a warm, brief person: one or two short sentences, plain words, no lists, no emoji. "
          "Answer the customer's actual question first, directly, using the approved information (the same thing may be worded differently: 'outdoor seating' can mean a patio). Never ask a question back unless you truly cannot answer without it, and then ask only one short one. Never end with 'is there anything else' or similar. "
          "Answer ONLY from the business profile, the approved facts, the approved lines and the order status given below. If the request is about something this business does not cover (other products, personal chat, anything not in the approved information), do NOT guess, joke or ask what they meant: say \"I don't have that information. Let me get someone to help you.\" and choose action \"handoff\". If the message is garbled or you truly cannot tell what was said, say \"Sorry, I didn't catch that. Could you say it again?\" and keep going. Never mention what you cannot do in other ways, never speculate. Never invent prices, hours, times, phone numbers, discounts or promises. Never give medical, legal or financial advice. Never ask for or repeat passwords, codes or card numbers. Never say you are a person. "
          "If an approved line says exactly what you want to say, choose it by its number instead of writing your own. "
          'Reply with ONE JSON object only: {"say": "what to say", "line": "L3 or empty", "action": "continue" | "handoff" | "end"}. '
          "Use \"end\" only when the person says they are done. Use \"handoff\" for complaints, anything urgent, anything you cannot answer, or when they ask for a person.")
ACTION_HELP = {"book": "book: book a table or appointment for the customer. Fields: name = the guest's name, party = how many people (a number), start = the local date and time as YYYY-MM-DDTHH:MM, area = where they want to sit (inside or outside), notes = extra needs such as a dog. Use it only when you have all of name, party, start and area. The booking book checks it and confirms or offers other times: never say it is booked yourself. If anything is missing, ask for it (one question at a time) and do not use book yet.",
               "notify": "notify: tell the team something they must act on (a booking request, a callback, a complaint, a quote). text = a short summary with the customer's name, what they want and when.",
               "sms": "sms: text the customer a short confirmation of what was agreed. text = the message.",
               "report_bug": "report_bug: the customer says something is broken (the website, the app, online ordering or payment, or an error message). text = what happened in the customer's words: what they tried to do and what went wrong. Use it, and tell the customer kindly that the team has been told.",
               "calendar_create": "calendar_create: add a booking to the calendar once the customer has given a day and time. title = a short title, start = the local date and time as YYYY-MM-DDTHH:MM, minutes = length."}
TEMPLATES = {"service": "This is a service business (appointments, quotes, repairs). When someone wants a booking or a quote, collect their name, what they need and the day or time they prefer, one question at a time, then use notify with a summary. Never promise a price or an arrival time that is not in the approved information.",
             "food": "This is a restaurant. For a reservation collect the name, party size and time, one question at a time, then use notify so the host confirms. Never promise a table.",
             "retail": "This is a store. Answer store questions and pickup updates. For anything that needs a person (returns, special orders) use notify with a summary."}
PROFILE_TEMPLATE = {"trades": "service", "beauty": "service", "auto": "service", "laundry": "service", "food": "food", "retail": "retail", "generic": "service"}
FILLERS = ["Yeah, sure. Let me check that for you.", "Sure thing, just a second.", "Mm-hm, let me look that up.", "Good question. One moment.", "Okay, let me pull that up for you.", "Yeah, absolutely. Give me just a second.",
           "Let me see what I've got on that.", "Sure, one sec while I check.", "Right, let me take a look.", "Of course. Bear with me for a moment.", "Okay, checking that now.", "Mm, let me find that for you.",
           "Sure, hang on just a moment.", "Got it. Let me check on that.", "Alright, one moment while I look.", "Yeah, let me double check that for you.",
           "Hmm, let me think about that.", "Hmm, okay. Let me see.", "Ooh, good one. Give me a second.", "Mm, hold on, let me check.", "Okay, so, let me look into that.", "Right, hmm, one moment.",
           "Yep, I'm on it. Just a sec.", "Hmm, let me pull that up."]
HANDOFF_TEXT = "I'll have someone from the team get back to you shortly."


def _cfg(agent):
    return {**G.DEFAULTS, **(agent.cfg.get("guardrails") or {})}


def enabled(agent, channel):
    """True when the owner switched this channel on and an AI is connected."""
    c = _cfg(agent)
    return bool(c["sms_replies" if channel == "sms" else "voice_calls"]) and brain.configured(agent)


def _state(agent):
    return agent.state.data.setdefault("converse", {})


def _session(agent, key, channel):
    now = time.time(); st = _state(agent)
    for k in [k for k, v in st.items() if now - v.get("last", 0) > (7200 if v.get("channel") == "sms" else 3600)]:
        st.pop(k)
    return st.setdefault(key, {"channel": channel, "turns": [], "n": 0, "t0": now, "last": now, "misses": 0})


def _hourly_ok(agent):
    now = time.time(); d = agent.state.data; times = [t for t in d.get("converse_times", []) if now - t < 3600]
    if len(times) >= min(_cfg(agent)["max_ai_replies_per_hour"], G.CEILING["max_ai_replies_per_hour"]):
        d["converse_times"] = times; return False
    d["converse_times"] = times + [now]; return True


def _library(agent, text, history):
    """Up to 24 approved lines that overlap with what is being talked about, numbered L1.. for the AI to choose from."""
    words = set(re.findall(r"[a-z']{3,}", (text + " " + " ".join(t for r, t in history[-4:])).lower()))
    scored = []
    for it in agent.pack.items:
        t = it.get("text") or ""
        if not t or len(t) > 220:
            continue
        s = len(words & set(re.findall(r"[a-z']{3,}", t.lower())))
        if s and str(it.get("id", "")).startswith("learned:"):
            s += 3                                                          # lines the owner recorded for their own business come first: they are exactly what the business wants said, and they play instantly
        if s:
            scored.append((s, it))
    scored.sort(key=lambda x: -x[0]); return [it for _s, it in scored[:10]]


def _order_status(agent, text):
    """Status of an order number the person mentioned, from the agent's own tracker. Never for industries whose records are private."""
    if agent.profile in PRIVATE_PROFILES or not (agent.cfg.get("tracking") or {}).get("enabled"):
        return ""
    from . import tracker
    for n in re.findall(r"\b(\d{2,10})\b", text):
        r = tracker._find(agent, order=n)
        if r:
            return f"Order {n} status: {tracker.LABEL.get(r['status'], r['status'])}." + (f" Expected {r['eta']}." if r.get("eta") else "") + (" It is running late." if r.get("delayed") else "")
    return ""


def _facts_text(agent):
    f = agent.cfg.get("facts") or {}
    return "\n".join(f"{k}: {v}" for k, v in f.items() if v and k != "oncall_phone")


def _checked(agent, say, user_text):
    """'' when the answer is fine, otherwise the reason it must not be said."""
    if not say or len(say) > 320:
        return "empty or too long"
    bad = industry_rules.violation(agent, say)
    if bad:
        return "blocked term: " + bad
    if controls.guard_speech(say) in ("secret",) or re.search(r"\b(i am|i'm) (a )?(real )?(human|person)\b", say, re.I):
        return "unsafe wording"
    kn = knowledge.text_all(agent)
    known = re.sub(r"\D", "", _facts_text(agent) + " " + user_text + " " + kn)
    for num in re.findall(r"\+?\d[\d\-\s().]{6,}\d", say):
        d = re.sub(r"\D", "", num)
        if d and d not in known and not any(d[-7:] == re.sub(r"\D", "", str(v))[-7:] for v in (agent.cfg.get("facts") or {}).values() if re.sub(r"\D", "", str(v))):
            return "invented phone number"
    allowed_money = " ".join([_facts_text(agent), brain.for_prompt(agent) or "", kn, " ".join(i.get("text", "") for i in agent.pack.items)])
    for m in re.findall(r"[$€£]\s?\d[\d,.]*", say):
        amount = re.sub(r"[^\d.]", "", m).rstrip(".")
        base = re.sub(r"\.0+$", "", amount)                                          # $16 and $16.00 are the same price
        if m.replace(" ", "") not in allowed_money.replace(" ", "") and not re.search(r"(?<![\d.,])(?:" + re.escape(base) + r"|" + re.escape(base) + r"\.0+)(?![\d]|\.\d)", kn):   # a menu lists prices as plain numbers ("Calamari 16")
            return "invented price"
    return ""


def _booking_rules(agent, cfg, channel):
    """When the owner switched booking on: today's date (so "tonight" and "Friday" become real dates), the rules the book enforces, and how to take a booking."""
    if "book" not in usable_actions(agent, cfg, channel):
        return ""
    b = bookings.settings(agent); now = bookings.dt.datetime.now(bookings._tz(agent)); days = ", ".join(bookings.WORDS[d] for d in b["days"])
    return (f"Today is {now.strftime('%A %Y-%m-%d')} and the time is {now.strftime('%H:%M')} (local). We take bookings {days}, from {b['open']} to {b['last_seating']}, for up to {b['max_party']} people, "
            f"sitting {' or '.join(b['areas'])}. Answer the guest's questions first, from the approved information, and start taking a booking only when they ask to book. To take a booking collect the name, how many people, the day and time, and where they want to sit, one question at a time, then use book. "
            "The booking book confirms it or offers other times. Never promise a table yourself.\n")


def _phone(agent, key):
    """The caller's number when it is known: a text conversation is keyed by it, a call on an office phone system carries it as the caller id."""
    if key.startswith("sms:"):
        return key[4:]
    call = getattr(getattr(agent, "_tl", None), "sip_call", None)
    who = str(getattr(call, "caller", "") or "")
    return who if re.fullmatch(r"\+?\d{7,15}", who) else ""


def usable_actions(agent, cfg, channel=""):
    """The allowed actions that can actually run right now: notify needs Slack or Teams connected, calendar_create needs a calendar that can create events, sms needs Twilio."""
    ok = []
    for a in cfg.get("allowed_actions", []):
        if a == "notify" and (getattr(agent.slack, "configured", False) or getattr(agent.teams, "configured", False)):
            ok.append(a)
        elif a == "sms" and channel != "sms" and getattr(agent.twilio, "configured", False):            # in a text conversation the reply already is the text
            ok.append(a)
        elif a == "book" and bookings.settings(agent)["enabled"]:
            ok.append(a)
        elif a == "report_bug" and getattr(agent.atlassian, "jira_ready", False):
            ok.append(a)
        elif a == "calendar_create" and (getattr(agent.gcal, "configured", False) and (agent.cfg.get("google_calendar") or {}).get("allow_create")):
            ok.append(a)
    return ok


def _actions(agent, raw, cfg, channel=""):
    """The actions the AI asked for, kept only if the owner allowed that kind (Settings, Built-in safeguards), with bounded text and nothing that looks like a secret."""
    allowed = set(usable_actions(agent, cfg, channel)) & set(ACTION_HELP); out = []
    for a in (raw if isinstance(raw, list) else [])[:3]:
        if not isinstance(a, dict) or a.get("type") not in allowed:
            continue
        t = " ".join(str(a.get("text") or "").split())[:300]
        if a["type"] in ("notify", "sms", "report_bug") and (len(t) < 6 or controls.guard_speech(t) == "secret" or industry_rules.violation(agent, t)):
            continue
        item = {"type": a["type"], "text": t}
        if a["type"] == "book":
            item.update(name=" ".join(str(a.get("name") or "").split())[:60], party=a.get("party"), start=str(a.get("start") or "").strip(), area=str(a.get("area") or "").strip().lower()[:20], notes=" ".join(str(a.get("notes") or "").split())[:200])
            out.append(item); continue
        if a["type"] == "calendar_create":
            m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", str(a.get("start") or "").strip())
            if not m:
                continue
            item.update(title=" ".join(str(a.get("title") or "Booking").split())[:80], start=m.group(0).replace(" ", "T"), minutes=max(10, min(int(a.get("minutes") or 60) if str(a.get("minutes") or "60").isdigit() else 60, 480)))
        out.append(item)
    return out


def turn(agent, key, channel, text):
    """One customer turn. Returns {'say', 'line' (library item id or ''), 'action': continue|handoff|end, 'why'}. Never raises: any problem is a hand-off."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:600]
    s = _session(agent, key, channel); cfg = _cfg(agent)
    out = {"say": "", "line": "", "action": "continue", "why": ""}
    try:
        from . import escalation
        esc = escalation.check(agent, key, text, "sms" if channel == "sms" else "call")                  # support, customer service, a person, or a frustrated caller: a person now, no AI needed
        if esc:
            return {**out, "action": "handoff", "why": esc["why"], "say": esc["say"], "escalation": True}
        if G.wants_human(agent, text):
            return {**out, "action": "handoff", "why": "asked for a person"}
        if s["n"] >= cfg["max_turns"] or (channel == "call" and time.time() - s["t0"] > cfg["max_call_minutes"] * 60):
            return {**out, "action": "handoff", "why": "turn or time limit"}
        if not _hourly_ok(agent):
            return {**out, "action": "handoff", "why": "hourly limit"}
        hit = knowledge.qa_match(agent, text)                                   # a question the owner already answered: use their exact words, no AI call
        if hit and not _checked(agent, hit[0], text):
            s["turns"] += [("c", text), ("a", hit[0])]; s["n"] += 1; s["last"] = time.time(); s["misses"] = 0
            return {"say": hit[0], "line": "", "action": "continue", "why": "", "sources": [], "ai_ms": 0, "instant": True}
        lib = _library(agent, text, s["turns"]); facts = _facts_text(agent); order = _order_status(agent, text); docs, srcs = knowledge.prompt(agent, text, [t for _r, t in s["turns"] if _r == "c"])
        user = (f"Business: {agent.cfg.get('business', '')}\nChannel: {'text message' if channel == 'sms' else 'phone call (speak in short natural sentences)'}\n" + industry_rules.prompt(agent) + (brain.for_prompt(agent) or "") + docs
                + ("APPROVED FACTS:\n" + facts + "\n" if facts else "") + (order + "\n" if order else "")
                + ("APPROVED LINES (choose by number when one fits exactly):\n" + "\n".join(f"L{i + 1}: {it['text']}" for i, it in enumerate(lib)) + "\n" if lib else "")
                + (_booking_rules(agent, cfg, channel) or (TEMPLATES.get(PROFILE_TEMPLATE.get(agent.profile, ""), "") + "\n" if TEMPLATES.get(PROFILE_TEMPLATE.get(agent.profile, ""), "") else ""))
                + ("ACTIONS you may request in \"do\" (a list of {\"type\": ..., fields}; leave it empty when nothing needs doing):\n" + "\n".join(ACTION_HELP[a] for a in usable_actions(agent, cfg, channel) if a in ACTION_HELP) + "\n" + "Actions run after your reply and may be held for approval: never say you have done one, say what will happen (for example \"the host will confirm your table\").\n" if any(a in ACTION_HELP for a in usable_actions(agent, cfg, channel)) else "")
                + "\nCONVERSATION SO FAR (the customer's phone numbers, emails and card-like numbers are hidden from you):\n" + R.redact("\n".join(f"{'Customer' if r == 'c' else 'You'}: {t}" for r, t in s["turns"][-8:]) + f"\nCustomer: {text}\n", None))
        t0 = time.time(); raw, _u = R._chat(agent.cfg["reasoner"], SYSTEM, user, 220); out["ai_ms"] = int((time.time() - t0) * 1000)
        m = re.search(r"\{.*\}", raw or "", re.S); j = json.loads(m.group(0)) if m else {}
        say = " ".join(str(j.get("say") or "").split()); act = j.get("action") if j.get("action") in ("continue", "handoff", "end") else "continue"
        ln = str(j.get("line") or "").strip().upper(); line_id = ""
        if re.fullmatch(r"L\d{1,2}", ln) and 0 < int(ln[1:]) <= len(lib):
            it = lib[int(ln[1:]) - 1]; line_id, say = it["id"], it["text"]
        todo = _actions(agent, j.get("do"), cfg, channel) if act != "handoff" else []
        why = _checked(agent, say, text)
        booked = None
        if not why and any(x["type"] == "book" for x in todo):                  # the AI asked to book: the booking book answers now, so the caller hears the real result on the same call
            item = next(x for x in todo if x["type"] == "book"); todo = [x for x in todo if x["type"] != "book"]
            booked = bookings.attempt(agent, item, _phone(agent, key), "text" if channel == "sms" else "call")
            agent.state.log(workflow="bookings", action="book", status="confirmed" if booked["ok"] else (booked.get("reason") or "not_booked"), dry_run=agent.dry, party=item.get("party"), area=item.get("area"), start=item.get("start"))
            if booked.get("say"):
                say, line_id = booked["say"], ""
            if booked["ok"]:
                b = booked["booking"]; todo.append({"type": "notify", "text": f"New booking {b['code']}: table for {b['party']} {b['area']} at {bookings.say_time(agent, b['start'])}, {b['name']}." + (f" Notes: {b['notes']}." if b["notes"] else "")})
        if why or act == "handoff":
            agent.state.log(workflow="converse", status="handoff", dry_run=False, why=why or "the AI chose a person", raw=str(raw)[:300], docs=len(srcs), stop=(_u or {}).get("stop"), blocks=(_u or {}).get("blocks"))        # what the AI actually said, for tuning
        if why:
            knowledge.note_gap(agent, text)
            return {**out, "action": "handoff", "why": why}
        s["turns"] += [("c", text), ("a", say)]; s["n"] += 1; s["last"] = time.time(); s["misses"] = 0
        if not line_id:
            learned.observe(agent, say)                                       # a line the AI keeps writing becomes a candidate for your library (you approve it)
        if act == "handoff" and not order:
            knowledge.note_gap(agent, text)                                   # a question nothing answers: shown in Library, Knowledge, so the owner can add the answer
        return {"say": say, "line": line_id, "action": act, "why": "", "sources": srcs, "ai_ms": out["ai_ms"], "prompt_chars": len(user), "do": todo}
    except Exception as e:  # noqa: BLE001 - an AI that is down, slow or confused must never break a call or a text
        agent.state.log(workflow="converse", status="error", dry_run=False, error=type(e).__name__ + ": " + str(e)[:140])
        s["misses"] = s.get("misses", 0) + 1
        return {**out, "action": "handoff", "why": "AI unavailable"}


def disclosure(agent):
    b = str(agent.cfg.get("business") or "").strip()
    return f"This is {b}'s automated assistant. " if b else "This is our automated assistant. "


class Pending:
    """An AI turn running in the background while a short filler plays, so a call never goes silent."""
    def __init__(self):
        self.ev = threading.Event(); self.result = None

    def run(self, fn):
        def go():
            try:
                self.result = fn()
            finally:
                self.ev.set()
        threading.Thread(target=go, daemon=True).start(); return self

    def wait(self, seconds):
        return self.ev.wait(seconds)


def new_id(key):
    return hashlib.sha1((key + str(time.time())).encode()).hexdigest()[:10]


def try_it(agent, question):
    """The dashboard's 'ask it' box: the AI's answer to a question, with the sources it used. Nothing is sent, recorded or counted against a conversation."""
    q = re.sub(r"\s+", " ", str(question or "")).strip()[:300]
    if not q:
        raise ValueError("Type a question a customer might ask.")
    if not brain.configured(agent):
        raise ValueError("Connect your AI first (Connect, Assistant).")
    key = "try:" + new_id(q)
    try:
        r = turn(agent, key, "sms", q)
    finally:
        _state(agent).pop(key, None)
    return {"answer": r["say"] or HANDOFF_TEXT, "handoff": r["action"] == "handoff", "why": r.get("why", ""), "sources": r.get("sources", [])}
