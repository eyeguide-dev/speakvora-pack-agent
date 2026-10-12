"""The agent: receives triggers (an event from your app, a calendar tick, an inbound text or call, a Slack command, a daily schedule), picks the matching workflows from workflows.json, and runs their actions through the connectors,
always through the safety checks first. Dry-run (the default) records what it WOULD do and sends nothing."""
import datetime as dt, json, re, threading, time
from zoneinfo import ZoneInfo

from . import i18n, safety as S, slots as slots_mod, templating as T
from .audio import AudioError, AudioStore
from .connectors import signing
from .connectors.gcal import GoogleCalendar
from .connectors.imap import Inbox
from .connectors.mailer import Email
from .connectors.outlook import OutlookCalendar
from .connectors.teams import Teams
from .connectors.slack import Slack
from .connectors.twilio import Twilio, twiml_menu, twiml_message, twiml_parts, twiml_play
from .providers import HttpProvider
from .pack import Pack, PackError
from .state import State
from . import web

PHONE_RX = re.compile(r"(\+?\d[\d\-\s().]{8,}\d)")
QUEUEABLE = ("sms", "call", "slack", "teams", "email", "webhook", "http", "calendar_create")       # actions that wait in the outbox when the network is down
KEEP_WHILE_BLOCKED = ("quiet_hours", "hourly_limit", "recipient_daily_limit")                      # a queued action blocked only by timing waits (until it expires); any other refusal drops it
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class Agent:
    def __init__(self, cfg, now=time.time):
        self.cfg, self.now = cfg, now
        self.pack = Pack(cfg["pack"])
        self.state = State(cfg["state_dir"], now)
        self.safe = S.Safety(cfg, self.state, now)
        self.audio = AudioStore(self.pack, cfg["state_dir"], cfg.get("public_base_url", ""))
        self.twilio, self.slack, self.gcal, self.mail = Twilio(cfg["twilio"]), Slack(cfg["slack"]), GoogleCalendar(cfg["google_calendar"]), Email(cfg["email"])
        self.teams, self.outlook, self.inbox = Teams(cfg.get("teams", {})), OutlookCalendar(cfg.get("microsoft_calendar", {})), Inbox(cfg.get("inbox", {}))
        self.imap_factory = None
        self.sms_provider, self.call_provider = HttpProvider(cfg.get("sms_provider")), HttpProvider(cfg.get("call_provider"))
        wf = json.load(open(cfg["workflows"], encoding="utf-8")) if cfg.get("workflows") else {}
        self.workflows = [w for w in wf.get("workflows", []) if w.get("enabled", True)]
        for name, spec in (wf.get("slots") or {}).items():                    # optional overrides: slot name -> a specific phrase
            try:
                self.pack.slots[name] = self.pack.resolve(spec)["id"]
            except PackError:
                pass
        self.dry = bool(cfg.get("dry_run", True))
        self._flush_lock = threading.Lock()
        base = str(cfg.get("public_base_url", "")).rstrip("/")
        self.twilio.status_url = base + "/twilio/status" if base.startswith("https://") and "YOUR-" not in base else ""     # Twilio tells us later whether a text or call really arrived
        self.lang = i18n.lang_of(self.pack.language)
        oc = str((cfg.get("facts") or {}).get("oncall_phone", ""))
        if oc and "YOUR-" not in oc:                                              # your own on-call phone is staff, not a customer: it may receive urgent alerts without a consent record
            cfg.setdefault("recipients", {}).setdefault("allow", []).append(oc)
        _lang, slug = slots_mod.pack_slug(str(self.pack.meta.get("pack", "")))
        self.profile = cfg.get("industry_profile") or slots_mod.profile_for(slug)
        found, _gaps = slots_mod.fill(self.pack, self.profile)                  # fill what the pack already says; the rest is reported by `slots` and can be requested
        for k, v in found.items():
            self.pack.slots.setdefault(k, v)
        self.registry = slots_mod.registry(self.profile)
        needed = slots_mod.needed_by(wf) | set(slots_mod.required_lines(self.profile, "call_out") + slots_mod.required_lines(self.profile, "menu") + slots_mod.required_lines(self.profile, "sms"))
        self.missing_required = sorted(x for x in needed if x in slots_mod.required_lines(self.profile, "call_out") + slots_mod.required_lines(self.profile, "menu") + slots_mod.required_lines(self.profile, "sms") and x not in self.pack.slots)
        self.missing_slots = sorted(x for x in needed if x not in self.pack.slots and x not in self.pack.by_id)

    # ---- required lines (always spoken / texted) -----------------------------------------------------------------------------------------------
    def _required(self, applies):
        comp = self.cfg.get("compliance", {}); extra = list(comp.get("extra_required", []))
        if comp.get("recording"):
            extra.append({"slot": "call_recorded_notice", "applies": ["menu", "call_out"]})
        return slots_mod.required_lines(self.profile, applies, extra)

    def _line_text(self, slot):
        try:
            return self.pack.text(slot)
        except PackError:
            return self.registry.get(slot, {}).get("example", "")

    def _line_part(self, slot):
        """('play', url) from the pack, or ('say', words) in the phone provider's voice when the pack has no audio for a REQUIRED line yet: the notice is never skipped, and the gap is logged."""
        try:
            return ("play", self.audio.url(self.pack.get(slot)["id"]))
        except (PackError, AudioError):
            self.state.log(workflow="compliance", status="required_line_fallback", slot=slot)
            return ("say", self._line_text(slot))

    def _sms_text(self, text, who):
        parts = [text]
        for slot in self._required("sms"):
            if slot == "opt_out_footer" and self.cfg["compliance"].get("sms_footer", "first") == "first" and f"footer:{who}" in self.state.data["done"]:
                continue
            t = self._line_text(slot)
            if t and t not in text:
                parts.append(t)
        return " ".join(parts)

    # ---- helpers -------------------------------------------------------------------------------------------------------------------------------
    def ctx(self, **kw):
        return {"facts": self.cfg.get("facts", {}), "business": self.cfg.get("business", ""), "lang": self.lang, **kw}

    def _slack_channel(self, name):
        """Workflows name a role ('#front', '#kitchen', '#host'). agent.json "slack": {"channel": "#general", "channels": {"#kitchen": "#orders"}}: a role listed under channels goes there, every other role goes to the one default channel, so a single setting is enough."""
        sc = self.cfg.get("slack") or {}; chmap = {str(k).lstrip("#"): v for k, v in (sc.get("channels") or {}).items()}
        key = str(name or "").lstrip("#")
        if key in chmap:
            return chmap[key]
        return (sc.get("channel") or name) if str(name or "").startswith("#") else name         # a channel written without '#' (an ID such as C0123ABC) is used exactly as written

    def _need(self, ok, what, hint):
        if not ok:
            raise PackError(f"{what} is not set up yet: {hint}")

    def record(self, wf, action, status, **extra):
        self.state.log(workflow=wf, action=action, status=status, dry_run=self.dry, **extra)

    @staticmethod
    def _when_ok(when, ctx):
        for path, want in (when or {}).items():
            have = T.lookup(ctx, path)
            if want == "*":
                if have in (None, "", False):
                    return False
            elif have != want:
                return False
        return True

    # ---- actions -------------------------------------------------------------------------------------------------------------------------------
    def run_actions(self, wf_name, actions, ctx, out=None):
        """Runs actions in order. `out` collects what an inbound text / call / Slack command should answer with: out['reply'], out['play'] (pack lines to play)."""
        out = out if out is not None else {"reply": "", "play": []}
        results = []
        for a in actions:
            kind = a.get("action")
            if a.get("if") and not self._when_ok(a["if"], ctx):                  # per-action condition, e.g. {"if": {"customer.prefers_call": "*"}}
                continue
            try:
                if kind == "http" and not re.match(r"^https?://[^/{}?#\s]+", str(a.get("url", ""))):
                    raise PackError("An http action must write the server address literally (https://host/...). Only the path, query and body may use {{...}} values.")
                a = T.render_obj({k: v for k, v in a.items() if k != "if"}, ctx, self.pack)
                if "YOUR-" in json.dumps(a):                                  # an example value from the sample config: never send it to a customer
                    raise PackError("Fill in the YOUR-... values in agent.json (for example the review link) before this can be sent.")
                r = self._do(wf_name, kind, a, ctx, out)
                ctx.setdefault("last", {})[kind] = r.get("status", "")      # later actions can say what really happened: {{last.sms}}
                results.append({"action": kind, **r})
            except (PackError, AudioError, PermissionError) as e:
                ctx.setdefault("last", {})[kind] = "skipped"
                self.record(wf_name, kind, "skipped", reason=str(e)); results.append({"action": kind, "status": "skipped", "reason": str(e)})
            except Exception as e:  # noqa: BLE001 - one failing service must never stop the others or the app
                ctx.setdefault("last", {})[kind] = "error"
                self.record(wf_name, kind, "error", error=type(e).__name__ + ": " + str(e)[:200]); results.append({"action": kind, "status": "error", "error": str(e)[:200]})
        return results

    def _gate(self, wf, kind, to, ctx, urgent=False):
        ok, why = self.safe.check(kind, to, ctx, urgent)
        if not ok:
            self.record(wf, kind, "blocked", to=to, reason=why)
            return {"status": "blocked", "reason": why}
        return None

    def _queueable(self, kind, a):
        q = self.cfg.get("queue") or {}
        return bool(q.get("enabled", True)) and kind in QUEUEABLE and not (kind == "http" and str(a.get("method", "POST")).upper() == "GET")

    def _do(self, wf, kind, a, ctx, out):
        """Runs one action. If the network is down (and only if the request provably never left this machine) the action is kept in the outbox and sent when the connection is back."""
        try:
            return self._do_now(wf, kind, a, ctx, out)
        except Exception as e:  # noqa: BLE001
            if not (self._queueable(kind, a) and web.is_offline(e)):
                raise
            qid = self.state.enqueue({"wf": wf, "kind": kind, "a": a, "ctx": {"customer": ctx.get("customer") or {}}})
            self.record(wf, kind, "queued", queue_id=qid, reason="offline")
            return {"status": "queued"}

    def flush_outbox(self):
        """Sends what was queued while offline, oldest first. Stops at the first action that still cannot leave (the connection is still down). Old actions expire (a reminder call 15 minutes late is worse than none: queue.max_age_minutes),
        timing blocks (quiet hours, hourly limit) keep an action waiting, and every other refusal drops it with a log line. The safety checks run again at send time."""
        items = self.state.outbox()
        stats = {"queued": len(items), "sent": 0, "expired": 0, "dropped": 0, "waiting": 0, "offline": False}
        if not items or self.dry or not self._flush_lock.acquire(blocking=False):
            return stats
        try:
            if self.safe.killed():
                stats["waiting"] = len(items); return stats
            ages = (self.cfg.get("queue") or {}).get("max_age_minutes") or {}
            for q in items:
                kind, a, now = q["kind"], q["a"], self.now()
                if now - q["queued_at"] > float(ages.get(kind, 1440)) * 60:
                    self.state.dequeue(q["id"]); stats["expired"] += 1
                    self.record(q["wf"], kind, "expired", queue_id=q["id"], waited_s=int(now - q["queued_at"])); continue
                ctx = self.ctx(**(q.get("ctx") or {}))
                who = S.norm_phone(a.get("to")) if kind in ("sms", "call") else str(a.get("to", ""))
                ok, why = self.safe.check("webhook" if kind == "http" else kind, who, ctx, bool(a.get("urgent")))
                if not ok and why in KEEP_WHILE_BLOCKED:
                    stats["waiting"] += 1; continue
                try:
                    r = self._do_now(q["wf"], kind, dict(a), ctx, {"reply": "", "play": []})
                except Exception as e:  # noqa: BLE001
                    if web.is_offline(e):
                        stats["offline"] = True; stats["waiting"] += len(items) - items.index(q); break
                    self.state.dequeue(q["id"]); stats["dropped"] += 1
                    self.record(q["wf"], kind, "failed_from_queue", queue_id=q["id"], error=type(e).__name__ + ": " + str(e)[:200]); continue
                self.state.dequeue(q["id"])
                if r.get("status") == "blocked":
                    stats["dropped"] += 1
                else:
                    stats["sent"] += 1; self.record(q["wf"], kind, "delivered_from_queue", queue_id=q["id"], waited_s=int(self.now() - q["queued_at"]))
            return stats
        finally:
            self._flush_lock.release()

    def _do_now(self, wf, kind, a, ctx, out):
        if kind == "reply":
            out["reply"] = a.get("text", ""); self.record(wf, kind, "ok"); return {"status": "ok"}
        if kind == "play":
            for spec in (a.get("audio") if isinstance(a.get("audio"), list) else [a.get("audio")]):
                out["play"].append(self.pack.get(spec["slot"] if isinstance(spec, dict) and "slot" in spec else spec)["id"] if not isinstance(spec, dict) else self.pack.resolve(spec)["id"])
            return {"status": "ok"}
        if kind == "log":
            self.record(wf, kind, "ok", text=a.get("text", "")); return {"status": "ok"}
        if kind == "sms":
            to = S.norm_phone(a["to"]); blocked = self._gate(wf, "sms", to, ctx, bool(a.get("urgent")))
            if blocked:
                return blocked
            media = self.audio.url(self.pack.resolve(a["audio"])["id"]) if a.get("audio") and a.get("media", False) else None
            wa = a.get("channel") == "whatsapp"                                  # same Twilio account; the number must be WhatsApp-enabled in Twilio (twilio.whatsapp_from)
            text = a["text"] if a.get("raw") else self._sms_text(a["text"], to)  # required notices (opt-out footer, debt-collector notice...) are added for you
            if self.dry:
                self.record(wf, kind, "dry_run", to=to, text=text, media=media, channel="whatsapp" if wa else "sms"); return {"status": "dry_run"}
            self._need(self.twilio.configured or self.sms_provider.configured, "Texting", "add the twilio section (or sms_provider) in agent.json")
            if self.sms_provider.configured and not wa:
                r = self.sms_provider.send(to=to, text=text, media_url=media or "")
            else:
                r = self.twilio.sms("whatsapp:" + to if wa else to, text, media, from_=("whatsapp:" + self.cfg["twilio"].get("whatsapp_from", self.twilio.from_number)) if wa else None)
            self.state.once(f"footer:{to}"); self.safe.sent("sms", to); self.record(wf, kind, "sent", to=to, sid=(r or {}).get("sid"), channel="whatsapp" if wa else "sms"); return {"status": "sent"}
        if kind == "teams":
            blocked = self._gate(wf, "teams", "teams", ctx)
            if blocked:
                return blocked
            if self.dry:
                self.record(wf, kind, "dry_run", text=a["text"]); return {"status": "dry_run"}
            self._need(self.teams.configured, "Microsoft Teams", "add teams.webhook_url in agent.json")
            self.teams.post(a["text"], a.get("title")); self.safe.sent("teams", "teams"); self.record(wf, kind, "sent"); return {"status": "sent"}
        if kind == "notify":
            # staff alert to every team chat you connected (Slack and/or Teams): the workflow does not care which one you use
            res = []
            if self.slack.configured or not self.teams.configured:
                res.append(self._do(wf, "slack", dict(a), ctx, out)["status"])
            if self.teams.configured:
                res.append(self._do(wf, "teams", {"text": a["text"], "title": a.get("title")}, ctx, out)["status"])
            return {"status": "sent" if "sent" in res else ("queued" if "queued" in res else (res[0] if res else "skipped"))}
        if kind == "call":
            to = S.norm_phone(a["to"]); blocked = self._gate(wf, "call", to, ctx, bool(a.get("urgent")))
            if blocked:
                return blocked
            body = [("play", self.audio.url(self.pack.resolve(x)["id"])) for x in (a["play"] if isinstance(a.get("play"), list) else [a["play"]])]
            parts = [self._line_part(x) for x in self._required("call_out")] + body        # required opening notices first (for example "This is an automated call.")
            twiml = twiml_parts(parts)
            if self.dry:
                self.record(wf, kind, "dry_run", to=to, parts=[list(p) for p in parts]); return {"status": "dry_run"}
            self._need(self.twilio.configured or self.call_provider.configured, "Calling", "add the twilio section (or call_provider) in agent.json")
            r = self.call_provider.send(to=to, twiml=twiml, audio_urls=[v for k, v in parts if k == "play"]) if self.call_provider.configured else self.twilio.call(to, twiml)
            self.safe.sent("call", to); self.record(wf, kind, "sent", to=to, sid=(r or {}).get("sid")); return {"status": "sent"}
        if kind == "slack":
            blocked = self._gate(wf, "slack", a.get("channel", ""), ctx)
            if blocked:
                return blocked
            path = self.audio.playable_file(self.pack.resolve(a["audio"])["id"]) if a.get("audio") else None
            ch = self._slack_channel(a.get("channel"))
            if self.dry:
                self.record(wf, kind, "dry_run", text=a["text"], channel=ch, audio=bool(path)); return {"status": "dry_run"}
            self._need(self.slack.configured, "Slack", "add slack.bot_token (or slack.webhook_url) in agent.json")
            if not a.get("_posted"):                                          # a retry after the text went out must not post it twice
                self.slack.post(a["text"], ch); a["_posted"] = True
            if path:
                self.slack.upload(ch, path, self.pack.text(self.pack.resolve(a["audio"])["id"])[:80])
            self.safe.sent("slack", a.get("channel", "")); self.record(wf, kind, "sent", channel=ch); return {"status": "sent"}
        if kind == "email":
            blocked = self._gate(wf, "email", a["to"], ctx)
            if blocked:
                return blocked
            path = self.audio.playable_file(self.pack.resolve(a["audio"])["id"]) if a.get("audio") else None
            if self.dry:
                self.record(wf, kind, "dry_run", to=a["to"], subject=a.get("subject")); return {"status": "dry_run"}
            self.mail.send(a["to"], a.get("subject", ""), a["text"], path); self.safe.sent("email", a["to"]); self.record(wf, kind, "sent", to=a["to"]); return {"status": "sent"}
        if kind == "webhook":
            blocked = self._gate(wf, "webhook", a["url"], ctx)
            if blocked:
                return blocked
            body = json.dumps(a.get("body", {})).encode()
            if self.dry:
                self.record(wf, kind, "dry_run", url=a["url"]); return {"status": "dry_run"}
            headers = signing.sign(self.cfg["events"]["secret"], body) if self.cfg["events"].get("secret") else {}
            web.request("POST", a["url"], {**headers, "content-type": "application/json"}, raw=body); self.safe.sent("webhook", a["url"]); self.record(wf, kind, "sent", url=a["url"]); return {"status": "sent"}
        if kind == "http":
            # Call ANY REST API (their booking system, CRM, POS...). The host is fixed by the workflow file: data from a webhook can fill the path, query and body but can never choose where the request goes.
            raw_url = a["url"]
            blocked = self._gate(wf, "webhook", raw_url, ctx)
            if blocked:
                return blocked
            method = a.get("method", "POST").upper()
            if self.dry or (method != "GET" and a.get("dry_run_only")):
                self.record(wf, kind, "dry_run", method=method, url=raw_url); return {"status": "dry_run"}
            kw = {"headers": a.get("headers", {})}
            if "json" in a:
                kw["body"] = a["json"]
            elif "form" in a:
                kw["form"] = a["form"]
            st, resp = web.request(method, raw_url, **kw)
            if a.get("save_as"):
                ctx.setdefault("http", {})[a["save_as"]] = resp if isinstance(resp, (dict, list)) else {"text": resp}
            self.safe.sent("webhook", raw_url); self.record(wf, kind, "ok", method=method, url=raw_url, status=st); return {"status": "ok", "http_status": st}
        if kind == "calendar_create":
            if self.dry:
                self.record(wf, kind, "dry_run", title=a.get("title")); return {"status": "dry_run"}
            start = int(a["start"]); self.gcal.create(a["title"], start, start + 60 * int(a.get("minutes", 60)), a.get("description", ""), a.get("location", ""))
            self.record(wf, kind, "created", title=a.get("title")); return {"status": "created"}
        raise PackError(f"Unknown action '{kind}' in workflow {wf}.")

    # ---- triggers ------------------------------------------------------------------------------------------------------------------------------
    def handle_event(self, payload):
        """An event from your app, e.g. {'event':'order.ready','id':'evt-9','customer':{...},'order':{...}}."""
        name, eid = str(payload.get("event", "")), str(payload.get("id") or json.dumps(payload, sort_keys=True)[:200])
        results = []
        for w in self.workflows:
            if (w.get("on") or {}).get("event") != name:
                continue
            ctx = self.ctx(**{k: v for k, v in payload.items() if k not in ("facts",)})
            if not self._when_ok(w.get("when"), ctx) or not self.state.once(f"event:{eid}:{w['name']}"):
                continue
            results.append({"workflow": w["name"], "results": self.run_actions(w["name"], w.get("do", []), ctx)})
        return {"event": name, "matched": len(results), "workflows": results}

    def _events(self, start, end):
        """Events from every connected calendar (Google and/or Microsoft 365), oldest first. A broken calendar is logged and skipped."""
        out = []
        for name, cal in (("google", self.gcal), ("outlook", self.outlook)):
            if cal.configured:
                try:
                    out += cal.events(start, end)
                except Exception as e:  # noqa: BLE001
                    self.state.log(workflow="calendar", status="error", calendar=name, error=str(e)[:200])
        return sorted(out, key=lambda e: e["start"])

    def poll_email(self):
        """New customer emails -> workflows with on.email.keywords. The sender wrote to us first, so answering them is allowed. Returns how many workflows ran."""
        ran = 0
        if self.imap_factory:
            self.inbox.factory = self.imap_factory
        for m in self.inbox.fetch():
            low = (m["subject"] + " " + m["body"]).lower()
            if not self.state.once("mail:" + (m["message_id"] or m["from"] + m["subject"])):
                continue
            for w in self.workflows:
                kw = self._triggers((w.get("on") or {}).get("email"))
                if (w.get("on") or {}).get("email") is not None and (not kw or any(i18n.matches(k, low, self.lang) for k in kw)):
                    ctx = self.ctx(email=m, customer={"email": m["from"], "sms_consent": True})
                    self.run_actions(w["name"], w.get("do", []), ctx); ran += 1
                    break
        return ran

    def calendar_contact(self, ev):
        cc = self.cfg["google_calendar"]
        text = f"{ev.get('title','')}\n{ev.get('description','')}"
        m = PHONE_RX.search(text)
        name = re.search(r"(?:name|for)\s*[:\-]\s*([^\n,]+)", text, re.I)
        rx = cc.get("consent_regex") or r"(?:sms|text)\s*ok\s*[:=]\s*(?:yes|true|1|sí|si|oui|sim|sì|ja|kyllä|हाँ|はい|是|نعم|예|네|да|evet|có|tak|ya)|consent\s*[:=]\s*(?:yes|true)"       # 'SMS OK: yes' in the event notes; 'SMS OK: False' is NOT consent
        return {"name": (name.group(1).strip() if name else ev.get("title", "")), "phone": S.norm_phone(m.group(1)) if m else "", "sms_consent": bool(re.search(rx, text.lower()))}

    def tick(self):
        """Call about once a minute: queued actions, calendar reminders and daily schedules."""
        self.flush_outbox()
        if self.inbox.configured:
            self.poll_email()
        if not (self.gcal.configured or self.outlook.configured or any((w.get("on") or {}).get("schedule") for w in self.workflows)):
            return []
        out, now = [], self.now()
        cal_wfs = [w for w in self.workflows if (w.get("on") or {}).get("calendar")]
        if cal_wfs and (self.gcal.configured or self.outlook.configured):
            horizon = max(int(x) for w in cal_wfs for x in [(w["on"]["calendar"].get("starts_in_minutes", 60))]) + 60
            events = self._events(now - 600, now + horizon * 60)
            for ev in events:
                for w in cal_wfs:
                    c = w["on"]["calendar"]; mins = (ev["start"] - now) / 60
                    lead, win = int(c.get("starts_in_minutes", 60)), int(c.get("window_minutes", 10))
                    if not (lead - win <= mins <= lead) or (c.get("title_contains") and c["title_contains"].lower() not in ev["title"].lower()):
                        continue
                    ctx = self.ctx(event=ev, customer=self.calendar_contact(ev), start_local=i18n.fmt_dt(ev["start"], self.cfg["timezone"], self.lang))
                    if self._when_ok(w.get("when"), ctx) and self.state.once(f"cal:{ev['id']}:{w['name']}:{lead}"):
                        out.append({"workflow": w["name"], "event": ev["title"], "results": self.run_actions(w["name"], w.get("do", []), ctx)})
        local = dt.datetime.fromtimestamp(now, ZoneInfo(self.cfg["timezone"]))
        for w in [w for w in self.workflows if (w.get("on") or {}).get("schedule")]:
            sc = w["on"]["schedule"]
            if local.strftime("%H:%M") >= sc.get("at", "09:00") and DAYS[local.weekday()] in sc.get("days", DAYS) and self.state.once(f"sched:{w['name']}:{local.date()}"):
                events = self._events(now, now + 86400)
                ctx = self.ctx(today=[{"title": e["title"], "time": i18n.fmt_dt(e["start"], self.cfg["timezone"], self.lang)} for e in events],
                               today_text="\n".join(f"{i18n.fmt_dt(e['start'], self.cfg['timezone'], self.lang)} {e['title']}" for e in events) or "-")
                out.append({"workflow": w["name"], "results": self.run_actions(w["name"], w.get("do", []), ctx)})
        return out

    def _triggers(self, spec):
        """Words that start a text/email workflow: explicit 'keywords' plus the 'topic' words (English + this pack's language + your own in agent.json 'keywords')."""
        return [k.lower() for k in (spec or {}).get("keywords", [])] + [k.lower() for k in (i18n.keywords(spec["topic"], self.lang, self.cfg.get("keywords")) if spec and spec.get("topic") else [])]

    def handle_delivery(self, params):
        """Twilio's status callback for a text or call we sent. A text Twilio accepted can still be refused by the carrier (for example error 30034, US numbers not yet registered for business texting): log what really happened."""
        sid = params.get("MessageSid") or params.get("CallSid") or ""
        kind = "sms" if params.get("MessageSid") else "call"
        st = (params.get("MessageStatus") or params.get("CallStatus") or "").lower()
        final = {"delivered": "delivered", "undelivered": "undelivered", "failed": "undelivered", "completed": "delivered", "busy": "undelivered", "no-answer": "undelivered", "canceled": "undelivered"}
        if st in final:
            extra = {"error_code": params["ErrorCode"]} if params.get("ErrorCode") else {}
            self.record("delivery", kind, final[st], sid=sid, provider_status=st, to=params.get("To", ""), **extra)
        return {"ok": True}

    def handle_sms(self, params):
        """An inbound text from Twilio. Returns the reply text ('' = no reply). STOP / START / HELP (and the opt-out words of the pack's language) are handled first, as carriers require."""
        who, body = S.norm_phone(params.get("From", "")), (params.get("Body") or "").strip()
        low = body.lower()
        if low in i18n.opt_out_words(self.lang):
            self.state.opt_out(who); self.state.log(workflow="sms", status="opt_out", to=who)
            try:
                return self.pack.text("opt_out_ack")
            except PackError:
                return "You have been unsubscribed and will not receive more messages."
        if low in ("start", "unstop", "yes"):
            self.state.opt_in(who); return "You are subscribed again. Reply STOP to unsubscribe."
        if low == "help":
            return self.cfg.get("help_text") or i18n.glue("help", self.lang)
        for w in self.workflows:
            kw = self._triggers((w.get("on") or {}).get("sms"))
            if kw and any(i18n.matches(k, low, self.lang) for k in kw):
                ctx = self.ctx(sms={"from": who, "body": body}, customer={"phone": who, "sms_consent": True})   # they texted us first: replying is always allowed
                out = {"reply": "", "play": []}
                self.run_actions(w["name"], w.get("do", []), ctx, out)
                if not out["reply"]:
                    return ""
                reply = self._sms_text(out["reply"], who); self.state.once(f"footer:{who}"); return reply
        return ""

    def sms_via_provider(self, frm, body):
        """A text that arrived through a source mapping (any provider's webhook, not Twilio): answer it with the configured sms provider."""
        who = S.norm_phone(frm); reply = self.handle_sms({"From": who, "Body": body or ""})
        if reply:
            self.run_actions("inbound_sms", [{"action": "sms", "to": who, "text": reply, "raw": True}], self.ctx(customer={"sms_consent": True}))
        return reply

    def handle_call(self, params, step="start", digits=""):
        """An inbound call from Twilio -> TwiML. The workflow with on.call.menu plays a prompt, then runs the actions of the pressed digit."""
        wf = next((w for w in self.workflows if (w.get("on") or {}).get("call")), None)
        if not wf:
            return twiml_message("Sorry, nobody is available to take your call.").replace("<Message>", "<Say>").replace("</Message>", "</Say>")
        menu = wf["on"]["call"]["menu"]; base = self.cfg.get("public_base_url", "")
        ctx = self.ctx(call={"from": S.norm_phone(params.get("From", ""))}, customer={"phone": S.norm_phone(params.get("From", "")), "sms_consent": True})
        if step == "start":
            urls = []
            try:
                urls = [self.audio.url(self.pack.resolve(menu["prompt"])["id"])]
            except (PackError, AudioError):
                pass
            pre = [self._line_part(x) for x in self._required("menu")]
            return twiml_menu(urls, f"{base}/twilio/call/menu", T.render(menu.get("fallback_say", "Press 1 for hours, 0 for a person."), ctx, self.pack), pre=pre)
        opt = (menu.get("options") or {}).get(digits)
        if not opt:
            return twiml_menu([], f"{base}/twilio/call/menu", "Sorry, that was not an option. Please try again.")
        out = {"reply": "", "play": []}
        self.run_actions(wf["name"], opt, ctx, out)
        urls = []
        for ref in out["play"]:
            try:
                urls.append(self.audio.url(ref))
            except (PackError, AudioError):
                pass
        xml = twiml_play(urls, then_hangup=False)[:-len("</Response>")] if urls else "<Response>"
        if out["reply"]:
            from xml.sax.saxutils import escape
            xml += f"<Say>{escape(out['reply'])}</Say>"
        return xml + "<Hangup/></Response>"

    def handle_slack_command(self, form):
        cmd, text = form.get("command", ""), (form.get("text") or "").strip()
        for w in self.workflows:
            if (w.get("on") or {}).get("slack_command") == cmd:
                parts = text.split()
                ctx = self.ctx(command={"text": text, "arg1": parts[0] if parts else "", "arg2": parts[1] if len(parts) > 1 else "", "rest": " ".join(parts[2:]), "user": form.get("user_name", "")},
                               customer={"phone": S.norm_phone(parts[1]) if len(parts) > 1 else "", "sms_consent": True})
                out = {"reply": "", "play": []}
                self.run_actions(w["name"], w.get("do", []), ctx, out)
                return {"response_type": "ephemeral", "text": out["reply"] or "Done."}
        return {"response_type": "ephemeral", "text": f"No workflow handles {cmd}."}
