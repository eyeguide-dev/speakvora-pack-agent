"""Calls and texts, as the business sees them: a short record of every conversation (when, which channel, what it was about, how it ended, a one-sentence summary), and, only if the business switches it on, the words that were said.
Always kept (small, no private words): time, channel, the caller's number with all but the last two digits hidden, the topics, how it ended, and a summary the agent writes from what happened.
Kept only when the business switches transcripts on (Library or Settings, off by default): what the caller said and what the assistant said. Emails, phone numbers and card-like numbers are removed before anything is saved; a password, code or card number said on a call is never saved; private details from the business's own records system are replaced with "[private details withheld]". Transcript words are deleted after the days chosen for customer details (Settings), the record of the conversation stays.
An AI summary is written only when the business presses the button, from the redacted words, by the business's own AI."""
import json, os, re, sqlite3, threading, time

from . import reasoner as R

_conns, _lock = {}, threading.RLock()
OUTCOMES = {"staff": "Connected to staff", "emergency": "Told to call 911", "poison": "Given Poison Control and 911", "secret": "Refused a password, code or card number", "optout": "Opted out", "goodbye": "Ended politely", "answered": "Answered", "unanswered": "Not understood",
            "handoff": "Handed to a person", "texted": "Details texted to the number on file", "none": "In progress"}
INTENTS = {"1": "opening hours and location", "2": "booking", "3": "order or booking status", "0": "a person"}


def _conn(agent):
    path = os.path.join(agent.state.dir, "conversations.db")
    with _lock:
        c = _conns.get(path)
        if c is None:
            os.makedirs(agent.state.dir, exist_ok=True)
            c = sqlite3.connect(path, check_same_thread=False, isolation_level=None); c.execute("pragma journal_mode=wal")
            c.execute("create table if not exists conv (id integer primary key autoincrement, key text, channel text, who text, started integer, updated integer, outcome text, intents text, handoff integer default 0, summary text default '', ai_summary text default '')")
            c.execute("create table if not exists turns (conv integer, t integer, role text, text text)")
            c.execute("create index if not exists conv_key on conv(key)"); c.execute("create index if not exists turns_conv on turns(conv)"); c.execute("create index if not exists conv_updated on conv(updated)")
            _conns[path] = c
        return c


def enabled(agent):
    return bool((agent.cfg.get("transcripts") or {}).get("enabled"))


def mask(number):
    d = re.sub(r"\D", "", str(number or ""))
    return ("*" * max(0, len(d) - 2) + d[-2:]) if d else ""


def clean(text):
    """Emails, phone numbers and card-like numbers never reach the saved words."""
    return " ".join(str(R.redact(str(text or ""), None)).split())[:600]


def _find_or_create(agent, key, channel, who, now):
    c = _conn(agent)
    window = 3600 if channel == "sms" else 86400 * 7
    r = c.execute("select id from conv where key=? and updated>=? order by id desc limit 1", (key, now - (window if channel == "sms" else 6 * 3600))).fetchone()
    if r:
        return r[0]
    cur = c.execute("insert into conv (key, channel, who, started, updated, outcome, intents) values (?,?,?,?,?,?,?)", (key, channel, mask(who), now, now, "none", "[]"))
    return cur.lastrowid


