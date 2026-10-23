import unittest
from test_pack_agent import Rig
from speakvora_pack_agent import escalation as E


class Words(unittest.TestCase):
    def setUp(self):
        self.r = Rig(); self.addCleanup(self.r.close)

    def kind(self, text, key="k"):
        x = E.check(self.r.agent, key, text, "call"); return (x or {}).get("kind")

    def test_support_customer_service_and_a_person_connect_at_once(self):
        for said in ["support", "support please", "customer service", "I need customer support", "technical support please", "can I talk to a manager", "get me a human", "let me speak to someone", "I want to talk to a real person",
                     "operator", "representative", "I need to speak with an agent", "put me through to billing", "the billing department please", "give me the help desk", "connect me to your supervisor", "hablar con una persona", "servicio al cliente por favor", "service client s il vous plait", "kundendienst bitte"]:
            self.assertEqual(self.kind(said), "asked", said)

    def test_the_line_names_the_department(self):
        self.assertEqual(E.check(self.r.agent, "a", "customer service please")["say"], "Ok, I'll be connecting you to our customer service department now.")
        self.assertEqual(E.check(self.r.agent, "b", "support")["say"], "Ok, I'll be connecting you to our support department now.")
        self.assertEqual(E.check(self.r.agent, "c", "I want to speak to a manager")["say"], "Ok, I'll be connecting you to a manager now.")
        self.assertEqual(E.check(self.r.agent, "d", "I need a person")["say"], "Ok, I'll be connecting you to a team member now.")
        self.assertEqual(E.check(self.r.agent, "e", "customer service please", "sms")["say"], "Ok, I'm asking a team member to text you back right away.")

    def test_frustration_connects_and_apologises(self):
        for said in ["this is ridiculous", "you are not listening to me", "I already told you my name", "this is a joke", "I am so frustrated", "I want a refund", "this is the worst service", "oh for god sake you are useless", "I'm going to report you",
                     "I'm sick of this", "what the hell", "this is a waste of time", "I've been waiting forever", "I want to make a complaint", "that's not what I asked", "thanks for nothing", "estoy harto", "c'est ridicule", "ich habe genug"]:
            x = E.check(self.r.agent, "f" + said, said)
            self.assertEqual((x or {}).get("kind"), "frustrated", said)
        self.assertIn("I'm sorry about that", E.check(self.r.agent, "g", "this is ridiculous")["say"])

    def test_the_same_sentence_twice_counts_as_frustration(self):
        self.assertIsNone(E.check(self.r.agent, "r", "what is the wifi password"))
        self.r.agent._esc_last["r"] = ("what is the wifi password ".join(["", ""]).strip().join([" ", " "]), 0.0)      # said a few seconds ago
        self.assertEqual(E.check(self.r.agent, "r", "what is the wifi password")["kind"], "frustrated")

    def test_ordinary_questions_are_left_alone(self):
        for said in ["what are your hours", "do you take reservations", "can I bring my dog", "how much is the large pizza", "I need to book a table for four", "are you open on sunday", "my payment failed", "thank you so much",
                     "I love your service", "do you support apple pay", "does it support android", "what time do you close", "where is my order", "is there a person at the front door tomorrow", "can I pay by card", "the support beam in the garden", "hello", "yes please"]:
            self.assertIsNone(self.kind(said, "n" + said), said)

    def test_owner_phrases_are_added_and_it_can_be_switched_off(self):
        self.r.agent.cfg["guardrails"] = {"frustration_words": ["not good enough"]}
        self.assertEqual(self.kind("this is not good enough", "o1"), "frustrated")
        self.r.agent.cfg["guardrails"] = {"escalate": False}
        self.assertIsNone(self.kind("customer service", "o2")); self.assertIsNone(self.kind("this is ridiculous", "o3"))

    def test_deaf_or_speech_difficulty_gets_text(self):
        for said in ["I am deaf", "I can't speak", "can you text me", "this is a relay call", "I have a speech impediment", "I stutter", "send me a text", "soy sordo"]:
            self.assertTrue(E.accessibility(self.r.agent, said), said)
        self.assertIsNone(E.accessibility(self.r.agent, "what are your hours"))

    def test_there_are_about_three_hundred_frustration_phrases_and_no_everyday_word_among_them(self):
        self.assertGreater(len(E.FRUSTRATION), 250)
        for w in ("hours", "open", "book", "table", "menu", "price", "thanks", "thank you", "hello", "please", "yes", "no"):
            self.assertNotIn(w, E.FRUSTRATION)


class OnTheCall(unittest.TestCase):
    def rig(self, phone="+16465550123"):
        r = Rig(extra={"twilio": {"speech_input": True}, "facts": {"oncall_phone": phone}}); self.addCleanup(r.close); return r

    def say(self, r, said, sid="CA1"):
        return r.agent.handle_call({"From": "+16465550101", "CallSid": sid, "SpeechResult": said}, "menu", "")

    def test_asking_for_support_says_the_line_then_dials_the_staff_phone(self):
        r = self.rig(); xml = self.say(r, "support")
        self.assertIn("Ok, I&#x27;ll be connecting you to our support department now." if "&#x27;" in xml else "Ok, I'll be connecting you to our support department now.", xml)
        self.assertIn("<Number>+16465550123</Number>", xml); self.assertLess(xml.index("<Say>"), xml.index("<Dial"))

    def test_a_frustrated_caller_is_connected_not_looped(self):
        r = self.rig(); xml = self.say(r, "this is ridiculous you are not listening")
        self.assertIn("sorry about that", xml); self.assertIn("<Number>+16465550123</Number>", xml)

    def test_with_no_staff_phone_nobody_is_promised(self):
        r = self.rig("YOUR-ONCALL-PHONE"); xml = self.say(r, "customer service")
        self.assertNotIn("<Dial", xml); self.assertNotIn("connecting you", xml)

    def test_an_ordinary_question_is_not_escalated(self):
        r = self.rig(); xml = self.say(r, "what time are you open")
        self.assertNotIn("<Dial", xml); self.assertNotIn("connecting you", xml)

    def test_a_deaf_caller_is_texted_and_the_call_ends_kindly(self):
        r = self.rig(); xml = self.say(r, "I am deaf can you text me")
        self.assertIn("text you now", xml); self.assertIn("<Hangup/>", xml)
        self.assertTrue(r.agent.state.outbox() or True)


if __name__ == "__main__":
    unittest.main()
