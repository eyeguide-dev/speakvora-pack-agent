"""The support-call upgrade through the phone path (handle_call): corrected details reach the person who picks up, an unanswered transfer becomes a task, retried webhooks do nothing twice, and the call record says what was booked."""
import html, json, re, time, unittest
from test_pack_agent import Rig
from test_support_flow import EXTRA, Script, iso, next_weekday
from speakvora_pack_agent import bookings as BK, callstate as CS, conversations as CV, converse

PHONE = "+16465550142"
CALL_EXTRA = {**EXTRA, "twilio": {"speech_input": True}, "facts": {"oncall_phone": "+16465550123", "phone": "+16465550199", "hours": "Tue-Sun 5-10 PM.", "address": "12 Main St"},
              "slack": {"channel": "#front"}}


def rig():
    r = Rig(extra={**CALL_EXTRA, "guardrails": {"voice_calls": True, "sms_replies": True, "allowed_actions": ["book", "notify"]}}); return r


def say(r, text, sid="CA9", **kw):
    return r.agent.handle_call({"From": PHONE, "CallSid": sid, "SpeechResult": text, **kw}, "menu", "")


def slack_texts(r):
    out = []
    for q in r.mock.requests:
        body = q.get("json")
        if isinstance(body, dict) and body.get("text"):
            out.append(body["text"])
    return out


class PhonePath(unittest.TestCase):
    def test_the_person_who_picks_up_hears_the_corrected_details_and_an_unanswered_transfer_becomes_a_task(self):
        r = rig(); self.addCleanup(r.close); a = r.agent; wed, thu = next_weekday(2), next_weekday(3)
        Script(self, [{"say": "Let me book that.", "action": "continue", "facts": {"topic": "table", "name": "Daniel Rivera", "party": 4, "start": iso(wed), "area": "outside"},
                       "do": [{"type": "book", "name": "Daniel Rivera", "party": 4, "start": iso(wed), "area": "outside"}]}])
        a.handle_call({"From": PHONE, "CallSid": "CA9"}, "start", "")
        x1 = say(r, "a table for four outside Wednesday at seven under Daniel Rivera"); self.assertIn("You are booked", html.unescape(x1)); self.assertIn("partialResultCallback", x1)
        code = BK.upcoming(a)[0]["code"]
        Script(self, [{"say": "Sure.", "action": "continue", "facts": {"start": iso(thu)}, "corrected": ["start"], "do": [{"type": "amend_booking", "code": code, "start": iso(thu)}]}])
        x2 = say(r, "actually make that Thursday"); self.assertIn("I changed it", html.unescape(x2)); self.assertEqual(len(BK.upcoming(a)), 1)
        x3 = say(r, "can I talk to a person")
        m = re.search(r'<Number url="([^"]+)"', x3); self.assertTrue(m, x3); self.assertIn("/twilio/call/whisper/", m.group(1)); self.assertIn("+16465550123", x3)
        wid = m.group(1).rsplit("/", 1)[1]; w = html.unescape(a.handle_whisper(wid))
        self.assertIn("Thursday", w); self.assertIn("booked and confirmed", w); self.assertIn(" ".join(code), w)
        self.assertTrue(any(code in t and "Thursday" in t and " ".join(code) not in t for t in slack_texts(r)), "the team text shows the code plainly")
        self.assertTrue(any("Thursday" in t and "Transferring" in t for t in slack_texts(r)), "the team was told too")
        done = a.handle_dial_done({"From": PHONE, "CallSid": "CA9", "DialCallStatus": "no-answer"})
        self.assertIn("call you back", html.unescape(done)); L = CS.get(a, "call:CA9", create=False)
        self.assertEqual(L["transfer"]["state"], "no_answer"); task = [t for t in L["tasks"] if t["kind"] == "callback"][0]; self.assertEqual(task["status"], "open"); self.assertIn("Thursday", task["text"]); self.assertGreater(task["due"], time.time())
        a.handle_dial_done({"From": PHONE, "CallSid": "CA9", "DialCallStatus": "no-answer"}); self.assertEqual(len([t for t in CS.get(a, "call:CA9")["tasks"] if t["kind"] == "callback"]), 1, "a repeat does not create a second task")
        rec = CV.list_(a)["items"][0] if isinstance(CV.list_(a), dict) and CV.list_(a).get("items") else None
        summ = CS.summary(a, "call:CA9"); self.assertIn("Booked:", summ); self.assertIn("Nobody answered the transfer", summ)

    def test_a_retried_webhook_is_answered_from_memory_and_runs_nothing_twice(self):
        r = rig(); self.addCleanup(r.close); a = r.agent; thu = next_weekday(3)
        sc = Script(self, [{"say": "Let me book that.", "action": "continue", "facts": {"party": 2, "start": iso(thu)}, "do": [{"type": "book", "name": "Kim", "party": 2, "start": iso(thu), "area": "inside"}]},
                           {"say": "should never be asked", "action": "continue"}])
        first = say(r, "a table for two Thursday at seven under Kim", sid="CA7", _idem="tok-1"); again = say(r, "a table for two Thursday at seven under Kim", sid="CA7", _idem="tok-1")
        self.assertEqual(first, again); self.assertEqual(len(sc.prompts), 1, "the AI was asked once"); self.assertEqual(len(BK.upcoming(a)), 1)

    def test_a_confirmation_the_caller_talked_over_is_flagged_for_the_person_on_the_phone(self):
        r = rig(); self.addCleanup(r.close); a = r.agent; thu = next_weekday(3)
        Script(self, [{"say": "Let me book that.", "action": "continue", "facts": {"party": 2, "start": iso(thu)}, "do": [{"type": "book", "name": "Kim", "party": 2, "start": iso(thu), "area": "inside"}]}])
        say(r, "a table for two Thursday at seven under Kim", sid="CA8")
        t = CS.last_turn(a, "call:CA8"); self.assertTrue(t["consequential"]); self.assertGreater(t["est_s"], 3)
        a.handle_partial({"CallSid": "CA8", "From": PHONE, "UnstableSpeechResult": "no"})                         # the caller starts talking right after the reply began
        self.assertEqual(t["heard"], "cut_off"); self.assertLess(t["heard_pct"], 60)
        b = CS.brief(a, "call:CA8"); self.assertTrue(b["unheard"]); self.assertIn("repeat it", b["text"])

    def test_a_reply_that_played_to_the_end_is_not_flagged(self):
        r = rig(); self.addCleanup(r.close); a = r.agent; thu = next_weekday(3)
        Script(self, [{"say": "Let me book that.", "action": "continue", "facts": {"party": 2, "start": iso(thu)}, "do": [{"type": "book", "name": "Kim", "party": 2, "start": iso(thu), "area": "inside"}]},
                      {"say": "Anything else?", "action": "continue"}])
        say(r, "a table for two Thursday at seven under Kim", sid="CA6"); t = CS.last_turn(a, "call:CA6"); t["sent_at"] -= 30                    # a long time passes before the caller says anything
        a.handle_partial({"CallSid": "CA6", "From": PHONE}); self.assertEqual(t["heard"], "full"); self.assertFalse(CS.unheard_confirmations(a, "call:CA6"))


if __name__ == "__main__":
    unittest.main()
