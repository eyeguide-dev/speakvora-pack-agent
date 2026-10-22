import datetime as dt, json, unittest
from zoneinfo import ZoneInfo
from test_pack_agent import Rig
from speakvora_pack_agent import bookings as BK, converse, connect as SU

TZ = ZoneInfo("America/New_York")
EXTRA = {"bookings": {"enabled": True, "areas": {"inside": 8, "outside": 8}}, "reasoner": {"provider": "anthropic", "api_key": "k", "model": "m"}, "timezone": "America/New_York",
         "guardrails": {"voice_calls": True, "sms_replies": True, "allowed_actions": ["book", "notify"]}}


def friday(hour=19, minute=0, weeks=1):
    d = dt.datetime.now(TZ).date() + dt.timedelta(days=2)
    while d.weekday() != 4:
        d += dt.timedelta(days=1)
    d += dt.timedelta(weeks=weeks - 1)
    return dt.datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ)


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M")


def rig(**kw):
    r = Rig(extra={**EXTRA, **kw}); return r


class Rules(unittest.TestCase):
    def test_a_normal_request_fits_and_is_confirmed_with_a_code(self):
        r = rig(); self.addCleanup(r.close); a = r.agent
        out = BK.attempt(a, {"name": "Daniel Rivera", "party": 4, "start": iso(friday()), "area": "outside", "notes": "bringing a dog"}, "+15555550123")
        self.assertTrue(out["ok"]); self.assertIn("table for 4 outside", out["say"]); self.assertIn("Daniel Rivera", out["say"]); self.assertEqual(len(out["code"]), 4)
        self.assertEqual(BK.get(a, out["code"])["notes"], "bringing a dog")

    def test_missing_details_are_asked_for_never_guessed(self):
        r = rig(); self.addCleanup(r.close)
        for bad in ({"name": "", "party": 4, "start": iso(friday())}, {"name": "Dan", "party": 0, "start": iso(friday())}, {"name": "Dan", "party": 4, "start": "tonight"}):
            self.assertEqual(BK.attempt(r.agent, bad)["reason"], "incomplete")

    def test_a_full_area_offers_other_times_and_the_other_area(self):
        r = rig(); self.addCleanup(r.close); a = r.agent; t = friday()
        self.assertTrue(BK.attempt(a, {"name": "A", "party": 8, "start": iso(t), "area": "outside"})["ok"])
        out = BK.attempt(a, {"name": "B", "party": 4, "start": iso(t), "area": "outside"})
        self.assertFalse(out["ok"]); self.assertEqual(out["reason"], "full"); self.assertTrue(out["alternatives"]); self.assertIn("full", out["say"].lower()); self.assertIn("Would one of those work", out["say"])
        self.assertTrue(any(area == "inside" and ts == int(t.timestamp()) for ts, area in out["alternatives"]), "the same time inside is offered")

    def test_closed_days_hours_party_size_and_lead_time_are_enforced(self):
        r = rig(); self.addCleanup(r.close); a = r.agent
        mon = friday() + dt.timedelta(days=3); self.assertEqual(BK.check(a, int(mon.timestamp()), 2, "inside")["reason"], "closed")
        self.assertEqual(BK.check(a, int(friday(23, 30).timestamp()), 2, "inside")["reason"], "closed")
        self.assertEqual(BK.check(a, int(friday().timestamp()), 12, "inside")["reason"], "party")
        self.assertEqual(BK.check(a, int(time_now() + 60), 2, "inside")["reason"], "window")

    def test_a_calendar_event_that_closes_the_day_blocks_booking(self):
        r = rig(); self.addCleanup(r.close); a = r.agent; t = friday()
        class Cal:
            configured = True
            def events(self, s, e): return [{"title": "Private party", "start": int(t.timestamp()) - 3600, "end": int(t.timestamp()) + 7200}]
        a.outlook = Cal()
        self.assertEqual(BK.check(a, int(t.timestamp()), 2, "inside")["reason"], "blocked")

    def test_a_calendar_that_refuses_means_no_confirmation(self):
        r = rig(google_calendar={"mode": "oauth", "client_id": "c", "client_secret": "s", "refresh_token": "r", "allow_create": True}); self.addCleanup(r.close); a = r.agent
        class Refuse:
            configured = True
            def create(self, *x, **k): raise RuntimeError("calendar said no")
            def events(self, s, e): return []
        a.gcal = Refuse()
        out = BK.attempt(a, {"name": "Dan", "party": 2, "start": iso(friday()), "area": "inside"})
        self.assertFalse(out["ok"]); self.assertEqual(out["reason"], "calendar"); self.assertEqual(BK.upcoming(a), [])

    def test_cancel_frees_the_seats_and_the_feed_hides_phone_numbers(self):
        r = rig(); self.addCleanup(r.close); a = r.agent; t = friday()
        code = BK.attempt(a, {"name": "A", "party": 8, "start": iso(t), "area": "outside"}, "+15555550123")["code"]
        feed = BK.ics(a); self.assertIn("BEGIN:VEVENT", feed); self.assertIn(code, feed); self.assertNotIn("5555550123", feed)
        self.assertTrue(BK.cancel(a, code)); self.assertNotIn(code, BK.ics(a)); self.assertTrue(BK.attempt(a, {"name": "B", "party": 8, "start": iso(t), "area": "outside"})["ok"])


