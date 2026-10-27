"""The acceptance test from the support feedback: a caller starts a booking, changes their mind, asks for a person; the person gets the corrected details and the summary says exactly what was booked."""
import datetime as dt, json, unittest
from zoneinfo import ZoneInfo
from test_pack_agent import Rig
from speakvora_pack_agent import bookings as BK, callstate as CS, converse

TZ = ZoneInfo("America/New_York")
EXTRA = {"bookings": {"enabled": True, "areas": {"inside": 8, "outside": 8}}, "reasoner": {"provider": "anthropic", "api_key": "k", "model": "m"}, "timezone": "America/New_York",
         "guardrails": {"voice_calls": True, "sms_replies": True, "allowed_actions": ["book", "notify"]}}


def next_weekday(wd, hour=19, weeks=1):
    d = dt.datetime.now(TZ).date() + dt.timedelta(days=2)
    while d.weekday() != wd:
        d += dt.timedelta(days=1)
    d += dt.timedelta(weeks=weeks - 1)
    return dt.datetime(d.year, d.month, d.day, hour, 0, tzinfo=TZ)


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M")


class Script:
    """Replaces the AI with a fixed list of replies, one per turn, and remembers the prompts it was shown."""
    def __init__(self, test, replies):
        self.replies = list(replies); self.prompts = []
        self.old = converse.R._chat; converse.R._chat = self; test.addCleanup(lambda: setattr(converse.R, "_chat", self.old))

    def __call__(self, cfg, system, user, max_tokens=220, **k):
        self.prompts.append(user); return json.dumps(self.replies.pop(0)), {}


class AcceptanceTest(unittest.TestCase):
    def test_change_of_mind_then_a_person_gets_the_corrected_details_and_the_summary_is_honest(self):
        r = Rig(extra=EXTRA); self.addCleanup(r.close); a = r.agent; key = "call:CA1"; wed, thu = next_weekday(2), next_weekday(3)
        Script(self, [
            {"say": "Let me book that.", "action": "continue", "facts": {"topic": "table", "name": "Daniel Rivera", "party": 4, "start": iso(wed), "area": "outside"},
             "do": [{"type": "book", "name": "Daniel Rivera", "party": 4, "start": iso(wed), "area": "outside"}]},
        ])
        t1 = converse.turn(a, key, "call", "a table for four outside Wednesday at seven, Daniel Rivera")
        self.assertIn("You are booked", t1["say"]); code = BK.upcoming(a)[0]["code"]; self.assertEqual(len(BK.upcoming(a)), 1)
        Script(self, [{"say": "Sure.", "action": "continue", "facts": {"start": iso(thu)}, "corrected": ["start"], "do": [{"type": "amend_booking", "code": code, "start": iso(thu)}]}])
        t2 = converse.turn(a, key, "call", "actually make it Thursday")
        self.assertIn("I changed it", t2["say"]); self.assertEqual(t2["corrected"], ["start"]); up = BK.upcoming(a); self.assertEqual(len(up), 1, "no second booking"); self.assertEqual(up[0]["code"], code)
        self.assertEqual(dt.datetime.fromtimestamp(up[0]["start"], TZ).weekday(), 3)
        t3 = converse.turn(a, key, "call", "can I talk to a person please")
        self.assertEqual(t3["action"], "handoff"); b = t3["brief"]
        self.assertIn("Thursday", b["text"]); self.assertIn("booked and confirmed", b["text"]); self.assertIn(code, b["text"]); self.assertIn(" ".join(code), b["spoken"]); self.assertIn("changed the day and time from Wednesday at 7 PM to Thursday at 7 PM", b["text"])
        self.assertTrue(any(c["field"] == "start" for c in b["corrections"]))
        summ = CS.summary(a, key)
        self.assertIn("Booked:", summ); self.assertIn(code, summ); self.assertIn("Thursday", summ); self.assertIn("A person was requested", summ); self.assertNotIn("No booking was made", summ)

    def test_a_booking_that_was_refused_is_never_reported_as_booked(self):
        r = Rig(extra=EXTRA); self.addCleanup(r.close); a = r.agent; key = "call:CA2"
        mon = next_weekday(0)                                                  # closed on Mondays
        Script(self, [{"say": "Let me try.", "action": "continue", "facts": {"topic": "table", "party": 2, "start": iso(mon)}, "do": [{"type": "book", "name": "Sam", "party": 2, "start": iso(mon), "area": "inside"}]}])
        t = converse.turn(a, key, "call", "a table for two Monday at seven, Sam")
        self.assertNotIn("You are booked", t["say"]); self.assertEqual(len(BK.upcoming(a)), 0)
        s = CS.summary(a, key); self.assertIn("Not booked", s); self.assertNotIn("Booked:", s)
        t2 = converse.turn(a, key, "call", "get me a person"); self.assertIn("NOT booked", t2["brief"]["text"])

    def test_a_handoff_still_runs_the_booking_the_caller_already_asked_for(self):
        r = Rig(extra=EXTRA); self.addCleanup(r.close); a = r.agent; key = "call:CA3"; thu = next_weekday(3)
        Script(self, [{"say": "One moment, I will get a person.", "action": "handoff", "facts": {"party": 2, "start": iso(thu)}, "do": [{"type": "book", "name": "Kim", "party": 2, "start": iso(thu), "area": "inside"}]}])
        t = converse.turn(a, key, "call", "book Thursday at seven for two under Kim and I need to ask about a refund")
        self.assertEqual(t["action"], "handoff"); self.assertEqual(len(BK.upcoming(a)), 1); self.assertIn("booked and confirmed", t["brief"]["text"])

    def test_only_a_booking_made_on_this_conversation_can_be_changed(self):
        r = Rig(extra=EXTRA); self.addCleanup(r.close); a = r.agent; thu = next_weekday(3)
        other = BK.attempt(a, {"name": "Someone Else", "party": 2, "start": iso(thu), "area": "inside"}, "+15555550999")
        Script(self, [{"say": "Sure.", "action": "continue", "do": [{"type": "cancel_booking", "code": other["code"]}]}])
        t = converse.turn(a, "call:CA4", "call", "cancel booking " + other["code"])
        self.assertEqual(BK.get(a, other["code"])["status"], "confirmed"); self.assertEqual(t["action"], "handoff")

    def test_a_correction_that_does_not_fit_leaves_the_original_booking_alone(self):
        r = Rig(extra=EXTRA); self.addCleanup(r.close); a = r.agent; thu = next_weekday(3); mon = next_weekday(0)
        b = BK.attempt(a, {"name": "Kim", "party": 2, "start": iso(thu), "area": "inside"}, "+15555550123")
        before = BK.get(a, b["code"])["start"]
        out = BK.amend(a, b["code"], {"start": iso(mon)}, "+15555550123")
        self.assertFalse(out["ok"]); self.assertIn("original booking is still", out["say"]); self.assertEqual(BK.get(a, b["code"])["start"], before)
        self.assertEqual(BK.amend(a, b["code"], {"party": 3}, "+15555550777")["reason"], "not_yours")


if __name__ == "__main__":
    unittest.main()
