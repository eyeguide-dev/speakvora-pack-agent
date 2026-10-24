import json, re, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from test_pack_agent import Rig
from speakvora_pack_agent import connect as SU, eventflows as EF
from speakvora_pack_agent.connectors import atlassian as AT


class Atlas:
    """A small Jira Cloud and Confluence Cloud look-alike that remembers what it was given."""
    def __init__(self):
        self.issues, self.comments, self.links, self.pages, self.calls = {}, {}, [], {}, []
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def go(self):
                n = int(self.headers.get("content-length") or 0); body = json.loads(self.rfile.read(n)) if n else None
                path = self.path.split("?")[0]; me.calls.append((self.command, self.path, body, self.headers.get("authorization")))
                code, obj = me.route(self.command, path, self.path.partition("?")[2], body)
                b = json.dumps(obj).encode(); self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
            do_GET = do_POST = do_PUT = go

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H); self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()

    def route(self, m, p, q, b):
        if p == "/rest/api/3/myself":
            return 200, {"displayName": "Test Owner"}
        if p == "/rest/api/3/project/BUG":
            return 200, {"name": "Bugs", "issueTypes": [{"name": "Bug"}, {"name": "Story"}]}
        if p == "/rest/api/3/search/jql":
            jql = b["jql"]; hit = []
            mk = re.search(r'labels = "([^"]+)"', jql); mkey = re.search(r'key = "([^"]+)"', jql); keys_in = re.search(r'key in \(([^)]*)\)', jql)
            if keys_in:
                want = re.findall(r'"([^"]+)"', keys_in.group(1)); done = "statusCategory = Done" in jql
                return 200, {"issues": [{"key": k, "fields": {"status": {"name": "Done"}}} for k in want if k in self.issues and self.issues[k]["done"] == done]}
            for k, i in self.issues.items():
                if mkey and mkey.group(1) == k and "statusCategory != Done" not in jql:
                    hit.append({"key": k, "fields": {"status": {"name": "Done" if i["done"] else "To Do"}}}); continue
                if i["done"]:
                    continue
                if (mk and mk.group(1) in i["fields"]["labels"]) or (mkey and mkey.group(1) == k):
                    hit.append({"key": k})
            return 200, {"issues": hit[: b.get("maxResults", 5)]}
        if p == "/rest/api/3/issue" and m == "POST":
            k = f"BUG-{len(self.issues) + 1}"; self.issues[k] = {"fields": b["fields"], "done": False}; return 201, {"key": k}
        mt = re.fullmatch(r"/rest/api/3/issue/([A-Z]+-\d+)/transitions", p)
        if mt and m == "GET":
            return 200, {"transitions": [{"id": "11", "to": {"statusCategory": {"key": "indeterminate"}}}, {"id": "31", "to": {"statusCategory": {"key": "done"}}}]}
        if mt and m == "POST":
            assert b["transition"]["id"] == "31", "closes through the transition that finishes the ticket"; self.issues[mt.group(1)]["done"] = True; return 204, {}
        mm = re.fullmatch(r"/rest/api/3/issue/([A-Z]+-\d+)/comment", p)
        if mm:
            self.comments.setdefault(mm.group(1), []).append(b["body"]); return 201, {"id": "1"}
        if p == "/rest/api/3/issueLink":
            self.links.append(b); return 201, {}
        if p == "/wiki/api/v2/spaces":
            if "keys=" in q:
                return 200, {"results": [{"id": "77", "key": "ENG", "name": "Engineering"}] if "keys=ENG" in q else []}
            return 200, {"results": [{"id": "77", "key": "ENG", "name": "Engineering"}]}
        if p == "/wiki/api/v2/pages" and m == "GET":
            return 200, {"results": list(self.pages.values())}
        if p == "/wiki/api/v2/pages" and m == "POST":
            self.pages["1"] = {"id": "1", "title": b["title"], "version": {"number": 1}, "body": {"storage": {"value": b["body"]["value"]}}}; return 200, {"id": "1"}
        if re.fullmatch(r"/wiki/api/v2/pages/1", p) and m == "PUT":
            assert b["version"]["number"] == self.pages["1"]["version"]["number"] + 1, "Confluence wants the next version number"
            self.pages["1"].update(version={"number": b["version"]["number"]}, body={"storage": {"value": b["body"]["value"]}}); return 200, {"id": "1"}
        return 404, {"error": p}


def rig(**kw):
    at = Atlas(); r = Rig(extra={"atlassian": {"site": at.url, "email": "me@example.com", "api_token": "tok", "project": "BUG", "space": "ENG", **kw}}); r.atlas = at
    old = r.close; r.close = lambda: (old(), at.close())
    return r


