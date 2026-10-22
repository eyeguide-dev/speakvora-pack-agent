"""The agent's own booking book, so the AI can book a table (or an appointment) and confirm it on the phone while the caller is still on the line.
It is off until the owner switches it on (Automations, Bookings). The book knows your opening days and hours, how many seats each area has, how long a booking lasts and the largest party;
a request is checked against those rules, against the bookings already made and against the events in your calendar that block the day ("Closed", "Private party"...). When the request fits, it is
written down and confirmed with a short code; when it does not, the caller gets the nearest times that do. If you connected a calendar the agent can write to (Google, with writing switched on),
a booking is confirmed only after that calendar accepts it. Every booking is also published as a calendar feed (an .ics address) that Outlook, Google or Apple Calendar can subscribe to.
Nothing here touches money, and a booking can be cancelled from the dashboard."""
import datetime as dt, hashlib, os, re, secrets, sqlite3, threading, time
from zoneinfo import ZoneInfo

DEFAULTS = {"enabled": False, "days": [1, 2, 3, 4, 5, 6], "open": "17:00", "last_seating": "21:00", "close": "22:00", "slot_minutes": 90, "max_party": 8, "lead_minutes": 30, "days_ahead": 30,
            "areas": {"inside": 40, "outside": 24}, "block_words": ["closed", "private", "buyout", "full", "event"]}
_LOCK = threading.Lock()
WORDS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def settings(agent):
    c = dict(DEFAULTS); c.update({k: v for k, v in (agent.cfg.get("bookings") or {}).items() if k in DEFAULTS}); c["areas"] = dict(c["areas"] or DEFAULTS["areas"]); return c


def _db(agent):
    p = os.path.join(agent.state.dir, "bookings.db"); con = sqlite3.connect(p, timeout=10)
    con.execute("CREATE TABLE IF NOT EXISTS bookings (code TEXT PRIMARY KEY, name TEXT, phone TEXT, party INT, area TEXT, start INT, minutes INT, notes TEXT, status TEXT, source TEXT, created INT, cal_ref TEXT)")
    return con


def _tz(agent):
    try:
        return ZoneInfo(agent.cfg.get("timezone") or "America/New_York")
    except Exception:  # noqa: BLE001
        return ZoneInfo("America/New_York")


def _hm(s):
    h, m = (int(x) for x in str(s).split(":")[:2]); return h * 60 + m


