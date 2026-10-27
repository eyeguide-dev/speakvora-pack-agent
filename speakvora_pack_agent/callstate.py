"""What is true about one conversation right now: a small ledger kept for each call or text thread.
It holds the current request (name, party size, day and time, area), every correction the caller made ("Wednesday... no, Thursday"), each booking this conversation made, changed or cancelled and its real outcome,
what is still pending, the transfer state, and how much of each assistant reply the caller probably heard. It is the single place the person who picks up a transfer, the after-call summary and the follow-up
tasks read from, so they all say the same thing. It stores facts about the request, not the caller's words, and is removed with the rest of the call details (Settings, Privacy).
Booking status words: proposed, confirmed, not_booked, changed, cancelled, unknown. A reply is never recorded as heard: Twilio does not tell the agent what played, so the ledger records when the caller started
talking over the reply (Twilio's partial speech results) and keeps an honest 'heard about N%' estimate; a confirmation the caller talked over is flagged so the person on the phone repeats it."""
import hashlib, re, time

KEEP_SECONDS = 7 * 86400
FACT_KEYS = ("topic", "name", "party", "start", "area", "notes")
SPEAK_WPS = 2.6                                                             # a calm phone voice says about this many words a second


def _all(agent):
    return agent.state.data.setdefault("callstate", {})


def _new_id(key):
    return "c" + hashlib.sha1((key + str(time.time())).encode()).hexdigest()[:8]


def get(agent, key, channel="call", create=True):
    """The ledger for this conversation (created on first use). Old ledgers are dropped after the retention window."""
    st = _all(agent); now = time.time()
    for k in [k for k, v in st.items() if now - v.get("last", 0) > KEEP_SECONDS]:
        st.pop(k)
    if key not in st and not create:
        return None
    return st.setdefault(key, {"id": _new_id(key), "key": key, "channel": channel, "t0": now, "last": now, "turns": [], "facts": {}, "corrections": [], "bookings": [], "actions": [], "pending": [],
                               "transfer": {"state": "none"}, "tasks": [], "summary": ""})


def est_seconds(text):
    return round(max(0.8, len(re.findall(r"\S+", str(text or ""))) / SPEAK_WPS + 0.4), 1)


def begin_turn(agent, key, channel, caller_text, now=None):
    """A caller turn starts: closes the previous reply's 'heard' estimate and returns the new turn record {'id', 'n', ...}."""
    L = get(agent, key, channel); now = float(now or time.time()); L["last"] = now
    prev = L["turns"][-1] if L["turns"] else None
    if prev and prev.get("said") and prev.get("heard") is None:
        close_reply(L, prev, None)
    t = {"id": f"{L['id']}.t{len(L['turns']) + 1}", "n": len(L["turns"]) + 1, "at": now, "caller_words": len(re.findall(r"\S+", str(caller_text or ""))), "said": "", "sent_at": None, "est_s": 0, "heard": None, "heard_pct": None, "ms": {}}
    L["turns"].append(t); del L["turns"][:-40]
    return t


def note_said(agent, key, turn, text, now=None, consequential=False):
    """The reply was handed to the phone provider. consequential = it states something the caller relies on (a confirmation code, a changed time, a cancellation)."""
    now = float(now or time.time()); turn.update(said=" ".join(str(text or "").split())[:400], sent_at=now, est_s=est_seconds(text), consequential=bool(consequential))
    L = get(agent, key, create=False)
    if L is not None:
        L["last"] = now


def voice_onset(agent, key, now=None):
    """Twilio's first partial speech result for a turn: the caller started talking at this moment, over the reply if it was still playing."""
    L = get(agent, key, create=False)
    if not L or not L["turns"]:
        return
    t = L["turns"][-1]
    if t.get("said") and t.get("heard") is None and t.get("sent_at"):
        close_reply(L, t, float(now or time.time()))


def close_reply(L, t, onset):
    """Sets heard to 'full', 'cut_off' or 'unknown' with a percentage. onset None = no talking-over was seen before the next turn, so it played to the end as far as anyone can tell."""
    est = t.get("est_s") or 1.0; sent = t.get("sent_at")
    if onset is None or not sent:
        t["heard"] = "full" if sent else "unknown"; t["heard_pct"] = 100 if sent else None; return
    pct = max(0, min(100, int(100 * (onset - sent) / est)))
    t["heard_pct"] = pct; t["heard"] = "cut_off" if pct < 85 else "full"


def last_turn(agent, key):
    L = get(agent, key, create=False)
    return L["turns"][-1] if L and L["turns"] else None


