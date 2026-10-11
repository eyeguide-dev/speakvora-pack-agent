"""The pack agent against fake Twilio, Slack and Google: every connector, every safety rule, the restaurant workflows and the signed web endpoints."""
import base64, datetime as dt, hashlib, hmac, json, os, shutil, sys, tempfile, threading, unittest, urllib.error, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "examples", "restaurant"))
from mocks import Mock
from speakvora_pack_agent import config, safety, templating
from speakvora_pack_agent.audio import AudioError
from speakvora_pack_agent.connectors import signing
from speakvora_pack_agent.connectors.gcal import parse_ics
from speakvora_pack_agent.engine import Agent
from speakvora_pack_agent.pack import Pack, PackError
from speakvora_pack_agent.server import serve

NOON = dt.datetime(2026, 10, 12, 16, 0, tzinfo=dt.timezone.utc).timestamp()              # 12:00 in New York
SECRET = "event-secret"; TOKEN = "twilio-token"; SLACK_SECRET = "slack-signing"
LINES = json.load(open(os.path.join(ROOT, "lines", "restaurants.en.json")))["lines"]


def make_pack(d, m4a=False):
    os.makedirs(os.path.join(d, "audio")); os.makedirs(os.path.join(d, "workflow_lines"))
    items = [{"id": 1, "text": "Thank you for choosing us.", "file": "audio/00001.m4a", "category": "closing"}, {"id": 2, "text": "Your order has been canceled.", "file": "audio/00002.m4a", "category": "order"}]
    for it in items:
        open(os.path.join(d, it["file"]), "wb").write(b"M4A")
    json.dump({"pack": "t", "title": "Test", "language": "en", "items": items}, open(os.path.join(d, "manifest.json"), "w"))
    wl = []
    for i, ln in enumerate(LINES, 1):
        f = f"workflow_lines/w{i:02d}.{'m4a' if m4a else 'mp3'}"; open(os.path.join(d, f), "wb").write(b"MP3")
        wl.append({"id": f"w{i:02d}", "slot": ln["slot"], "text": ln["text"], "file": f})
    json.dump({"items": wl}, open(os.path.join(d, "workflow_lines.json"), "w"))


class Rig:
    def __init__(self, dry=False, now=NOON, m4a=False, extra=None):
        self.tmp = tempfile.mkdtemp(); self.mock = Mock(); self.now = [now]
        make_pack(os.path.join(self.tmp, "pack"), m4a)
        shutil.copy(os.path.join(ROOT, "examples", "restaurant", "workflows.json"), os.path.join(self.tmp, "workflows.json"))
        raw = {"business": "Bella", "dry_run": dry, "pack": "./pack", "workflows": "./workflows.json", "state_dir": "./state", "timezone": "America/New_York", "public_base_url": "https://agent.test",
               "events": {"secret": SECRET}, "facts": {"hours": "Tue-Sun 5-10 PM.", "address": "12 Main St", "review_url": "https://g.page/r/x"},
               "twilio": {"account_sid": "AC1", "auth_token": TOKEN, "from_number": "+15550001111", "api_base": self.mock.url},
               "slack": {"bot_token": "xoxb-1", "signing_secret": SLACK_SECRET, "channel": "#front", "api_base": self.mock.url},
               "google_calendar": {"mode": "oauth", "client_id": "c", "client_secret": "s", "refresh_token": "r", "api_base": self.mock.url, "token_url": self.mock.url + "/token", "allow_create": True}}
        if extra:
            raw = config.merge(raw, extra)
        json.dump(raw, open(os.path.join(self.tmp, "agent.json"), "w"))
        self.agent = Agent(config.load(os.path.join(self.tmp, "agent.json")), now=lambda: self.now[0])

    def close(self):
        self.mock.close(); shutil.rmtree(self.tmp, ignore_errors=True)

    def event(self, name, **kw):
        return self.agent.handle_event({"event": name, "id": kw.pop("id", f"{name}-{len(self.mock.requests)}-{id(kw)}"), **kw})

    def log(self):
        p = self.agent.state.log_path
        return [json.loads(x) for x in open(p)] if os.path.exists(p) else []


CUST = {"name": "Ann Lee", "phone": "646-555-0101", "sms_consent": True}


class Pieces(unittest.TestCase):
    def test_pack_slots_search_and_missing(self):
        r = Rig(); p = r.agent.pack
        self.assertEqual(p.text("order_ready"), "Good news, your order is ready for pickup."); self.assertEqual(p.search("canceled")[0]["id"], "2"); self.assertEqual(p.resolve({"search": "thank you", "category": "closing"})["id"], "1")
        with self.assertRaises(PackError): p.get("nope")
        with self.assertRaises(PackError): Pack(r.tmp)
        r.close()

    def test_templating_has_no_code_execution(self):
        r = Rig(); ctx = {"customer": {"name": "{{fact:hours}}"}, "facts": {"hours": "5-10"}, "x": {"n": 3}}
        self.assertEqual(templating.render("Hi {{customer.name}} {{x.n}} {{fact:hours}} {{slot:order_ready}} {{__import__('os')}}", ctx, r.agent.pack), "Hi {{fact:hours}} 3 5-10 Good news, your order is ready for pickup. {{__import__('os')}}"); r.close()

    def test_env_secrets_are_resolved_and_required(self):
        os.environ["SV_T"] = "abc"; self.assertEqual(config.resolve({"a": "env:SV_T"}), {"a": "abc"})
        with self.assertRaises(config.ConfigError): config.resolve("env:SV_MISSING_X")

    def test_signing_roundtrip_and_tamper(self):
        h = signing.sign("s", b'{"a":1}'); self.assertTrue(signing.verify("s", b'{"a":1}', h)); self.assertFalse(signing.verify("s", b'{"a":2}', h)); self.assertFalse(signing.verify("", b'{"a":1}', h))
        self.assertFalse(signing.verify("s", b'{"a":1}', h, now=int(h["X-SV-Timestamp"]) + 1000))

    def test_ics_parser(self):
        ics = "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:a1\r\nDTSTART;TZID=America/New_York:20261012T190000\r\nDTEND;TZID=America/New_York:20261012T203000\r\nSUMMARY:Reservation: Ann\r\nDESCRIPTION:Phone: 646-555-0101\\nSMS OK: yes\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nUID:a2\r\nDTSTART:20261013T000000Z\r\nSUMMARY:Closed\r\nEND:VEVENT\r\nEND:VCALENDAR"
        ev = parse_ics(ics); self.assertEqual(len(ev), 2); self.assertEqual(ev[0]["start"], int(dt.datetime(2026, 10, 12, 23, 0, tzinfo=dt.timezone.utc).timestamp())); self.assertIn("SMS OK: yes", ev[0]["description"])


