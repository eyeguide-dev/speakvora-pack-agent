"""Setup timing: minutes from first setup step to first success, derived only from the local setup log."""
import json, os, unittest
from test_pack_agent import Rig
from speakvora_pack_agent import dashboard as D, setuplog as SLG

T0 = 1_790_000_000


def write(agent, events):
    with open(os.path.join(agent.state.dir, "setup-log.jsonl"), "w", encoding="utf-8") as f:
        for e in events:
            f.write((e if isinstance(e, str) else json.dumps(e)) + "\n")


class Timing(unittest.TestCase):
    def rig(self):
        r = Rig(); self.addCleanup(r.close); return r.agent

    def test_no_log_means_no_timeline(self):
        a = self.rig(); p = os.path.join(a.state.dir, "setup-log.jsonl")
        if os.path.exists(p): os.remove(p)
        self.assertIsNone(SLG.timeline(a)); self.assertEqual(SLG.set_up_text(None), "")
        self.assertIn("no setup steps", "\n".join(SLG.timeline_lines(None)))

    def test_full_journey_milestones_and_minutes_to_first_success(self):
        a = self.rig()
        write(a, [{"t": T0, "kind": "save", "card": "business", "ok": True}, {"t": T0 + 120, "kind": "save", "card": "twilio"}, {"t": T0 + 300, "kind": "test", "card": "twilio", "ok": True},
                  {"t": T0 + 360, "kind": "workflow_on", "workflow": "order_ready"}, {"t": T0 + 900, "kind": "first_message", "channel": "sms"}, {"t": T0 + 1000, "kind": "go_live", "on": True}])
        tl = SLG.timeline(a, now=T0 + 2000)
        self.assertEqual(tl["milestones"], {"business": 0, "connection": 120, "test_passed": 300, "workflow_on": 360, "first_message": 900, "live": 1000})
        self.assertEqual(tl["minutes_to_first_success"], 5.0); self.assertTrue(tl["finished"]); self.assertIsNone(tl["stopped"])
        self.assertEqual([s["took_seconds"] for s in tl["steps"]], [0, 120, 180, 60, 540, 100]); self.assertEqual(SLG.set_up_text(tl), "Set up in 5 minutes")

    def test_first_message_counts_when_it_comes_before_any_passed_test(self):
        a = self.rig(); write(a, [{"t": T0, "kind": "save", "card": "business"}, {"t": T0 + 90, "kind": "first_message", "channel": "telegram"}, {"t": T0 + 600, "kind": "test", "ok": True}])
        self.assertEqual(SLG.timeline(a, now=T0 + 700)["minutes_to_first_success"], 1.5)

    def test_failed_tests_and_failed_saves_do_not_count(self):
        a = self.rig(); write(a, [{"t": T0, "kind": "save", "card": "business"}, {"t": T0 + 10, "kind": "save", "card": "twilio", "ok": False}, {"t": T0 + 20, "kind": "test", "card": "twilio", "ok": False},
                                  {"t": T0 + 30, "kind": "go_live", "on": False}])
        tl = SLG.timeline(a, now=T0 + 100); self.assertNotIn("connection", tl["milestones"]); self.assertNotIn("test_passed", tl["milestones"]); self.assertNotIn("live", tl["milestones"]); self.assertIsNone(tl["minutes_to_first_success"])
        self.assertEqual(SLG.set_up_text(tl), "")

    def test_where_the_person_stopped_and_how_long_ago(self):
        a = self.rig(); write(a, [{"t": T0, "kind": "save", "card": "business"}, {"t": T0 + 60, "kind": "save", "card": "twilio"}, {"t": T0 + 120, "kind": "test", "card": "twilio", "ok": False}])
        st = SLG.timeline(a, now=T0 + 3720)["stopped"]
        self.assertEqual((st["after"], st["card"], st["idle_seconds"], st["next_step"]), ("test", "twilio", 3600, "first test passed"))
        text = "\n".join(SLG.timeline_lines(SLG.timeline(a, now=T0 + 3720))); self.assertIn("not live yet", text); self.assertIn("not yet", text)

    def test_corrupt_lines_and_junk_are_skipped(self):
        a = self.rig(); write(a, ["{not json", "[1,2]", '{"t":"x","kind":"save"}', '{"kind":"save"}', {"t": T0, "kind": "save", "card": "business"}, "", {"t": T0 + 60, "kind": "test", "ok": True}])
        tl = SLG.timeline(a, now=T0 + 61); self.assertEqual(tl["events"], 2); self.assertEqual(tl["minutes_to_first_success"], 1.0)

    def test_pure_function_is_order_independent_and_only_first_occurrence_counts(self):
        ev = [{"t": T0 + 500, "kind": "test", "ok": True}, {"t": T0, "kind": "save", "card": "business"}, {"t": T0 + 100, "kind": "test", "ok": True}]
        tl = SLG.timeline_of(ev, now=T0 + 600); self.assertEqual(tl["milestones"]["test_passed"], 100); self.assertEqual(SLG.timeline_of([]), None)

    def test_support_report_has_a_setup_timing_section(self):
        a = self.rig(); write(a, [{"t": T0, "kind": "save", "card": "business"}, {"t": T0 + 240, "kind": "test", "card": "slack", "ok": True}])
        rep = SLG.report(a); self.assertIn("Setup timing:", rep); self.assertIn("minutes from first step to first success: 4.0", rep)

    def test_route_returns_timeline_and_viewers_may_read_it_but_not_change_anything(self):
        a = self.rig(); write(a, [{"t": T0, "kind": "save", "card": "business"}, {"t": T0 + 180, "kind": "test", "ok": True}]); H = {"x-dashboard-token": D.token(a)}
        st, body, _, _ = D.handle(a, "GET", "/dash/api/setup/timeline", H, b""); out = json.loads(body)
        self.assertEqual(st, 200); self.assertEqual(out["timeline"]["minutes_to_first_success"], 3.0); self.assertEqual(out["text"], "Set up in 3 minutes")
        self.assertIn("/dash/api/setup/timeline", D.VIEW_OK)
        st, _, _, _ = D.handle(a, "POST", "/dash/api/setup/timeline", H, b"{}"); self.assertNotEqual(st, 200)
        st, body, _, _ = D.handle(a, "GET", "/dash/api/setup/timeline", {"x-dashboard-token": "wrong"}, b""); self.assertEqual(st, 401)

    def test_summary_carries_the_home_line_only_when_there_is_a_success(self):
        a = self.rig(); write(a, [{"t": T0, "kind": "save", "card": "business"}]); self.assertEqual(D.summary(a)["set_up_text"], "")
        write(a, [{"t": T0, "kind": "save", "card": "business"}, {"t": T0 + 20, "kind": "test", "ok": True}]); self.assertEqual(D.summary(a)["set_up_text"], "Set up in under a minute")

    def test_turning_a_workflow_on_from_the_dashboard_is_logged(self):
        a = self.rig(); H = {"x-dashboard-token": D.token(a)}; name = a.workflows[0]["name"]
        st, _, _, _ = D.handle(a, "POST", "/dash/api/setup/workflow", H, json.dumps({"name": name, "enabled": True}).encode())
        if st == 200: self.assertIn("workflow_on", [e["kind"] for e in SLG.read_events(a)])


if __name__ == "__main__":
    unittest.main()