def parse_start(agent, text):
    """'YYYY-MM-DDTHH:MM' in the business's time zone -> epoch seconds, or None."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", str(text or "").strip())
    if not m:
        return None
    try:
        return int(dt.datetime(*(int(x) for x in m.groups()), tzinfo=_tz(agent)).timestamp())
    except ValueError:
        return None


def say_time(agent, ts):
    d = dt.datetime.fromtimestamp(ts, _tz(agent)); today = dt.datetime.now(_tz(agent)).date()
    day = "today" if d.date() == today else "tomorrow" if d.date() == today + dt.timedelta(days=1) else d.strftime("%A")
    h = d.hour % 12 or 12; return f"{day} at {h}" + (f":{d.minute:02d}" if d.minute else "") + (" PM" if d.hour >= 12 else " AM")


def _used(agent, start, end, area, ignore=None):
    con = _db(agent)
    try:
        rows = con.execute("SELECT party FROM bookings WHERE status='confirmed' AND area=? AND start < ? AND start + minutes*60 > ?" + (" AND code != ?" if ignore else ""), (area, end, start) + ((ignore,) if ignore else ())).fetchall()
    finally:
        con.close()
    return sum(r[0] for r in rows)


def _blocked(agent, start, end, cfg):
    """A calendar event that overlaps and has one of the blocking words in its title closes the book for that time."""
    cal = [c for c in (getattr(agent, "gcal", None), getattr(agent, "outlook", None)) if c is not None and getattr(c, "configured", False)]
    for c in cal:
        try:
            for e in c.events(start - 6 * 3600, end):
                if e.get("end", e["start"]) > start and e["start"] < end and any(w in str(e.get("title", "")).lower() for w in cfg["block_words"]):
                    return e.get("title") or "an event"
        except Exception:  # noqa: BLE001 - a calendar that cannot be read never blocks a guest from booking; the book's own rules still apply
            continue
    return ""


def check(agent, start, party, area, ignore=None):
    """-> {'ok': bool, 'reason': str, 'alternatives': [(epoch, area)]}. Never raises."""
    cfg = settings(agent); now = time.time(); tz = _tz(agent); d = dt.datetime.fromtimestamp(start, tz); minutes = int(cfg["slot_minutes"]); end = start + minutes * 60
    area = area if area in cfg["areas"] else ("inside" if "inside" in cfg["areas"] else next(iter(cfg["areas"])))
    def verdict(ok, reason):
        return {"ok": ok, "reason": reason, "area": area, "alternatives": [] if ok else alternatives(agent, start, party, area, cfg)}
    if not cfg["enabled"]:
        return {"ok": False, "reason": "off", "area": area, "alternatives": []}
    if party < 1 or party > int(cfg["max_party"]):
        return {"ok": False, "reason": "party", "area": area, "alternatives": []}
    if start < now + int(cfg["lead_minutes"]) * 60 or start > now + int(cfg["days_ahead"]) * 86400:
        return {"ok": False, "reason": "window", "area": area, "alternatives": []}
    if d.weekday() not in cfg["days"] or not (_hm(cfg["open"]) <= d.hour * 60 + d.minute <= _hm(cfg["last_seating"])):
        return verdict(False, "closed")
    if _blocked(agent, start, end, cfg):
        return verdict(False, "blocked")
    if _used(agent, start, end, area, ignore) + party > int(cfg["areas"][area]):
        return verdict(False, "full")
    return {"ok": True, "reason": "", "area": area, "alternatives": []}


def alternatives(agent, start, party, area, cfg=None, limit=3):
    """The nearest times (within three hours, any area) that do fit, closest first."""
    cfg = cfg or settings(agent); out = []
    for off in (0, 30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180, -180):
        t = start + off * 60
        for a in ([area] + [x for x in cfg["areas"] if x != area]):
            if off == 0 and a == area:                                     # the time they asked for in the area they asked for is the one that failed
                continue
            if len(out) < limit and not any(o[0] == t for o in out):
                c = _fits(agent, t, party, a, cfg)
                if c:
                    out.append((t, a)); break
    return out


def _fits(agent, t, party, area, cfg):
    now = time.time(); d = dt.datetime.fromtimestamp(t, _tz(agent)); end = t + int(cfg["slot_minutes"]) * 60
    if t < now + int(cfg["lead_minutes"]) * 60 or d.weekday() not in cfg["days"] or not (_hm(cfg["open"]) <= d.hour * 60 + d.minute <= _hm(cfg["last_seating"])):
        return False
    return not _blocked(agent, t, end, cfg) and _used(agent, t, end, area) + party <= int(cfg["areas"][area])


def _writable_calendar(agent):
    g = getattr(agent, "gcal", None)
    if g is not None and getattr(g, "configured", False) and (agent.cfg.get("google_calendar") or {}).get("allow_create"):
        return g
    return None


def _new_code(agent):
    """A four-digit confirmation code: easy to say and to hear on the phone, and not used by another upcoming booking."""
    taken = {b["code"] for b in upcoming(agent, 500)}
    for _ in range(50):
        c = str(secrets.randbelow(9000) + 1000)
        if c not in taken:
            return c
    return str(secrets.randbelow(900000) + 100000)


def create(agent, name, party, start, area, notes="", phone="", source="call"):
    """Writes the booking. Returns {'ok', 'code', 'say', 'booking'}; with a writable calendar the booking is confirmed only when that calendar accepts it."""
    cfg = settings(agent); name = " ".join(str(name or "").split())[:60] or "Guest"; notes = " ".join(str(notes or "").split())[:200]
    with _LOCK:
        c = check(agent, start, party, area)
        if not c["ok"]:
            return {"ok": False, "reason": c["reason"], "say": unavailable_say(agent, c, party, start), "alternatives": c["alternatives"]}
        area = c["area"]; code = _new_code(agent); minutes = int(cfg["slot_minutes"]); ref = ""
        cal = None if agent.dry else _writable_calendar(agent)          # practice mode takes the booking in the local book only: no calendar is touched
        if cal is not None:
            try:
                r = cal.create(f"Table for {party} ({area}): {name}", start, start + minutes * 60, description=(notes + "\nBooked by phone through the agent. Code " + code).strip(), ref=code)
                ref = str((r or {}).get("id") or code)
            except Exception as e:  # noqa: BLE001 - the calendar did not accept it: never confirm what the calendar refused
                agent.state.log(workflow="bookings", action="calendar_write", status="refused", dry_run=False, error=str(e)[:140])
                return {"ok": False, "reason": "calendar", "say": "I could not confirm that with our calendar just now. I will have the host call you to book it.", "alternatives": []}
        con = _db(agent)
        try:
            con.execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (code, name, phone, party, area, start, minutes, notes, "confirmed", ("practice " if agent.dry else "") + source, int(time.time()), ref)); con.commit()
        finally:
            con.close()
    b = get(agent, code); spoken = " ".join(code)                                          # "4 8 2 7": said digit by digit
    return {"ok": True, "code": code, "booking": b, "say": f"You are booked: a table for {party} {area}, {say_time(agent, start)}, under {name}. Your confirmation code is {spoken}."}


def unavailable_say(agent, c, party, start):
    r = c["reason"]; alts = c.get("alternatives") or []
    if r == "off":
        return "I cannot book that myself, so I will have the host call you."
    if r == "party":
        return f"For a party that size I will have the host call you to arrange it."
    if r == "window":
        return "I can only book a little while ahead, and not too far out. What other day or time works?"
    why = {"closed": "We are not seating at that time.", "blocked": "We are closed to bookings at that time.", "full": "That time is full."}.get(r, "I cannot book that time.")
    if alts:
        opts = " or ".join(f"{say_time(agent, t)}" + (f" {a}" if a != c.get("area") else "") for t, a in alts[:3])
        return f"{why} I do have {opts}. Would one of those work?"
    return f"{why} What other day or time would work?"


def get(agent, code):
    con = _db(agent)
    try:
        r = con.execute("SELECT code,name,phone,party,area,start,minutes,notes,status,source,created,cal_ref FROM bookings WHERE code=?", (str(code).upper(),)).fetchone()
    finally:
        con.close()
    return dict(zip(("code", "name", "phone", "party", "area", "start", "minutes", "notes", "status", "source", "created", "cal_ref"), r)) if r else None


def upcoming(agent, limit=50):
    con = _db(agent)
    try:
        rows = con.execute("SELECT code,name,phone,party,area,start,minutes,notes,status,source,created,cal_ref FROM bookings WHERE status='confirmed' AND start + minutes*60 > ? ORDER BY start LIMIT ?", (int(time.time()), limit)).fetchall()
    finally:
        con.close()
    return [dict(zip(("code", "name", "phone", "party", "area", "start", "minutes", "notes", "status", "source", "created", "cal_ref"), r)) for r in rows]


def cancel(agent, code):
    b = get(agent, code)
    if not b or b["status"] != "confirmed":
        return False
    cal = _writable_calendar(agent)
    if cal is not None and b.get("cal_ref"):
        try:
            cal.cancel(b["code"])
        except Exception:  # noqa: BLE001
            pass
    con = _db(agent)
    try:
        con.execute("UPDATE bookings SET status='cancelled' WHERE code=?", (b["code"],)); con.commit()
    finally:
        con.close()
    return True


def attempt(agent, item, phone="", source="call"):
    """The AI asked to book. item = {name, party, start 'YYYY-MM-DDTHH:MM', area, notes}. Returns create()'s answer; bad or missing details are asked for, never guessed."""
    start = parse_start(agent, item.get("start")); party = item.get("party")
    try:
        party = int(party)
    except (TypeError, ValueError):
        party = 0
    if start is None or party < 1 or not str(item.get("name") or "").strip():
        return {"ok": False, "reason": "incomplete", "say": "", "alternatives": []}
    return create(agent, item.get("name"), party, start, str(item.get("area") or "").lower(), item.get("notes") or "", phone, source)