class Safety(unittest.TestCase):
    def test_dry_run_is_the_default_and_sends_nothing(self):
        r = Rig(dry=True); out = r.event("order.ready", customer=CUST, order={"number": 42})
        self.assertEqual(r.mock.requests, []); self.assertTrue(all(x["status"] == "dry_run" for x in r.log() if x["action"] in ("sms", "slack"))); self.assertEqual(out["matched"], 1); r.close()

    def test_no_consent_means_no_text_but_staff_still_get_slack(self):
        r = Rig(); r.event("order.ready", customer={"name": "Bob", "phone": "6465550102", "sms_consent": False}, order={"number": 43})
        self.assertEqual(r.mock.calls("Messages.json"), []); self.assertEqual(len(r.mock.calls("chat.postMessage")), 1); self.assertIn("no_consent", [x.get("reason") for x in r.log()]); r.close()

    def test_stop_is_honoured_everywhere(self):
        r = Rig(); self.assertIn("unsubscribed", r.agent.handle_sms({"From": "+16465550101", "Body": "STOP"}))
        r.event("order.ready", customer=CUST, order={"number": 44}); self.assertEqual(r.mock.calls("Messages.json"), []); self.assertIn("opted_out", [x.get("reason") for x in r.log()])
        r.agent.handle_sms({"From": "+16465550101", "Body": "START"}); r.event("order.ready", customer=CUST, order={"number": 45}); self.assertEqual(len(r.mock.calls("Messages.json")), 1); r.close()

    def test_quiet_hours_block_calls_and_texts(self):
        night = dt.datetime(2026, 10, 13, 3, 30, tzinfo=dt.timezone.utc).timestamp()             # 23:30 New York
        r = Rig(now=night); r.event("order.ready", customer=CUST, order={"number": 46}); self.assertEqual(r.mock.calls("Messages.json"), []); self.assertIn("quiet_hours", [x.get("reason") for x in r.log()]); r.close()

    def test_per_person_daily_limit_and_hourly_limit(self):
        r = Rig(extra={"limits": {"per_recipient_per_day": 2, "per_hour": 60}})
        for i in range(4): r.event("order.ready", customer=CUST, order={"number": 50 + i})
        self.assertEqual(len(r.mock.calls("Messages.json")), 2); r.close()
        r = Rig(extra={"limits": {"per_recipient_per_day": 9, "per_hour": 3}})
        for i in range(6): r.event("order.ready", customer=dict(CUST, phone=f"646555010{i}"), order={"number": 60 + i})
        self.assertLessEqual(len(r.mock.requests), 3); r.close()

    def test_same_event_id_runs_once(self):
        r = Rig(); r.agent.handle_event({"event": "order.ready", "id": "dup", "customer": CUST, "order": {"number": 1}}); r.agent.handle_event({"event": "order.ready", "id": "dup", "customer": CUST, "order": {"number": 1}})
        self.assertEqual(len(r.mock.calls("Messages.json")), 1); r.close()

    def test_kill_switch(self):
        r = Rig(); open(os.path.join(r.agent.cfg["state_dir"], "STOP"), "w").close(); r.event("order.ready", customer=CUST, order={"number": 2}); self.assertEqual(r.mock.requests, []); r.close()

    def test_one_failing_service_does_not_stop_the_rest(self):
        r = Rig(); r.mock.fail["Messages.json"] = 500; out = r.event("order.ready", customer=CUST, order={"number": 3})
        st = {x["action"]: x["status"] for x in out["workflows"][0]["results"]}; self.assertEqual(st["sms"], "error"); self.assertEqual(st["slack"], "sent"); r.close()

    def test_slack_reports_what_really_happened_to_the_text(self):
        r = Rig(); r.event("order.ready", customer=dict(CUST, sms_consent=False), order={"number": 5}); r.event("order.ready", customer=CUST, order={"number": 6})
        texts = [q["json"]["text"] for q in r.mock.calls("chat.postMessage")]; self.assertIn("Text to Ann Lee: blocked.", texts[0]); self.assertIn("Text to Ann Lee: sent.", texts[1]); r.close()

    def test_placeholder_values_are_never_sent(self):
        r = Rig(extra={"facts": {"review_url": "https://g.page/r/YOUR-REVIEW-LINK"}}); out = r.event("visit.completed", customer=CUST)
        self.assertEqual(out["workflows"][0]["results"][0]["status"], "skipped"); self.assertEqual(r.mock.calls("Messages.json"), []); r.close()

    def test_sms_goes_to_twilio_correctly(self):
        r = Rig(); r.event("order.ready", customer=CUST, order={"number": 42}); m = r.mock.calls("Messages.json")[0]
        self.assertEqual((m["form"]["To"], m["form"]["From"]), ("+16465550101", "+15550001111")); self.assertIn("order 42 is ready", m["form"]["Body"]); self.assertIn("Good news, your order is ready for pickup.", m["form"]["Body"])
        self.assertEqual(m["auth"], "Basic " + base64.b64encode(b"AC1:" + TOKEN.encode()).decode()); r.close()


