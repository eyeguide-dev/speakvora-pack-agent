"""Google Calendar. Two ways to connect, pick one:
  * mode "ics": paste your calendar's private iCal address. Read-only, no Google sign-in. Repeating events are not expanded.
  * mode "oauth": your own Google Cloud OAuth client + a refresh token for your account. Reads events (repeating ones expanded) and, if you turn it on, creates events.
Either way the agent only looks at events in the next day or two and only ever reads the title, time, place and notes."""
import datetime as dt, re, time
from urllib.parse import quote

from .. import web as http


def _unfold(t):
    return re.sub(r"\r?\n[ \t]", "", t)


def _ics_time(val, params):
    val = val.strip()
    if re.fullmatch(r"\d{8}", val):
        return int(dt.datetime.strptime(val, "%Y%m%d").replace(tzinfo=dt.timezone.utc).timestamp())
    if val.endswith("Z"):
        return int(dt.datetime.strptime(val, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc).timestamp())
    naive = dt.datetime.strptime(val, "%Y%m%dT%H%M%S")
    tz = re.search(r"TZID=([^;:]+)", params or "")
    try:
        from zoneinfo import ZoneInfo
        return int(naive.replace(tzinfo=ZoneInfo(tz.group(1)) if tz else dt.timezone.utc).timestamp())
    except Exception:  # noqa: BLE001
        return int(naive.replace(tzinfo=dt.timezone.utc).timestamp())


def parse_ics(text):
    events = []
    for blk in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", _unfold(text), re.S):
        f = {}
        for line in blk.strip().splitlines():
            m = re.match(r"([A-Z\-]+)((?:;[^:]*)?):(.*)", line)
            if m:
                f.setdefault(m.group(1), (m.group(3), m.group(2)))
        if "DTSTART" not in f:
            continue
        unesc = lambda s: s.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")  # noqa: E731
        start = _ics_time(*f["DTSTART"])
        events.append({"id": f.get("UID", ("", ""))[0] or f"{start}", "title": unesc(f.get("SUMMARY", ("", ""))[0]), "start": start,
                       "end": _ics_time(*f["DTEND"]) if "DTEND" in f else start, "description": unesc(f.get("DESCRIPTION", ("", ""))[0]), "location": unesc(f.get("LOCATION", ("", ""))[0])})
    return events


