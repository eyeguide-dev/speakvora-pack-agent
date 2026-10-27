import json, time, unittest
from test_atlassian import rig, no_errors, desc_text
from test_bugflow import ERR
from speakvora_pack_agent import changes, investigate

TOKEN = "ghp_SECRETTOKEN1234567890abcdef"
CODE = {"provider": "github", "repo": "acme/shop", "token": TOKEN}
STACK = ["TypeError: Cannot read properties of undefined (reading 'redirect')", "    at placeOrder (src/payments/checkout_redirect.js:42:13)", "    at onClick (src/ui/PayButton.jsx:10:5)",
         "    at https://shop.example.com/static/main.js:1:2000 user ann@example.com"]


def with_error(**extra):
    e = {**ERR["data"]["error"], **extra}; return {**ERR, "data": {"error": e}}


def gh_files(*names, extra=None):
    return {"html_url": "https://github.com/acme/shop/compare/aaaa1111...bbbb2222", "files": [{"filename": n, "additions": 3 + i, "deletions": i, "status": "modified", "patch": "@@ SECRET DIFF BODY @@", **(extra or {})} for i, n in enumerate(names)]}


class Fake:
    """Replaces the code host: remembers every request and answers from `reply`."""
    def __init__(self, case, reply):
        self.calls, self.reply = [], reply
        old = investigate._get; investigate._get = self.get; case.addCleanup(setattr, investigate, "_get", old)

    def get(self, url, headers, timeout=8):
        self.calls.append((url, dict(headers)))
        if isinstance(self.reply, Exception): raise self.reply
        return self.reply


def two_deploys(r, repo="g/p"):
    changes.record(r.agent, "deploy.succeeded", {"repo": repo, "environment": "production", "sha": "aaaa1111", "title": "Release 41", "author": "sam"}, now=time.time() - 3 * 3600)
    changes.record(r.agent, "deploy.succeeded", {"repo": repo, "environment": "production", "sha": "bbbb2222", "title": "Fix checkout redirect", "author": "sam"}, now=time.time() - 20 * 60)