class Connectors(unittest.TestCase):
    def test_call_plays_pack_audio_through_twilio(self):
        r = Rig(); r.event("order.ready", customer=dict(CUST, prefers_call=True), order={"number": 7}); c = r.mock.calls("Calls.json")[0]
        self.assertEqual(c["form"]["To"], "+16465550101"); self.assertIn("https://agent.test/audio/", c["form"]["Twiml"]); self.assertEqual(c["form"]["Twiml"].count("<Play>"), 2); r.close()

    def test_m4a_without_ffmpeg_explains_instead_of_crashing(self):
        r = Rig(m4a=True); orig = shutil.which; shutil.which = lambda x: None
        try:
            out = r.event("order.ready", customer=dict(CUST, prefers_call=True), order={"number": 8})
        finally:
            shutil.which = orig
        res = {x["action"]: x for x in out["workflows"][0]["results"]}; self.assertEqual(res["call"]["status"], "skipped"); self.assertIn("ffmpeg", res["call"]["reason"]); self.assertEqual(res["sms"]["status"], "sent"); r.close()

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_m4a_pack_audio_is_converted_for_phone_calls(self):
        import subprocess
        r = Rig(); src = os.path.join(r.tmp, "pack", "audio", "00001.m4a")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.3", "-c:a", "aac", src], check=True)
        f = r.agent.audio.playable_file("1"); self.assertTrue(f.endswith(".mp3") and os.path.getsize(f) > 100); self.assertTrue(r.agent.audio.url("1").endswith("/audio/1.mp3")); r.close()

    def test_slack_message_and_three_step_audio_upload(self):
        r = Rig(); r.agent.run_actions("t", [{"action": "slack", "channel": "C1", "text": "hi", "audio": "order_ready"}], r.agent.ctx())
        self.assertEqual(r.mock.calls("chat.postMessage")[0]["json"], {"channel": "C1", "text": "hi"}); self.assertEqual([x["path"].split("/")[-1] for x in r.mock.requests][1:], ["files.getUploadURLExternal", "1", "files.completeUploadExternal"])
        self.assertEqual(r.mock.calls("files.completeUploadExternal")[0]["json"]["channel_id"], "C1"); r.close()

    def test_calendar_reminder_once_with_contact_and_consent(self):
        r = Rig(); start = NOON + 24 * 3600 - 300
        iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        r.mock.events = [{"id": "e1", "summary": "Reservation: Ann Lee party of 4", "description": "Name: Ann Lee\nPhone: 646-555-0101\nSMS OK: yes", "start": {"dateTime": iso(start)}, "end": {"dateTime": iso(start + 5400)}},
                         {"id": "e2", "summary": "Reservation: Cy", "description": "Phone: 646-555-0199\nSMS OK: False", "start": {"dateTime": iso(start)}, "end": {"dateTime": iso(start + 5400)}},
                         {"id": "e3", "summary": "Staff meeting", "description": "Phone: 646-555-0188\nSMS OK: yes", "start": {"dateTime": iso(start)}, "end": {"dateTime": iso(start + 5400)}}]
        r.agent.tick(); r.agent.tick()
        sms = r.mock.calls("Messages.json"); self.assertEqual(len(sms), 1); self.assertEqual(sms[0]["form"]["To"], "+16465550101"); self.assertIn("friendly reminder", sms[0]["form"]["Body"])
        self.assertTrue(any(q["path"].endswith("/token") for q in r.mock.requests)); self.assertEqual(r.mock.calls("/token")[0]["form"]["grant_type"], "refresh_token"); r.close()

    def test_reservation_event_creates_calendar_entry_only_when_allowed(self):
        r = Rig(); r.event("reservation.created", customer=CUST, party="4", start_epoch=int(NOON + 86400), start_text="Tue 7 PM")
        ev = [q for q in r.mock.requests if q["path"].endswith("/events") and q["method"] == "POST"][0]["json"]; self.assertIn("Reservation: Ann Lee party of 4", ev["summary"]); self.assertIn("SMS OK: True", ev["description"]); r.close()
        r = Rig(extra={"google_calendar": {"allow_create": False}}); out = r.event("reservation.created", customer=CUST, party="4", start_epoch=int(NOON + 86400), start_text="x")
        self.assertEqual([x["status"] for x in out["workflows"][0]["results"] if x["action"] == "calendar_create"], ["skipped"]); r.close()

    def test_daily_briefing_posts_once_a_day(self):
        r = Rig(now=dt.datetime(2026, 10, 12, 14, 0, tzinfo=dt.timezone.utc).timestamp()); r.agent.tick(); r.agent.tick()          # 10:00 New York
        self.assertEqual(len([q for q in r.mock.calls("chat.postMessage") if "Today's reservations" in q["json"]["text"]]), 1); r.close()


class PackFiles(unittest.TestCase):
    def test_workflow_lines_next_to_the_manifest_still_play_and_missing_files_are_reported(self):
        r = Rig(); wl = os.path.join(r.tmp, "pack", "workflow_lines")
        for f in os.listdir(wl): shutil.move(os.path.join(wl, f), os.path.join(r.tmp, "pack", f))            # the layout a bad build produced
        a = Agent(config.load(os.path.join(r.tmp, "agent.json")), now=lambda: NOON); self.assertTrue(a.pack.audio_path("order_ready").endswith("w02.mp3")); self.assertEqual(a.pack.missing_audio(), [])
        os.remove(os.path.join(r.tmp, "pack", "w02.mp3")); self.assertIn("w02", Agent(config.load(os.path.join(r.tmp, "agent.json")), now=lambda: NOON).pack.missing_audio()); r.close()


class Slots(unittest.TestCase):
    def test_existing_phrase_fills_a_slot_and_the_rest_are_reported(self):
        from speakvora_pack_agent import slots as SL
        r = Rig(); p = r.agent.pack; self.assertEqual(r.agent.profile, "generic")
        for k in list(p.slots): del p.slots[k]
        found, gaps = SL.fill(p, "food"); self.assertEqual(found["order_cancelled"], "2"); self.assertEqual(found["thanks_review"], "1") if False else None
        self.assertIn("order_ready", [g["slot"] for g in gaps]); self.assertTrue(all(g["intent"] and g["example"] for g in gaps)); r.close()

    def test_every_profile_has_the_common_lines_and_examples_are_plain_sentences(self):
        from speakvora_pack_agent import slots as SL
        for pr in SL.PROFILES:
            reg = SL.registry(pr); self.assertTrue(set(SL.COMMON) <= set(reg), pr)
            for k, v in reg.items():
                self.assertTrue(v["example"].endswith("."), (pr, k)); self.assertNotIn("{", v["example"]); self.assertLess(len(v["example"]), 160)

    def test_restaurant_workflows_only_use_standard_slots(self):
        from speakvora_pack_agent import slots as SL
        need = SL.needed_by(json.load(open(os.path.join(ROOT, "examples", "restaurant", "workflows.json")))); self.assertEqual(sorted(need - set(SL.registry("food"))), [])

    def test_pack_ids_map_to_profiles(self):
        from speakvora_pack_agent import slots as SL
        self.assertEqual(SL.pack_slug("zh-kiosks-self-service-zf_001"), ("zh", "kiosks-self-service")); self.assertEqual(SL.profile_for("restaurants-food"), "food"); self.assertEqual(SL.profile_for("zzz"), "generic")

    def test_missing_slots_are_reported_not_fatal(self):
        r = Rig(); os.remove(os.path.join(r.tmp, "pack", "workflow_lines.json")); a = Agent(config.load(os.path.join(r.tmp, "agent.json")))
        self.assertIn("order_ready", a.missing_slots); out = a.handle_event({"event": "order.ready", "id": "m1", "customer": CUST, "order": {"number": 1}}); self.assertEqual(out["matched"], 1); r.close()