def unheard_confirmations(agent, key):
    """Replies that stated something the caller relies on but were talked over: the person on the phone should repeat them."""
    L = get(agent, key, create=False)
    return [t for t in (L or {}).get("turns", []) if t.get("consequential") and t.get("heard") == "cut_off"]


def _norm(k, v):
    if v in (None, "", [], {}):
        return None
    if k == "party":
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    return " ".join(str(v).split())[:120]


def update_facts(agent, key, turn_id, facts):
    """The AI's current understanding of the request. A new value for a field that already had a different one is a correction: both are kept, the new one wins everywhere."""
    L = get(agent, key); changed = []
    for k, v in (facts or {}).items():
        if k not in FACT_KEYS:
            continue
        v = _norm(k, v)
        if v is None:
            continue
        old = L["facts"].get(k)
        if old is not None and str(old) != str(v):
            L["corrections"].append({"field": k, "from": old, "to": v, "turn": turn_id, "at": time.time()}); changed.append(k)
        L["facts"][k] = v
    return changed


def booking(agent, key, code, status, **info):
    """Records (or updates) a booking made, changed or cancelled in this conversation."""
    L = get(agent, key)
    for b in L["bookings"]:
        if b["code"] == code:
            b.update(status=status, **info); b["at"] = time.time(); return b
    b = {"code": code, "status": status, "at": time.time(), **info}; L["bookings"].append(b); return b


def action(agent, key, turn_id, kind, status, **info):
    """One action the conversation asked for (book, notify, sms...) and what really happened. status: proposed, executing, confirmed, failed, unknown."""
    L = get(agent, key); a = {"id": f"{turn_id}.{kind}", "kind": kind, "status": status, "at": time.time(), **info}
    L["actions"] = [x for x in L["actions"] if x["id"] != a["id"]] + [a]; return a


def done_already(agent, key, turn_id, kind):
    L = get(agent, key, create=False)
    return bool(L and any(a["id"] == f"{turn_id}.{kind}" and a["status"] in ("confirmed", "executing") for a in L["actions"]))


def set_transfer(agent, key, state, **info):
    """state: none, requested, dialing, connected, no_answer, failed."""
    L = get(agent, key); L["transfer"] = {**L["transfer"], "state": state, "at": time.time(), **info}; return L["transfer"]


def add_task(agent, key, kind, text, owner="front desk", due_minutes=30):
    """A promised follow-up (callback, unresolved question) with an owner and a due time. The same kind for the same conversation is kept once."""
    L = get(agent, key)
    for t in L["tasks"]:
        if t["kind"] == kind and t["status"] == "open":
            t["text"] = text; return t
    t = {"id": f"{L['id']}.k{len(L['tasks']) + 1}", "kind": kind, "text": text[:300], "owner": owner, "created": time.time(), "due": time.time() + due_minutes * 60, "status": "open", "notified": False}
    L["tasks"].append(t); return t


def _when(agent, ts):
    from . import bookings
    try:
        return bookings.say_time(agent, int(ts))
    except Exception:  # noqa: BLE001
        return str(ts)


def _label(field):
    return {"start": "day and time", "party": "party size"}.get(field, field)


def _nice(agent, field, value):
    if field == "start":
        try:
            from . import bookings
            ts = bookings.parse_start(agent, value)
            return bookings.say_time(agent, ts) if ts else str(value)
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value)


def _fact_line(agent, L):
    f = L["facts"]; bits = []
    topic = str(f.get("topic") or "").strip()
    if f.get("party") and topic.lower() in ("table", "reservation", "booking", "appointment", ""):
        bits.append(f"{topic or 'party'} for {f['party']}" if topic else f"party of {f['party']}"); topic = ""
    elif f.get("party"):
        bits.append(f"party of {f['party']}")
    if f.get("start"):
        try:
            from . import bookings
            ts = bookings.parse_start(agent, f["start"]); bits.append(_when(agent, ts) if ts else str(f["start"]))
        except Exception:  # noqa: BLE001
            bits.append(str(f["start"]))
    if f.get("area"):
        bits.append(str(f["area"]))
    who = f.get("name") or ""
    return ((topic + ": ") if topic else "") + ", ".join(bits) + ((" under " + who) if who else "")