class Investigate(unittest.TestCase):
    def go(self, reply, event=ERR, code=CODE, deploys=True):
        r = rig(); self.addCleanup(r.close); self.fake = Fake(self, reply)
        if code is not None: r.agent.cfg["code"] = dict(code)
        if deploys: two_deploys(r)
        r.event("app.error", **event); self.r = r
        return desc_text(r.atlas.issues["BUG-1"])

    def test_the_ticket_lists_changed_files_between_the_two_deploys_with_counts_only(self):
        d = self.go(gh_files("src/payments/checkout_redirect.js", "README.md"))
        self.assertIn("Possible causes (evidence, not a diagnosis)", d); self.assertIn("src/payments/checkout_redirect.js (+3 -0)", d); self.assertIn("README.md (+4 -1)", d)
        self.assertEqual(self.fake.calls[0][0], "https://api.github.com/repos/acme/shop/compare/aaaa1111...bbbb2222"); self.assertNotIn("SECRET DIFF BODY", d); self.assertIn("github.com/acme/shop/compare/aaaa1111...bbbb2222", d); no_errors(self, self.r)

    def test_at_most_15_files_are_listed_and_the_total_is_said(self):
        d = self.go(gh_files(*[f"src/f{i:02d}.py" for i in range(22)])); self.assertIn("src/f14.py", d); self.assertNotIn("src/f15.py", d); self.assertIn("22", d); self.assertIn("showing the first 15", d)

    def test_the_stack_trace_and_log_lines_are_cut_and_have_private_details_removed(self):
        stack = [f"frame {i} at fn{i} (a/b{i}.js)" for i in range(30)]; stack[0] = "Error for ann@example.com with password: hunter2"
        logs = [f"log line {i}" for i in range(9)]; logs[8] = "card 4242 4242 4242 4242 declined, Bearer abcdefghijklmnop1234"
        d = self.go(gh_files("a.py"), event=with_error(stack="\n".join(stack), logs=logs))
        self.assertIn("frame 11", d); self.assertNotIn("frame 12 at", d); self.assertIn("log line 4", d); self.assertNotIn("log line 3", d, "the last five lines")
        for bad in ("ann@example.com", "hunter2", "4242", "abcdefghijklmnop1234"): self.assertNotIn(bad, d)

    def test_possible_causes_are_ranked_by_matching_the_stack_with_the_evidence_link(self):
        d = self.go(gh_files("docs/guide.md", "src/ui/PayButton.jsx", "src/payments/checkout_redirect.js", "src/db/migrate.py", "src/orders/place_order_view.py"), event=with_error(stack="\n".join(STACK)))
        i = d.index("Files that may be related"); causes = d[i:]
        self.assertIn("src/payments/checkout_redirect.js", causes); self.assertIn("Matches stack frame", causes); self.assertIn("at placeOrder (src/payments/checkout_redirect.js:42:13)", causes)
        self.assertNotIn("docs/guide.md", causes); self.assertNotIn("migrate.py", causes); self.assertIn("compare/aaaa1111...bbbb2222", causes)
        self.assertLess(causes.index("checkout_redirect.js"), causes.index("PayButton.jsx"), "two matching words beat one")

    def test_at_most_three_causes_are_given(self):
        names = [f"src/payments/pay{i}.js" for i in range(6)]
        d = self.go(gh_files(*names), event=with_error(stack="at pay (src/payments/x.js:1:1)")); causes = d[d.index("Files that may be related"):]
        self.assertEqual(sum(1 for n in names if n in causes), 3)

    def test_the_page_or_action_can_match_too_and_says_so_without_calling_it_a_stack_frame(self):
        d = self.go(gh_files("src/pages/order.js", "src/misc.js")); causes = d[d.index("Files that may be related"):]
        self.assertIn("src/pages/order.js", causes); self.assertIn("page or action word", causes); self.assertNotIn("Matches stack frame", causes)

    def test_secret_looking_file_names_are_listed_by_name_only_and_flagged(self):
        d = self.go(gh_files(".env.production", "config/secrets.yml", "deploy/id_rsa", "src/ok.py", extra={"contents": "AWS=hunter2"}))
        for n in (".env.production", "config/secrets.yml", "deploy/id_rsa"): self.assertIn(n + " (+", d); self.assertIn(n.split("/")[-1], d)
        self.assertEqual(d.count("(sensitive file name)"), 3); self.assertNotIn("src/ok.py (+3 -3) (sensitive", d); self.assertNotIn("hunter2", d); self.assertNotIn("AWS=", d)
        self.assertTrue(investigate.sensitive("a/.env") and investigate.sensitive("id_rsa") and not investigate.sensitive("src/orders.py"))

    def test_the_token_is_only_sent_as_a_header_and_never_written_anywhere(self):
        d = self.go(gh_files("src/payments/checkout_redirect.js"), event=with_error(stack=f"Error token: {TOKEN}\n" + "\n".join(STACK)))
        self.assertEqual(self.fake.calls[0][1]["authorization"], "Bearer " + TOKEN); self.assertNotIn(TOKEN, self.fake.calls[0][0])
        blob = d + json.dumps([q.get("json") for q in self.r.mock.requests]) + json.dumps(self.r.atlas.comments) + json.dumps(self.r.log()) + open(self.r.agent.state.log_path).read() + json.dumps(self.r.agent.state.data)
        self.assertNotIn(TOKEN, blob)

    def test_a_failing_code_host_adds_nothing_and_never_stops_the_ticket(self):
        for err in (RuntimeError("boom " + TOKEN), TimeoutError(), ValueError("bad json")):
            d = self.go(err); self.assertNotIn("Possible causes", d); self.assertEqual(len(self.r.atlas.issues), 1); self.assertIn("Forbidden", d); no_errors(self, self.r)
            self.assertNotIn(TOKEN, open(self.r.agent.state.log_path).read())

    def test_an_answer_with_no_files_or_the_wrong_shape_adds_nothing(self):
        for reply in ({"files": []}, {"unexpected": True}, [], "text"):
            self.assertNotIn("Possible causes", self.go(reply))

    def test_without_a_code_host_or_without_a_previous_deploy_nothing_is_asked(self):
        self.assertNotIn("Possible causes", self.go(gh_files("a.py"), code=None)); self.assertEqual(self.fake.calls, [])
        self.assertNotIn("Possible causes", self.go(gh_files("a.py"), deploys=False)); self.assertEqual(self.fake.calls, [])
        r = rig(); self.addCleanup(r.close); fake = Fake(self, gh_files("a.py")); r.agent.cfg["code"] = dict(CODE)
        changes.record(r.agent, "deploy.succeeded", {"repo": "g/p", "environment": "production", "sha": "bbbb2222", "title": "only one", "author": "sam"}, now=time.time() - 60)
        r.event("app.error", **ERR); self.assertEqual(fake.calls, []); self.assertEqual(len(r.atlas.issues), 1)

    def test_an_unset_token_variable_or_an_unknown_provider_means_no_look(self):
        for code in ({**CODE, "token": ""}, {**CODE, "token": "env:NOT_SET"}, {**CODE, "provider": "svn"}, {**CODE, "repo": ""}):
            self.assertNotIn("Possible causes", self.go(gh_files("a.py"), code=code)); self.assertEqual(self.fake.calls, [])

    def test_gitlab_uses_its_own_compare_call_and_counts_lines_without_keeping_them(self):
        reply = {"web_url": "https://gitlab.com/acme/shop/-/compare/aaaa1111...bbbb2222", "diffs": [{"new_path": "app/pay.rb", "old_path": "app/pay.rb", "diff": "@@ -1,2 +1,3 @@\n-old\n+new1\n+new2 SECRETBODY\n keep"}, {"new_path": ".env", "old_path": ".env", "diff": "+A=1"}]}
        d = self.go(reply, code={"provider": "gitlab", "repo": "acme/shop", "token": "glpat-TOPSECRET"})
        url, hdr = self.fake.calls[0]; self.assertEqual(url, "https://gitlab.com/api/v4/projects/acme%2Fshop/repository/compare?from=aaaa1111&to=bbbb2222"); self.assertEqual(hdr["private-token"], "glpat-TOPSECRET")
        self.assertIn("app/pay.rb (+2 -1)", d); self.assertIn(".env (+1 -0) (sensitive file name)", d); self.assertNotIn("SECRETBODY", d); self.assertNotIn("glpat-TOPSECRET", d)

    def test_a_repeat_report_does_not_ask_again(self):
        r = rig(); self.addCleanup(r.close); fake = Fake(self, gh_files("a.py")); r.agent.cfg["code"] = dict(CODE); two_deploys(r)
        r.event("app.error", **ERR); r.event("app.error", **{**ERR, "id": "second"}); self.assertEqual(len(fake.calls), 1)

    def test_practice_mode_asks_nothing(self):
        r = rig(); self.addCleanup(r.close); fake = Fake(self, gh_files("a.py")); r.agent.cfg["code"] = dict(CODE); two_deploys(r); r.agent.dry = True
        r.event("app.error", **ERR); self.assertEqual(fake.calls, [])


class Previous(unittest.TestCase):
    def test_the_previous_deploy_is_the_one_before_in_the_same_repo_and_environment(self):
        r = rig(); self.addCleanup(r.close)
        for repo, env, sha, ago in (("g/p", "production", "11111111", 9000), ("g/p", "staging", "22222222", 5000), ("o/q", "production", "33333333", 4000), ("g/p", "production", "44444444", 3000), ("g/p", "production", "55555555", 100)):
            changes.record(r.agent, "deploy.succeeded", {"repo": repo, "environment": env, "sha": sha, "title": sha}, now=time.time() - ago)
        head = changes.latest(r.agent, hint={"text": "x"}) if False else next(x for x in r.agent.state.data["changes"] if x["sha"] == "55555555")
        self.assertEqual(changes.previous(r.agent, head)["sha"], "44444444"); self.assertEqual(changes.previous(r.agent, next(x for x in r.agent.state.data["changes"] if x["sha"] == "44444444"))["sha"], "11111111")
        self.assertIsNone(changes.previous(r.agent, next(x for x in r.agent.state.data["changes"] if x["sha"] == "11111111"))); self.assertIsNone(changes.previous(r.agent, None))


if __name__ == "__main__":
    unittest.main()