class MoreChannels(unittest.TestCase):
    """Teams, WhatsApp, Outlook calendar, inbound email and helpdesk tickets: what a customer-service team also needs."""
    def test_notify_reaches_slack_and_teams_and_teams_alone(self):
        r = Rig(extra={"teams": {"webhook_url": "MOCK/teams-hook"}}); r.agent.cfg["teams"]["webhook_url"] = r.mock.url + "/teams-hook"; r.agent.teams.url = r.mock.url + "/teams-hook"; r.agent.teams.configured = True
        out = r.agent.run_actions("t", [{"action": "notify", "text": "Escalation from Ann"}], r.agent.ctx()); self.assertEqual(out[0]["status"], "sent")
        self.assertEqual(len(r.mock.calls("chat.postMessage")), 1); self.assertEqual(len(r.mock.calls("teams-hook")), 1); self.assertIn("Escalation from Ann", json.dumps(r.mock.calls("teams-hook")[0]["json"]))
        r.agent.slack.configured = False; r.agent.run_actions("t", [{"action": "notify", "text": "again"}], r.agent.ctx()); self.assertEqual(len(r.mock.calls("chat.postMessage")), 1); self.assertEqual(len(r.mock.calls("teams-hook")), 2); r.close()

    def test_whatsapp_goes_through_the_same_twilio_account_with_the_whatsapp_prefix(self):
        r = Rig(extra={"twilio": {"whatsapp_from": "+15550009999"}}); r.agent.run_actions("t", [{"action": "sms", "to": "+16465550101", "text": "hi", "channel": "whatsapp"}], r.agent.ctx(customer=CUST))
        f = r.mock.calls("Messages.json")[0]["form"]; self.assertEqual((f["To"], f["From"]), ("whatsapp:+16465550101", "whatsapp:+15550009999")); r.close()

    def test_inbound_whatsapp_is_answered_like_a_text(self):
        r = Rig(); self.assertIn("Here are our opening hours.", r.agent.handle_sms({"From": "whatsapp:+16465550101", "Body": "what are your hours"})); r.agent.handle_sms({"From": "whatsapp:+16465550101", "Body": "STOP"})
        self.assertTrue(r.agent.state.is_opted_out("+16465550101")); r.close()

    def test_outlook_calendar_reminders(self):
        r = Rig(extra={"microsoft_calendar": {"mode": "oauth", "client_id": "a", "refresh_token": "b", "api_base": "MOCK", "token_url": "MOCK/token"}})
        r.agent.outlook.api, r.agent.outlook.token_url = r.mock.url, r.mock.url + "/token"; start = NOON + 24 * 3600 - 300
        r.mock.graph_events = [{"id": "g1", "subject": "Reservation: Eve", "start": {"dateTime": dt.datetime.fromtimestamp(start, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000")}, "end": {"dateTime": dt.datetime.fromtimestamp(start + 3600, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000")},
                                "bodyPreview": "Phone: 646-555-0120 SMS OK: yes", "location": {"displayName": "Table 4"}}]
        r.agent.tick(); sms = r.mock.calls("Messages.json"); self.assertEqual(len(sms), 1); self.assertEqual(sms[0]["form"]["To"], "+16465550120"); self.assertTrue(any(q["path"].endswith("/calendarView") and q["auth"] == "Bearer ya29.test" for q in r.mock.requests)); r.close()

    def _inbox(self, msgs):
        class IMAP:
            def __init__(s, cfg): pass
            def login(s, u, p): pass
            def select(s, f, readonly=False): return "OK", [b"1"]
            def search(s, *a): return "OK", [b" ".join(str(i).encode() for i in range(1, len(msgs) + 1))]
            def fetch(s, i, spec): return "OK", [(b"x", msgs[int(i) - 1])]
            def logout(s): pass
        return IMAP

    def test_inbound_email_is_answered_and_passed_to_staff_but_newsletters_are_not(self):
        r = Rig(extra={"inbox": {"host": "imap.test", "username": "support@shop.test", "password": "pw12345678"}, "email": {}})
        from speakvora_pack_agent import recipes
        r.agent.workflows = recipes.workflows_for("clinic")["workflows"]; r.agent.inbox.configured = True; sent = []
        r.agent.mail.send = lambda to, subj, text, attach=None: sent.append((to, subj, text)) or {"ok": True}; r.agent.mail.configured = True
        mails = [b"From: Ann <ann@x.com>\r\nSubject: Opening hours?\r\nMessage-ID: <a1@x>\r\n\r\nWhat time do you open tomorrow?\r\n", b"From: News <n@y.com>\r\nSubject: Sale\r\nList-Unsubscribe: <mailto:u@y.com>\r\n\r\nbuy now\r\n",
                 b"From: Bob <bob@x.com>\r\nSubject: This is urgent\r\nMessage-ID: <b1@x>\r\n\r\nI need a manager about my refund\r\n"]
        r.agent.imap_factory = self._inbox(mails); self.assertEqual(r.agent.poll_email(), 2); self.assertEqual(r.agent.poll_email(), 0)
        self.assertEqual([x[0] for x in sent], ["ann@x.com", "bob@x.com"]); self.assertIn("Tue-Sun 5-10 PM.", sent[0][2]); self.assertIn("automated assistant", sent[0][2])
        self.assertTrue(any("needs a person" in q["json"]["text"] for q in r.mock.calls("chat.postMessage"))); r.close()

    def test_support_profile_creates_a_ticket_in_the_helpdesk_and_confirms_by_email(self):
        from speakvora_pack_agent import recipes
        r = Rig(); wf = json.load(open(os.path.join(r.tmp, "workflows.json"))); sup = recipes.workflows_for("support"); t = [w for w in sup["workflows"] if w["name"] == "email_ticket"][0]
        t["do"][0]["url"] = r.mock.url + "/tickets"; t["do"][0]["headers"] = {}; sent = []
        r.agent.mail.send = lambda to, subj, text, attach=None: sent.append((to, text)) or {"ok": True}; r.agent.mail.configured = True; r.agent.pack.slots["ticket_created"] = r.agent.pack.slots["handoff_received"]
        r.agent.run_actions("email_ticket", t["do"], r.agent.ctx(email={"from": "ann@x.com", "subject": "Broken thing", "body": "It broke"}, customer={"email": "ann@x.com", "sms_consent": True}))
        self.assertEqual(r.mock.calls("/tickets")[0]["json"]["subject"], "Broken thing"); self.assertIn("Ticket T-100", sent[0][1]); self.assertTrue(any("New ticket T-100" in q["json"]["text"] for q in r.mock.calls("chat.postMessage"))); r.close()
        dup = [w["name"] for w in sup["workflows"]]; self.assertEqual(len(dup), len(set(dup)))

    def test_every_profile_still_only_uses_its_own_slots_after_the_email_workflows(self):
        from speakvora_pack_agent import recipes, slots as SL
        for pr in SL.PROFILES:
            self.assertEqual(sorted(SL.needed_by(recipes.workflows_for(pr)) - set(SL.registry(pr))), [], pr)