class GoogleCalendar:
    def __init__(self, cfg):
        self.mode = cfg.get("mode", "")
        self.cfg = cfg
        self.api = cfg.get("api_base", "https://www.googleapis.com").rstrip("/")
        self.token_url = cfg.get("token_url", "https://oauth2.googleapis.com/token")
        self.calendar_id = cfg.get("calendar_id", "primary")
        self.allow_create = bool(cfg.get("allow_create"))
        self.configured = (self.mode == "ics" and bool(cfg.get("ics_url"))) or (self.mode == "oauth" and all(cfg.get(k) for k in ("client_id", "client_secret", "refresh_token")))
        self._tok = ("", 0)

    def _access(self, now=None):
        now = now or time.time()
        if self._tok[1] > now + 60:
            return self._tok[0]
        _st, r = http.request("POST", self.token_url, form={"client_id": self.cfg["client_id"], "client_secret": self.cfg["client_secret"], "refresh_token": self.cfg["refresh_token"], "grant_type": "refresh_token"})
        self._tok = (r["access_token"], now + int(r.get("expires_in", 3600)))
        return self._tok[0]

    def events(self, start_ts, end_ts):
        """Events that START between the two times (epoch seconds), oldest first."""
        if self.mode == "ics":
            _st, txt = http.request("GET", self.cfg["ics_url"])
            return sorted([e for e in parse_ics(txt if isinstance(txt, str) else "") if start_ts <= e["start"] < end_ts], key=lambda e: e["start"])
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        url = f"{self.api}/calendar/v3/calendars/{quote(self.calendar_id, safe='')}/events?singleEvents=true&orderBy=startTime&timeMin={iso(start_ts)}&timeMax={iso(end_ts)}&maxResults=100"
        _st, r = http.request("GET", url, {"authorization": "Bearer " + self._access()})
        out = []
        for e in (r.get("items") or []):
            s = (e.get("start") or {}).get("dateTime") or ((e.get("start") or {}).get("date", "") + "T00:00:00Z")
            en = (e.get("end") or {}).get("dateTime") or s
            p = lambda x: int(dt.datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp())  # noqa: E731
            out.append({"id": e.get("id", ""), "title": e.get("summary", ""), "start": p(s), "end": p(en), "description": e.get("description", ""), "location": e.get("location", "")})
        return out

    def _writable(self):
        if not (self.mode == "oauth" and self.allow_create):
            raise PermissionError("Changing calendar events is off. Set google_calendar.allow_create to true (oauth mode) if you want it.")

    def _ev_url(self, event_id=""):
        base = f"{self.api}/calendar/v3/calendars/{quote(self.calendar_id, safe='')}/events"
        return base + ("/" + quote(event_id, safe="") if event_id else "")

    def conflicts(self, start_ts, end_ts, exclude_id=""):
        """Timed, busy entries that overlap [start_ts, end_ts). All-day entries and ones marked free never block a booking."""
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        q = f"?singleEvents=true&orderBy=startTime&maxResults=50&timeMin={iso(start_ts)}&timeMax={iso(end_ts)}"
        _st, r = http.request("GET", self._ev_url() + q, {"authorization": "Bearer " + self._access()})
        p = lambda x: int(dt.datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp())  # noqa: E731
        out = []
        for e in (r.get("items") or []):
            st, en = (e.get("start") or {}).get("dateTime"), (e.get("end") or {}).get("dateTime")
            if not st or not en or e.get("status") == "cancelled" or e.get("transparency") == "transparent" or e.get("id") == exclude_id:
                continue
            if p(st) < end_ts and p(en) > start_ts:
                out.append(e)
        return out

    def _guard(self, start_ts, end_ts, exclude_id="", ignore=False):
        if ignore or self.cfg.get("double_booking") == "allow":
            return
        hit = self.conflicts(start_ts, end_ts, exclude_id)
        if hit:
            raise PermissionError("That time is already taken on the calendar (" + str(hit[0].get("summary") or "another entry")[:40] + "). Pick another time, or set google_calendar.double_booking to \"allow\".")

    def create(self, title, start_ts, end_ts, description="", location="", ref="", ignore_busy=False):
        """Adds an event and tags it as made by this agent (and with your booking reference, if you give one) so it can later be moved or cancelled by the agent and by nothing else."""
        self._writable(); self._guard(start_ts, end_ts, ignore=ignore_busy)
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        priv = {"speakvora": "1"}
        if ref:
            priv["ref"] = str(ref)[:200]
        body = {"summary": title, "description": description, "location": location, "start": {"dateTime": iso(start_ts)}, "end": {"dateTime": iso(end_ts)}, "extendedProperties": {"private": priv}}
        return http.request("POST", self._ev_url(), {"authorization": "Bearer " + self._access()}, body=body)[1]

    def find(self, ref):
        """The live event this agent made for that booking reference. Events the agent did not make are never returned, so they can never be changed through it."""
        ref = str(ref or "").strip()
        if not ref:
            raise PermissionError("Give a booking reference (for example the appointment id) so the right calendar entry can be found.")
        q = f"?privateExtendedProperty={quote('speakvora=1')}&privateExtendedProperty={quote('ref=' + ref)}&maxResults=5&showDeleted=false"
        _st, r = http.request("GET", self._ev_url() + q, {"authorization": "Bearer " + self._access()})
        for e in (r.get("items") or []):
            if e.get("status") != "cancelled" and ((e.get("extendedProperties") or {}).get("private") or {}).get("speakvora") == "1":
                return e
        raise PermissionError(f"No calendar entry made by this agent was found for reference {ref}.")

    def reschedule(self, ref, start_ts, end_ts, ignore_busy=False):
        self._writable(); e = self.find(ref); self._guard(start_ts, end_ts, exclude_id=e["id"], ignore=ignore_busy)
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        return http.request("PATCH", self._ev_url(e["id"]), {"authorization": "Bearer " + self._access()}, body={"start": {"dateTime": iso(start_ts)}, "end": {"dateTime": iso(end_ts)}})[1]

    def cancel(self, ref):
        """Keeps the entry but marks it cancelled and free, so your history shows what happened."""
        self._writable(); e = self.find(ref); title = e.get("summary", "")
        body = {"summary": title if title.startswith("Cancelled: ") else "Cancelled: " + title, "transparency": "transparent"}
        return http.request("PATCH", self._ev_url(e["id"]), {"authorization": "Bearer " + self._access()}, body=body)[1]

    def delete(self, ref):
        self._writable(); e = self.find(ref)
        http.request("DELETE", self._ev_url(e["id"]), {"authorization": "Bearer " + self._access()})
        return {"id": e["id"], "deleted": True}
