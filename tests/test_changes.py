import json, time, unittest
from test_atlassian import rig, no_errors
from test_bugflow import ERR
from speakvora_pack_agent import sources, changes

ROOT = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
def src(name): return json.load(open(f"{ROOT}/speakvora_pack_agent/data/sources/{name}.json"))
def run(s, hdr, payload): return sources.map_request(s, {"payload": payload, "headers": {k.lower(): v for k, v in hdr.items()}, "query": {}})


class Mapping(unittest.TestCase):
    def test_gitlab_deploy_merge_release_and_pipeline_become_events(self):
        g = src("gitlab"); proj = {"path_with_namespace": "g/p"}
        d = run(g, {"X-Gitlab-Event": "Deployment Hook"}, {"status": "success", "environment": "production", "short_sha": "a1b2c3d4", "commit_title": "Fix checkout redirect", "deployable_url": "u", "project": proj, "user": {"username": "sam"}})
        self.assertEqual((d["event"], d["environment"], d["sha"], d["title"]), ("deploy.succeeded", "production", "a1b2c3d4", "Fix checkout redirect"))
        m = run(g, {"X-Gitlab-Event": "Merge Request Hook"}, {"object_attributes": {"action": "merge", "title": "Fix", "target_branch": "main", "merge_commit_sha": "dead"}, "project": proj})
        self.assertEqual(m["event"], "pull_request.merged")
        self.assertEqual(run(g, {"X-Gitlab-Event": "Merge Request Hook"}, {"object_attributes": {"action": "open", "title": "x"}, "project": proj})["event"], "pull_request.ready")
        self.assertEqual(run(g, {"X-Gitlab-Event": "Release Hook"}, {"action": "create", "name": "v2.4.1", "project": proj})["event"], "release.published")
        self.assertEqual(run(g, {"X-Gitlab-Event": "Pipeline Hook"}, {"object_attributes": {"status": "failed", "ref": "main"}, "project": proj})["event"], "pipeline.failed")

    def test_github_deploy_merge_and_review_request_become_events(self):
        h = src("github"); repo = {"full_name": "o/r"}
        d = run(h, {"X-GitHub-Event": "deployment_status"}, {"action": "created", "deployment_status": {"state": "success"}, "deployment": {"environment": "production", "sha": "1234567890abcdef", "description": "Release 2.4.1"}, "repository": repo, "sender": {"login": "ci"}})
        self.assertEqual((d["event"], d["environment"], d["title"]), ("deploy.succeeded", "production", "Release 2.4.1"))
        self.assertEqual(run(h, {"X-GitHub-Event": "pull_request"}, {"action": "closed", "pull_request": {"merged": True, "title": "Fix", "merge_commit_sha": "abc"}, "repository": repo})["event"], "pull_request.merged")
        self.assertEqual(run(h, {"X-GitHub-Event": "pull_request"}, {"action": "review_requested", "pull_request": {"merged": False, "title": "WIP"}, "repository": repo})["event"], "pull_request.ready")
        self.assertIsNone(run(h, {"X-GitHub-Event": "pull_request"}, {"action": "closed", "pull_request": {"merged": False}, "repository": repo}))


def deploy(r, title="Fix checkout redirect", env="production", sha="a1b2c3d4", ago=0):
    changes.record(r.agent, "deploy.succeeded", {"repo": "g/p", "environment": env, "sha": sha, "title": title, "author": "sam"}, now=time.time() - ago)


class Context(unittest.TestCase):
    def test_a_new_bug_names_the_newest_production_deploy_as_timing_only(self):
        r = rig(); self.addCleanup(r.close); deploy(r, ago=35 * 60); r.event("app.error", **ERR)
        desc = json.dumps(list(r.atlas.issues.values())[0]["fields"]["description"])
        self.assertIn("Possibly related change", desc); self.assertIn("Fix checkout redirect", desc); self.assertIn("35 minutes earlier", desc); self.assertIn("not a diagnosis", desc)

    def test_the_alert_to_the_team_carries_the_line(self):
        r = rig(); self.addCleanup(r.close); deploy(r, ago=10 * 60); r.event("app.error", **ERR)
        sent = json.dumps([q.get("json") or q.get("form") for q in r.mock.requests])
        self.assertIn("Timing only", sent)

    def test_staging_deploys_and_old_changes_are_not_blamed(self):
        r = rig(); self.addCleanup(r.close); deploy(r, env="staging", ago=60); deploy(r, title="Old", ago=72 * 3600); r.event("app.error", **ERR)
        self.assertNotIn("Possibly related change", json.dumps(list(r.atlas.issues.values())[0]["fields"]["description"]))

    def test_a_merge_is_mentioned_as_not_seen_deployed_when_nothing_deployed(self):
        r = rig(); self.addCleanup(r.close); changes.record(r.agent, "pull_request.merged", {"repo": "g/p", "title": "Fix pay", "author": "sam", "sha": "dead"}, now=time.time() - 1200); r.event("app.error", **ERR)
        d = json.dumps(list(r.atlas.issues.values())[0]["fields"]["description"]); self.assertIn("merged but not seen deployed", d)

    def test_a_repeat_report_after_a_newer_deploy_says_so(self):
        r = rig(); self.addCleanup(r.close); r.event("app.error", **ERR); time.sleep(0.05)
        deploy(r, title="Hotfix 2.4.2", sha="ffff0000"); r.event("app.error", **{**ERR, "customer": {"name": "Sam"}, "id": "second"})
        self.assertIn("Hotfix 2.4.2", json.dumps(r.atlas.comments["BUG-1"])); no_errors(self, r)

    def test_the_same_deploy_reported_twice_is_stored_once(self):
        r = rig(); self.addCleanup(r.close); deploy(r); deploy(r); self.assertEqual(len(r.agent.state.data["changes"]), 1)

    def test_changes_can_be_switched_off(self):
        r = rig(); self.addCleanup(r.close); r.agent.cfg["changes"] = {"enabled": False}; deploy(r); self.assertFalse(r.agent.state.data.get("changes"))

    def test_events_from_the_webhook_are_remembered(self):
        r = rig(); self.addCleanup(r.close); r.event("deploy.succeeded", repo="g/p", environment="production", sha="aaaa1111", title="Release 3", author="ci")
        self.assertEqual(r.agent.state.data["changes"][0]["title"], "Release 3")