def time_now():
    import time; return time.time()


class OnThePhone(unittest.TestCase):
    def test_the_ai_books_and_the_caller_hears_the_real_confirmation_and_the_host_is_told(self):
        r = rig(); self.addCleanup(r.close); a = r.agent; t = friday()
        reply = {"say": "Let me book that for you.", "action": "continue", "do": [{"type": "book", "name": "Daniel Rivera", "party": 4, "start": iso(t), "area": "outside", "notes": "bringing a dog"}]}
        old = converse.R._chat; converse.R._chat = lambda *x, **k: (json.dumps(reply), {})
        self.addCleanup(lambda: setattr(converse.R, "_chat", old))
        out = converse.turn(a, "sms:+15555550123", "call", "a table for four outside Friday at seven under Daniel Rivera")
        self.assertIn("You are booked", out["say"]); self.assertNotIn("Let me book", out["say"]); self.assertEqual(len(BK.upcoming(a)), 1)
        self.assertTrue([x for x in out["do"] if x["type"] == "notify" and "New booking" in x["text"]]); self.assertFalse([x for x in out["do"] if x["type"] == "book"])

    def test_in_practice_mode_the_booking_is_kept_but_flagged_and_never_published(self):
        r = rig(dry_run=True); self.addCleanup(r.close); a = r.agent; t = friday()
        out = BK.attempt(a, {"name": "Dan", "party": 2, "start": iso(t), "area": "inside"}); self.assertTrue(out["ok"])
        self.assertTrue(BK.get(a, out["code"])["source"].startswith("practice")); self.assertNotIn(out["code"], BK.ics(a)); self.assertTrue(BK.view(a)["upcoming"][0]["practice"])

    def test_a_slow_ai_keeps_the_caller_company_up_to_the_owners_limit_then_hands_off(self):
        import time
        r = rig(guardrails={"voice_calls": True, "sms_replies": True, "allowed_actions": ["book", "notify"], "max_wait_seconds": 20}); self.addCleanup(r.close); a = r.agent
        for waited, want_handoff in ((8, False), (25, True)):
            pend = converse.Pending(); pid = f"p{waited}"; a.__dict__.setdefault("_pending", {})[pid] = [pend, time.time() - waited, {"From": "+15555550123"}, 0, "call:x"]
            a._talk_xml = lambda res, p0, _w=want_handoff: "HANDOFF" if res.get("action") == "handoff" else "ok"
            xml = a.call_wait(pid, {"From": "+15555550123"})
            self.assertEqual("HANDOFF" in xml, want_handoff, waited)

    def test_booking_off_means_the_ai_cannot_book(self):
        r = rig(bookings={"enabled": False}); self.addCleanup(r.close); a = r.agent
        self.assertNotIn("book", converse.usable_actions(a, converse._cfg(a), "call"))

    def test_the_dashboard_saves_the_rules_and_lets_the_ai_use_them(self):
        r = Rig(extra={"reasoner": {"provider": "anthropic", "api_key": "k", "model": "m"}}); self.addCleanup(r.close); a = r.agent
        out = BK.save(a, {"enabled": True, "days": [1, 2, 3], "open": "18:00", "last_seating": "20:30", "close": "22:00", "slot_minutes": 120, "max_party": 6, "lead_minutes": 30, "days_ahead": 14, "areas": {"Patio": 20, "Inside": 30}})
        self.assertTrue(out["settings"]["enabled"]); self.assertEqual(out["settings"]["areas"], {"patio": 20, "inside": 30}); self.assertIn("book", a.cfg["guardrails"]["allowed_actions"])
        with self.assertRaises(SU.SetupError):
            BK.save(a, {"enabled": True, "open": "tonight"})


if __name__ == "__main__":
    unittest.main()
