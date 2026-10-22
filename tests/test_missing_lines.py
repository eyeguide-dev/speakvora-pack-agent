import unittest
from test_pack_agent import Rig


class MissingLine(unittest.TestCase):
    def test_a_line_the_pack_does_not_have_falls_back_to_plain_words_and_is_logged_once(self):
        r = Rig(); self.addCleanup(r.close); a = r.agent
        a.pack.slots.pop("reservation_help", None); a.pack.by_id = {k: v for k, v in a.pack.by_id.items() if v.get("slot") != "reservation_help"}
        reply = a._handle_sms({"From": "+16465550101", "Body": "reserve"})
        self.assertIn("reservation", reply.lower()); self.assertTrue(r.mock.calls("chat.postMessage"), "the team is still told")
        a._handle_sms({"From": "+16465550102", "Body": "reserve"})
        warn = [x for x in r.log() if x.get("action") == "missing_line"]; self.assertEqual(len(warn), 1); self.assertEqual(warn[0]["slot"], "reservation_help")


if __name__ == "__main__":
    unittest.main()
