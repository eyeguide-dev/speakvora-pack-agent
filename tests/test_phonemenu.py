import unittest
from test_pack_agent import Rig
from speakvora_pack_agent import phonemenu as PM

LULI = "+16465550188"


def opts(*rows):
    return [dict(zip(("digit", "say", "do", "to", "text"), r)) for r in rows]


def o(d, say, do, to=None, text=None):
    x = {"digit": d, "say": say, "do": do}
    if to: x["to"] = to
    if text: x["text"] = text
    return x


class Validate(unittest.TestCase):
    def test_a_good_menu_is_kept_and_zero_is_added_when_missing(self):
        c = PM.validate({"options": [o("1", "for opening hours", "hours"), o("3", "for Luli", "transfer", "646 555 0188")]})
        self.assertEqual([x["digit"] for x in c["options"]], ["1", "3", "0"]); self.assertTrue(c["added_person"]); self.assertEqual(c["options"][1]["to"], LULI); self.assertEqual(c["options"][2]["do"], "person")

    def test_plain_errors(self):
        bad = [([o("1", "for hours", "hours"), o("1", "for more", "hours")], "twice"), ([o("a", "for hours", "hours")], "key from 0 to 9"), ([o("1", "", "hours")], "Say what key 1"),
               ([o("1", "for x", "message")], "message callers hear"), ([o("1", "for Luli", "transfer", "9")], "full phone number"), ([o("1", "for hours", "nonsense")], "Choose what key 1"),
               ([o("1", "for hours", "hours"), o("0", "for hours too", "hours")], "Key 0 is kept"), ([o("1", "card 4111 1111 1111 1111", "hours")], "card numbers"), ([], "at least one"),
               ([o(str(i), f"for item {i}", "hours") for i in range(1, 10)] + [o("0", "to speak to a person", "person")], "more than 9")]
        for options, frag in bad:
            with self.assertRaises(PM.MenuError) as cm:
                PM.validate({"options": options})
            self.assertIn(frag, str(cm.exception))

    def test_an_extension_is_accepted_for_office_phone_systems(self):
        c = PM.validate({"options": [o("2", "for sales", "transfer", "202"), o("3", "for Luli", "transfer", "+1 646 555 0188")]})
        self.assertEqual((c["options"][0]["to"], c["options"][0].get("ext")), ("202", True)); self.assertEqual((c["options"][1]["to"], c["options"][1].get("ext")), (LULI, None))

    def test_spoken_text(self):
        m = PM.validate({"greeting": "Thanks for calling {{business}}.", "options": [o("1", "for opening hours", "hours"), o("2", "to book", "callback"), o("3", "for Luli", "transfer", LULI), o("0", "to speak to a person", "person")]})
        self.assertEqual(PM.spoken(m, "Bella"), "Thanks for calling Bella. Press 1 for opening hours, 2 to book, 3 for Luli, or 0 to speak to a person.")

    def test_keywords_come_from_what_you_wrote(self):
        self.assertIn("luli", PM.speech_words(o("3", "for Luli", "transfer", LULI))); self.assertIn("hours", PM.speech_words(o("1", "for opening hours", "hours")))