def brief(agent, key):
    """What the person who takes the call needs, in one place: {'spoken', 'text', 'facts', 'bookings', 'corrections', 'unheard', 'pending'}. Built only from what is recorded: confirmed bookings are said as confirmed,
    anything else as not confirmed, and corrections are said once with the final value."""
    L = get(agent, key, create=False)
    if not L:
        return {"spoken": "A caller is on the line. I have no details yet.", "text": "A caller is on the line. No details were taken.", "facts": {}, "bookings": [], "corrections": [], "unheard": [], "pending": []}
    parts = []; line = _fact_line(agent, L)
    status_say = {"confirmed": "booked and confirmed", "changed": "booked and confirmed after a change", "cancelled": "cancelled", "not_booked": "NOT booked", "proposed": "NOT booked yet", "unknown": "unknown, please check"}
    for b in L["bookings"]:
        parts.append(f"Booking {' '.join(str(b['code']))}: {status_say.get(b['status'], b['status'])}" + (f", {b['detail']}" if b.get("detail") else "") + ".")
    if line and not L["bookings"]:
        parts.insert(0, "Request: " + line + ".")
    last = {}
    for c in L["corrections"]:
        last[c["field"]] = c
    for c in last.values():
        parts.append(f"They changed the {_label(c['field'])} from {_nice(agent, c['field'], c['from'])} to {_nice(agent, c['field'], c['to'])}; use the new one.")
    pend = [a for a in L["actions"] if a["status"] in ("proposed", "executing", "unknown", "failed") and a["kind"] != "book"]
    if pend:
        parts.append("Not finished: " + "; ".join(f"{a['kind']} ({a['status']})" for a in pend) + ".")
    un = unheard_confirmations(agent, key)
    if un:
        parts.append("The caller may have missed the last confirmation, please repeat it.")
    if not any(L["bookings"]) and not line:
        parts.append("They have not given booking details yet.")
    spoken = " ".join(parts); text = spoken
    for b in L["bookings"]:
        text = text.replace(" ".join(str(b["code"])), str(b["code"]))                      # a code is read digit by digit aloud, but written plainly for the team
    live = [b for b in L["bookings"] if b["status"] in ("confirmed", "changed")]
    short = (f"booking {live[-1]['code']} {status_say.get(live[-1]['status'], '')}: {live[-1].get('detail', '')}" if live else (line or "no booking details")).strip()
    return {"short": short, "spoken": spoken, "text": text, "facts": dict(L["facts"]), "bookings": [dict(b) for b in L["bookings"]], "corrections": [dict(c) for c in L["corrections"]], "unheard": [t["said"] for t in un],
            "pending": [dict(a) for a in pend]}


def summary(agent, key):
    """The after-call summary, built from the ledger: what was asked, what really happened to each booking, what is unresolved and who owns it. Never says something was booked unless a booking is confirmed."""
    L = get(agent, key, create=False)
    if not L:
        return ""
    out = []; line = _fact_line(agent, L)
    if line:
        out.append("Asked for: " + line + ".")
    if L["corrections"]:
        last = {}
        for c in L["corrections"]:
            last[c["field"]] = c
        out.append("Changed during the call: " + "; ".join(f"{_label(k)} {_nice(agent, k, c['from'])} to {_nice(agent, k, c['to'])}" for k, c in last.items()) + ".")
    done = [b for b in L["bookings"] if b["status"] in ("confirmed", "changed")]
    gone = [b for b in L["bookings"] if b["status"] == "cancelled"]
    nope = [b for b in L["bookings"] if b["status"] in ("not_booked", "proposed", "unknown")]
    for b in done:
        out.append(f"Booked: {(b.get('detail') or '').rstrip('.')}. Confirmation {b['code']}.")
    for b in gone:
        out.append(f"Cancelled: booking {b['code']}" + (f" ({b['detail']})" if b.get("detail") else "") + ".")
    if nope:
        out.append("Not booked: " + "; ".join((b.get("detail") or b["code"]) + (f" ({b['reason']})" if b.get("reason") else "") for b in nope) + ".")
    if not L["bookings"] and (L["facts"].get("start") or L["facts"].get("party")):
        out.append("No booking was made.")
    tr = L["transfer"]
    if tr["state"] != "none":
        out.append({"requested": "A person was requested.", "dialing": "Transfer to a person was started.", "connected": "A person took the call.", "no_answer": "Nobody answered the transfer; a callback is owed.",
                    "failed": "The transfer failed."}.get(tr["state"], "Transfer: " + tr["state"]))
    open_tasks = [t for t in L["tasks"] if t["status"] == "open"]
    if open_tasks:
        out.append("Open follow-ups: " + "; ".join(f"{t['text']} (owner: {t['owner']})" for t in open_tasks) + ".")
    un = unheard_confirmations(agent, key)
    if un:
        out.append("The caller talked over " + str(len(un)) + " confirmation(s); they may not have heard it.")
    L["summary"] = " ".join(out); return L["summary"]


def forget(agent, key):
    _all(agent).pop(key, None)
