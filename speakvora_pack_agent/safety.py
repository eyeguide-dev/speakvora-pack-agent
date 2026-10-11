"""The guard rails. Nothing leaves this process unless it passes here: dry-run by default, consent for customer messages, opt-outs (STOP), quiet hours, per-person and hourly limits, and a kill switch."""
import datetime as dt, os, re
from zoneinfo import ZoneInfo

CUSTOMER_KINDS = ("sms", "call", "email")


def norm_phone(p):
    d = re.sub(r"[^\d+]", "", str(p or ""))
    return d if d.startswith("+") else ("+1" + d if len(d) == 10 else ("+" + d if d else ""))


class Safety:
    def __init__(self, cfg, state, now=None):
        self.cfg, self.state = cfg, state
        self.now = now or state.now

    def killed(self):
        return os.path.exists(os.path.join(self.state.dir, "STOP")) or os.environ.get("SV_AGENT_STOP") == "1"

    def in_quiet_hours(self, kind):
        q = self.cfg["quiet_hours"]
        if not q or kind not in q.get("applies_to", []):
            return False
        local = dt.datetime.fromtimestamp(self.now(), ZoneInfo(self.cfg["timezone"])).strftime("%H:%M")
        s, e = q["start"], q["end"]
        return (s <= local or local < e) if s > e else (s <= local < e)

    def check(self, kind, to, ctx, urgent=False):
        """Returns (ok, reason). Internal messages (Slack, your own webhooks) only face the kill switch and the hourly cap."""
        if self.killed():
            return False, "kill_switch"
        lim = self.cfg["limits"]
        if lim.get("per_hour") is not None and self.state.sent_since(3600) >= lim["per_hour"]:
            return False, "hourly_limit"
        if kind not in CUSTOMER_KINDS:
            return True, ""
        who = norm_phone(to) if kind != "email" else str(to).lower()
        if not who:
            return False, "no_recipient"
        if self.state.is_opted_out(who):
            return False, "opted_out"
        allow = [norm_phone(x) if kind != "email" else str(x).lower() for x in self.cfg.get("recipients", {}).get("allow", [])]
        c = self.cfg["consent"]
        if c.get("required") and who not in allow:
            have = ctx
            for part in c["field"].split("."):
                have = have.get(part) if isinstance(have, dict) else None
            if not have:
                return False, "no_consent"
        staff = who in allow
        if self.in_quiet_hours(kind) and not (urgent and staff):          # an urgent alert to a number on your own allow-list (for example the on-call phone) may wake someone up
            return False, "quiet_hours"
        if lim.get("per_recipient_per_day") is not None and not (urgent and staff) and self.state.sent_since(86400, to=who) >= lim["per_recipient_per_day"]:
            return False, "recipient_daily_limit"
        return True, ""

    def sent(self, kind, to):
        self.state.record_send(kind, norm_phone(to) if kind in ("sms", "call") else str(to).lower())
