import json, unittest
from test_pack_agent import Rig, CUST
from speakvora_pack_agent import eventflows as EF, simulate as SIM, connect as SU, builder as BD


def payload(ev, i):
    return {"event": ev, "id": f"t-{i}", "customer": CUST, "order": {"number": 1049}, "incident": {"title": "Checkout is down"}, "repo": "acme/app", "branch": "main", "url": "https://example.com/x", "author": "sam",
            "start_epoch": 1791907200, "start_text": "Friday 7:00 PM", "party": 2, "minutes": 60, "appointment": {"id": "a1"}, "issue": {"title": "Login bug"}, "pull_request": {"title": "Fix login"}, "release": {"name": "v2.1"}, "alert": {"title": "Leaked key"}}


class EveryEvent(unittest.TestCase):
    def test_every_event_in_the_list_has_a_working_ready_made_automation(self):
        for i, ev in enumerate(EF.SPECS):
            with self.subTest(event=ev):
                r = Rig(); a = r.agent
                try:
                    out = a.handle_event(payload(ev, i)); self.assertGreaterEqual(out["matched"], 1, ev)
                    log = r.log(); bad = [x for x in log if x.get("status") == "error"]; self.assertEqual(bad, [], ev)
                    kind = EF.SPECS[ev][2]
                    if kind in ("c", "b"):
                        self.assertTrue(r.mock.calls("Messages.json"), ev + ": the customer text was not sent")
                        text = str(r.mock.calls("Messages.json"))
                        self.assertNotIn("{{", text, ev)
                    if kind in ("t", "b", "j", "k"):
                        self.assertTrue(r.mock.calls("chat.postMessage"), ev + ": the team was not told")
                finally:
                    r.close()

    def test_a_customer_text_waits_for_consent_and_the_team_notice_does_not(self):
        r = Rig(); self.addCleanup(r.close)
        a = r.agent; out = a.handle_event({"event": "order.ready", "id": "n1", "customer": {"name": "Ann", "phone": "+16465550101", "sms_consent": False}, "order": {"number": 5}})
        self.assertEqual(r.mock.calls("Messages.json"), [])                                            # no consent: no text
        a.handle_event({"event": "pipeline.failed", "id": "n2", "repo": "acme/app"}); self.assertTrue(r.mock.calls("chat.postMessage"))

    def test_nothing_is_added_twice_and_switches_are_kept(self):
        r = Rig(); self.addCleanup(r.close); a = r.agent
        self.assertEqual(EF.ensure(a), 0)
        SU.set_workflow(a, EF.name_for("order.cancelled"), False); a._load_workflows(); self.assertEqual(EF.ensure(a), 0)
        self.assertEqual(a.handle_event(payload("order.cancelled", 99))["matched"] if not any(w["name"] != EF.name_for("order.cancelled") and (w.get("on") or {}).get("event") == "order.cancelled" for w in a.workflows) else 0, 0)

    def test_your_own_workflow_replaces_the_ready_made_one_for_that_event(self):
        r = Rig(); self.addCleanup(r.close); a = r.agent
        BD.save(a, {"name": "My cancel text", "trigger": {"type": "event", "event": "ticket.resolved"}, "steps": [{"type": "sms", "text": "Mine: resolved."}]}); a._load_workflows()
        out = a.handle_event(payload("ticket.resolved", 7)); names = [w["workflow"] for w in out["workflows"]]
        self.assertEqual(len(names), 1); self.assertNotIn(EF.name_for("ticket.resolved"), names)

    def test_coming_soon_events_are_listed_last_and_do_nothing(self):
        r = Rig(); self.addCleanup(r.close); a = r.agent
        v = SIM.view(a); self.assertEqual([e["id"] for e in v["events"] if e["soon"]], ["facility.lockdown"]); self.assertTrue(v["events"][-1]["soon"])
        self.assertTrue(all(e["handled"] for e in v["events"] if not e["soon"]))
        bv = BD.view(a); self.assertTrue(bv["events"][-1]["soon"]); self.assertEqual(len(bv["events"]), 60)
        self.assertEqual(a.handle_event({"event": "facility.lockdown", "id": "l1", "customer": CUST})["matched"], 0)
        soon = [w for w in SU.workflows(a) if w.get("soon")]; self.assertEqual(len(soon), 1); self.assertTrue(SU.workflows(a)[-1]["soon"])

    def test_the_pretend_test_works_for_every_event(self):
        r = Rig(); self.addCleanup(r.close); a = r.agent
        for ev in EF.SPECS:
            out = SIM.event(a, ev); self.assertTrue(out["matched"] and out["matched"] != "Nothing matched", ev); self.assertFalse(out["sent"])


if __name__ == "__main__":
    unittest.main()
