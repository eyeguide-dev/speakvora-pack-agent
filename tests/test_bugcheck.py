import json, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from test_atlassian import rig, no_errors
from test_bugflow import ERR
from test_bugdesk import msg
from speakvora_pack_agent import bugcheck

CHECK = {"name": "Checkout page", "match": "pay", "url": "https://shop.example.com/health/checkout", "expect_status": 200}


class Net:
    """Replaces the network: a name resolver and the one request function."""
    def __init__(self, case, answers=None, dns=None):
        self.calls, self.answers, self.dns = [], list(answers or [(200, "ok", "")]), dns or {}
        for name, new in (("_fetch", self.fetch), ("_resolve", self.resolve)):
            old = getattr(bugcheck, name); setattr(bugcheck, name, new); case.addCleanup(setattr, bugcheck, name, old)

    def resolve(self, host, port):
        return self.dns.get(host, ["93.184.216.34"])

    def fetch(self, method, url, headers, body, timeout, allow_private):
        self.calls.append((method, url, body, timeout, allow_private))
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception): raise a
        return a


class Choosing(unittest.TestCase):
    def agent(self, checks):
        r = rig(); self.addCleanup(r.close); r.agent.cfg["bug_checks"] = checks; return r.agent

    def test_the_check_whose_words_all_appear_is_picked_ignoring_capitals(self):
        a = self.agent([{"name": "Login", "match": "login", "url": "https://x.test/l"}, {"name": "Pay", "match": "Checkout, PAY", "url": "https://x.test/p"}])
        self.assertEqual(bugcheck.find(a, "403 error on /order when they clicked Pay at CHECKOUT")["name"], "Pay")
        self.assertEqual(bugcheck.find(a, "the login page is blank")["name"], "Login")

    def test_no_match_or_only_some_words_means_no_check(self):
        a = self.agent([{"name": "Pay", "match": "checkout pay", "url": "https://x.test/p"}])
        self.assertIsNone(bugcheck.find(a, "the menu is blank")); self.assertIsNone(bugcheck.find(a, "pay button broken")); self.assertIsNone(bugcheck.find(self.agent([]), "anything"))

    def test_the_most_specific_check_wins(self):
        a = self.agent([{"name": "Any pay", "match": "pay", "url": "https://x.test/1"}, {"name": "Checkout pay", "match": "checkout pay", "url": "https://x.test/2"}])
        self.assertEqual(bugcheck.find(a, "pay failed on checkout")["name"], "Checkout pay")