def flag(a):
    return next(w for w in json.load(open(a.cfg["workflows"]))["workflows"] if w["name"] == "auto_bug_text").get("enabled", True)


def no_errors(case, r):
    case.assertEqual([x for x in r.log() if x.get("status") in ("error", "failed")], [], "every step must finish cleanly, not just change the page")


def desc_text(issue):
    return json.dumps(issue["fields"]["description"])


class Words(unittest.TestCase):
    def test_private_details_never_reach_a_ticket(self):
        t = AT.redact("Pay failed, card 4242 4242 4242 4242, my password is hunter2, mail ann@x.com, call 646-555-0101, key sk_live_abcdef12345678, SSN 123-45-6789")
        for bad in ("4242", "hunter2", "ann@x.com", "646-555", "sk_live", "123-45-6789"):
            self.assertNotIn(bad, t)

    def test_same_problem_in_other_words_has_the_same_fingerprint(self):
        self.assertEqual(AT.fingerprint("Checkout freezes after I press Pay"), AT.fingerprint("after pressing pay the checkout freezes"))
        self.assertNotEqual(AT.fingerprint("Checkout freezes after I press Pay"), AT.fingerprint("Login page shows a blank screen"))


class Flow(unittest.TestCase):
    def test_a_report_creates_a_bug_that_says_what_is_unknown_and_links_the_story(self):
        r = rig(); self.addCleanup(r.close)
        r.event("bug.reported", description="Checkout freezes after I press Pay. My card 4242 4242 4242 4242 and email ann@x.com", app_version="2.4.1", story="BUG-100", source="text message")
        self.assertEqual(len(r.atlas.issues), 1); i = r.atlas.issues["BUG-1"]; d = desc_text(i)
        self.assertEqual(i["fields"]["issuetype"]["name"], "Bug"); self.assertIn("speakvora", i["fields"]["labels"])
        for want in ("Steps to reproduce: Unknown", "Root cause: not determined", "Fix: none confirmed", "2.4.1"):
            self.assertIn(want, d)
        for bad in ("4242", "ann@x.com"):
            self.assertNotIn(bad, d)
        self.assertEqual(r.atlas.links[0]["outwardIssue"]["key"], "BUG-100")
        self.assertTrue(r.mock.calls("chat.postMessage"), "the team is told")
        self.assertIn("BUG-1", r.atlas.pages["1"]["body"]["storage"]["value"]); no_errors(self, r)

    def test_a_customer_text_about_a_problem_reaches_jira_even_when_the_ai_would_answer(self):
        r = rig(reasoner={"model": "x", "api_key": "k", "provider": "openai", "base_url": r"http://127.0.0.1:9"}); self.addCleanup(r.close)
        SU.save(r.agent, "atlassian", {"project": "BUG"})
        reply = r.agent._handle_sms({"From": "+16465550101", "Body": "The app keeps crashing when I try to book a table, error on the payment screen"})
        self.assertIn("logged this", reply); self.assertEqual(len(r.atlas.issues), 1); no_errors(self, r)
        r.agent._handle_sms({"From": "+16465550102", "Body": "my app crashes when I try to book a table, payment screen error"}); self.assertEqual(len(r.atlas.issues), 1)

    def test_a_long_first_report_and_a_short_later_one_are_the_same_bug(self):
        r = rig(); self.addCleanup(r.close)
        r.event("bug.reported", description="Checkout freezes after I press Pay. My card 4242 4242 4242 4242, mail ann@example.com, call 646-555-0101.")
        r.event("bug.reported", description="After pressing pay the checkout freezes!")
        self.assertEqual(len(r.atlas.issues), 1)

    def test_more_reports_become_evidence_on_the_same_bug_and_the_page_count_follows(self):
        r = rig(); self.addCleanup(r.close)
        r.event("bug.reported", description="Checkout freezes after I press Pay")
        r.event("bug.reported", description="after pressing pay the checkout freezes!")
        r.event("bug.reported", description="Checkout freezes when I press Pay again")
        self.assertEqual(len(r.atlas.issues), 1); self.assertEqual(len(r.atlas.comments["BUG-1"]), 2)
        self.assertIn("<td>3</td>", r.atlas.pages["1"]["body"]["storage"]["value"])

    def test_a_different_problem_is_a_different_ticket(self):
        r = rig(); self.addCleanup(r.close)
        r.event("bug.reported", description="Checkout freezes after I press Pay"); r.event("bug.reported", description="Login page shows a blank screen")
        self.assertEqual(len(r.atlas.issues), 2)
        v = r.atlas.pages["1"]["body"]["storage"]["value"]; self.assertIn("BUG-1", v); self.assertIn("BUG-2", v)

    def test_resolved_updates_the_row_keeps_the_teams_note_and_a_later_report_is_a_new_ticket(self):
        r = rig(); self.addCleanup(r.close)
        r.event("bug.reported", description="Checkout freezes after I press Pay")
        pg = r.atlas.pages["1"]; pg["body"]["storage"]["value"] = pg["body"]["storage"]["value"].replace("None confirmed", "Use the web checkout")     # the team writes a verified workaround in Confluence
        r.atlas.issues["BUG-1"]["done"] = True
        r.event("bug.resolved", ticket="BUG-1", title="Checkout freezes", status="Done")
        v = r.atlas.pages["1"]["body"]["storage"]["value"]
        self.assertIn("Fixed", v); self.assertIn("Use the web checkout", v); self.assertEqual(v.count("/browse/BUG-1"), 1)
        self.assertEqual(v.count("<tr>"), 2, "one header row and one ticket row"); no_errors(self, r)
        r.event("bug.reported", description="Checkout freezes after I press Pay")
        self.assertEqual(len(r.atlas.issues), 2, "the old ticket was finished, so this is a new one")

    def test_practice_mode_touches_nothing(self):
        r = rig(); self.addCleanup(r.close); r.agent.dry = True
        r.event("bug.reported", description="Checkout freezes after I press Pay"); r.event("bug.resolved", ticket="BUG-1", title="x")
        self.assertEqual(r.atlas.calls, [])

    def test_without_jira_the_ready_made_automations_skip_quietly_and_a_plain_step_says_what_is_missing(self):
        r = Rig(); self.addCleanup(r.close)
        r.event("bug.reported", description="Checkout freezes"); self.assertFalse([x for x in r.log() if x.get("status") == "error"])
        self.assertTrue([x for x in r.log() if x.get("action") == "jira_bug" and x.get("reason") == "jira_not_connected"])

    def test_a_failed_jira_never_hides_behind_success(self):
        r = rig(); self.addCleanup(r.close); r.atlas.close()
        r.event("bug.reported", description="Checkout freezes after I press Pay")
        self.assertTrue([x for x in r.log() if x.get("action") == "jira_bug" and x.get("status") in ("error", "failed", "queued", "needs_review")])


