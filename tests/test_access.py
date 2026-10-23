import unittest
from test_pack_agent import Rig
from speakvora_pack_agent import access as A, conversations as CV, reasoner as R, escalation as E


class Cleaning(unittest.TestCase):
    def test_a_stutter_becomes_the_words_meant(self):
        for raw, want in [("b-b-b-book a t-t-table, um, f-f-for four, o-outside", "book a table for four outside"), ("I I I want to b book a ta table for for four", "i want to book a table for four"),
                          ("buh buh book a table", "book a table"), ("f f four p people o outside please", "four people outside please"), ("FF4, P people, O outside P please.", "four people outside please"), ("Can I b-b-bring my d-d-dog", "can i bring my dog"), ("um uh I need to b b b book a table for for four people on s s s saturday", "i need to book a table for four people on saturday"),
                          ("what time are you open", "what time are you open"), ("I'd like to book an appointment", "i'd like to book an appointment"), ("I want to speak to a manager", "i want to speak to a manager")]:
            self.assertEqual(A.clean_speech(raw)[0], want, raw)

    def test_a_sentence_that_stops_in_the_middle_is_noticed(self):
        for t in ["book a table for", "i would like to", "my name is", "t"]:
            self.assertTrue(A.dangling(t), t)
        for t in ["book a table for four", "what are your hours", "thank you", "book a table", "four people outside please"]:
            self.assertFalse(A.dangling(t), t)

    def test_the_business_type_decides_the_way_and_the_owner_can_change_it(self):
        r = Rig(); self.addCleanup(r.close)
        r.agent.profile = "clinic"; self.assertEqual(A.preset(r.agent), "person_first")
        r.agent.profile = "food"; self.assertEqual(A.preset(r.agent), "text_first")
        r.agent.profile = "support"; self.assertEqual(A.preset(r.agent), "support_app")
        A.save(r.agent, "person_first"); self.assertEqual(A.view(r.agent)["by"], "owner"); self.assertEqual(A.preset(r.agent), "person_first")
        with self.assertRaises(ValueError): A.save(r.agent, "nonsense")

    def test_the_owners_ai_picks_a_way_from_what_it_knows_of_the_business(self):
        r = Rig(extra={"reasoner": {"provider": "x", "model": "m", "api_key": "k"}}); self.addCleanup(r.close)
        old = R._chat; R._chat = lambda cfg, system, user, n: ('{"preset": "person_first", "why": "A dental office needs to be sure it understood."}', {})
        try:
            r.agent.profile = "clinic"; v = A.suggest(r.agent)
        finally:
            R._chat = old
        self.assertEqual(v["preset"], "person_first"); self.assertEqual(v["by"], "your AI"); self.assertIn("dental", v["why"])


class OnTheCall(unittest.TestCase):
    def rig(self, profile="food", phone="+16465550123"):
        r = Rig(extra={"twilio": {"speech_input": True}, "facts": {"oncall_phone": phone}, "transcripts": {"enabled": True}}); self.addCleanup(r.close); r.agent.profile = profile; return r

    def say(self, r, said, sid="CA9"):
        return r.agent.handle_call({"From": "+16465550101", "CallSid": sid, "SpeechResult": said}, "menu", "")

    def test_a_caller_who_stutters_is_given_time_then_answered_and_it_is_all_recorded(self):
        r = self.rig()
        xml = self.say(r, "I I I want to b b book a t t table for")                                  # stops mid-sentence
        self.assertIn("Take your time", xml); self.assertIn('timeout="12"', xml)
        xml = self.say(r, "four people outside")                                                      # the rest, joined to the first part
        self.assertNotIn("Take your time", xml); self.assertNotIn("did not catch", xml)
        row = CV.get(r.agent, CV.list_(r.agent)["items"][0]["id"])
        said = " | ".join(t["text"] for t in row["turns"] if t["role"] == "caller")
        self.assertIn("understood as:", said); self.assertIn("book a table for four people outside", said)

    def test_a_stutter_in_a_complete_sentence_still_works_like_any_caller(self):
        r = self.rig(); xml = self.say(r, "w w what t t time are you o open", "CA10")
        self.assertNotIn("<Dial", xml); self.assertNotIn("did not catch", xml); self.assertIn("5-10 PM", xml)

    def test_a_caller_who_cannot_hear_well_gets_slower_louder_speech(self):
        r = self.rig(); xml = self.say(r, "I am hard of hearing can you speak up", "CA11")
        self.assertIn('volume="x-loud"', xml); self.assertIn('rate="slow"', xml); self.assertIn("speak louder and slower", xml); self.assertNotIn("text you now", xml)           # hard of hearing is not deaf: slower and louder, with a text on offer
        xml2 = self.say(r, "what time are you open", "CA11")
        self.assertIn('volume="x-loud"', xml2)                                                        # for the rest of the call

    def test_a_deaf_caller_is_texted_and_a_clinic_is_told(self):
        r = self.rig("clinic"); told = []
        r.agent._do_ai_actions = lambda who, todo, ch: told.append(todo)
        xml = self.say(r, "I am deaf please text me", "CA12")
        self.assertIn("text you now", xml); self.assertTrue(told and told[0][0]["type"] == "notify")
        r2 = self.rig("food"); told2 = []; r2.agent._do_ai_actions = lambda who, todo, ch: told2.append(todo)
        self.say(r2, "I am deaf please text me", "CA13"); self.assertFalse(told2)                      # a restaurant offers text without alerting anyone

    def test_press_star_for_a_text(self):
        r = self.rig(); xml = r.agent.handle_call({"From": "+16465550101", "CallSid": "CA14"}, "menu", "*")
        self.assertIn("text you now", xml)

    def test_a_clinic_connects_a_person_after_one_missed_word(self):
        r = self.rig("clinic"); self.say(r, "I I I um w w want", "CA15")                                 # stutter detected, mid-sentence: given time
        xml = r.agent.handle_call({"From": "+16465550101", "CallSid": "CA15", "SpeechResult": ""}, "menu", "")          # silence: what they managed to say is used, and it matches nothing
        self.assertIn("<Dial", xml); self.assertIn("<Number>+16465550123</Number>", xml)
        r2 = self.rig("food"); self.say(r2, "I I I um w w want", "CA16")
        xml2 = r2.agent.handle_call({"From": "+16465550101", "CallSid": "CA16", "SpeechResult": ""}, "menu", "")
        self.assertNotIn("<Dial", xml2)                                                                  # a restaurant asks again first


if __name__ == "__main__":
    unittest.main()