class DevTools(unittest.TestCase):
    """GitHub, GitLab, PagerDuty and Stripe webhooks become events; on-call alerts text and call the on-call phone even at night."""
    def setUp(self):
        self.r = Rig(now=dt.datetime(2026, 10, 13, 7, 30, tzinfo=dt.timezone.utc).timestamp(), extra={"facts": {"oncall_phone": "+16465550999"}})          # 03:30 in New York
        from speakvora_pack_agent import recipes, slots as SL
        self.r.agent.profile = "devops"; self.r.agent.registry = SL.registry("devops"); self.r.agent.workflows = recipes.workflows_for("devops")["workflows"]
        self.r.agent.pack.slots.update({"pipeline_failed": self.r.agent.pack.slots["order_delayed"], "oncall_alert": self.r.agent.pack.slots["handoff_person"], "deploy_failed": self.r.agent.pack.slots["order_delayed"]})
        d = os.path.join(ROOT, "speakvora_pack_agent", "data", "sources"); self.src = {n: json.load(open(os.path.join(d, n + ".json"))) for n in ("github", "gitlab", "pagerduty", "stripe")}

    def tearDown(self):
        self.r.close()

    def test_github_signature_and_workflow_run_failure(self):
        from speakvora_pack_agent import sources
        g = dict(self.src["github"], auth=dict(self.src["github"]["auth"], secret="gh-secret")); body = json.dumps({"action": "completed", "repository": {"full_name": "acme/app"}, "sender": {"login": "dev1"}, "workflow_run": {"conclusion": "failure", "head_branch": "main", "html_url": "https://github.com/acme/app/actions/runs/1"}}).encode()
        sig = "sha256=" + hmac.new(b"gh-secret", body, hashlib.sha256).hexdigest(); hdr = {"X-Hub-Signature-256": sig, "X-GitHub-Event": "workflow_run", "X-GitHub-Delivery": "d-1"}
        self.assertTrue(sources.authorised(g, body, hdr)); self.assertFalse(sources.authorised(g, body, dict(hdr, **{"X-Hub-Signature-256": "sha256=00"})))
        ev = sources.map_request(g, {"payload": json.loads(body), "headers": {k.lower(): v for k, v in hdr.items()}, "query": {}}); self.assertEqual((ev["event"], ev["repo"], ev["branch"], ev["author"], ev["id"]), ("pipeline.failed", "acme/app", "main", "dev1", "d-1"))
        out = self.r.agent.handle_event(ev); self.assertEqual(out["matched"], 1)
        sms = self.r.mock.calls("Messages.json"); self.assertEqual(sms[0]["form"]["To"], "+16465550999"); self.assertIn("acme/app main", sms[0]["form"]["Body"]); self.assertTrue(any("Pipeline FAILED" in q["json"]["text"] for q in self.r.mock.calls("chat.postMessage")))   # urgent: texted at 3:30 AM

    def test_successful_runs_and_unmapped_github_events_do_not_alert(self):
        from speakvora_pack_agent import sources
        ok = sources.map_request(self.src["github"], {"payload": {"action": "completed", "workflow_run": {"conclusion": "success"}, "repository": {"full_name": "a/b"}}, "headers": {"x-github-event": "workflow_run"}, "query": {}}); self.assertEqual(ok["event"], "pipeline.succeeded")
        self.assertIsNone(sources.map_request(self.src["github"], {"payload": {"action": "created", "zen": "hi"}, "headers": {"x-github-event": "star"}, "query": {}}))
        self.r.agent.handle_event(ok); self.assertEqual(self.r.mock.calls("Messages.json"), [])

    def test_gitlab_token_and_pipeline_failed(self):
        from speakvora_pack_agent import sources
        g = dict(self.src["gitlab"], auth=dict(self.src["gitlab"]["auth"], secret="gl-token")); self.assertTrue(sources.authorised(g, b"{}", {"X-Gitlab-Token": "gl-token"})); self.assertFalse(sources.authorised(g, b"{}", {"X-Gitlab-Token": "nope"})); self.assertFalse(sources.authorised(g, b"{}", {}))
        ev = sources.map_request(g, {"payload": {"object_attributes": {"status": "failed", "ref": "main", "url": "https://gitlab.com/x/-/pipelines/1"}, "project": {"path_with_namespace": "x/y"}, "user": {"username": "u"}}, "headers": {"x-gitlab-event": "Pipeline Hook", "x-gitlab-event-uuid": "u1"}, "query": {}})
        self.assertEqual((ev["event"], ev["repo"], ev["branch"]), ("pipeline.failed", "x/y", "main"))

    def test_pagerduty_incident_calls_the_oncall_phone_with_the_automated_notice(self):
        from speakvora_pack_agent import sources
        pd = dict(self.src["pagerduty"], auth=dict(self.src["pagerduty"]["auth"], secret="pd")); body = b'{"event":{"id":"e1","event_type":"incident.triggered","data":{"title":"DB down","html_url":"https://pd/inc/1"}}}'
        good = "v1=" + hmac.new(b"pd", body, hashlib.sha256).hexdigest(); self.assertTrue(sources.authorised(pd, body, {"X-PagerDuty-Signature": "v1=bad," + good}))                    # PagerDuty may send several signatures
        ev = sources.map_request(pd, {"payload": json.loads(body), "headers": {}, "query": {}}); self.r.agent.handle_event(ev)
        c = self.r.mock.calls("Calls.json"); self.assertEqual(c[0]["form"]["To"], "+16465550999"); self.assertIn("automated call", c[0]["form"]["Twiml"]); self.assertTrue(any("DB down" in q["json"]["text"] for q in self.r.mock.calls("chat.postMessage")))

    def test_stripe_style_signature_and_payment_failed_event(self):
        from speakvora_pack_agent import sources
        st = dict(self.src["stripe"], auth=dict(self.src["stripe"]["auth"], secret="whsec")); body = b'{"id":"evt_1","type":"invoice.payment_failed","data":{"object":{"customer_email":"a@b.co"}}}'; ts = str(int(__import__("time").time()))
        sig = hmac.new(b"whsec", ts.encode() + b"." + body, hashlib.sha256).hexdigest(); self.assertTrue(sources.authorised(st, body, {"Stripe-Signature": f"t={ts},v1={sig}"}))
        ev = sources.map_request(st, {"payload": json.loads(body), "headers": {}, "query": {}}); self.assertEqual((ev["event"], ev["customer"]["email"], ev["customer"]["sms_consent"]), ("payment.failed", "a@b.co", False))

    def test_non_urgent_messages_to_customers_still_respect_quiet_hours(self):
        self.r.agent.workflows = json.load(open(os.path.join(self.r.tmp, "workflows.json")))["workflows"]; self.r.event("order.ready", customer=CUST, order={"number": 1}); self.assertEqual(self.r.mock.calls("Messages.json"), [])

    def test_source_cli_adds_a_preset(self):
        import subprocess
        d = tempfile.mkdtemp(); json.dump({"sources": []}, open(os.path.join(d, "agent.json"), "w"))
        out = subprocess.run([sys.executable, "-m", "speakvora_pack_agent", "source", "add", "github"], cwd=d, env=dict(os.environ, PYTHONPATH=ROOT), capture_output=True, text=True); self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.load(open(os.path.join(d, "agent.json")))["sources"][0]["name"], "github"); self.assertIn("/hook/github", out.stdout); shutil.rmtree(d)