class Card(unittest.TestCase):
    def test_the_test_button_checks_sign_in_project_type_and_space_then_creates_a_test_ticket(self):
        r = rig(); self.addCleanup(r.close)
        out = SU.test(r.agent, "atlassian", {}); self.assertTrue(out["ok"], out); self.assertIn("Test Owner", out["message"]); self.assertIn("ENG", out["message"])
        out = SU.test(r.agent, "atlassian", {"create": True}); self.assertTrue(out["ok"]); self.assertIn("speakvora-test", r.atlas.issues["BUG-1"]["fields"]["labels"])
        self.assertTrue(all(c[3].startswith("Basic ") for c in r.atlas.calls))

    def test_the_space_can_be_typed_by_its_name_instead_of_its_key(self):
        r = rig(space="Engineering"); self.addCleanup(r.close)
        out = SU.test(r.agent, "atlassian", {}); self.assertTrue(out["ok"], out)
        r.event("bug.reported", description="Checkout freezes after I press Pay"); self.assertIn("BUG-1", r.atlas.pages["1"]["body"]["storage"]["value"])

    def test_a_missing_ticket_type_is_explained(self):
        r = rig(issue_type="Defect"); self.addCleanup(r.close)
        out = SU.test(r.agent, "atlassian", {}); self.assertFalse(out["ok"]); self.assertIn("Defect", out["message"]); self.assertIn("Bug", out["message"])

    def test_connecting_jira_switches_on_the_customer_text_workflow_once(self):
        r = Rig(); self.addCleanup(r.close); a = r.agent; EF.ensure(a); a._load_workflows()
        self.assertFalse(flag(a))
        SU.save(a, "atlassian", {"site": "acme.atlassian.net", "email": "me@acme.com", "api_token": "tok", "project": "bug"})
        self.assertTrue(flag(a))
        SU.set_workflow(a, "auto_bug_text", False); SU.save(a, "atlassian", {"project": "BUG"}); self.assertFalse(flag(a), "the owner's own switch is kept")

    def test_a_site_that_is_not_an_atlassian_address_is_refused(self):
        r = Rig(); self.addCleanup(r.close)
        with self.assertRaises(SU.SetupError):
            SU.save(r.agent, "atlassian", {"site": "https://evil.example.com"})


if __name__ == "__main__":
    unittest.main()
