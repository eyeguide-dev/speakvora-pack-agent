import base64, json, os, unittest
from test_atlassian import Atlas, no_errors
from test_bugflow import ERR
from test_pack_agent import Rig
from speakvora_pack_agent import teams_in as TI, connect as SU

SECRET = base64.b64encode(b"teams-test-security-token-0123456789").decode()


def rig(allow=None, **guard):
    at = Atlas()
    t = {"webhook_url": "MOCK/teams-hook", "outgoing_secret": SECRET}
    if allow is not None:
        t["allow"] = allow
    r = Rig(extra={"atlassian": {"site": at.url, "email": "me@example.com", "api_token": "tok", "project": "BUG", "space": "ENG"}, "teams": t, "guardrails": guard}); r.atlas = at
    r.agent.teams.url = r.mock.url + "/teams-hook"
    old = r.close; r.close = lambda: (old(), at.close())
    r.event("app.error", **ERR)
    return r


def post(r, text, who="Ann Owner", conv="19:abc@thread.tacv2;messageid=100", n=[0], secret=SECRET, **kw):
    n[0] += 1
    raw = json.dumps({"type": "message", "id": f"m{n[0]}", "text": f"<at>Speakvora</at> {text}", "from": {"id": "u1", "name": who}, "conversation": {"id": conv}, **kw}).encode()
    return TI.handle(r.agent, raw, TI.sign(secret, raw) if secret is not None else ""), raw


