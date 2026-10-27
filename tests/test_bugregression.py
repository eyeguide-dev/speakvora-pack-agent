import json, time, unittest
from test_atlassian import rig, no_errors, desc_text
from test_bugflow import ERR
from test_bugdesk import msg
from speakvora_pack_agent import changes


def unique_threads(r):
    """The Slack mock answers every post with the same message id; real Slack gives each alert its own thread."""
    old, n = r.agent.slack.post, [0]

    def post(text, channel=None, thread_ts=None):
        res = dict(old(text, channel, thread_ts)); n[0] += 1; res["ts"] = f"9.{n[0]}"; return res
    r.agent.slack.post = post


def alerts(r):
    return [q["json"]["text"] for q in r.mock.requests if q["path"].endswith("/chat.postMessage") and not q["json"].get("thread_ts")]


def thread_of(r, key):
    return next(ref for ref, k in r.agent.state.data["bug_threads"].items() if k == key)


class Regression(unittest.TestCase):
    def closed_then_again(self, **guard):
        r = rig(); self.addCleanup(r.close); unique_threads(r)
        if guard: r.agent.cfg.setdefault("guardrails", {}).update(guard)
        r.event("app.error", **ERR)
        r.agent.handle_slack_command({"command": "/fixed", "text": "BUG-1 payment redirect fixed and deployed", "user_name": "sam"})
        self.assertTrue(r.atlas.issues["BUG-1"]["done"])
        return r

    def again(self, r):
        r.event("app.error", **{**ERR, "customer": {"name": "Sam"}, "id": "again"})

    def test_a_report_after_the_ticket_was_closed_is_a_new_ticket_that_says_it_is_a_regression(self):
        r = self.closed_then_again(); self.again(r)
        self.assertEqual(len(r.atlas.issues), 2); d = desc_text(r.atlas.issues["BUG-2"])
        self.assertIn("Regression of BUG-1 (closed on " + time.strftime("%Y-%m-%d") + ")", d); self.assertNotIn("Regression of", desc_text(r.atlas.issues["BUG-1"])); no_errors(self, r)

    def test_the_two_tickets_are_linked_and_the_old_one_is_told(self):
        r = self.closed_then_again(); self.again(r)
        self.assertEqual({(l["inwardIssue"]["key"], l["outwardIssue"]["key"]) for l in r.atlas.links}, {("BUG-2", "BUG-1")})
        self.assertIn("The same problem was reported again after it was closed: BUG-2", json.dumps(r.atlas.comments["BUG-1"]))

    def test_a_failed_link_falls_back_to_a_comment_on_the_old_ticket(self):
        r = self.closed_then_again()
        def boom(*a): raise RuntimeError("link type missing")
        r.agent.atlassian.link_issues = boom; self.again(r)
        self.assertEqual(r.atlas.links, []); c = json.dumps(r.atlas.comments["BUG-1"])
        self.assertIn("reported again after it was closed: BUG-2", c); self.assertIn("could not be linked", c); self.assertIn("BUG-2", r.atlas.pages["1"]["body"]["storage"]["value"])
        self.assertTrue([x for x in r.log() if x.get("status") == "link_failed"])

    def test_the_team_alert_says_regression_and_keeps_the_timing_line(self):
        r = rig(); self.addCleanup(r.close); unique_threads(r)
        changes.record(r.agent, "deploy.succeeded", {"repo": "g/p", "environment": "production", "sha": "a1b2c3d4", "title": "Fix checkout redirect", "author": "sam"}, now=time.time() - 600)
        r.event("app.error", **ERR); r.agent.handle_slack_command({"command": "/fixed", "text": "BUG-1 fixed", "user_name": "sam"}); self.again(r)
        last = alerts(r)[-1]; day = time.strftime("%Y-%m-%d")
        self.assertIn(f"REGRESSION: BUG-1 was marked fixed on {day} and was reported again. Reply reopen to reopen it instead.", last); self.assertIn("Timing only", last); self.assertIn("BUG-2", last)
        self.assertNotIn("REGRESSION", alerts(r)[0])

    def test_the_regression_is_stored_and_counted_and_the_old_ticket_stays_known(self):
        r = self.closed_then_again(); self.again(r); bugs = r.agent.state.data["jira_bugs"]
        new = next(v for v in bugs.values() if v["key"] == "BUG-2"); old = next(v for v in bugs.values() if v["key"] == "BUG-1")
        self.assertEqual(new["regression_of"], "BUG-1"); self.assertEqual(old["regressions"], 1); self.assertTrue(old.get("closed")); self.assertEqual(r.agent.state.data["bug_regression_count"], 1)

    def test_replying_reopen_in_the_new_alert_goes_through_the_approval_for_the_old_ticket(self):
        r = self.closed_then_again(); self.again(r); th = thread_of(r, "BUG-2"); chan, ts = th.split(":")
        out = r.agent.handle_slack_event(msg("reopen", thread=ts, chan=chan))
        self.assertEqual((out["ticket"], out["action"]), ("BUG-1", "asked")); self.assertTrue(r.atlas.issues["BUG-1"]["done"], "nothing changes before approval")
        out = r.agent.handle_slack_event(msg("approve", thread=ts, chan=chan)); self.assertEqual((out["ticket"], out["action"]), ("BUG-1", "reopen_done"))
        self.assertFalse(r.atlas.issues["BUG-1"]["done"]); self.assertEqual(r.atlas.moved[-1], ("BUG-1", "To Do")); no_errors(self, r)

    def test_keep_open_in_that_thread_leaves_the_old_ticket_closed(self):
        r = self.closed_then_again(); self.again(r); chan, ts = thread_of(r, "BUG-2").split(":")
        r.agent.handle_slack_event(msg("reopen", thread=ts, chan=chan)); out = r.agent.handle_slack_event(msg("keep open", thread=ts, chan=chan))
        self.assertEqual(out["action"], "kept"); self.assertTrue(r.atlas.issues["BUG-1"]["done"])

    def test_any_other_reply_in_the_new_thread_is_a_note_on_the_new_ticket(self):
        r = self.closed_then_again(); self.again(r); chan, ts = thread_of(r, "BUG-2").split(":")
        out = r.agent.handle_slack_event(msg("looking at the logs now", thread=ts, chan=chan)); self.assertEqual(out["ticket"], "BUG-2"); self.assertIn("logs", json.dumps(r.atlas.comments["BUG-2"]))

    def test_the_guardrail_off_goes_back_to_a_plain_new_ticket(self):
        r = self.closed_then_again(bug_regression="off"); self.again(r)
        self.assertEqual(len(r.atlas.issues), 2); self.assertNotIn("Regression of", desc_text(r.atlas.issues["BUG-2"])); self.assertEqual(r.atlas.links, []); self.assertNotIn("REGRESSION", alerts(r)[-1])

    def test_a_ticket_that_is_still_open_just_gets_the_report_as_evidence(self):
        r = rig(); self.addCleanup(r.close); r.event("app.error", **ERR); self.again(r)
        self.assertEqual(len(r.atlas.issues), 1); self.assertEqual(r.atlas.links, []); self.assertFalse(r.agent.state.data.get("bug_regression_count"))

    def test_a_ticket_closed_in_jira_by_the_team_counts_even_before_the_agent_noticed(self):
        r = rig(); self.addCleanup(r.close); r.event("app.error", **ERR); r.atlas.issues["BUG-1"]["done"] = True; self.again(r)
        self.assertIn("Regression of BUG-1", desc_text(r.atlas.issues["BUG-2"]))

    def test_practice_mode_changes_nothing(self):
        r = self.closed_then_again(); r.agent.dry = True; n = len(r.atlas.calls); self.again(r); self.assertEqual(len(r.atlas.calls), n)


if __name__ == "__main__":
    unittest.main()