class Running(unittest.TestCase):
    def go(self, net=None, **kw):
        r = rig(); self.addCleanup(r.close); self.net = net or Net(self); return bugcheck.run(r.agent, {**CHECK, **kw})

    def test_a_good_answer_passes_with_status_and_time(self):
        res = self.go(); self.assertTrue(res["ok"]); self.assertEqual(res["status"], 200); self.assertRegex(res["detail"], r"^200 in \d+ ms$"); self.assertLessEqual(self.net.calls[0][3], 8)

    def test_a_wrong_status_fails_and_says_which(self):
        res = self.go(net=Net(self, [(500, "boom", "")])); self.assertFalse(res["ok"]); self.assertEqual((res["status"], res["detail"]), (500, "status 500"))

    def test_the_expected_text_must_be_in_the_answer(self):
        self.assertFalse(self.go(expect_text="all good", net=Net(self, [(200, "maintenance", "")]))["ok"])
        self.assertTrue(self.go(expect_text="all good", net=Net(self, [(200, "status: all good", "")]))["ok"])

    def test_post_sends_the_json_body_and_other_methods_are_refused(self):
        self.go(method="POST", body={"ping": 1}); self.assertEqual((self.net.calls[0][0], json.loads(self.net.calls[0][2])), ("POST", {"ping": 1}))
        res = self.go(method="DELETE"); self.assertFalse(res["ok"]); self.assertEqual(self.net.calls, [])

    def test_a_network_failure_is_a_failed_check_not_an_exception(self):
        res = self.go(net=Net(self, [OSError("connection refused: https://u:secret@x")])); self.assertFalse(res["ok"]); self.assertNotIn("secret", json.dumps(res))
        self.assertFalse(self.go(net=Net(self, [TimeoutError()]))["ok"])

    def test_addresses_that_are_not_public_are_refused_without_a_request(self):
        for host, ip in (("a.test", "127.0.0.1"), ("b.test", "10.1.2.3"), ("c.test", "192.168.0.9"), ("d.test", "169.254.169.254"), ("e.test", "::1"), ("f.test", "fd00:ec2::254"), ("g.test", "100.64.0.1"), ("h.test", "::ffff:127.0.0.1")):
            res = self.go(net=Net(self, dns={host: [ip]}), url=f"https://{host}/x"); self.assertFalse(res["ok"], ip); self.assertIn("not a public one", res["detail"]); self.assertEqual(self.net.calls, [], ip)

    def test_a_name_with_one_private_answer_among_public_ones_is_refused(self):
        res = self.go(net=Net(self, dns={"mix.test": ["93.184.216.34", "10.0.0.5"]}), url="https://mix.test/x"); self.assertFalse(res["ok"]); self.assertEqual(self.net.calls, [])

    def test_literal_private_addresses_and_odd_schemes_are_refused(self):
        dns = {"127.0.0.1": ["127.0.0.1"], "169.254.169.254": ["169.254.169.254"], "::1": ["::1"]}
        for url in ("http://169.254.169.254/latest/meta-data", "http://127.0.0.1:8080/", "http://[::1]/", "file:///etc/passwd", "ftp://x.test/", "https://user:pw@x.test/"):
            res = self.go(url=url, net=Net(self, dns=dns)); self.assertFalse(res["ok"], url); self.assertEqual(self.net.calls, [], url)

    def test_allow_private_lets_an_owner_check_their_own_internal_service(self):
        res = self.go(net=Net(self, dns={"intranet.test": ["10.0.0.5"]}), url="http://intranet.test/health", allow_private=True); self.assertTrue(res["ok"]); self.assertTrue(self.net.calls[0][4])

    def test_a_redirect_to_another_host_is_not_followed_but_the_same_host_is(self):
        res = self.go(net=Net(self, [(302, "", "https://evil.example.org/steal")])); self.assertFalse(res["ok"]); self.assertIn("another host", res["detail"]); self.assertEqual(len(self.net.calls), 1)
        res = self.go(net=Net(self, [(301, "", "/health/v2"), (200, "ok", "")])); self.assertTrue(res["ok"]); self.assertEqual(self.net.calls[1][1], "https://shop.example.com/health/v2")

    def test_a_redirect_to_another_port_counts_as_another_host(self):
        res = self.go(net=Net(self, [(302, "", "http://shop.example.com:8080/x")])); self.assertFalse(res["ok"]); self.assertEqual(len(self.net.calls), 1)

    def test_endless_redirects_stop(self):
        res = self.go(net=Net(self, [(302, "", "/again")])); self.assertFalse(res["ok"]); self.assertLessEqual(len(self.net.calls), 4)


class Local(unittest.TestCase):
    """The real request function against a throw-away server on this computer (allow_private), for what a fake cannot show."""
    def setUp(self):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_GET(self):
                if self.path == "/big":
                    b = b"x" * 200000 + b"NEEDLE"; self.send_response(200); self.send_header("content-length", str(len(b))); self.end_headers()
                    try: self.wfile.write(b)
                    except OSError: pass
                elif self.path == "/redir":
                    self.send_response(302); self.send_header("location", "http://other.invalid/x"); self.send_header("content-length", "0"); self.end_headers()
                else:
                    self.send_response(200); self.send_header("content-length", "2"); self.end_headers(); self.wfile.write(b"ok")
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H); self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start(); self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))
        self.r = rig(); self.addCleanup(self.r.close)

    def test_only_the_first_20_kb_are_read_and_a_redirect_is_not_followed(self):
        st, text, loc = bugcheck._fetch("GET", self.base + "/big", {}, None, 5, True); self.assertEqual(st, 200); self.assertLessEqual(len(text), 20 * 1024); self.assertNotIn("NEEDLE", text)
        st, text, loc = bugcheck._fetch("GET", self.base + "/redir", {}, None, 5, True); self.assertEqual((st, loc), (302, "http://other.invalid/x"))
        self.assertTrue(bugcheck.run(self.r.agent, {"name": "x", "url": self.base + "/ok", "allow_private": True, "expect_text": "ok"})["ok"])

    def test_this_computer_is_refused_by_default_even_for_the_real_function(self):
        res = bugcheck.run(self.r.agent, {"name": "x", "url": self.base + "/ok"}); self.assertFalse(res["ok"]); self.assertIn("not a public one", res["detail"])
        with self.assertRaises(ValueError): bugcheck._fetch("GET", self.base + "/ok", {}, None, 5, False)