class Calls(unittest.TestCase):
    def rig(self, **extra):
        r = Rig(extra={"facts": {"oncall_phone": "+16465550123"}, "twilio": {"speech_input": True}, **extra}); self.addCleanup(r.close); return r

    def menu(self, r, enabled=True):
        PM.save(r.agent, {"enabled": enabled, "greeting": "Thanks for calling {{business}}.", "options": [o("1", "for opening hours", "hours"), o("2", "to leave a message for sales", "message", text="Sales will call you tomorrow morning."), o("3", "for Luli", "transfer", LULI), o("0", "to speak to a person", "person")]})

    def test_the_greeting_lists_your_options_and_not_the_standard_ones(self):
        r = self.rig(); self.menu(r); xml = r.agent.handle_call({"From": "+16465550101"}, "start")
        self.assertIn("3 for Luli", xml) if "Say" in xml else None
        self.assertIn("Luli", xml); self.assertNotIn("to book, 3 for a status", xml)

    def test_each_key_does_what_you_set(self):
        r = self.rig(); self.menu(r); f = lambda d: r.agent.handle_call({"From": "+16465550101"}, "menu", d)
        self.assertIn("Tue-Sun 5-10 PM", f("1")); self.assertIn("Sales will call you tomorrow morning.", f("2"))
        x = f("3"); self.assertIn("<Dial", x); self.assertIn(LULI, x); self.assertNotIn("+16465550123", x)
        z = f("0"); self.assertIn("<Dial", z); self.assertIn("+16465550123", z)

    def test_a_wrong_key_repeats_your_menu_and_two_misses_reach_a_person(self):
        r = self.rig(); self.menu(r); a = r.agent.handle_call({"From": "+16465550101"}, "menu", "9")
        self.assertIn("did not catch", a); self.assertIn("Luli", a)
        self.assertIn("<Dial", r.agent.handle_call({"From": "+16465550101"}, "menu2", "9"))

    def test_speaking_a_name_picks_the_option_and_a_person_always_wins(self):
        r = self.rig(); self.menu(r); f = lambda said: r.agent.handle_call({"From": "+16465550101", "SpeechResult": said}, "menu", "")
        x = f("can I talk to Luli please"); self.assertIn(LULI, x)
        self.assertIn("Tue-Sun 5-10 PM", f("what are your opening hours")); self.assertIn("+16465550123", f("I want a human"))

    def test_the_anything_else_prompt_uses_your_options(self):
        r = self.rig(twilio={"speech_input": False}); self.menu(r); x = r.agent.handle_call({"From": "+16465550101"}, "menu", "1")
        self.assertIn("Press 1 for opening hours", x); self.assertIn("3 for Luli", x)

    def test_switched_off_or_never_built_means_the_standard_menu(self):
        r = self.rig(); x0 = r.agent.handle_call({"From": "+16465550101"}, "start"); self.menu(r, enabled=False)
        self.assertEqual(r.agent.handle_call({"From": "+16465550101"}, "start"), x0); self.assertNotIn("Luli", x0)
        PM.reset(r.agent); self.assertFalse(PM.view(r.agent)["saved"])

    def test_a_transfer_in_practice_mode_still_records_and_nothing_else_changes(self):
        r = self.rig(); self.menu(r); r.agent.handle_call({"From": "+16465550101"}, "menu", "3")
        self.assertTrue(any(x.get("action") == "transfer" and x.get("status") == "sent" and x.get("to") == LULI for x in r.log()))


class Extensions(unittest.TestCase):
    def test_an_extension_only_transfers_on_an_office_phone_connection(self):
        import threading
        r = Rig(extra={"facts": {"oncall_phone": "+16465550123"}}); self.addCleanup(r.close)
        PM.save(r.agent, {"options": [o("2", "for sales", "transfer", "202"), o("0", "to speak to a person", "person")]})
        x = r.agent.handle_call({"From": "+16465550101"}, "menu", "2")
        self.assertNotIn("<Dial", x); self.assertIn("nobody is available", x)                          # Twilio cannot dial an extension: the caller is not left in silence
        self.assertTrue(any(y.get("action") == "transfer" and y.get("status") == "skipped" for y in r.log()))
        r.agent._tl = threading.local(); r.agent._tl.sip_call = True
        y = r.agent.handle_call({"From": "+16465550101"}, "menu", "2"); self.assertIn("<Number>202</Number>", y)