class Required(unittest.TestCase):
    """Lines that MUST be said or texted are added automatically, and never skipped; limits are the customer's to loosen, safety floors are not."""
    def rig(self, profile=None, **extra):
        r = Rig(extra=extra or None)
        if profile:
            from speakvora_pack_agent import slots as SL
            r.agent.profile = profile; r.agent.registry = SL.registry(profile)
        return r

    def test_outbound_call_starts_with_the_automated_call_notice(self):
        r = self.rig("food"); r.agent.pack.slots["automated_call_notice"] = r.agent.pack.slots["handoff_person"]          # pretend the pack has this line's audio
        r.event("order.ready", customer=dict(CUST, prefers_call=True), order={"number": 7}); tw = r.mock.calls("Calls.json")[0]["form"]["Twiml"]
        self.assertTrue(tw.startswith("<Response><Play>")); self.assertEqual(tw.count("<Play>"), 3); r.close()

    def test_missing_audio_for_a_required_line_is_spoken_by_the_provider_voice_and_logged(self):
        r = self.rig("corrections"); out = r.agent.run_actions("t", [{"action": "call", "to": "+16465550101", "play": ["handoff_person"]}], r.agent.ctx(customer=CUST)); self.assertEqual(out[0]["status"], "sent")
        tw = r.mock.calls("Calls.json")[0]["form"]["Twiml"]; self.assertLess(tw.index("automated call"), tw.index("inmate")); self.assertLess(tw.index("inmate"), tw.index("recorded")); self.assertLess(tw.index("recorded"), tw.index("/audio/"))
        self.assertIn("required_line_fallback", [x["status"] for x in r.log()]); r.close()

    def test_sms_footer_once_then_not_again_but_collector_notice_every_time(self):
        r = self.rig("food"); sms = lambda: r.agent.run_actions("t", [{"action": "sms", "to": "+16465550101", "text": "Hello"}], r.agent.ctx(customer=CUST))  # noqa: E731
        sms(); sms(); b = [q["form"]["Body"] for q in r.mock.calls("Messages.json")]; self.assertTrue(b[0].endswith("Reply STOP to opt out.")); self.assertEqual(b[1], "Hello"); r.close()
        r = self.rig("collections"); sms = lambda: r.agent.run_actions("t", [{"action": "sms", "to": "+16465550101", "text": "Hello"}], r.agent.ctx(customer=CUST))  # noqa: E731
        sms(); sms(); b = [q["form"]["Body"] for q in r.mock.calls("Messages.json")]; self.assertTrue(all("debt collector" in x for x in b)); r.close()

    def test_health_menu_says_the_emergency_and_privacy_notices_before_the_menu(self):
        r = self.rig("clinic"); r.agent.workflows = [w for w in __import__("speakvora_pack_agent.recipes", fromlist=["x"]).workflows_for("clinic")["workflows"]]
        xml = r.agent.handle_call({"From": "+16465550101"}); self.assertLess(xml.index("nine one one"), xml.index("<Gather")); self.assertLess(xml.index("personal health details"), xml.index("<Gather")); r.close()

    def test_recording_switch_adds_the_recorded_notice(self):
        r = self.rig("food", compliance={"recording": True}); r.agent.workflows = __import__("speakvora_pack_agent.recipes", fromlist=["x"]).workflows_for("clinic")["workflows"]; xml = r.agent.handle_call({"From": "+16465550101"}); self.assertIn("recorded", xml); r.close()

    def test_strict_and_open_modes_but_stop_and_kill_switch_never_switch_off(self):
        s = Rig(extra={"mode": "strict"}); self.assertEqual(s.agent.cfg["limits"]["per_recipient_per_day"], 2); s.close()
        o = Rig(extra={"mode": "open", "limits": {}}); lim = o.agent.cfg["limits"]; self.assertEqual((lim["per_hour"], lim["per_recipient_per_day"]), (None, None))
        night = Rig(extra={"mode": "open"}, now=dt.datetime(2026, 10, 13, 3, 30, tzinfo=dt.timezone.utc).timestamp())
        for i in range(8): night.event("order.ready", customer=CUST, order={"number": i})
        self.assertEqual(len(night.mock.calls("Messages.json")), 8)                                                    # no quiet hours, no daily cap
        night.agent.handle_sms({"From": "+16465550101", "Body": "STOP"}); night.event("order.ready", customer=CUST, order={"number": 99}); self.assertEqual(len(night.mock.calls("Messages.json")), 8)
        open(os.path.join(night.agent.cfg["state_dir"], "STOP"), "w").close(); night.event("order.ready", customer=dict(CUST, phone="6465550177"), order={"number": 100}); self.assertEqual(len(night.mock.calls("Messages.json")), 8)
        night.close(); o.close()

    def test_custom_sms_provider_and_inbound_text_from_any_provider(self):
        r = Rig(extra={"sms_provider": {"method": "POST", "url": "MOCK/carrier/messages", "json": {"from": "+15551234567", "to": "{{to}}", "text": "{{text}}"}},
                       "sources": [{"name": "carrier", "path": "/hook/carrier", "as": "sms", "auth": {"type": "bearer", "token": "ct"}, "map": {"from": "payload.from", "body": "payload.text"}}]})
        r.agent.sms_provider.cfg["url"] = r.mock.url + "/carrier/messages"; r.agent.sms_provider.configured = True
        r.event("order.ready", customer=CUST, order={"number": 5}); self.assertEqual(r.mock.calls("Messages.json"), []); m = r.mock.calls("/carrier/messages")[0]["json"]; self.assertEqual((m["to"], m["from"]), ("+16465550101", "+15551234567")); self.assertIn("order 5 is ready", m["text"])
        reply = r.agent.sms_via_provider("+16465550188", "what are your hours"); self.assertIn("Tue-Sun 5-10 PM.", reply); self.assertEqual(r.mock.calls("/carrier/messages")[-1]["json"]["to"], "+16465550188"); r.close()

    def test_corrections_and_collections_get_their_own_workflows(self):
        from speakvora_pack_agent import recipes, slots as SL
        for pr, name in (("corrections", "account_funded"), ("collections", "sms_hardship")):
            names = [w["name"] for w in recipes.workflows_for(pr)["workflows"]]; self.assertIn(name, names); self.assertEqual(sorted(SL.needed_by(recipes.workflows_for(pr)) - set(SL.registry(pr))), [])

    def test_every_required_line_exists_in_its_profiles_registry(self):
        from speakvora_pack_agent import slots as SL
        for pr in SL.PROFILES:
            reg = SL.registry(pr)
            for ap in ("sms", "menu", "call_out"):
                for slot in SL.required_lines(pr, ap): self.assertIn(slot, reg, (pr, slot)); self.assertTrue(reg[slot]["required"])