# ---- the calendar feed --------------------------------------------------------------------------------------------------------------------------------------------------------------------
def feed_token(agent):
    t = agent.state.data.get("bookings_feed_token")
    if not t:
        t = secrets.token_urlsafe(18); agent.state.data["bookings_feed_token"] = t; agent.state.save()
    return t


def ics(agent):
    """All upcoming confirmed bookings as an iCalendar feed. No customer phone numbers: just name, party, area, notes and the code."""
    def utc(ts):
        return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    esc = lambda s: str(s).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")  # noqa: E731
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Speakvora agent//Bookings//EN", "CALSCALE:GREGORIAN", "X-WR-CALNAME:" + esc((agent.cfg.get("business") or "Agent") + " bookings")]
    for b in [x for x in upcoming(agent, 500) if not str(x["source"]).startswith("practice")]:
        lines += ["BEGIN:VEVENT", f"UID:{b['code']}@speakvora-agent", f"DTSTAMP:{utc(b['created'])}", f"DTSTART:{utc(b['start'])}", f"DTEND:{utc(b['start'] + b['minutes'] * 60)}",
                  "SUMMARY:" + esc(f"Table for {b['party']} ({b['area']}): {b['name']}"), "DESCRIPTION:" + esc((b["notes"] + "\n" if b["notes"] else "") + "Code " + b["code"] + ". Booked by the agent."), "END:VEVENT"]
    lines.append("END:VCALENDAR"); return "\r\n".join(lines) + "\r\n"