def _spoken(agent, xml):
    """What a caller hears in a TwiML answer, as text: Say text as written, Play audio as the recording's own words."""
    out = []
    xml = xml or ""
    if "</Gather>" in xml:                                                    # what follows the question only plays when nobody answers it (a goodbye): not part of what was said
        xml = xml[:xml.rindex("</Gather>")]
    for m in re.finditer(r"<Say>(.*?)</Say>|<Play>(.*?)</Play>", xml, re.S):
        if m.group(1) is not None:
            out.append(re.sub(r"&amp;", "&", re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", m.group(1)))))
        else:
            mm = re.search(r"/audio/([^/.]+)\.", m.group(2))
            try:
                if mm and mm.group(1).startswith(("talk_", "keep_")):
                    out.append(agent.audio.dynamic_text(mm.group(1)) or "(a recorded line)"); continue
                out.append(agent.pack.text(mm.group(1).replace("_", ":")) if mm else "(a recorded line)")
            except Exception:  # noqa: BLE001
                out.append("(a recorded line)")
    return out


def record(agent, key, channel, who, caller, assistant, outcome=None, intent=None, handoff=False, private=False, withhold=False):
    """Adds one exchange to a conversation. caller: what was said or pressed; assistant: list of lines the caller heard. Never raises."""
    try:
        now = int(agent.now()); c = _conn(agent)
        with _lock:
            cid = _find_or_create(agent, key, channel, who, now)
            row = c.execute("select outcome, intents, handoff from conv where id=?", (cid,)).fetchone()
            intents = json.loads(row[1] or "[]")
            if intent and intent not in intents:
                intents.append(intent)
            new_out = outcome or row[0]
            c.execute("update conv set updated=?, outcome=?, intents=?, handoff=? where id=?", (now, new_out, json.dumps(intents), int(bool(row[2]) or handoff), cid))
            if enabled(agent):
                if caller:
                    c.execute("insert into turns values (?,?,?,?)", (cid, now, "caller", "[withheld]" if withhold else clean(caller)))
                for line in assistant or []:
                    c.execute("insert into turns values (?,?,?,?)", (cid, now, "assistant", "[private details withheld]" if private else clean(line)))
            summ = _summary(c, cid, channel)
            try:
                from . import callstate
                led = callstate.summary(agent, key)                                  # what really happened to each booking, from the conversation ledger (not from the words spoken)
                if led:
                    summ = (summ + " " + led).strip()
            except Exception:  # noqa: BLE001
                pass
            c.execute("update conv set summary=? where id=?", (summ, cid))
        return cid
    except Exception as e:  # noqa: BLE001 - a record problem must never break a call
        agent.state.log(workflow="conversations", status="error", error=str(e)[:160], dry_run=False)
        return None


def _summary(c, cid, channel):
    r = c.execute("select outcome, intents, handoff from conv where id=?", (cid,)).fetchone()
    intents = json.loads(r[1] or "[]"); what = ", ".join(intents) if intents else "nothing specific yet"
    kind = "Caller" if channel == "call" else "Texter"
    s = f"{kind} asked about {what}. " if intents else f"{kind} contacted the business. "
    end = {"staff": "They were connected to staff.", "emergency": "They described an emergency and were told to call 911.", "poison": "They were given Poison Control and 911.", "secret": "They tried to say a password, code or card number, which was refused.",
           "optout": "They asked not to be contacted and were opted out.", "goodbye": "The call ended politely.", "answered": "It was answered.", "unanswered": "The assistant did not understand and asked again.", "handoff": "A team member was told to follow up.",
           "texted": "Details were texted to the number on file.", "none": ""}.get(r[0], "")
    return (s + end).strip()


def list_(agent, q="", kind="", offset=0, limit=40):
    with _lock:                                                  # the connection is shared between request threads: reads wait for writes
        return _list(agent, q, kind, offset, limit)


def _list(agent, q="", kind="", offset=0, limit=40):
    c = _conn(agent); where, args = ["1=1"], []
    if kind in ("call", "sms"):
        where.append("channel=?"); args.append(kind)
    elif kind == "person":
        where.append("(handoff=1 or outcome in ('staff','handoff'))")
    elif kind == "urgent":
        where.append("outcome in ('emergency','poison','secret')")
    if q:
        like = "%" + q.strip()[:60] + "%"
        where.append("(summary like ? or intents like ? or outcome like ? or id in (select conv from turns where text like ?))"); args += [like, like, like, like]
    total = c.execute("select count(*) from conv where " + " and ".join(where), args).fetchone()[0]
    rows = c.execute("select id, channel, who, started, updated, outcome, summary, handoff from conv where " + " and ".join(where) + " order by updated desc limit ? offset ?", args + [int(limit), int(offset)]).fetchall()
    return {"total": total, "transcripts_on": enabled(agent), "items": [{"id": r[0], "channel": r[1], "who": r[2], "started": r[3], "updated": r[4], "outcome": r[5], "outcome_label": OUTCOMES.get(r[5], r[5]), "summary": r[6], "needs_person": bool(r[7]) or r[5] in ("staff", "handoff")} for r in rows]}


def get(agent, cid):
    with _lock:
        return _get(agent, cid)


def _get(agent, cid):
    c = _conn(agent); r = c.execute("select id, channel, who, started, updated, outcome, intents, summary, ai_summary from conv where id=?", (int(cid),)).fetchone()
    if not r:
        return None
    turns = c.execute("select t, role, text from turns where conv=? order by rowid", (int(cid),)).fetchall()
    return {"id": r[0], "channel": r[1], "who": r[2], "started": r[3], "updated": r[4], "outcome": r[5], "outcome_label": OUTCOMES.get(r[5], r[5]), "topics": json.loads(r[6] or "[]"), "summary": r[7], "ai_summary": r[8],
            "turns": [{"t": t, "role": role, "text": text} for t, role, text in turns], "transcripts_on": enabled(agent), "extracted": {"number_shown": r[2], "topics": json.loads(r[6] or "[]"), "outcome": OUTCOMES.get(r[5], r[5]), "needs_person": r[5] in ("staff", "handoff")}}


def ai_summary(agent, cid):
    """Owner pressed the button: the business's own AI writes a two-sentence summary from the saved words (already redacted). Needs transcripts on and the AI connected."""
    from . import brain
    d = get(agent, cid)
    if not d:
        raise ValueError("That conversation was not found.")
    if not d["turns"]:
        raise ValueError("There are no saved words for this conversation. Switch transcripts on to keep them.")
    if not brain.configured(agent):
        raise ValueError("Connect your AI first (Connect tab).")
    text = "\n".join(f"{x['role']}: {x['text']}" for x in d["turns"])[:6000]
    raw, _u = R._chat(agent.cfg["reasoner"], "Summarise this phone call or text conversation between a business's automated assistant and a customer in at most two plain sentences: what the customer wanted and how it ended. Use only what is written. Do not invent anything and do not repeat any personal details.", R.redact(text, None), 200)
    s = " ".join(str(raw or "").split())[:400]
    with _lock:
        _conn(agent).execute("update conv set ai_summary=? where id=?", (s, int(cid)))
    return get(agent, cid)


def delete(agent, cid=None):
    c = _conn(agent)
    with _lock:
        if cid is None:
            c.execute("delete from turns"); n = c.execute("delete from conv").rowcount
        else:
            c.execute("delete from turns where conv=?", (int(cid),)); n = c.execute("delete from conv where id=?", (int(cid),)).rowcount
    return n


def scrub(agent, days):
    """Deletes the saved words of conversations older than `days` (the record, outcome and summary stay). Returns how many conversations lost their words."""
    c = _conn(agent); cutoff = int(agent.now()) - int(days) * 86400
    with _lock:
        ids = [r[0] for r in c.execute("select id from conv where updated<? and id in (select conv from turns)", (cutoff,)).fetchall()]
        for i in ids:
            c.execute("delete from turns where conv=?", (i,))
    return len(ids)


def set_enabled(agent, on):
    from . import connect as SU
    raw = SU._raw(agent); raw.setdefault("transcripts", {})["enabled"] = bool(on)
    SU._write_raw(agent, raw); SU._reload(agent)
    return {"enabled": enabled(agent)}