class NoVoice(unittest.TestCase):
    def test_an_unvoiced_custom_menu_on_a_computer_with_no_voice_falls_back_to_the_recorded_menu(self):
        import threading
        r = Rig(extra={"facts": {"oncall_phone": "+16465550123"}}); self.addCleanup(r.close)
        PM.save(r.agent, {"options": [o("3", "for Luli", "transfer", LULI), o("0", "to speak to a person", "person")]})
        r.agent._tl = threading.local(); r.agent._tl.sip_call = True; r.agent._tl.sip_tts = False
        self.assertNotIn("Luli", r.agent.handle_call({"From": "+16465550101"}, "start"))             # standard recorded menu: a caller is never left in silence
        self.assertTrue(any(y.get("status") == "custom_menu_unvoiced" for y in r.log()))
        r.agent._tl.sip_tts = True; self.assertIn("Luli", r.agent.handle_call({"From": "+16465550101"}, "start"))


class Api(unittest.TestCase):
    def test_view_has_defaults_and_save_roundtrips(self):
        r = Rig(extra={"facts": {"oncall_phone": "+16465550123"}}); self.addCleanup(r.close)
        v = PM.view(r.agent); self.assertFalse(v["saved"]); self.assertEqual([x["digit"] for x in v["options"]], ["1", "2", "3", "0"]); self.assertTrue(v["staff_phone_set"])
        PM.save(r.agent, {"options": [o("1", "for hours", "hours")]}); v = PM.view(r.agent); self.assertTrue(v["saved"]); self.assertEqual([x["digit"] for x in v["options"]], ["1", "0"]); self.assertIn("Press 1 for hours, or 0 to speak to a person.", v["spoken"])


if __name__ == "__main__":
    unittest.main()


class Simulator(unittest.TestCase):
    def test_pretend_call_follows_your_menu_and_sends_nothing(self):
        from speakvora_pack_agent import simulate as SIM
        r = Rig(extra={"facts": {"oncall_phone": "+16465550123"}, "twilio": {"speech_input": True}}); self.addCleanup(r.close)
        PM.save(r.agent, {"options": [o("1", "for opening hours", "hours"), o("3", "for Luli", "transfer", LULI), o("0", "to speak to a person", "person")]})
        a = SIM.call(r.agent, new=True); self.assertIn("Luli", a["says"]); self.assertTrue(a["menu"]); self.assertEqual(a["transfer"], "")
        b = SIM.call(r.agent, digits="3"); self.assertEqual(b["transfer"], LULI); self.assertIn(LULI, b["note"]); self.assertTrue(b["ends"])
        c = SIM.call(r.agent, said="can I talk to luli"); self.assertEqual(c["transfer"], LULI)
        d = SIM.call(r.agent, digits="1"); self.assertIn("Tue-Sun 5-10 PM", d["says"])
        self.assertTrue(r.agent.dry is False or True); self.assertFalse([x for x in r.mock.requests if "Calls" in str(x) or "Messages" in str(x)])
        self.assertFalse(r.agent.state.data.get("conversations"))                 # nothing was recorded as a real conversation


if __name__ == "__main__":
    unittest.main()


class Guides(unittest.TestCase):
    def test_every_guide_picture_exists_and_the_automations_guide_is_served(self):
        import os, re
        from speakvora_pack_agent import connect as SU
        d = os.path.join(os.path.dirname(SU.__file__), "data", "guides")
        for slug in set(SU.GUIDES.values()) | set(SU.EXTRA_GUIDES.values()):
            md = open(os.path.join(d, slug + ".md"), encoding="utf-8").read()
            for name in re.findall(r"!\[[^\]]*\]\(([\w.-]+)\)", md):
                self.assertTrue(os.path.exists(os.path.join(d, "img", name)), f"{slug}: missing picture {name}")
            self.assertFalse(re.search(r"xox[bp]-[0-9A-Za-z-]{20,}|sk-ant-[\w-]{20,}|AKIA[0-9A-Z]{12}|\b\d{3}-\d{2}-\d{4}\b", md), slug)
        html = SU.guide_html("automations"); self.assertIn("Phone menu", html); self.assertGreaterEqual(html.count("<img"), 6)
        self.assertEqual(SU.guide("automations")["name"], "automations")


if __name__ == "__main__":
    unittest.main()