# ---- the dashboard (Automations, Bookings) --------------------------------------------------------------------------------------------------------------------------------------------
def view(agent):
    cfg = settings(agent); base = str(agent.cfg.get("public_base_url") or "").rstrip("/")
    if "YOUR-" in base:
        base = ""
    local = f"http://127.0.0.1:{agent.cfg['listen']['port']}"
    path = "/bookings/" + feed_token(agent) + ".ics"
    rows = [{"code": b["code"], "name": b["name"], "party": b["party"], "area": b["area"], "when": say_time(agent, b["start"]), "start": b["start"], "notes": b["notes"], "source": b["source"], "practice": str(b["source"]).startswith("practice"), "calendar": bool(b.get("cal_ref"))} for b in upcoming(agent, 40)]
    return {"settings": cfg, "upcoming": rows, "feed_url": (base or local) + path, "feed_public": bool(base), "writes_calendar": _writable_calendar(agent) is not None,
            "ai_ready": bool(getattr(agent, "cfg", {}).get("reasoner")), "words": WORDS}


def save(agent, v):
    """Saves the booking rules from the dashboard. Switching booking on also lets the AI use it (Settings, Built-in safeguards)."""
    from . import connect as SU
    cur = settings(agent); new = {}
    new["enabled"] = bool(v.get("enabled"))
    days = [int(d) for d in (v.get("days") or cur["days"]) if str(d).isdigit() and 0 <= int(d) <= 6] or cur["days"]; new["days"] = sorted(set(days))
    for k in ("open", "last_seating", "close"):
        val = str(v.get(k) or cur[k]).strip()
        if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", val):
            raise SU.SetupError("Times look like 17:00.")
        new[k] = val.zfill(5)
    for k, lo, hi in (("slot_minutes", 30, 240), ("max_party", 1, 40), ("lead_minutes", 0, 1440), ("days_ahead", 1, 365)):
        try:
            new[k] = max(lo, min(int(v.get(k, cur[k])), hi))
        except (TypeError, ValueError):
            raise SU.SetupError(f"{k.replace('_', ' ').capitalize()} must be a number.")
    areas = {}
    for name, seats in (v.get("areas") or cur["areas"]).items():
        n = re.sub(r"[^a-z ]", "", str(name).lower()).strip()[:20]
        if n and str(seats).isdigit() and 1 <= int(seats) <= 500:
            areas[n] = int(seats)
    if not areas:
        raise SU.SetupError("Add at least one seating area with a number of seats.")
    new["areas"] = areas; new["block_words"] = cur["block_words"]
    raw = SU._raw(agent); raw["bookings"] = new
    g = raw.setdefault("guardrails", {}); acts = list(g.get("allowed_actions") or [])
    if new["enabled"] and "book" not in acts:
        acts.append("book")
    if not new["enabled"]:
        acts = [a for a in acts if a != "book"]
    g["allowed_actions"] = acts
    SU._write_raw(agent, raw); SU._reload(agent)
    return view(agent)
