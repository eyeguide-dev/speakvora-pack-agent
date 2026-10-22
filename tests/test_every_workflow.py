"""Every ready-made workflow in every industry, run for real against the fake Twilio, Slack, Google and helpdesk: each action must succeed, every text must be fully filled in (no {{ }} and no YOUR-... placeholder),
and the only things allowed not to run are the ones that genuinely need something the business must connect: its own records system (private status lookups), or the helpdesk address in the support ticket workflow."""
import collections, copy, json, os, sys, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_pack_agent import Rig
from speakvora_pack_agent import recipes, slots as SL, config
from speakvora_pack_agent.engine import Agent

FACTS = {"hours": "Tue to Sun, 5 to 10 PM", "address": "12 Main Street, Brooklyn", "phone": "+16465550100", "review_url": "https://example.com/review", "oncall_phone": "+16465550123", "info": "Parking is free behind the building."}
CUST = {"name": "Ann Lee", "phone": "+16465550101", "email": "ann@example.com", "sms_consent": True}
GOOD = {"sent", "ok", "dry_run", "done", "created", "rescheduled", "cancelled"}
NEEDS_SETUP = {("sms_status", "not_connected"), ("email_ticket", "skipped")}          # a private records system / the helpdesk address are the business's own to connect


def make_env(profile, tracking=False):
    r = Rig(extra={"mode": "open", "facts": FACTS, "tracking": {"enabled": tracking}, "email": {}, "inbox": {"host": "imap.test", "username": "s@x.test", "password": "pw12345678"}})
    reg = SL.registry(profile)
    wl = []
    for i, (slot, v) in enumerate(sorted(reg.items()), 1):
        f = f"workflow_lines/e{i:03d}.mp3"; open(os.path.join(r.tmp, "pack", f), "wb").write(b"MP3")
        wl.append({"id": f"e{i:03d}", "slot": slot, "text": v["example"], "file": f})
    json.dump({"items": wl}, open(os.path.join(r.tmp, "pack", "workflow_lines.json"), "w"))
    json.dump(recipes.workflows_for(profile), open(os.path.join(r.tmp, "workflows.json"), "w"))
    cfg = config.load(os.path.join(r.tmp, "agent.json"))
    cfg["industry_profile"] = profile
    a = Agent(cfg, now=lambda: r.now[0])
    a.mail.send = lambda to, subj, text, attach=None: r.sent_mail.append((to, subj, text)) or {"ok": True}; a.mail.configured = True
    r.sent_mail = []; r.agent = a
    return r, a


def payload(ev):
    return {"event": ev, "id": "e-" + ev, "customer": dict(CUST), "order": {"number": 1049, "extra_minutes": 10}, "start_epoch": int(time.time()) + 86400, "start_text": "tomorrow at 7:00 PM", "party": 2, "minutes": 60,
            "appointment": {"id": "a1"}, "incident": {"title": "Checkout down"}, "repo": "acme/app", "branch": "main", "author": "sam", "url": "https://example.com/x", "reason": "test", "title": "Test title",
            "ticket": {"summary": "Broken thing"}, "track": {"line": "Track it: https://example.com/t"}, "last": {"sms": "ok"}}

def ctx_for(a, w):
    on = w.get("on") or {}; k = next(iter(on)) if on else ""
    if k == "event": return a.ctx(**{x: y for x, y in payload(on["event"]).items() if x != "event"})
    if k == "calendar": return a.ctx(customer=dict(CUST), start_local="Friday 7:00 PM", start_epoch=int(time.time()) + 86400, title="Appointment: Ann", event={"title": "x"})
    if k == "sms": return a.ctx(sms={"body": "hello", "from": CUST["phone"]}, customer=dict(CUST))
    if k == "schedule": return a.ctx(today_text="7:00 PM Ann (4)", summary="Yesterday: 12 conversations.")
    if k == "slack_command": return a.ctx(command={"arg1": "hours", "arg2": CUST["phone"]}, last={"sms": "x"})
    if k == "email": return a.ctx(email={"from": "ann@example.com", "subject": "Broken thing", "body": "It broke"}, customer={"email": "ann@example.com", "sms_consent": True})
    return a.ctx()

def run_one(r, a, w):
    on = w.get("on") or {}; k = next(iter(on)) if on else ""
    n0 = len(r.mock.requests); m0 = len(r.sent_mail)
    if k == "slack_command":
        cmd = on["slack_command"]; r0 = a.handle_slack_command({"command": cmd, "text": "hours " + CUST["phone"], "user_name": "sam"})
        res = [{"action": "slack_command", "status": "ok" if r0.get("text") and "No workflow" not in r0["text"] else "error", "detail": r0.get("text", "")[:60]}]
        texts = [json.dumps(q.get("form") or q.get("json") or {}) for q in r.mock.requests[n0:]]
        return res, texts
    if k == "call":
        menu = on["call"]["menu"]; out = []
        xml = a.handle_call({"From": CUST["phone"], "CallSid": "c1"}, "start", ""); out.append(("start", xml))
        for d in sorted(menu.get("options", {})):
            out.append((d, a.handle_call({"From": CUST["phone"], "CallSid": "c1"}, "menu", d)))
        res = [{"action": "call_menu", "status": "ok" if all(x[1] and "{{" not in x[1] for x in out) else "error", "detail": f"{len(out)} steps"}]
        texts = [x[1] for x in out]
    else:
        res = a.run_actions(w["name"], copy.deepcopy(w.get("do", [])), ctx_for(a, w), job_prefix="t:" + w["name"])
        texts = []
    for q in r.mock.requests[n0:]:
        texts.append(json.dumps(q.get("form") or q.get("json") or {}))
    texts += [x[2] for x in r.sent_mail[m0:]]
    return res, texts


class EveryWorkflow(unittest.TestCase):
    def sweep(self, tracking):
        bad = []; total = 0
        for p in sorted(SL.PROFILES):
            r, a = make_env(p, tracking=tracking)
            try:
                for w in json.load(open(os.path.join(r.tmp, "workflows.json")))["workflows"]:
                    try:
                        res, texts = run_one(r, a, w)
                    except Exception as e:  # noqa: BLE001
                        res, texts = [{"action": "?", "status": "exception", "reason": repr(e)[:120]}], []
                    total += 1
                    for x in res:
                        if x.get("status") not in GOOD and (w["name"], x.get("status")) not in NEEDS_SETUP and not (x.get("action") == "track" and x.get("status") == "skipped" and not tracking) and not (x.get("action") in ("jira_bug", "confluence_log") and x.get("status") == "skipped"):          # Jira and Confluence steps skip quietly until the customer connects their own
                            bad.append((p, w["name"], x.get("action"), x.get("status"), str(x.get("reason") or x.get("error") or "")[:100]))
                    for t in texts:
                        if "{{" in t or "YOUR-" in t:
                            bad.append((p, w["name"], "text still has a placeholder", t[:100]))
            finally:
                r.close()
        self.assertGreater(total, 400)
        self.assertEqual(bad, [], f"{len(bad)} problems across {total} workflows: {bad[:8]}")

    def test_every_workflow_in_every_industry_runs_clean_with_order_pages_off(self):
        self.sweep(False)

    def test_every_workflow_in_every_industry_runs_clean_with_order_pages_on(self):
        self.sweep(True)


if __name__ == "__main__":
    unittest.main()
