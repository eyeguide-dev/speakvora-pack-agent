"""Quick start: basics in, a working smart agent out. Every smart step needs the owner's yes; transcripts become pending answers the owner approves."""
import base64, json, unittest
from test_pack_agent import Rig
from speakvora_pack_agent import brain, knowledge, learned as L, quickstart as Q, reasoner as R, sharing as SH

AI = {"provider": "anthropic", "api_key": "k", "model": "m"}
BASICS = {"business": "Bella Trattoria", "street": "12 Main St", "city": "Albany", "state": "New York", "zip": "12207", "phone": "(518) 555-0142", "hours": "Tue to Sun, 5 to 10 PM"}


class QS(unittest.TestCase):
    def setUp(self):
        self._f, self._chat, self._v, self._k, self._site, self._learn = Q._fetch, R._chat, L._voice, SH._key, knowledge.add_site, brain.start_learning_now; self.learned_for = []; brain.start_learning_now = lambda agent, website='', notes='': (self.learned_for.append(website) or True)
        self.voiced = []; L._voice = lambda agent, text: (self.voiced.append(text) or (b"ID3x", ".mp3")); SH._key = lambda agent=None: "svk"

    def tearDown(self):
        Q._fetch, R._chat, L._voice, SH._key, knowledge.add_site, brain.start_learning_now = self._f, self._chat, self._v, self._k, self._site, self._learn

    def rig(self, ai=True, **kw):
        r = Rig(extra={"reasoner": AI} if ai else None, **kw); self.addCleanup(r.close); return r

    def test_the_basics_are_saved_in_the_right_places_with_the_time_zone_from_the_state(self):
        a = self.rig().agent; Q._fetch = lambda u: ""
        out = Q.apply(a, {**BASICS, "allow": {"site": False}}); self.assertEqual(out["steps"][0]["id"], "business"); f = a.cfg["facts"]
        self.assertEqual(f["address"], "12 Main St, Albany, NY 12207"); self.assertEqual(f["phone"], "+15185550142"); self.assertEqual(f["hours"], "Tue to Sun, 5 to 10 PM"); self.assertEqual(a.cfg["timezone"], "America/New_York"); self.assertEqual(a.cfg["business"], "Bella Trattoria")
        with self.assertRaises(Exception): Q.apply(a, {**BASICS, "state": "Narnia"})
        with self.assertRaises(Exception): Q.apply(a, {**BASICS, "phone": "12"})
        with self.assertRaises(Exception): Q.apply(a, {**BASICS, "business": ""})

    def test_a_website_found_by_name_is_only_suggested_and_added_after_the_owner_says_yes(self):
        a = self.rig().agent
        Q._fetch = lambda u: "<title>Bella Trattoria | Albany NY</title><p>Bella Trattoria, Albany, New York. Open Tue to Sun.</p>" if u == "https://www.bellatrattoria.com" else ""
        added = []; knowledge.add_site = lambda agent, url, **k: (added.append(url) or {"id": "s1"})
        out = Q.apply(a, BASICS); w = [s for s in out["steps"] if s["id"] == "website"][0]; self.assertEqual(w["status"], "confirm"); self.assertEqual(w["candidates"][0]["url"], "https://www.bellatrattoria.com"); self.assertEqual(added, [], "not added without a yes")
        out = Q.apply(a, {**BASICS, "confirm_site": "https://www.bellatrattoria.com"}); self.assertEqual(added, ["https://www.bellatrattoria.com"]); self.assertEqual([s for s in out["steps"] if s["id"] == "website"][0]["status"], "done"); self.assertEqual(a.cfg["facts"]["website"], "https://www.bellatrattoria.com")

    def test_a_site_that_does_not_match_is_not_even_suggested_and_a_blocked_read_says_so(self):
        a = self.rig().agent; Q._fetch = lambda u: "<title>Domain for sale</title><p>buy this domain</p>"
        self.assertEqual([s for s in Q.apply(a, BASICS)["steps"] if s["id"] == "website"][0]["status"], "needs_you")
        def boom(agent, url, **k): raise ValueError("That website could not be read.")
        knowledge.add_site = boom; w = [s for s in Q.apply(a, {**BASICS, "website": "bella.example"})["steps"] if s["id"] == "website"][0]; self.assertEqual(w["status"], "needs_you"); self.assertIn("could not be read", w["text"])

    def test_phrases_are_written_only_with_permission_wait_for_approval_and_voice_only_when_also_allowed(self):
        a = self.rig().agent; knowledge.add_site = lambda *x, **k: {"id": "s1"}
        R._chat = lambda cfg, system, user, n=0: (json.dumps({"lines": ["We are closed today but we open again tomorrow evening.", "Thanks so much for visiting us, we hope to see you again soon.", "Sorry about the wait, we are running a little behind today."]}), {})
        off = Q.apply(a, {**BASICS, "website": "https://bella.example"}); self.assertEqual([s for s in off["steps"] if s["id"] == "lines"][0]["status"], "waiting"); self.assertEqual(len(L.load(a).get("suggested") or {}), 0)
        on = Q.apply(a, {**BASICS, "website": "https://bella.example", "allow": {"lines": True}}); s = [s for s in on["steps"] if s["id"] == "lines"][0]; self.assertEqual(s["status"], "done"); self.assertIn("Nothing is voiced until you approve", s["text"])
        self.assertEqual(len(L.load(a)["suggested"]), 3); self.assertEqual(self.voiced, []); self.assertEqual(self.learned_for, ["https://bella.example"], "the AI profile starts only with the yes, from the saved website"); self.assertIn("profile", [s["id"] for s in on["steps"]])
        self.assertEqual(Q.apply(a, {**BASICS, "website": "https://bella.example"}) and self.learned_for, ["https://bella.example"], "no yes, no profile")
        L.load(a)["suggested"].clear(); d = L.load(a); d["suggested"] = {}; L.save(a, d)
        both = Q.apply(a, {**BASICS, "website": "https://bella.example", "allow": {"lines": True, "voice_lines": True}}); self.assertEqual(len(self.voiced), 3); self.assertIn("3 voiced already", [s for s in both["steps"] if s["id"] == "lines"][0]["text"])

    def test_without_an_ai_the_smart_steps_wait_and_say_what_to_do(self):
        a = self.rig(ai=False).agent; out = Q.apply(a, {**BASICS, "allow": {"site": False, "lines": True}}); st = {s["id"]: s for s in out["steps"]}
        self.assertEqual(st["ai"]["status"], "needs_you"); self.assertEqual(st["lines"]["status"], "waiting"); self.assertEqual(out["next"], "Connect your AI"); self.assertFalse(Q.prefill(a)["ai_connected"])

    def test_transcripts_become_pending_answers_private_details_are_dropped_and_nothing_is_said_until_approved(self):
        a = self.rig().agent
        t = "\n".join(["Customer: Do you take reservations for large parties?", "Agent: Yes, we take reservations for groups, just call ahead and we will find you a table.", "Customer: Do you take reservations for large parties?", "Agent: Yes, groups are welcome with a reservation.",
                       "Customer: What time do you close on Sundays?", "Agent: On Sundays we close at nine in the evening.", "Customer: Can you call me back at 518 555 0199?", "Agent: Sure, we will call you right back on that number.",
                       "Customer: Is there parking nearby?", "Agent: Email us at info@bella.example and we will send the map.", "Customer: Thanks.", "Agent: Anytime."])
        r = Q.import_transcripts(a, "calls.txt", base64.b64encode(t.encode()).decode()); self.assertEqual(r["pairs"], 2, r)
        p = Q.pending(a); top = p[0] if p[0]["count"] == 2 else p[1]; self.assertEqual(top["count"], 2); self.assertTrue(all("555" not in x["q"] + x["a"] and "@" not in x["a"] for x in p))
        self.assertIsNone(knowledge.qa_match(a, "do you take reservations for large parties")); n = Q.approve(a, [top["id"]], {top["id"]: "Yes, groups are welcome. Call ahead and we will find you a table."})
        self.assertEqual(n["added"], 1); hit = knowledge.qa_match(a, "do you take reservations for large parties"); self.assertTrue(hit); self.assertIn("groups are welcome", hit[0])
        self.assertEqual(Q.dismiss(a, [x["id"] for x in Q.pending(a)])["pending"], 0)

    def test_a_file_with_no_conversation_says_how_it_should_look(self):
        a = self.rig().agent; r = Q.import_transcripts(a, "x.txt", base64.b64encode(b"just some notes about the restaurant opening hours and menu items").decode()); self.assertEqual(r["pairs"], 0); self.assertIn("Customer:", r["message"])


if __name__ == "__main__":
    unittest.main()