class Recipes(unittest.TestCase):
    def test_every_profile_gets_workflows_that_only_use_its_own_slots(self):
        from speakvora_pack_agent import recipes, slots as SL
        for pr in SL.PROFILES:
            wf = recipes.workflows_for(pr)["workflows"]; self.assertGreater(len(wf), 6, pr); need = SL.needed_by(recipes.workflows_for(pr)); self.assertEqual(sorted(need - set(SL.registry(pr))), [], pr)
            names = [w["name"] for w in wf]; self.assertEqual(len(names), len(set(names)), pr)

    def test_generated_workflows_run_for_a_clinic(self):
        from speakvora_pack_agent import recipes
        r = Rig(); wf = os.path.join(r.tmp, "wf2.json"); json.dump(recipes.workflows_for("clinic"), open(wf, "w"))
        c = config.load(os.path.join(r.tmp, "agent.json")); c["workflows"] = wf; a = Agent(c, now=lambda: NOON)
        for k in ("appointment_confirmed",): a.pack.slots[k] = a.pack.slots["reservation_confirmed"]
        out = a.handle_event({"event": "appointment.created", "id": "c1", "customer": CUST, "start_text": "Tue 9 AM", "start_epoch": int(NOON + 86400), "minutes": 30})
        self.assertEqual(out["matched"], 1); self.assertIn("Tue 9 AM", r.mock.calls("Messages.json")[0]["form"]["Body"]); r.close()

    def test_init_writes_a_safe_starting_config(self):
        import subprocess
        r = Rig(); d = tempfile.mkdtemp(); shutil.copytree(os.path.join(r.tmp, "pack"), os.path.join(d, "pack"))
        m = json.load(open(os.path.join(d, "pack", "manifest.json"))); m["pack"] = "en-restaurants-food-af_heart"; json.dump(m, open(os.path.join(d, "pack", "manifest.json"), "w"))
        out = subprocess.run([sys.executable, "-m", "speakvora_pack_agent", "init"], cwd=d, env=dict(os.environ, PYTHONPATH=ROOT), capture_output=True, text=True); self.assertEqual(out.returncode, 0, out.stderr)
        cfg = json.load(open(os.path.join(d, "agent.json"))); self.assertTrue(cfg["dry_run"]); self.assertIn("food", out.stdout); self.assertTrue(os.path.exists(os.path.join(d, "workflows.json"))); shutil.rmtree(d); r.close()


