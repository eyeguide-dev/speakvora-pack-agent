"""Microsoft 365 / Outlook calendar (read-only) through Microsoft Graph. Use your own Azure app registration (delegated Calendars.Read, offline_access) and a refresh token; or a private ICS link (mode "ics" works with Outlook too)."""
import datetime as dt, time

from .. import web as http
from .gcal import parse_ics


class OutlookCalendar:
    def __init__(self, cfg):
        self.cfg, self.mode = cfg, cfg.get("mode", "")
        self.api = cfg.get("api_base", "https://graph.microsoft.com").rstrip("/")
        self.token_url = cfg.get("token_url", f"https://login.microsoftonline.com/{cfg.get('tenant', 'common')}/oauth2/v2.0/token")
        self.configured = (self.mode == "ics" and bool(cfg.get("ics_url"))) or (self.mode == "oauth" and all(cfg.get(k) for k in ("client_id", "refresh_token")))
        self._tok = ("", 0)

    def _access(self):
        if self._tok[1] > time.time() + 60:
            return self._tok[0]
        form = {"client_id": self.cfg["client_id"], "refresh_token": self.cfg["refresh_token"], "grant_type": "refresh_token", "scope": "https://graph.microsoft.com/Calendars.Read offline_access"}
        if self.cfg.get("client_secret"):
            form["client_secret"] = self.cfg["client_secret"]
        _st, r = http.request("POST", self.token_url, form=form)
        self._tok = (r["access_token"], time.time() + int(r.get("expires_in", 3600)))
        return self._tok[0]

    def events(self, start_ts, end_ts):
        if self.mode == "ics":
            _st, txt = http.request("GET", self.cfg["ics_url"])
            return sorted([e for e in parse_ics(txt if isinstance(txt, str) else "") if start_ts <= e["start"] < end_ts], key=lambda e: e["start"])
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")  # noqa: E731
        _st, r = http.request("GET", f"{self.api}/v1.0/me/calendarView?startDateTime={iso(start_ts)}&endDateTime={iso(end_ts)}&$top=100&$select=id,subject,start,end,bodyPreview,location",
                              {"authorization": "Bearer " + self._access(), "Prefer": 'outlook.timezone="UTC"'})
        p = lambda x: int(dt.datetime.fromisoformat(x.split(".")[0]).replace(tzinfo=dt.timezone.utc).timestamp())  # noqa: E731
        return [{"id": e["id"], "title": e.get("subject", ""), "start": p(e["start"]["dateTime"]), "end": p(e["end"]["dateTime"]), "description": e.get("bodyPreview", ""), "location": (e.get("location") or {}).get("displayName", "")}
                for e in (r.get("value") or [])]
