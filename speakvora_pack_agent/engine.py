"""The agent: receives triggers (an event from your app, a calendar tick, an inbound text or call, a Slack command, a daily schedule), picks the matching workflows from workflows.json, and runs their actions through the connectors,
always through the safety checks first. Dry-run (the default) records what it WOULD do and sends nothing."""
import datetime as dt, http.client, json, os, re, smtplib, ssl, threading, time
from zoneinfo import ZoneInfo

from . import i18n, reasoner as R, safety as S, slots as slots_mod, templating as T
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
QUEUEABLE = ("sms", "call", "slack", "teams", "email", "webhook", "http", "calendar_create", "reason")       # actions that wait in the outbox when the network is down
KEEP_WHILE_BLOCKED = ("quiet_hours", "hourly_limit", "recipient_daily_limit")                      # a queued action blocked only by timing waits (until it expires); any other refusal drops it
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class Agent:
    def __init__(self, cfg, now=time.time):
        self.cfg, self.now = cfg, now
        self.pack = Pack(cfg["pack"])
        self.state = State(cfg["state_dir"], now)
        self.safe = S.Safety(cfg, self.state, now)
        self.audio = AudioStore(self.pack, cfg["state_dir"], cfg.get("public_base_url", ""))
        from . import learned
        learned.attach(self)                                                     # lines learned from your AI's repeated replies
        self.imap_factory = None
        self._init_services()
        wf = self._load_workflows()
        for name, spec in (wf.get("slots") or {}).items():                    # optional overrides: slot name -> a specific phrase
            try:
                self.pack.slots[name] = self.pack.resolve(spec)["id"]
            except PackError:
                pass
        self.dry = bool(cfg.get("dry_run", True)) and not self.state.data.get("live", False)      # the dashboard's "go live" switch is remembered here
        self._flush_lock = threading.Lock()
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

    def _init_services(self):
        cfg = self.cfg
        self.twilio, self.slack, self.gcal, self.mail = Twilio(cfg["twilio"]), Slack(cfg["slack"]), GoogleCalendar(cfg["google_calendar"]), Email(cfg["email"])
        self.teams, self.outlook, self.inbox = Teams(cfg.get("teams", {})), OutlookCalendar(cfg.get("microsoft_calendar", {})), Inbox(cfg.get("inbox", {}))
        self.sms_provider, self.call_provider = HttpProvider(cfg.get("sms_provider")), HttpProvider(cfg.get("call_provider"))
        base = str(cfg.get("public_base_url", "")).rstrip("/")
        self.twilio.status_url = base + "/twilio/status" if base.startswith("https://") and "YOUR-" not in base else ""     # Twilio tells us later whether a text or call really arrived

    def _load_workflows(self):
        wf = json.load(open(self.cfg["workflows"], encoding="utf-8")) if self.cfg.get("workflows") else {}
        self.workflows = [w for w in wf.get("workflows", []) if w.get("enabled", True)]
        return wf

    def reload(self, new_cfg):
        """Applies a changed agent.json / secrets / workflows without a restart (the dashboard's Save). The same cfg object is updated in place because the web server holds a reference to it."""
        keep = {k: self.cfg[k] for k in ("dry_run",) if k in self.cfg}
        self.cfg.clear(); self.cfg.update(new_cfg); self.cfg.update(keep)
        self._init_services(); self._load_workflows()
        oc = str((self.cfg.get("facts") or {}).get("oncall_phone", ""))
        if oc and "YOUR-" not in oc and oc not in (self.cfg.setdefault("recipients", {}).setdefault("allow", [])):
            self.cfg["recipients"]["allow"].append(oc)

    def set_live(self, on):
        """Sending for real (True) or practice mode (False), remembered across restarts."""
        self.state.data["live"] = bool(on)
        with self.state.lock:
            self.state.save()
        self.cfg["dry_run"] = not on; self.dry = not on

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
    def run_actions(self, wf_name, actions, ctx, out=None, job_prefix=None):
        """Runs actions in order. `out` collects what an inbound text / call / Slack command should answer with: out['reply'], out['play'] (pack lines to play)."""
        out = out if out is not None else {"reply": "", "play": []}
        results = []
        for idx, a in enumerate(actions):
            kind = a.get("action")
            if a.get("each_step") and self._tracking_on() and not (self.cfg.get("tracking") or {}).get("text_each_step"):         # with order pages on, the customer gets one text with their link and the page shows the rest; without them every step is texted as before
                continue
            if a.get("if") and not self._when_ok(a["if"], ctx):                  # per-action condition, e.g. {"if": {"customer.prefers_call": "*"}}
                continue
            try:
                if kind == "http" and not a.get("connection") and not re.match(r"^https?://[^/{}?#\s]+", str(a.get("url", ""))):
                    raise PackError("An http action must write the server address literally (https://host/...). Only the path, query and body may use {{...}} values.")
                a = self._render_reason(a, ctx) if kind == "reason" else T.render_obj({k: v for k, v in a.items() if k != "if"}, ctx, self.pack)
                if "YOUR-" in json.dumps(a):                                  # an example value from the sample config: never send it to a customer
                    raise PackError("Fill in the YOUR-... values in agent.json (for example the review link) before this can be sent.")
                jid = f"{job_prefix}:{idx}" if job_prefix else None; ctx["_jid"] = jid or ""
                r = self._do(wf_name, kind, a, ctx, out, jid)
                ctx.setdefault("last", {})[kind] = r.get("status", "")      # later actions can say what really happened: {{last.sms}}
                results.append({"action": kind, **r})
            except (PackError, AudioError, PermissionError) as e:
                ctx.setdefault("last", {})[kind] = "skipped"
                self.record(wf_name, kind, "skipped", reason=str(e)); results.append({"action": kind, "status": "skipped", "reason": str(e)})
            except Exception as e:  # noqa: BLE001 - one failing service must never stop the others or the app
                ctx.setdefault("last", {})[kind] = "error"
                self.record(wf_name, kind, "error", error=type(e).__name__ + ": " + str(e)[:200]); results.append({"action": kind, "status": "error", "error": str(e)[:200]})
        if not wf_name.endswith("/mirror"):
            try:
                self._mirror(wf_name, ctx, results, job_prefix)
            except Exception as e:  # noqa: BLE001 - a broken connection never stops the workflow
                self.record(wf_name, "mirror", "error", error=str(e)[:200])
        return results

    def _tracking_on(self):
        """Order pages are optional: a business switches them on in the dashboard (Connect, Order pages). Off, order events simply text the customer at each step."""
        return bool((self.cfg.get("tracking") or {}).get("enabled"))

    def _render_reason(self, a, ctx):
        """Like normal rendering, but {{path}} on its own resolves to the real value (a list, a record) so a workflow can hand the model structured data it fetched."""
        def val(o):
            if isinstance(o, str):
                m = re.fullmatch(r"\{\{\s*([\w.:\-]+)\s*\}\}", o)
                if m and not m.group(1).startswith(("slot:", "slotvar:", "t:", "fact:")):
                    v = T.lookup(ctx, m.group(1)); return "" if v is None else v
                return T.render(o, ctx, self.pack)
            if isinstance(o, dict):
                return {k: val(v) for k, v in o.items()}
            if isinstance(o, list):
                return [val(v) for v in o]
            return o
        return {k: val(v) for k, v in a.items() if k != "if"}

    def _lookup(self, wf, a, ctx, out):
        """Asks the business's own records system about the person who texted or called, and passes the answer on ONLY to a number that system lists as allowed (the patient or their caregiver). The answer comes from that system word for word (the AI never writes it), is sent to the asking number only,
        and is not kept: a text reply goes straight back in the answer to the incoming message, and a text sent for a phone call is cleared from the job record as soon as it is sent. Without a connected system, or when the number is not allowed, the person is told to contact staff."""
        phone = S.norm_phone((ctx.get("customer") or {}).get("phone", ""))
        def fallback(why):
            try:
                out["reply"] = self.pack.text(a.get("fallback_slot") or "handoff_received")
            except PackError:
                out["reply"] = "Please contact our staff and they will help you."
            self.record(wf, "lookup", why); return {"status": why}
        try:
            c = self._with_connection({"connection": a.get("connection") or "records", "method": "POST"})
        except PackError:
            return fallback("not_connected")
        from . import controls
        if not controls.private_lookups_ready(self):                              # private records stay off until the settings that make them safe are approved; no request is made
            return fallback("policy_not_approved")
        if self.dry:
            self.record(wf, "lookup", "dry_run"); out["reply"] = "(practice mode) A lookup would be made in your records system."; return {"status": "dry_run"}
        try:
            st, resp = web.request("POST", c["url"], c.get("headers") or {}, body={"phone": phone, "text": str((ctx.get("sms") or {}).get("body", ""))[:300], "channel": "text" if ctx.get("sms") else "call"}, timeout=10)
        except Exception:  # noqa: BLE001
            return fallback("system_unreachable")
        allowed = {S.norm_phone(x) for x in (resp.get("allowed_phones") or [])} if isinstance(resp, dict) else set()
        msg = str(resp.get("message") or "").strip()[:600] if isinstance(resp, dict) else ""
        if not (isinstance(resp, dict) and resp.get("found") and resp.get("verified") is True and msg and phone and phone in allowed):      # the records system must have verified who is asking (caller ID alone never counts) and list this number as allowed
            return fallback("not_authorised")
        if a.get("deliver") == "sms":                                             # a phone call never speaks health details aloud: they are texted to the number on file
            self.run_actions(wf, [{"action": "sms", "to": phone, "text": msg, "raw": True, "sensitive": True}], dict(ctx, customer={"phone": phone, "sms_consent": True}))
            from . import privacy
            privacy.clear_sensitive(self)
            out["reply"] = "I have sent the details by text to the number we have on file."
        else:
            out["reply"] = msg
        self.record(wf, "lookup", "answered", channel=a.get("deliver") or "reply"); return {"status": "answered"}

    def _with_connection(self, a):
        """An http action that names one of the connections set up in the dashboard ("connection": "my-app") uses its address and key, so the workflow never contains the key."""
        c = next((x for x in (self.cfg.get("connections") or []) if x.get("id") == a["connection"]), None)
        if not c or not str(c.get("url", "")).startswith(("https://", "http://")):
            raise PackError(f"The connection '{a['connection']}' is not set up yet: add it in the dashboard's Connect tab.")
        a = {k: v for k, v in a.items() if k not in ("connection", "path")}
        base = str(c["url"]); a["url"] = base.rstrip("/") + "/" + str(a_path).lstrip("/") if (a_path := a.get("path")) else base
        h = dict(a.get("headers") or {}); au = c.get("auth") or {}; sec = au.get("secret") or ""
        if sec and "YOUR-" not in sec and not str(sec).startswith("env:"):
            if au.get("type") == "bearer":
                h["Authorization"] = "Bearer " + sec
            elif au.get("type") == "header" and au.get("header"):
                h[au["header"]] = sec
            elif au.get("type") == "basic":
                import base64 as _b; h["Authorization"] = "Basic " + _b.b64encode(sec.encode()).decode()
        a["headers"] = h
        return a

    def _mirror(self, wf_name, ctx, results, job_prefix):
        """A workflow can also tell your own apps what it did (workflows.json: "also_send_to": ["my-app"]): one JSON post per connection, journaled like any other send."""
        w = next((x for x in self.workflows if x["name"] == wf_name), None)
        for cid in ((w or {}).get("also_send_to") or []):
            payload = {"source": "speakvora-pack-agent", "workflow": wf_name, "at": int(self.now()), "results": [{"action": r.get("action"), "status": r.get("status")} for r in results],
                       **{k: ctx[k] for k in ("event", "customer", "order", "appointment", "party", "command", "sms", "call", "email") if k in ctx}}
            self.run_actions(wf_name + "/mirror", [{"action": "http", "connection": cid, "method": "POST", "json": json.loads(json.dumps(payload, default=str))}], self.ctx(), job_prefix=(f"{job_prefix}:mirror:{cid}" if job_prefix else None))

    def _gate(self, wf, kind, to, ctx, urgent=False):
        ok, why = self.safe.check(kind, to, ctx, urgent)
        if not ok:
            self.record(wf, kind, "blocked", to=to, reason=why)
            return {"status": "blocked", "reason": why}
        return None

    # ---- ask-or-auto: what the person chose (kept in agent-state). Keys are "<workflow>:<action>"; "ask_before" is the list of action kinds that always wait for a click. -----------------------------
    def policy(self):
        p = self.state.data.get("policy") or {}
        return {"ask_before": list(p.get("ask_before") or []), "decisions": dict(p.get("decisions") or {})}

    def set_policy(self, ask_before=None, decision=None, reset=None):
        with self.state.lock:
            p = self.state.data.setdefault("policy", {"ask_before": [], "decisions": {}}); p.setdefault("decisions", {}); p.setdefault("ask_before", [])
            if ask_before is not None:
                p["ask_before"] = [k for k in ask_before if k in ("sms", "call", "email", "slack", "teams", "http", "calendar_create")]
            if decision:
                p["decisions"][decision[0]] = decision[1] if decision[1] in ("auto", "never", "ask") else "ask"
                if p["decisions"][decision[0]] == "ask":
                    p["decisions"].pop(decision[0], None)
            if reset:
                p["decisions"].pop(reset, None)
            self.state.save()
        return self.policy()

    def _decision(self, wf, kind):
        return self.policy()["decisions"].get(f"{wf}:{kind}")

    def _journaled(self, kind, a):
        """Actions that leave this machine and cannot be taken back are written to the job journal before they are sent. Replies, audio picks, log lines and read-only API calls (GET) are not."""
        return kind in QUEUEABLE and not (kind == "http" and str(a.get("method", "POST")).upper() == "GET")

    def _queue_on(self):
        return bool((self.cfg.get("queue") or {}).get("enabled", True))

    def _do(self, wf, kind, a, ctx, out, jid=None):
        """Runs one action through the job journal: written down first (pending), marked sending just before the network call, then sent / queued (offline) / needs_review (cannot know) / failed / blocked.
        With a job id from an earlier run (after a restart) an action that already has a job is never started again."""
        if self.dry or not self._journaled(kind, a):
            return self._do_now(wf, kind, a, ctx, out)
        jid = jid or self.state.new_job_id(); old = self.state.job_get(jid)
        if old:
            if old["status"] == "sending":
                self.state.job_set(jid, "needs_review", "agent stopped while sending: check with the provider before sending again"); return {"status": "needs_review", "job": jid}
            return {"status": "queued" if old["status"] in ("pending", "queued") else old["status"], "job": jid, "resumed": True}
        d = self._decision(wf, kind)
        if not ctx.get("_approved") and kind != "reason":
            if d == "never":
                self.state.job_create(jid, wf, kind, a, {"customer": ctx.get("customer") or {}}, "cancelled"); self.record(wf, kind, "declined_by_rule", job=jid); return {"status": "cancelled", "job": jid}
            if d != "auto" and kind in self.policy()["ask_before"]:
                self.state.job_create(jid, wf, kind, a, {"customer": ctx.get("customer") or {}}, "needs_approval"); self.record(wf, kind, "needs_approval", job=jid); return {"status": "needs_approval", "job": jid}
        self.state.job_create(jid, wf, kind, a, {"customer": ctx.get("customer") or {}}, "pending")
        return self._attempt(jid, wf, kind, a, ctx, out)

    def _attempt(self, jid, wf, kind, a, ctx, out):
        """One send of a journaled action. Never retries by itself: only a request that provably never left the machine goes back to the queue; anything uncertain waits for a person."""
        j = self.state.job_get(jid); self.state.job_set(jid, "sending", attempts=(j or {}).get("attempts", 0) + 1)
        ctx["_jid"] = jid
        try:
            r = self._do_now(wf, kind, a, ctx, out)
        except (PackError, AudioError, PermissionError) as e:
            self.state.job_set(jid, "failed", str(e)[:200], error=str(e)[:200]); raise
        except Exception as e:  # noqa: BLE001
            err = type(e).__name__ + ": " + str(e)[:200]
            if web.is_offline(e):
                if self._queue_on():
                    self.state.job_set(jid, "queued", "offline", error=err); self.record(wf, kind, "queued", queue_id=jid, reason="offline"); return {"status": "queued", "job": jid}
                self.state.job_set(jid, "failed", "offline and the queue is switched off", error=err); raise
            refused_by_smtp = isinstance(e, (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPConnectError))
            if kind == "reason":                                        # asking a model has no side effects, so a timeout is simply a failed attempt: safe to try again
                self.state.job_set(jid, "failed", err, error=err); return {"status": "failed", "job": jid, "error": err}
            uncertain = (isinstance(e, web.HttpError) and (e.status == 0 or e.status >= 500)) or (isinstance(e, (OSError, http.client.HTTPException, ssl.SSLError, smtplib.SMTPException)) and not refused_by_smtp)
            if uncertain:                                               # a timeout, a server error or a dropped connection: it may have arrived, so it is NEVER sent again by itself
                self.state.job_set(jid, "needs_review", err, error=err); self.record(wf, kind, "needs_review", job=jid, error=err)
                return {"status": "needs_review", "job": jid, "error": err}
            self.state.job_set(jid, "failed", err, error=err); raise      # the provider refused it (4xx or an error answer): nothing was sent
        st = r.get("status")
        if st in ("proposed", "answered"):
            self.state.job_set(jid, st, (r["result"]["summary"] or "")[:150], result=r["result"], error="")
            if st == "proposed":
                self._after_proposal(jid, wf, a)
        elif st == "blocked":
            self.state.job_set(jid, "blocked", r.get("reason", ""), reason=r.get("reason", ""))
        elif st in ("sent", "ok", "created"):
            self.state.job_set(jid, "sent", "provider accepted it", provider_id=r.get("sid") or None, error="")
        else:
            self.state.job_set(jid, st or "sent")
        return {**r, "job": jid}

    def recover(self):
        """Call once at start-up. A job caught in 'sending' by a crash is NOT sent again (it may have gone out): it waits for a person as needs_review. Jobs that were written but never started are queued.
        Events accepted from your app but not finished are resumed: actions that already have a job are skipped, the rest run."""
        n = {"needs_review": 0, "queued": 0, "events": 0}
        for j in self.state.jobs("sending"):
            self.state.job_set(j["id"], "needs_review", "agent stopped while sending: check with the provider before sending again"); n["needs_review"] += 1
        for j in self.state.jobs("pending"):
            self.state.job_set(j["id"], "queued", "written but never started"); n["queued"] += 1
        for key, ev in self.state.events_running().items():
            w = next((w for w in self.workflows if w["name"] == ev["wf"]), None)
            if w:
                payload = ev["payload"]; ctx = self.ctx(**{k: v for k, v in payload.items() if k not in ("facts",)})
                self.run_actions(w["name"], w.get("do", []), ctx, job_prefix=key); n["events"] += 1
            self.state.event_done(key)
        return n

    # ---- people controlling jobs (CLI and dashboard) ------------------------------------------------------------------------------------------------
    def cancel_job(self, jid):
        """Stops a job that has not been sent, or dismisses one that failed or needs a look."""
        j = self.state.job_get(jid)
        if not j or j["status"] not in ("pending", "queued", "needs_review", "needs_approval", "failed", "expired", "undelivered"):
            raise PermissionError("Only a job that has not been sent, or one that failed or needs a look, can be cancelled.")
        self.state.job_set(jid, "cancelled", "cancelled by a person"); return self.state.job_get(jid)

    APPROVAL_MAX_HOURS = {"call": 1, "sms": 24, "email": 48}

    def approve_job(self, jid, remember=False):
        """A person says yes to an action that was waiting. It is sent now, through the same safety checks as everything else. remember=True makes this kind of action automatic from now on."""
        j = self.state.job_get(jid)
        if not j or j["status"] != "needs_approval":
            raise PermissionError("This is not waiting for approval.")
        if self.now() - j["created"] > self.APPROVAL_MAX_HOURS.get(j["kind"], 72) * 3600:
            self.state.job_set(jid, "expired", "too old to send now"); raise PermissionError("This is too old to send now, so it was dropped. The agent will ask again next time.")
        if remember:
            self.set_policy(decision=(f"{j['wf']}:{j['kind']}", "auto"))
        ctx = self.ctx(**(j.get("ctx") or {})); ctx["_approved"] = True
        self.state.job_set(jid, "pending", "approved by a person")
        out = {"reply": "", "play": []}
        try:
            return self._attempt(jid, j["wf"], j["kind"], j["a"], ctx, out)
        except (PackError, AudioError, PermissionError) as e:
            return {"status": "failed", "error": str(e)[:200]}

    def decline_job(self, jid, remember=False):
        j = self.state.job_get(jid)
        if not j or j["status"] != "needs_approval":
            raise PermissionError("This is not waiting for approval.")
        if remember:
            self.set_policy(decision=(f"{j['wf']}:{j['kind']}", "never"))
        self.state.job_set(jid, "cancelled", "declined by a person"); return self.state.job_get(jid)

    def retry_job(self, jid, confirm_not_sent=False):
        """Puts a failed, expired, cancelled or blocked job back in the queue (the safety checks run again when it is sent). A needs_review job may already have arrived, so it needs confirm_not_sent=True: you looked at the provider and it did not."""
        j = self.state.job_get(jid)
        if not j or j["status"] not in ("failed", "expired", "cancelled", "blocked", "needs_review"):
            raise PermissionError("Only a failed, expired, cancelled, blocked or needs_review job can be retried.")
        if j["status"] == "needs_review" and not confirm_not_sent:
            raise PermissionError("This job may already have been delivered. Check with the provider; if it did not arrive, retry with confirm_not_sent.")
        self.state.job_set(jid, "queued", "retried by a person"); return self.state.job_get(jid)

    def mark_job_sent(self, jid):
        j = self.state.job_get(jid)
        if not j or j["status"] != "needs_review":
            raise PermissionError("Only a needs_review job can be marked as sent.")
        self.state.job_set(jid, "sent", "marked as sent by a person after checking the provider"); return self.state.job_get(jid)

    # ---- proposals: what a reasoning step suggests. Nothing runs until a person approves it (or the workflow listed the action under auto_allow). ---------------------------------------------------
    def _after_proposal(self, jid, wf, a):
        j = self.state.job_get(jid); res = j["result"]
        wfn = self.state.job_get(jid)["wf"]
        for i, p in enumerate(res["proposals"]):                              # a saved "always" or "never" for this kind of proposal is applied at once
            if self._decision(wfn, p["action"]) == "never":
                self.state.update_proposal(jid, i, state="rejected")
        res = self.state.job_get(jid)["result"]
        auto = [i for i, p in enumerate(res["proposals"]) if p["state"] == "pending" and (p["action"] in (a.get("auto_allow") or []) or self._decision(wfn, p["action"]) == "auto")]
        if auto:
            self.execute_proposals(jid, auto)
        self._finish_proposals(jid)
        if a.get("notify"):                                                    # a short note to the team: what was found and that proposals wait in the dashboard
            n = sum(1 for p in self.state.job_get(jid)["result"]["proposals"] if p["state"] == "pending")
            txt = (res["summary"] or "Done.") + (f" {n} proposed action(s) wait for your approval in the dashboard." if n else "")
            self.run_actions(wf, [{"action": "slack", "channel": a["notify"], "text": txt}], self.ctx(), job_prefix=f"{jid}:notify")

    def _finish_proposals(self, jid):
        j = self.state.job_get(jid); ps = j["result"]["proposals"]
        if all(p["state"] != "pending" for p in ps):
            self.state.job_set(jid, "approved" if any(p["state"] in ("done", "failed", "approved") for p in ps) else "rejected", "all proposals decided")

    def execute_proposals(self, jid, indexes, remember=False):
        """Runs the chosen proposals as normal journaled sends (consent, STOP, quiet hours, limits and the kill switch apply). A proposal runs once: its job id is fixed, so approving twice sends nothing twice."""
        j = self.state.job_get(jid)
        if not j or j["kind"] != "reason" or j["status"] not in ("proposed", "approved"):
            raise PermissionError("Only a reasoning result that still has proposals waiting can be approved.")
        out = []
        for i in indexes:
            res = self.state.job_get(jid)["result"]
            if not (0 <= i < len(res["proposals"])) or res["proposals"][i]["state"] != "pending":
                continue
            p = res["proposals"][i]; k, args = p["action"], p["args"]
            contacts = {c["id"]: c for c in (j["a"].get("contacts") or []) if isinstance(c, dict)}
            c = contacts.get(args.get("contact", ""), {})
            consent = bool(c.get("sms_consent") or c.get("consent"))
            ctx = self.ctx(customer={"name": c.get("name", ""), "phone": c.get("phone", ""), "email": c.get("email", ""), "sms_consent": consent})
            if k == "sms":
                a2 = {"action": "sms", "to": c.get("phone", ""), "text": args["text"], "raw": False}
            elif k == "email":
                a2 = {"action": "email", "to": c.get("email", ""), "subject": args["subject"], "text": args["text"]}
            elif k in ("slack", "teams"):
                a2 = {"action": k, "channel": args["channel"], "text": args["text"]}
            elif k == "http":
                a2 = {"action": "http", "method": "POST", "url": args["url"], "json": args["json"]}
            else:
                a2 = {"action": "calendar_create", "title": args["title"], "start": args["start"], "minutes": args["minutes"]}
            if remember:
                self.set_policy(decision=(f"{j['wf']}:{k}", "auto"))
            from . import industry_rules
            bad = industry_rules.violation(self, args.get("text", "")) if k in ("sms", "email", "slack", "teams") else ""
            if bad and k in ("sms", "email"):                                              # an AI-written customer message that breaks the industry's rules is never sent
                self.state.update_proposal(jid, i, state="failed", status="blocked_by_industry_rule", reason=bad)
                out.append({"index": i, "state": "failed", "status": "blocked_by_industry_rule"}); continue
            ctx["_approved"] = True
            cj = f"{jid}:p{i}"
            try:
                r = self._do(j["wf"], k, a2, ctx, {"reply": "", "play": []}, cj)            # the model's text is sent as written: it is NOT run through templates
                state = "done" if r.get("status") in ("sent", "ok", "created", "queued", "dry_run") else "failed"
                if state == "done" and k in ("sms", "email") and not self.dry:
                    from . import learned
                    learned.observe(self, args["text"])
            except Exception as e:  # noqa: BLE001
                r, state = {"status": "failed", "error": str(e)[:200]}, "failed"
            self.state.update_proposal(jid, i, state=state, job=cj, status=r.get("status"))
            out.append({"index": i, "state": state, "status": r.get("status")})
        self._finish_proposals(jid)
        return out

    def reject_proposals(self, jid, indexes=None, remember=False):
        j = self.state.job_get(jid)
        if not j or j["kind"] != "reason" or j["status"] != "proposed":
            raise PermissionError("Only a reasoning result that still has proposals waiting can be rejected.")
        ps = j["result"]["proposals"]
        for i in (range(len(ps)) if indexes is None else indexes):
            if 0 <= i < len(ps) and ps[i]["state"] == "pending":
                self.state.update_proposal(jid, i, state="rejected")
                if remember:
                    self.set_policy(decision=(f"{j['wf']}:{ps[i]['action']}", "never"))
        self._finish_proposals(jid)
        return self.state.job_get(jid)

    def flush_outbox(self):
        """Sends the queued jobs, oldest first. Stops at the first one that still cannot leave (the connection is still down). Old jobs expire (queue.max_age_minutes): a reminder call 15 minutes late is worse than none.
        Timing blocks (quiet hours, limits) keep a job waiting; any other refusal ends it. The safety checks run again at send time."""
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
                if self.state.job_get(q["id"])["status"] != "queued":      # changed by a person meanwhile (cancelled...)
                    continue
                if now - q["queued_at"] > float(ages.get(kind, 1440)) * 60:
                    self.state.job_set(q["id"], "expired", "too old to send"); stats["expired"] += 1
                    self.record(q["wf"], kind, "expired", queue_id=q["id"], waited_s=int(now - q["queued_at"])); continue
                ctx = self.ctx(**(q.get("ctx") or {}))
                who = S.norm_phone(a.get("to")) if kind in ("sms", "call") else str(a.get("to", ""))
                ok, why = self.safe.check("webhook" if kind == "http" else kind, who, ctx, bool(a.get("urgent")))
                if not ok and why in KEEP_WHILE_BLOCKED:
                    stats["waiting"] += 1; continue
                try:
                    r = self._attempt(q["id"], q["wf"], kind, a, ctx, {"reply": "", "play": []})
                except Exception as e:  # noqa: BLE001
                    stats["dropped"] += 1
                    self.record(q["wf"], kind, "failed_from_queue", queue_id=q["id"], error=type(e).__name__ + ": " + str(e)[:200]); continue
                if r.get("status") == "queued":                              # offline again
                    stats["offline"] = True; stats["waiting"] += len(items) - items.index(q); break
                if r.get("status") == "blocked" or r.get("status") == "needs_review":
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
        if kind == "track":
            if not self._tracking_on():
                return {"status": "skipped"}                                              # no log noise, no link, and the texts below simply leave the link out
            from . import tracker
            o = ctx.get("order") or {}
            try:
                r = tracker.set_status(self, a.get("order") or o.get("number") or o.get("id"), str(a.get("status", "")), delivery=bool(a.get("delivery") or o.get("delivery") or str(o.get("type", "")).lower() == "delivery"), delayed=a.get("delayed"), eta=a.get("eta") if "eta" in a else o.get("eta"), flow=str(a.get("flow") or "order"))
            except ValueError as ex:                                                  # for example no public address yet: say so and skip, never crash the workflow
                raise PackError(str(ex))
            try:
                intro = self.pack.text("track_intro")
            except PackError:
                intro = ""
            ctx["track"] = {"url": r["url"], "status": a.get("status"), "line": (intro + " " + r["url"]).strip()}          # {{track.line}} = a short invitation and the link, or nothing when order pages are off
            st = "dry_run" if self.dry else "ok"
            self.record(wf, kind, st, step=a.get("status"), order=str(a.get("order") or o.get("number") or o.get("id"))); return {"status": st}
        if kind == "lookup":
            return self._lookup(wf, a, ctx, out)
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
                r = self.sms_provider.send(to=to, text=text, media_url=media or "", _idem=ctx.get("_jid"))
            else:
                r = self.twilio.sms("whatsapp:" + to if wa else to, text, media, from_=("whatsapp:" + self.cfg["twilio"].get("whatsapp_from", self.twilio.from_number)) if wa else None, idem=ctx.get("_jid"))
            self.state.once(f"footer:{to}"); self.safe.sent("sms", to); self.record(wf, kind, "sent", to=to, sid=(r or {}).get("sid"), channel="whatsapp" if wa else "sms"); return {"status": "sent", "sid": (r or {}).get("sid")}
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
                res.append(self._do(wf, "slack", dict(a), ctx, out, (ctx.get("_jid") + ":slack") if ctx.get("_jid") else None)["status"])
            if self.teams.configured:
                res.append(self._do(wf, "teams", {"text": a["text"], "title": a.get("title")}, ctx, out, (ctx.get("_jid") + ":teams") if ctx.get("_jid") else None)["status"])
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
            r = self.call_provider.send(to=to, twiml=twiml, audio_urls=[v for k, v in parts if k == "play"], _idem=ctx.get("_jid")) if self.call_provider.configured else self.twilio.call(to, twiml, idem=ctx.get("_jid"))
            self.safe.sent("call", to); self.record(wf, kind, "sent", to=to, sid=(r or {}).get("sid")); return {"status": "sent", "sid": (r or {}).get("sid")}
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
        if kind == "http" and a.get("connection"):
            a = self._with_connection(a)
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
        if kind == "reason":
            if self.safe.killed():
                self.record(wf, kind, "blocked", reason="kill_switch"); return {"status": "blocked", "reason": "kill_switch"}
            rc = self.cfg.get("reasoner") or {}
            allow = [k for k in (a.get("allow") or []) if k in R.KINDS]; contacts = [c for c in (a.get("contacts") or []) if isinstance(c, dict) and c.get("id")]
            channels, hosts = [str(x) for x in (a.get("channels") or [])], [str(x) for x in (a.get("hosts") or [])]
            user = R.build_user(a.get("task", ""), a.get("inputs", ""), contacts, allow, channels, hosts, int(rc.get("max_input_chars", R.DEFAULT_MAX_CHARS)), rc.get("redact"))
            if self.dry:
                self.record(wf, kind, "dry_run", task=str(a.get("task", ""))[:120], would_send_chars=len(user)); return {"status": "dry_run"}
            self._need(rc.get("model") and (rc.get("api_key") or rc.get("base_url")), "Reasoning", "add the reasoner section (provider, model, api_key) in agent.json")
            if self.state.sent_since(3600, kind="reason") >= int(rc.get("max_per_hour", 20)):
                self.record(wf, kind, "blocked", reason="reason_limit"); return {"status": "blocked", "reason": "reason_limit"}
            from . import brain, industry_rules
            text, usage = R.ask(rc, brain.for_prompt(self) + industry_rules.prompt(self) + user)
            self.safe.sent("reason", "model")
            res = R.parse(text); kept, dropped = R.validate(res["proposals"], allow, contacts, channels, hosts)
            result = {"summary": res["summary"], "reasoning": res["reasoning"], "proposals": kept, "dropped": dropped, "sent_to_model": user[:4000], "sent_chars": len(user), "model": rc.get("model"), "usage": usage}
            self.record(wf, kind, "proposed" if kept else "answered", proposals=len(kept), dropped=len(dropped), sent_chars=len(user), model=rc.get("model"))
            return {"status": "proposed" if kept else "answered", "result": result}
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
            key = f"event:{eid}:{w['name']}"
            self.state.event_begin(key, payload, w["name"])                    # written down BEFORE the app gets its answer: a crash from here on resumes it
            results.append({"workflow": w["name"], "results": self.run_actions(w["name"], w.get("do", []), ctx, job_prefix=key)})
            self.state.event_done(key)
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
        from . import sharing
        from . import learned, privacy, tracker
        try:
            tracker.sync(self)                                                   # order pages Speakvora has not seen yet (offline earlier) are sent now
            from . import connect as _cn
            if _cn.tracking_needed(self) and tracker.mode(self) == "hosted" and sharing._key(self) and not tracker.pages_current(self) and (self.state.data.get("order_pages") or {}).get("preview_url"):
                tracker.push_business(self)                                      # a business detail changed here: update every page
        except Exception:  # noqa: BLE001
            pass
        privacy.scrub(self)                                                      # customer details are cleaned from finished jobs and old log lines after the days you chose
        learned.auto(self)                                                       # repeated AI lines become library lines, inside the monthly budget, if switched on
        sharing.auto(self)                                                       # missing phrases go to Speakvora once a day, if the person agreed
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
            job = self.state.job_by_provider_id(sid)
            if job:
                self.state.job_set(job["id"], final[st], f"provider status {st}" + (f", error {params['ErrorCode']}" if params.get("ErrorCode") else ""), **({"error": f"provider error {params['ErrorCode']}"} if params.get("ErrorCode") else {}))
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

    SPEECH_WORDS = {"1": ("hours", "open", "close", "closing", "address", "where", "location", "directions"), "2": ("book", "booking", "appointment", "schedule", "reschedule", "cancel", "quote", "estimate", "visit"),
                    "3": ("status", "order", "ready", "late", "update", "progress", "arrive")}

    def _speech_on(self):
        return bool((self.cfg.get("twilio") or {}).get("speech_input")) and self.pack.language == "en"

    def _speech_hints(self, menu):
        if not self._speech_on():
            return ""
        ws = menu.get("words") or self.SPEECH_WORDS
        return ", ".join(sorted({w for v in ws.values() for w in v} | {"person", "manager", "operator", "human"}))[:480]

    def _speech_choice(self, menu, said):
        """The menu option a caller's spoken words mean, or ''. Asking for a person always wins, so nobody is trapped in the menu."""
        said = str(said or "").strip()
        if not said or not self._speech_on():
            return ""
        from . import guardrails
        if guardrails.wants_human(self, said):
            return "0"
        words = set(re.findall(r"[a-z']+", said.lower()))
        for k, ws in (menu.get("words") or self.SPEECH_WORDS).items():
            if words & set(ws):
                return k
        return ""

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
            return twiml_menu(urls, f"{base}/twilio/call/menu", T.render(menu.get("fallback_say", "Press 1 for hours, 0 for a person."), ctx, self.pack), pre=pre, speech_hints=self._speech_hints(menu), no_input_url=f"{base}/twilio/call/menu")
        said = re.sub(r"[^a-z0-9' ]+", " ", str(params.get("SpeechResult", "")).lower()).strip()
        if said and os.environ.get("SV_DEBUG_SPEECH"):
            self.state.log(workflow=wf["name"], action="call_speech", status="heard", dry_run=False, step=step, heard=said[:80])         # test aid only: what the caller said, never on by default
        from . import controls
        guard = controls.guard_speech(said)
        if guard == "emergency":                                                   # an emergency is never queued or handled by a menu: say what to do and stop
            self.record(wf["name"], "emergency_redirect", "said")
            return "<Response><Say>If this is an emergency, hang up and call nine one one now. This line cannot send emergency help.</Say><Hangup/></Response>"
        if guard == "secret":                                                      # passwords, codes and card numbers are never taken on this line
            self.record(wf["name"], "secret_refused", "said")
            return twiml_menu([], f"{base}/twilio/call/menu2", "Please do not say passwords, codes or card numbers on this call. I cannot take them. Press 0 or say person for a team member, or press 1 for hours.", speech_hints=self._speech_hints(menu), no_input_url=f"{base}/twilio/call/menu3")
        bye = bool(re.search(r"\b(bye|goodbye|nope|nah|nothing|no thank you|no thanks|that's all|that is all|that's it|that is it|all done|all set|i'm good|im good|i am good)\b", said)) or said == "no"
        digits = (digits or "").strip() or self._speech_choice(menu, said)
        if bye and not digits and step == "menu":
            return "<Response><Say>Thanks for calling. Goodbye.</Say><Hangup/></Response>"
        if not digits or digits not in (menu.get("options") or {}):
            if step in ("menu2", "menu3") and "0" in (menu.get("options") or {}):         # a second miss: do not leave the caller stuck, connect them to a person
                digits = "0"
            else:
                return twiml_menu([], f"{base}/twilio/call/menu2", "Sorry, I did not catch that. " + T.render(menu.get("fallback_say", "Press 1 for hours, 0 for a person."), ctx, self.pack), speech_hints=self._speech_hints(menu), no_input_url=f"{base}/twilio/call/menu3")
        opt = (menu.get("options") or {}).get(digits)
        xfer = [a for a in opt if isinstance(a, dict) and a.get("action") == "transfer"]
        opt = [a for a in opt if not (isinstance(a, dict) and a.get("action") == "transfer")]
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
        if xfer:                                                                  # connect the caller to a person right now (the staff phone from agent.json facts.oncall_phone)
            from xml.sax.saxutils import escape, quoteattr
            to = S.norm_phone(T.render(str(xfer[0].get("to") or "{{fact:oncall_phone}}"), ctx, self.pack))
            if to and "YOUR-" not in to and len(to) >= 8:
                self.record(wf["name"], "transfer", "sent", to=to)
                return xml + f'<Dial timeout="25" answerOnBridge="true"><Number>{escape(to)}</Number></Dial><Say>{escape(xfer[0].get("say_if_busy") or "Sorry, nobody could pick up. We will call you back as soon as we can.")}</Say><Hangup/></Response>'
            self.record(wf["name"], "transfer", "skipped", reason="no staff phone number set (facts.oncall_phone)")
            xml += "<Say>Sorry, nobody is available to take your call right now. We will call you back as soon as we can.</Say>"
        if menu.get("again", True):                                               # after an answer, ask whether there is anything else; silence or "no" ends the call politely
            from xml.sax.saxutils import quoteattr
            hints = "no, no thanks, goodbye, hours, book, status, person" if self._speech_on() else ""
            mode = f' input="dtmf speech" speechTimeout="auto" bargeIn="true" hints={quoteattr(hints)}' if hints else ' input="dtmf"'
            return xml + f'<Gather{mode} numDigits="1" action={quoteattr(base + "/twilio/call/menu")} method="POST" timeout="6"><Say>Is there anything else I can help with? Press 1 for hours, 2 to book, 3 for a status, or 0 for a person.</Say></Gather><Say>Thanks for calling. Goodbye.</Say><Hangup/></Response>'
        return xml + "<Hangup/></Response>"

    def handle_slack_command(self, form):
        cmd, text = form.get("command", ""), (form.get("text") or "").strip()
        for w in self.workflows:
            if (w.get("on") or {}).get("slack_command") == cmd:
                parts = text.split()
                ctx = self.ctx(command={"text": text, "arg1": parts[0] if parts else "", "arg2": parts[1] if len(parts) > 1 else "", "rest": " ".join(parts[2:]), "user": form.get("user_name", "")},
                               customer={"phone": S.norm_phone(parts[1]) if len(parts) > 1 else "", "sms_consent": True})
                out = {"reply": "", "play": []}
                if any(x.get("action") == "reason" for x in w.get("do", [])):          # a model can take longer than Slack waits: answer now, work in the background
                    threading.Thread(target=self.run_actions, args=(w["name"], w.get("do", []), ctx, out), daemon=True).start()
                    return {"response_type": "ephemeral", "text": w.get("ack") or "On it. What I find will wait for your approval in the dashboard."}
                self.run_actions(w["name"], w.get("do", []), ctx, out)
                return {"response_type": "ephemeral", "text": out["reply"] or "Done."}
        return {"response_type": "ephemeral", "text": f"No workflow handles {cmd}."}