class TellCustomers(unittest.TestCase):
    TEXTER = {"customer": {"name": "Ann", "phone": "+16465550123", "sms_consent": True}, "data": {"error": {"code": 403, "message": "Forbidden", "page": "/order", "action": "Pay"}}}

    def texts_to(self, r, number):
        return [q for q in r.mock.requests if q["path"].endswith("/Messages.json") and number in json.dumps(q.get("form") or {})]

    def test_everyone_who_reported_it_is_told_when_it_is_closed_and_only_once(self):
        r = rig(); self.addCleanup(r.close); r.event("app.error", **self.TEXTER); before = len(self.texts_to(r, "6465550123"))
        r.event("bug.resolved", ticket="BUG-1", title="x", note="Fixed"); sent = self.texts_to(r, "6465550123")
        self.assertEqual(len(sent) - before, 1); self.assertIn("is fixed", str(sent[-1])); self.assertIn("try again", str(sent[-1]))
        r.event("bug.resolved", ticket="BUG-1", title="x", note="Fixed again", id="again"); self.assertEqual(len(self.texts_to(r, "6465550123")), len(sent)); no_errors(self, r)

    def test_a_customer_without_consent_is_not_texted(self):
        r = rig(); self.addCleanup(r.close); r.event("app.error", **{**self.TEXTER, "customer": {"name": "Bo", "phone": "+16465550124", "sms_consent": False}})
        r.event("bug.resolved", ticket="BUG-1", title="x", note="Fixed"); self.assertEqual(self.texts_to(r, "6465550124"), [])

    def test_closing_as_not_fixed_does_not_say_fixed(self):
        r = rig(); self.addCleanup(r.close); r.event("app.error", **self.TEXTER); n = len(self.texts_to(r, "6465550123"))
        from speakvora_pack_agent import bugdesk
        r.agent.state.data["bug_pending"] = {}
        r.agent.run_actions("t", [{"action": "jira_close", "ticket": "BUG-1", "note": "dup", "verb": "Closed as not fixed", "status_label": "Closed, not fixed"}], r.agent.ctx(), {"reply": "", "play": []})
        self.assertEqual(len(self.texts_to(r, "6465550123")), n)

    def test_the_switch_turns_it_off(self):
        r = rig(); self.addCleanup(r.close); r.agent.cfg.setdefault("guardrails", {})["bug_tell_customers"] = False; r.event("app.error", **self.TEXTER); n = len(self.texts_to(r, "6465550123"))
        r.event("bug.resolved", ticket="BUG-1", title="x", note="Fixed"); self.assertEqual(len(self.texts_to(r, "6465550123")), n)

    def test_a_ticket_closed_in_jira_also_tells_the_reporter(self):
        r = rig(); self.addCleanup(r.close); r.event("app.error", **self.TEXTER); n = len(self.texts_to(r, "6465550123")); r.atlas.issues["BUG-1"]["done"] = True
        r.agent._jira_sync(); self.assertEqual(len(self.texts_to(r, "6465550123")) - n, 1)

    def test_closing_from_slack_tells_the_customer_and_the_thread_says_so(self):
        from test_bugdesk import msg
        r = rig(); self.addCleanup(r.close); r.event("app.error", **self.TEXTER); n = len(self.texts_to(r, "6465550123"))
        r.agent.handle_slack_event(msg("fixed and deployed")); r.agent.handle_slack_event(msg("approve"))
        self.assertEqual(len(self.texts_to(r, "6465550123")) - n, 1)
        self.assertIn("Told 1 customer", json.dumps([q.get("json") for q in r.mock.requests]))


if __name__ == "__main__":
    unittest.main()
