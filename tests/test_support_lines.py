"""Asking Speakvora for a line: it is voiced once right away through the owner's key, stored, mapped to the slot and playable at once; the same words are never voiced or charged twice; practice mode and other languages stay a plain request."""
import os, unittest
from test_pack_agent import Rig
from speakvora_pack_agent import dashboard as D, learned as L, sharing as SH

CUSTOM = {"custom": {"when": "When a customer asks about parking", "text": "We have free parking right behind the building."}}


class Instant(unittest.TestCase):
    def setUp(self):
        self.voiced = []; self._v, self._r, self._k = L._voice, SH.web.request, SH._key
        L._voice = lambda agent, text: (self.voiced.append(text) or (b"ID3audio", ".mp3"))
        SH.web.request = lambda *a, **k: (200, {"note": "Queued."})
        SH._key = lambda agent=None: "svk_test"

    def tearDown(self):
        L._voice, SH.web.request, SH._key = self._v, self._r, self._k

    def rig(self, **kw):
        r = Rig(**kw); self.addCleanup(r.close); return r

    def test_a_requested_line_is_voiced_once_right_away_and_plays_from_its_slot(self):
        r = self.rig(); a = r.agent
        out = D.request_phrases(a, CUSTOM); self.assertTrue(out["sent"]); slot = out["slots"][0]; self.assertEqual(out["ready"], [slot]); self.assertIn("ready now", out["message"])
        self.assertEqual(self.voiced, ["We have free parking right behind the building."]); it = a.pack.get(slot); self.assertTrue(os.path.exists(a.pack.audio_path(slot))); self.assertIn("free parking", a.pack.text(slot))
        again = D.request_phrases(a, CUSTOM); self.assertEqual(self.voiced.__len__(), 1, "the same words are never voiced twice")
        self.assertEqual(L.load(a)["spent"] and sum(L.load(a)["spent"].values()), len(CUSTOM["custom"]["text"]), "charged once")

    def test_a_line_that_is_already_in_the_library_is_mapped_without_a_new_voicing_or_charge(self):
        r = self.rig(); a = r.agent
        L._store(a, "We have free parking right behind the building.", "typed"); spent = sum(L.load(a)["spent"].values())
        out = L.instant_line(a, "custom_parking", "We have free parking right behind the building."); self.assertTrue(out["ready"] and out["cached"]); self.assertEqual(len(self.voiced), 1); self.assertEqual(sum(L.load(a)["spent"].values()), spent)
        self.assertIn("free parking", a.pack.text("custom_parking"))

    def test_practice_mode_other_languages_bad_wording_and_the_budget_stay_plain_requests(self):
        r = self.rig(dry=True); self.assertEqual(L.instant_line(r.agent, "custom_x1", "We have free parking right behind the building.")["why"], "practice_mode"); self.assertEqual(self.voiced, [])
        r = self.rig(); a = r.agent
        self.assertEqual(L.instant_line(a, "custom_x2", "Call me at 555 123 4567 about the table")["why"], "wording"); self.assertEqual(L.instant_line(a, "Bad Slot!", "We have free parking right behind the building.")["why"], "bad_slot")
        r2 = self.rig(extra={"guardrails": {"phrase_chars_per_month": 20}}); out = L.instant_line(r2.agent, "custom_x3", "We have free parking right behind the building."); self.assertFalse(out["ready"]); self.assertIn("budget", out["why"])
        self.assertEqual(self.voiced, [])
        r3 = self.rig(lang="es"); out = D.request_phrases(r3.agent, {"slots": [g["slot"] for g in D._gaps(r3.agent)][:1]}) if D._gaps(r3.agent) else {"ready": []}; self.assertEqual(out["ready"], [])

    def test_no_key_means_a_plain_request_and_nothing_is_voiced(self):
        SH._key = lambda agent=None: ""
        r = self.rig(); out = D.request_phrases(r.agent, CUSTOM); self.assertEqual(out["ready"], []); self.assertEqual(self.voiced, [])


if __name__ == "__main__":
    unittest.main()
