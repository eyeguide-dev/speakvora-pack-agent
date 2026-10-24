import json, unittest
from test_atlassian import rig, no_errors


ERR = {"customer": {"name": "Alex", "sms_consent": False}, "data": {"error": {"code": 403, "message": "Forbidden: payment session could not be created", "page": "/order", "action": "Pay and place order", "id": "pay-403"}}}


class BugFlow(unittest.TestCase):
    def test_a_site_error_opens_a_ticket_documents_it_with_the_date_and_tells_the_team(self):
        r = rig(); self.addCleanup(r.close)
        res = r.event("app.error", **ERR)
        self.assertEqual(len(r.atlas.issues), 1)
        desc = json.dumps(list(r.atlas.issues.values())[0]["fields"]["description"])
        self.assertIn("Alex got a 403 error", desc); self.assertIn("Pay and place order", desc)
        v = r.atlas.pages["1"]["body"]["storage"]["value"]; self.assertIn("BUG-1", v); self.assertIn("Open", v)
        self.assertTrue([x for x in r.log() if x.get("action") in ("slack", "teams") or x.get("action") == "notify"]); no_errors(self, r)

    def test_the_same_error_again_adds_to_the_ticket_and_does_not_open_a_second(self):
        r = rig(); self.addCleanup(r.close)
        r.event("app.error", **ERR); r.event("app.error", **{**ERR, "customer": {"name": "Sam"}, "id": "second"})
        self.assertEqual(len(r.atlas.issues), 1); self.assertEqual(len(r.atlas.comments.get("BUG-1", [])), 1)

    def test_slack_fixed_command_closes_the_ticket_with_the_note_and_marks_the_page_fixed(self):
        r = rig(); self.addCleanup(r.close)
        r.event("app.error", **ERR)
        out = r.agent.handle_slack_command({"command": "/fixed", "text": "BUG-1 payment redirect fixed and deployed", "user_name": "sam"})
        self.assertIn("closed", out["text"].lower()); self.assertTrue(r.atlas.issues["BUG-1"]["done"])
        self.assertIn("payment redirect fixed", json.dumps(r.atlas.comments["BUG-1"]))
        v = r.atlas.pages["1"]["body"]["storage"]["value"]; self.assertIn("Fixed", v); self.assertIn("payment redirect fixed", v); no_errors(self, r)

    def test_bug_resolved_event_closes_the_ticket_too(self):
        r = rig(); self.addCleanup(r.close)
        r.event("app.error", **ERR); r.event("bug.resolved", ticket="BUG-1", title="Checkout error", note="Fixed the redirect")
        self.assertTrue(r.atlas.issues["BUG-1"]["done"]); no_errors(self, r)

    def test_a_ticket_the_team_closes_in_jira_is_marked_fixed_on_the_page_and_announced_once(self):
        r = rig(); self.addCleanup(r.close)
        r.event("app.error", **ERR); r.atlas.issues["BUG-1"]["done"] = True
        self.assertEqual(r.agent._jira_sync(), 1)
        self.assertIn("Fixed", r.atlas.pages["1"]["body"]["storage"]["value"])
        r.agent.state.data["jira_sync_at"] = 0; self.assertEqual(r.agent._jira_sync(), 0)

    def test_a_problem_a_caller_describes_becomes_a_ticket(self):
        r = rig(); self.addCleanup(r.close)
        n = r.agent._do_ai_actions("+16465550123", [{"type": "report_bug", "text": "I pressed Pay on the order page and it said error 403."}], "call")
        self.assertEqual(n, 1); self.assertEqual(len(r.atlas.issues), 1); no_errors(self, r)

    def test_closing_does_nothing_in_practice_mode(self):
        r = rig(); self.addCleanup(r.close); r.event("app.error", **ERR); r.agent.dry = True; before = len(r.atlas.calls)
        r.agent.handle_slack_command({"command": "/fixed", "text": "BUG-1 done", "user_name": "sam"}); self.assertEqual(len(r.atlas.calls), before)


if __name__ == "__main__":
    unittest.main()