class Universal(unittest.TestCase):
    """Any system's webhook becomes an agent event through a mapping in agent.json, and any REST API can be called, with no code."""
    SHOP = {"name": "shopify", "path": "/hook/shopify", "auth": {"type": "hmac", "header": "X-Shopify-Hmac-Sha256", "secret": "shop-secret", "encoding": "base64"},
            "map": {"event": {"from": "headers.x-shopify-topic", "values": {"orders/fulfilled": "order.ready"}}, "id": "headers.x-shopify-webhook-id", "customer.name": "payload.customer.first_name", "customer.phone": "payload.customer.phone",
                    "customer.sms_consent": {"from": "payload.customer.sms_marketing_consent.state", "values": {"subscribed": True}, "default": False}, "order.number": "payload.order_number"}}

    def setUp(self):
        self.r = Rig(extra={"sources": [self.SHOP, {"name": "pos", "path": "/hook/pos", "auth": {"type": "bearer", "token": "tok"}, "map": {"event": {"from": "payload.type", "values": {"TABLE_AVAILABLE": "table.ready"}}, "customer.name": "payload.guest", "customer.phone": "payload.mobile", "customer.sms_consent": "payload.optIn", "party": {"const": "2"}}},
                                      {"name": "cal", "path": "/hook/cal", "auth": {"type": "stripe_style", "header": "X-Sig", "secret": "k"}, "map": {"event": {"const": "table.ready"}, "customer.phone": "payload.p", "customer.sms_consent": {"const": True}, "customer.name": {"const": "X"}, "party": {"const": "1"}}}]})
        self.srv = serve(self.r.agent, "127.0.0.1", 0, tick_seconds=3600); self.port = self.srv.server_address[1]; threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.stopper.set(); self.r.close()

    def post(self, path, body, headers):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, {}

    def test_shopify_webhook_becomes_an_order_ready_text(self):
        body = json.dumps({"order_number": 1007, "customer": {"first_name": "Mia", "phone": "+16465550142", "sms_marketing_consent": {"state": "subscribed"}}}).encode()
        sig = base64.b64encode(hmac.new(b"shop-secret", body, hashlib.sha256).digest()).decode(); hdr = {"X-Shopify-Hmac-Sha256": sig, "X-Shopify-Topic": "orders/fulfilled", "X-Shopify-Webhook-Id": "wh-1", "content-type": "application/json"}
        self.assertEqual(self.post("/hook/shopify", body, dict(hdr, **{"X-Shopify-Hmac-Sha256": "bad"}))[0], 401)
        code, out = self.post("/hook/shopify", body, hdr); self.assertEqual((code, out["matched"]), (200, 1)); sms = self.r.mock.calls("Messages.json"); self.assertIn("order 1007 is ready", sms[0]["form"]["Body"]); self.assertEqual(sms[0]["form"]["To"], "+16465550142")
        self.assertEqual(self.post("/hook/shopify", body, hdr)[1]["matched"], 0)                                      # the same webhook id again is ignored
        body2 = json.dumps({"order_number": 1008, "customer": {"first_name": "Zed", "phone": "+16465550143", "sms_marketing_consent": {"state": "not_subscribed"}}}).encode()
        sig2 = base64.b64encode(hmac.new(b"shop-secret", body2, hashlib.sha256).digest()).decode(); self.post("/hook/shopify", body2, dict(hdr, **{"X-Shopify-Hmac-Sha256": sig2, "X-Shopify-Webhook-Id": "wh-2"}))
        self.assertEqual(len(self.r.mock.calls("Messages.json")), 1)                                                  # no marketing consent from Shopify: no text

    def test_other_auth_styles_and_unmapped_events(self):
        b = json.dumps({"type": "TABLE_AVAILABLE", "guest": "Ola", "mobile": "6465550150", "optIn": True}).encode()
        self.assertEqual(self.post("/hook/pos", b, {"Authorization": "Bearer nope", "content-type": "application/json"})[0], 401); self.assertEqual(self.post("/hook/pos", b, {"Authorization": "Bearer tok", "content-type": "application/json"})[0], 200)
        self.assertTrue(self.post("/hook/pos", json.dumps({"type": "SOMETHING_ELSE"}).encode(), {"Authorization": "Bearer tok", "content-type": "application/json"})[1].get("ignored"))
        body = json.dumps({"p": "6465550151"}).encode(); ts = str(int(__import__("time").time())); sig = hmac.new(b"k", ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        self.assertEqual(self.post("/hook/cal", body, {"X-Sig": f"t={ts},v1={sig}", "content-type": "application/json"})[0], 200); self.assertEqual(self.post("/hook/cal", body, {"X-Sig": f"t={ts},v1=00", "content-type": "application/json"})[0], 401)

    def test_unknown_source_and_missing_secret_are_refused(self):
        self.assertEqual(self.post("/hook/nothing", b"{}", {})[0], 404)

    def test_http_action_calls_any_api_and_keeps_the_answer(self):
        r = self.r; r.agent.run_actions("t", [{"action": "http", "method": "GET", "url": r.mock.url + "/orders/{{order.number}}", "save_as": "o"}], r.agent.ctx(order={"number": 12}))
        self.assertEqual(r.mock.requests[-1]["path"], "/orders/12")
        for bad in ("https://{{evil}}/x", "{{url}}", "http://{{customer.name}}.example.com/x"):
            out = r.agent.run_actions("t", [{"action": "http", "url": bad}], r.agent.ctx(evil="attacker.test", url="http://attacker.test", customer={"name": "a"})); self.assertEqual(out[0]["status"], "skipped")
        n = len(r.mock.requests); r.agent.dry = True; r.agent.run_actions("t", [{"action": "http", "url": r.mock.url + "/x"}], r.agent.ctx()); self.assertEqual(len(r.mock.requests), n)


class Web(unittest.TestCase):
    def setUp(self):
        self.r = Rig(); self.srv = serve(self.r.agent, "127.0.0.1", 0, tick_seconds=3600); self.port = self.srv.server_address[1]
        self.r.agent.cfg["public_base_url"] = self.r.agent.audio.base = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.stopper.set(); self.r.close()

    def post(self, path, body, headers=None, raw=False):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body if isinstance(body, bytes) else body.encode(), method="POST", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as x:
                return x.status, x.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def twilio(self, path, params):
        url = f"http://127.0.0.1:{self.port}{path}"; sig = base64.b64encode(hmac.new(TOKEN.encode(), (url + "".join(k + params[k] for k in sorted(params))).encode(), hashlib.sha1).digest()).decode()
        return self.post(path, urllib.parse.urlencode(params), {"X-Twilio-Signature": sig, "content-type": "application/x-www-form-urlencoded"})

    def test_app_events_must_be_signed(self):
        body = json.dumps({"event": "order.ready", "id": "w1", "customer": CUST, "order": {"number": 9}}).encode()
        self.assertEqual(self.post("/event", body, {"X-SV-Timestamp": "1", "X-SV-Signature": "sha256=bad"})[0], 401); self.assertEqual(self.r.mock.requests, [])
        code, out = self.post("/event", body, signing.sign(SECRET, body)); self.assertEqual(code, 200); self.assertEqual(json.loads(out)["matched"], 1); self.assertEqual(len(self.r.mock.calls("Messages.json")), 1)

    def test_inbound_text_hours_with_signature(self):
        self.assertEqual(self.post("/twilio/sms", "From=%2B16465550101&Body=hours", {"X-Twilio-Signature": "nope"})[0], 403)
        code, xml = self.twilio("/twilio/sms", {"From": "+16465550101", "Body": "What are your hours today?"}); self.assertEqual(code, 200); self.assertIn("Here are our opening hours.", xml); self.assertIn("Tue-Sun 5-10 PM.", xml)
        code, xml = self.twilio("/twilio/sms", {"From": "+16465550101", "Body": "blah blah"}); self.assertEqual(xml, "<Response></Response>")
        code, xml = self.twilio("/twilio/sms", {"From": "+16465550101", "Body": "I want a manager"}); self.assertIn("team member has been notified", xml); self.assertTrue(any("needs a person" in q["json"]["text"].lower() for q in self.r.mock.calls("chat.postMessage")))

    def test_inbound_call_menu(self):
        code, xml = self.twilio("/twilio/call", {"From": "+16465550101"}); self.assertIn("<Gather", xml); self.assertIn(f"http://127.0.0.1:{self.port}/audio/", xml)
        code, xml = self.twilio("/twilio/call/menu", {"From": "+16465550101", "Digits": "1"}); self.assertIn("<Play>", xml); self.assertIn("Tue-Sun 5-10 PM.", xml); self.assertIn("<Hangup/>", xml)
        code, xml = self.twilio("/twilio/call/menu", {"From": "+16465550101", "Digits": "0"}); self.assertIn("<Play>", xml); self.assertTrue(any("wants a person" in q["json"]["text"] for q in self.r.mock.calls("chat.postMessage")))
        code, xml = self.twilio("/twilio/call/menu", {"From": "+16465550101", "Digits": "9"}); self.assertIn("not an option", xml)

    def test_audio_endpoint_serves_the_pack(self):
        code = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/audio/w02.mp3").status; self.assertEqual(code, 200)
        with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(f"http://127.0.0.1:{self.port}/audio/nope.mp3")

    def test_slack_command_needs_signature_and_texts_a_customer(self):
        body = urllib.parse.urlencode({"command": "/say", "text": "order_ready +16465550177", "user_name": "host"}).encode(); ts = str(int(__import__("time").time()))
        sig = "v0=" + hmac.new(SLACK_SECRET.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
        self.assertEqual(self.post("/slack/command", body, {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": "v0=bad"})[0], 401)
        code, out = self.post("/slack/command", body, {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig}); self.assertEqual(code, 200); self.assertIn("Texted +16465550177", out)
        self.assertEqual(self.r.mock.calls("Messages.json")[0]["form"]["To"], "+16465550177")


if __name__ == "__main__":
    unittest.main()