class TeamsIn(unittest.TestCase):
    def setUp(self):
        self.r = rig(); self.addCleanup(self.r.close)

    def test_valid_invalid_and_missing_signatures(self):
        r = self.r; raw = b'{"type":"message","text":"hi"}'
        self.assertTrue(TI.verify(SECRET, raw, TI.sign(SECRET, raw)))
        self.assertFalse(TI.verify(SECRET, raw, TI.sign(SECRET, raw + b" ")))
        self.assertFalse(TI.verify(SECRET, raw, "HMAC AAAA"))
        self.assertFalse(TI.verify(SECRET, raw, ""))
        self.assertFalse(TI.verify("", raw, TI.sign("", raw)))               # no secret saved: nothing is ever accepted
        self.assertEqual(TI.handle(r.agent, raw, "")[0], 401)
        self.assertEqual(TI.handle(r.agent, raw, "HMAC wrong")[0], 401)

    def test_replay_of_the_same_message_is_answered_but_not_done_twice(self):
        r = self.r; (c1, b1), raw = post(r, "BUG-1 maybe the Stripe key expired"); self.assertEqual(c1, 200)
        notes = len(r.atlas.comments["BUG-1"]); c2, b2 = TI.handle(r.agent, raw, TI.sign(SECRET, raw))
        self.assertIn("Already handled", b2["text"]); self.assertEqual(len(r.atlas.comments["BUG-1"]), notes)
        old = json.dumps({"type": "message", "id": "old", "text": "x", "timestamp": "2020-01-01T00:00:00Z"}).encode()
        self.assertEqual(TI.handle(r.agent, old, TI.sign(SECRET, old))[0], 401)

    def test_the_bot_mention_and_markup_are_stripped(self):
        self.assertEqual(TI.strip_mentions("<at>Speakvora</at>&nbsp;BUG-1   fixed<br>now"), "BUG-1 fixed now")
        self.assertEqual(TI.strip_mentions("<div><at>Bot Name</at> hello &amp; bye</div>"), "hello & bye")

    def test_a_ticket_key_in_the_text_adds_a_note_and_answers_as_a_teams_message(self):
        r = self.r; (code, body), _ = post(r, "BUG-1 looks like the Stripe key expired")
        self.assertEqual(code, 200); self.assertEqual(body["type"], "message"); self.assertIn("BUG-1", body["text"])
        self.assertIn("Stripe key expired", json.dumps(r.atlas.comments["BUG-1"])); self.assertNotIn("<at>", json.dumps(r.atlas.comments["BUG-1"])); no_errors(self, r)

    def test_private_details_are_redacted_before_jira(self):
        r = self.r; post(r, "BUG-1 customer card 4242 4242 4242 4242 mail ann@x.com failed")
        c = json.dumps(r.atlas.comments["BUG-1"]); self.assertNotIn("4242", c); self.assertNotIn("ann@x.com", c)

    def test_later_messages_in_the_same_thread_reach_the_remembered_ticket(self):
        r = self.r; post(r, "BUG-1 checking the config")
        self.assertEqual(r.agent.state.data["bug_threads"]["teams:19:abc@thread.tacv2;messageid=100"], "BUG-1")
        (code, body), _ = post(r, "it was the renewal date"); self.assertIn("note", body["text"].lower())
        self.assertIn("renewal date", json.dumps(r.atlas.comments["BUG-1"]))
        (_c, other), _ = post(r, "no key here", conv="19:other@thread.tacv2"); self.assertIn("ticket", other["text"].lower())

    def test_fixed_asks_and_approve_closes_with_the_fake_jira(self):
        r = self.r; (_c, b), _ = post(r, "BUG-1 fixed: the key was renewed")
        self.assertIn("Reply approve", b["text"]); self.assertFalse(r.atlas.issues["BUG-1"].get("done"))
        (_c, b2), _ = post(r, "approve"); self.assertTrue(r.atlas.issues["BUG-1"]["done"]); self.assertIn("Closed BUG-1", b2["text"])
        self.assertIn("key was renewed", json.dumps(r.atlas.comments["BUG-1"])); no_errors(self, r)

    def test_keep_open_and_the_ask_mode_never_closes_without_approval(self):
        r = self.r; post(r, "BUG-1 fixed and deployed"); (_c, b), _ = post(r, "keep it open")
        self.assertIn("stays as it is", b["text"]); self.assertFalse(r.atlas.issues["BUG-1"].get("done"))

    def test_only_allowed_people_when_a_list_is_set(self):
        r = rig(allow=["ann owner", "bob@example.com"]); self.addCleanup(r.close)
        (_c, b), _ = post(r, "BUG-1 fixed", who="Mallory"); self.assertIn("not on the list", b["text"]); self.assertNotIn("BUG-1", r.atlas.comments)
        self.assertFalse(r.agent.state.data.get("bug_pending"))
        post(r, "BUG-1 looking at it now", who="Ann Owner"); self.assertIn("looking at it", json.dumps(r.atlas.comments["BUG-1"]))
        raw = json.dumps({"type": "message", "id": "e1", "text": "BUG-1 note from bob", "from": {"name": "Robert", "email": "Bob@Example.com"}, "conversation": {"id": "c9"}}).encode()
        TI.handle(r.agent, raw, TI.sign(SECRET, raw)); self.assertIn("note from bob", json.dumps(r.atlas.comments["BUG-1"]))

    def test_alert_text_carries_the_ticket_key_when_two_way_is_on(self):
        r = self.r; hooks = r.mock.calls("teams-hook")
        r.agent.run_actions("t", [{"action": "teams", "text": "Checkout is down"}], r.agent.ctx(jira={"key": "BUG-1"}))
        txt = json.dumps(r.mock.calls("teams-hook")[-1]["json"]); self.assertIn("BUG-1", txt); self.assertIn("@mention", txt)

    def test_secrets_never_reach_the_log_and_selftest_works(self):
        r = self.r; (_c, _b), raw = post(r, "BUG-1 note"); TI.handle(r.agent, raw, "HMAC bogusbogus")
        res = SU.test(r.agent, "teams", {"inbound": True}); self.assertTrue(res["ok"], res)
        log = open(r.agent.state.log_path).read(); self.assertNotIn(SECRET, log); self.assertNotIn("bogusbogus", log); self.assertNotIn(TI.sign(SECRET, raw), log)
        self.assertNotIn("Stripe", log)

    def test_the_connect_card_has_the_second_field_and_three_steps(self):
        card = next(c for c in SU.status(self.r.agent)["cards"] if c["name"] == "teams")
        self.assertEqual(len(card["steps"]), 3); self.assertEqual([f["key"] if "key" in f else f.get("name") for f in card["fields"]].__len__(), 2)

    def test_the_route_answers_and_locks_out_a_sender_after_eight_wrong_signatures(self):
        import threading, urllib.request, urllib.error
        from http.server import ThreadingHTTPServer
        from speakvora_pack_agent import server as SV
        SV.bad_by.clear(); srv = ThreadingHTTPServer(("127.0.0.1", 0), SV.make_handler(self.r.agent)); threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close); self.addCleanup(srv.shutdown)
        def go(raw, auth):
            q = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/teams/messages", data=raw, method="POST", headers={"Authorization": auth, "X-Forwarded-For": "9.9.9.9"})
            try:
                with urllib.request.urlopen(q) as x: return x.status, json.loads(x.read())
            except urllib.error.HTTPError as e: return e.code, None
        raw = json.dumps({"type": "message", "id": "h1", "text": "<at>B</at> ping", "from": {"name": "A"}}).encode()
        self.assertEqual(go(raw, TI.sign(SECRET, raw)), (200, {"type": "message", "text": "Pong. Speakvora is listening."}))
        codes = [go(raw, "HMAC bad")[0] for _ in range(9)]; self.assertEqual(codes[:8], [401] * 8); self.assertEqual(codes[8], 429)
        self.assertEqual(go(raw, TI.sign(SECRET, raw))[0], 429); SV.bad_by.clear()


if __name__ == "__main__":
    unittest.main()
