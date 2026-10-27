"""What the AI learned fills the settings only after the owner approves it, only where they are still empty, and shows up straight away."""
import unittest
from test_pack_agent import Rig
from speakvora_pack_agent import brain


def learned(a, hours="Tue to Sun, 5 to 10 PM", website="https://bella.example"):
    d = brain.load(a); d.update(status="needs_review", website=website, profile={"summary": "A family restaurant.", "tone": "warm", "hours": hours, "services": ["dine-in", "takeout", "catering"], "policies": ["Reservations are held for 15 minutes", "Parking is free in the east lot"], "faqs": [], "unknowns": []}); brain.save(a, d)


class Sync(unittest.TestCase):
    def rig(self, facts):
        r = Rig(extra={"facts": facts}); self.addCleanup(r.close); return r.agent

    def test_nothing_is_filled_before_the_owner_approves_and_everything_empty_is_filled_after(self):
        a = self.rig({"hours": "YOUR-HOURS", "info": ""}); learned(a); self.assertEqual(a.cfg["facts"]["hours"], "YOUR-HOURS", "before approval nothing changes")
        d = brain.approve(a); self.assertEqual(d["filled"], ["hours", "info", "website"]); f = a.cfg["facts"]
        self.assertEqual(f["hours"], "Tue to Sun, 5 to 10 PM"); self.assertEqual(f["website"], "https://bella.example"); self.assertIn("We offer dine-in, takeout, catering.", f["info"]); self.assertIn("Parking is free in the east lot.", f["info"])
        import json, os; saved = json.load(open(os.path.join(os.path.dirname(a.state.dir), "agent.json"))); self.assertEqual(saved["facts"]["hours"], "Tue to Sun, 5 to 10 PM")

    def test_what_the_owner_typed_is_never_overwritten(self):
        a = self.rig({"hours": "Mon to Fri, 9 to 5", "info": "Our own note.", "website": "https://mine.example"}); learned(a); d = brain.approve(a)
        self.assertEqual(d["filled"], []); self.assertEqual(a.cfg["facts"]["hours"], "Mon to Fri, 9 to 5"); self.assertEqual(a.cfg["facts"]["info"], "Our own note."); self.assertEqual(a.cfg["facts"]["website"], "https://mine.example")

    def test_approving_twice_or_with_nothing_learned_is_harmless(self):
        a = self.rig({"hours": ""}); learned(a, hours="", website=""); d = brain.approve(a); self.assertEqual(d["filled"], ["info"]); self.assertEqual(brain.approve(a)["filled"], [])
        with self.assertRaises(ValueError): brain.approve(self.rig({}))


if __name__ == "__main__":
    unittest.main()