class OnTheTicket(unittest.TestCase):
    TEXTER = {"customer": {"name": "Ann", "phone": "+16465550123", "sms_consent": True}, "data": {"error": {"code": 403, "message": "Forbidden", "page": "/order", "action": "Pay and place order"}}}

    def opened(self, checks=(CHECK,), answers=None, event=ERR, **guard):
        r = rig(); self.addCleanup(r.close); self.net = Net(self, answers); r.agent.cfg["bug_checks"] = list(checks)
        if guard: r.agent.cfg.setdefault("guardrails", {}).update(guard)
        r.event("app.error", **event); return r

    def thread(self, r):
        chan, ts = next(iter(r.agent.state.data["bug_threads"])).split(":"); return {"thread": ts, "chan": chan}

    def said(self, r):
        return " || ".join(str(q["json"]["text"]) for q in r.mock.requests if q["path"].endswith("/chat.postMessage"))

    def fixed(self, r):
        r.agent.handle_slack_command({"command": "/fixed", "text": "BUG-1 redirect fixed", "user_name": "sam"})

    def test_by_default_closing_runs_nothing_and_saying_verify_runs_the_check(self):
        r = self.opened(); self.fixed(r)
        self.assertEqual(self.net.calls, []); self.assertNotIn("verified", next(iter(r.agent.state.data["jira_bugs"].values())))
        out = r.agent.handle_slack_event(msg("verify", **self.thread(r))); self.assertEqual(out["action"], "verified"); self.assertEqual(len(self.net.calls), 1); no_errors(self, r)

    def test_the_message_keeps_who_said_fixed_apart_from_the_check_result(self):
        r = self.opened(); self.fixed(r); r.agent.handle_slack_event(msg("run the check", **self.thread(r)))
        said = self.said(r); self.assertIn("Marked fixed by sam at ", said); self.assertRegex(said, r"Verified by check Checkout page: passed \(200 in \d+ ms\)")
        c = json.dumps(r.atlas.comments["BUG-1"]); self.assertIn("Marked fixed by sam at", c); self.assertIn("Verified by check Checkout page: passed", c)
        v = next(iter(r.agent.state.data["jira_bugs"].values()))["verified"]; self.assertEqual((v["ok"], v["check"]), (True, "Checkout page")); self.assertTrue(v["at"])

    def test_a_failed_check_says_not_verified_and_leaves_the_ticket_closed(self):
        r = self.opened(answers=[(500, "err", "")]); self.fixed(r); out = r.agent.handle_slack_event(msg("check it again", **self.thread(r)))
        self.assertEqual(out["action"], "verify_failed"); self.assertIn("Check Checkout page FAILED (status 500): the ticket is NOT verified. Reply reopen to reopen it.", self.said(r))
        self.assertTrue(r.atlas.issues["BUG-1"]["done"]); self.assertFalse(next(iter(r.agent.state.data["jira_bugs"].values()))["verified"]["ok"])

    def test_auto_runs_right_after_closing_from_the_slash_command_and_from_approve(self):
        r = self.opened(bug_verify="auto"); self.fixed(r); self.assertEqual(len(self.net.calls), 1)
        r2 = self.opened(bug_verify="auto"); r2.agent.handle_slack_event(msg("fixed and deployed", **self.thread(r2))); self.assertEqual(self.net.calls, [], "asking is not closing")
        r2.agent.handle_slack_event(msg("approve", **self.thread(r2))); self.assertEqual(len(self.net.calls), 1); self.assertIn("Verified by check", self.said(r2)); no_errors(self, r2)

    def test_auto_never_reopens_by_itself(self):
        r = self.opened(answers=[(503, "", "")], bug_verify="auto"); self.fixed(r)
        self.assertTrue(r.atlas.issues["BUG-1"]["done"]); self.assertEqual(r.atlas.moved, [("BUG-1", "Done")]); self.assertNotIn("BUG-1", r.agent.state.data.get("bug_pending", {}))

    def test_auto_reopen_asks_first_when_closing_needs_approval_and_reopens_when_it_is_automatic(self):
        r = self.opened(answers=[(503, "", "")], bug_verify="auto_reopen"); self.fixed(r)
        self.assertIn("BUG-1", r.agent.state.data["bug_pending"]); self.assertTrue(r.atlas.issues["BUG-1"]["done"]); self.assertIn("Reopen BUG-1", self.said(r))
        self.assertEqual(r.agent.handle_slack_event(msg("approve", **self.thread(r)))["action"], "reopen_done"); self.assertFalse(r.atlas.issues["BUG-1"]["done"])
        r2 = self.opened(answers=[(503, "", "")], bug_verify="auto_reopen", bug_close="auto"); self.fixed(r2); self.assertFalse(r2.atlas.issues["BUG-1"]["done"])

    def test_a_ticket_with_no_matching_check_is_never_checked_and_the_thread_says_so_once(self):
        r = self.opened(checks=[{"name": "Login", "match": "login", "url": "https://x.test/l"}]); self.fixed(r)
        for _ in range(2): self.assertEqual(r.agent.handle_slack_event(msg("verify", **self.thread(r)))["action"], "verify_no_check")
        self.assertEqual(self.net.calls, []); self.assertEqual(self.said(r).count("cannot be verified automatically"), 1)

    def test_verify_on_a_ticket_that_is_not_fixed_yet_does_nothing(self):
        r = self.opened(); out = r.agent.handle_slack_event(msg("verify", **self.thread(r))); self.assertEqual(out["action"], "verify_not_fixed"); self.assertEqual(self.net.calls, []); self.assertIn("not marked fixed yet", self.said(r))

    def test_off_switches_everything_off(self):
        r = self.opened(bug_verify="off"); self.fixed(r); out = r.agent.handle_slack_event(msg("verify", **self.thread(r)))
        self.assertEqual((out["action"], self.net.calls), ("verify_off", []))

    def texts(self, r):
        return [q for q in r.mock.requests if q["path"].endswith("/Messages.json") and "6465550123" in json.dumps(q.get("form") or {})]

    def test_customers_hear_fixed_right_away_by_default(self):
        r = self.opened(event=self.TEXTER, bug_verify="auto", answers=[(500, "", "")]); n = len(self.texts(r)); self.fixed(r); self.assertEqual(len(self.texts(r)) - n, 1)

    def test_with_tell_after_verify_customers_wait_for_a_passed_check(self):
        r = self.opened(event=self.TEXTER, bug_tell_after_verify=True, answers=[(500, "", ""), (200, "ok", "")]); n = len(self.texts(r))
        self.fixed(r); self.assertEqual(len(self.texts(r)) - n, 0, "closed but not verified")
        r.agent.handle_slack_event(msg("verify", **self.thread(r))); self.assertEqual(len(self.texts(r)) - n, 0, "the check failed")
        r.agent.handle_slack_event(msg("verify", **self.thread(r))); self.assertEqual(len(self.texts(r)) - n, 1, "now it passed"); self.assertIn("Told 1 customer", self.said(r))
        r.agent.handle_slack_event(msg("verify", **self.thread(r))); self.assertEqual(len(self.texts(r)) - n, 1, "once only"); no_errors(self, r)

    def test_tell_after_verify_with_no_check_tells_nobody(self):
        r = self.opened(checks=[], event=self.TEXTER, bug_tell_after_verify=True); n = len(self.texts(r)); self.fixed(r); self.assertEqual(len(self.texts(r)) - n, 0)

    def test_reopening_forgets_the_old_verification(self):
        r = self.opened(); self.fixed(r); r.agent.handle_slack_event(msg("verify", **self.thread(r)))
        self.assertIn("verified", next(iter(r.agent.state.data["jira_bugs"].values())))
        r.agent.handle_slack_event(msg("reopen", **self.thread(r))); r.agent.handle_slack_event(msg("approve", **self.thread(r))); self.assertNotIn("verified", next(iter(r.agent.state.data["jira_bugs"].values())))

    def test_the_check_address_never_reaches_the_ticket_or_the_thread(self):
        r = self.opened(checks=[{**CHECK, "url": "https://shop.example.com/h?key=SECRETKEY123"}]); self.fixed(r); r.agent.handle_slack_event(msg("verify", **self.thread(r)))
        blob = json.dumps(r.atlas.comments) + self.said(r) + json.dumps(r.log()); self.assertNotIn("SECRETKEY123", blob); self.assertNotIn("shop.example.com", blob)

    def test_practice_mode_runs_no_check(self):
        r = self.opened(bug_verify="auto"); self.fixed(r); n = len(self.net.calls); r.agent.dry = True
        r.agent.handle_slack_event(msg("verify", **self.thread(r))); self.assertEqual(len(self.net.calls), n)


if __name__ == "__main__":
    unittest.main()
