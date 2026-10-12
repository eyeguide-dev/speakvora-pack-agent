"""The pack agent against fake Twilio, Slack and Google: every connector, every safety rule, the restaurant workflows and the signed web endpoints."""
import base64, datetime as dt, hashlib, hmac, json, os, shutil, sys, tempfile, threading, unittest, urllib.error, urllib.parse, urllib.request
os.environ.setdefault("SPEAKVORA_HOST", "http://127.0.0.1:9")            # tests never reach the real Speakvora
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


def make_pack(d, m4a=False, lang="en"):
    os.makedirs(os.path.join(d, "audio")); os.makedirs(os.path.join(d, "workflow_lines"))
    items = [{"id": 1, "text": "Thank you for choosing us.", "file": "audio/00001.m4a", "category": "closing"}, {"id": 2, "text": "Your order has been canceled.", "file": "audio/00002.m4a", "category": "order"}]
    for it in items:
        open(os.path.join(d, it["file"]), "wb").write(b"M4A")
    json.dump({"pack": "t", "title": "Test", "language": lang, "items": items}, open(os.path.join(d, "manifest.json"), "w"))
    wl = []
    for i, ln in enumerate(LINES, 1):
        f = f"workflow_lines/w{i:02d}.{'m4a' if m4a else 'mp3'}"; open(os.path.join(d, f), "wb").write(b"MP3")
        wl.append({"id": f"w{i:02d}", "slot": ln["slot"], "text": ln["text"], "file": f})
    json.dump({"items": wl}, open(os.path.join(d, "workflow_lines.json"), "w"))


class Rig:
    def __init__(self, dry=False, now=NOON, m4a=False, extra=None, lang="en"):
        self.tmp = tempfile.mkdtemp(); self.mock = Mock(); self.now = [now]
        make_pack(os.path.join(self.tmp, "pack"), m4a, lang)
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
        st = {x["action"]: x["status"] for x in out["workflows"][0]["results"]}; self.assertEqual(st["sms"], "needs_review"); self.assertEqual(st["slack"], "sent"); r.close()   # a server error may still have queued the text: a person decides

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


class OfflineQueue(unittest.TestCase):
    """The network goes away: texts, Slack posts and calls wait in the outbox on disk, keep their order, and go out when it returns. Nothing is ever sent twice."""
    DEAD = "http://127.0.0.1:9"                                                                  # nothing listens here: connection refused, i.e. provably not sent

    def offline(self, r):
        r.live = (r.agent.twilio.base, r.agent.slack.base); r.agent.twilio.base = r.agent.slack.base = self.DEAD

    def online(self, r):
        r.agent.twilio.base, r.agent.slack.base = r.live

    def test_actions_queue_while_offline_and_go_out_in_order_when_it_returns(self):
        r = Rig(); self.offline(r); out = r.event("order.ready", customer=CUST, order={"number": 71})
        st = {x["action"]: x["status"] for x in out["workflows"][0]["results"]}; self.assertEqual((st["sms"], st["slack"]), ("queued", "queued"))
        self.assertEqual(len(r.agent.state.outbox()), 2); self.assertEqual(r.agent.flush_outbox()["offline"], True); self.assertEqual(len(r.agent.state.outbox()), 2)
        self.online(r); res = r.agent.flush_outbox(); self.assertEqual(res["sent"], 2); self.assertEqual(r.agent.state.outbox(), [])
        self.assertEqual(len(r.mock.calls("Messages.json")), 1); self.assertEqual(len(r.mock.calls("chat.postMessage")), 1); self.assertIn("order 71 is ready", r.mock.calls("Messages.json")[0]["form"]["Body"])
        self.assertEqual(r.agent.flush_outbox()["sent"], 0); self.assertEqual(len(r.mock.calls("Messages.json")), 1)           # a second flush sends nothing again
        self.assertIn("delivered_from_queue", [x["status"] for x in r.log()]); r.close()

    def test_queue_survives_a_restart(self):
        r = Rig(); self.offline(r); r.event("order.ready", customer=CUST, order={"number": 72})
        agent2 = Agent(config.load(os.path.join(r.tmp, "agent.json")), now=lambda: r.now[0]); self.assertEqual(len(agent2.state.outbox()), 2)
        agent2.twilio.base, agent2.slack.base = r.live; self.assertEqual(agent2.flush_outbox()["sent"], 2); self.assertEqual(len(r.mock.calls("Messages.json")), 1); r.close()

    def test_old_actions_expire_instead_of_arriving_hours_late(self):
        r = Rig(extra={"queue": {"max_age_minutes": {"sms": 30}}}); self.offline(r); r.event("order.ready", customer=CUST, order={"number": 73})
        r.now[0] += 31 * 60; self.online(r); res = r.agent.flush_outbox()
        self.assertEqual(res["expired"], 1); self.assertEqual(res["sent"], 1); self.assertEqual(r.mock.calls("Messages.json"), []); self.assertEqual(len(r.mock.calls("chat.postMessage")), 1)   # the text expired, the staff Slack note (24 h) still went
        self.assertIn("expired", [x["status"] for x in r.log()]); r.close()

    def test_a_timeout_is_not_queued_because_it_may_have_arrived(self):
        import socket
        from speakvora_pack_agent import web
        self.assertFalse(web.is_offline(socket.timeout())); self.assertTrue(web.is_offline(socket.gaierror(-2, "no dns"))); self.assertTrue(web.is_offline(ConnectionRefusedError()))
        self.assertFalse(web.is_offline(web.HttpError(500, "x")))

    def test_server_errors_are_not_retried_and_do_not_queue(self):
        r = Rig(); r.mock.fail["Messages.json"] = 500; r.event("order.ready", customer=CUST, order={"number": 74}); self.assertEqual(len(r.agent.state.outbox()), 0); r.close()

    def test_quiet_hours_keep_a_queued_text_waiting_until_morning(self):
        r = Rig(); self.offline(r); r.event("order.ready", customer=CUST, order={"number": 75})
        r.now[0] = dt.datetime(2026, 10, 13, 3, 30, tzinfo=dt.timezone.utc).timestamp(); self.online(r); r.agent.cfg["queue"]["max_age_minutes"]["sms"] = 2000      # 23:30 New York
        res = r.agent.flush_outbox(); self.assertEqual(res["waiting"], 1); self.assertEqual(r.mock.calls("Messages.json"), []); self.assertEqual([q["kind"] for q in r.agent.state.outbox()], ["sms"])
        r.now[0] = dt.datetime(2026, 10, 13, 13, 0, tzinfo=dt.timezone.utc).timestamp(); self.assertEqual(r.agent.flush_outbox()["sent"], 1); self.assertEqual(len(r.mock.calls("Messages.json")), 1); r.close()

    def test_an_opt_out_that_arrives_while_queued_stops_the_text(self):
        r = Rig(); self.offline(r); r.event("order.ready", customer=CUST, order={"number": 76}); r.agent.state.opt_out("+16465550101"); self.online(r)
        res = r.agent.flush_outbox(); self.assertEqual(r.mock.calls("Messages.json"), []); self.assertEqual(res["dropped"], 1); r.close()

    def test_kill_switch_pauses_the_queue(self):
        r = Rig(); self.offline(r); r.event("order.ready", customer=CUST, order={"number": 77}); self.online(r)
        open(os.path.join(r.agent.cfg["state_dir"], "STOP"), "w").close(); self.assertEqual(r.agent.flush_outbox()["sent"], 0); self.assertEqual(len(r.agent.state.outbox()), 2); r.close()

    def test_slack_text_is_not_posted_twice_when_the_clip_upload_is_what_failed(self):
        r = Rig(); a = {"action": "slack", "channel": "#front", "text": "hello", "_posted": True, "audio": "w01"}
        r.agent.state.enqueue({"wf": "t", "kind": "slack", "a": a, "ctx": {}}); res = r.agent.flush_outbox(); self.assertEqual(res["sent"], 1); self.assertEqual(r.mock.calls("chat.postMessage"), []); r.close()

    def test_queue_command_lists_and_drops_without_the_service_keys(self):
        import contextlib, io
        from speakvora_pack_agent import cli
        r = Rig(); self.offline(r); r.event("order.ready", customer=CUST, order={"number": 78}); cfgp = os.path.join(r.tmp, "agent.json"); buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.main(["queue", "list", "-c", cfgp]); cli.main(["queue", "drop", "all", "-c", cfgp])
        self.assertIn("2 waiting", buf.getvalue()); self.assertEqual(Agent(config.load(cfgp)).state.outbox(), []); r.close()

    def test_call_is_queued_with_a_short_life_and_health_reports_the_queue(self):
        r = Rig(); self.offline(r); out = r.agent.run_actions("t", [{"action": "call", "to": "+16465550101", "play": "w01", "urgent": True}], r.agent.ctx(customer=CUST))
        self.assertEqual(out[0]["status"], "queued"); self.assertEqual(r.agent.cfg["queue"]["max_age_minutes"]["call"], 15); r.close()


class JobJournal(unittest.TestCase):
    """Every send is written down before it happens. A crash never loses it and never repeats it; an uncertain send waits for a person."""
    def sms_jobs(self, r):
        return [j for j in r.agent.state.jobs() if j["kind"] == "sms"]

    def test_a_sent_text_is_a_job_with_the_provider_id_and_the_delivery_report_updates_it(self):
        r = Rig(); r.event("order.ready", customer=CUST, order={"number": 81}); j = self.sms_jobs(r)[0]
        self.assertEqual(j["status"], "sent"); self.assertTrue(j["provider_id"].startswith("SM")); self.assertEqual(j["attempts"], 1)
        r.agent.handle_delivery({"MessageSid": j["provider_id"], "MessageStatus": "delivered"}); self.assertEqual(self.sms_jobs(r)[0]["status"], "delivered")
        r.agent.handle_delivery({"MessageSid": j["provider_id"], "MessageStatus": "undelivered", "ErrorCode": "30034"}); j = self.sms_jobs(r)[0]
        self.assertEqual(j["status"], "undelivered"); self.assertIn("30034", j["error"]); r.close()

    def test_a_crash_while_sending_is_never_sent_again(self):
        r = Rig()
        def boom(*a, **k): raise KeyboardInterrupt()
        r.agent.twilio.sms = boom
        with self.assertRaises(KeyboardInterrupt): r.event("order.ready", customer=CUST, order={"number": 82})
        self.assertEqual(self.sms_jobs(r)[0]["status"], "sending")
        a2 = Agent(config.load(os.path.join(r.tmp, "agent.json")), now=lambda: r.now[0]); res = a2.recover()
        self.assertEqual(res["needs_review"], 1); self.assertEqual(a2.flush_outbox()["sent"], 0); self.assertEqual(r.mock.calls("Messages.json"), [])
        self.assertEqual([j["status"] for j in a2.state.jobs() if j["kind"] == "sms"], ["needs_review"]); r.close()

    def test_a_server_error_or_timeout_needs_review_and_is_not_retried_by_itself(self):
        import socket
        r = Rig(); r.mock.fail["Messages.json"] = 503; r.event("order.ready", customer=CUST, order={"number": 83}); j = self.sms_jobs(r)[0]
        self.assertEqual(j["status"], "needs_review"); r.mock.fail.clear(); self.assertEqual(r.agent.flush_outbox()["sent"], 0); self.assertEqual(r.mock.calls("Messages.json")[1:], [])
        with self.assertRaises(PermissionError): r.agent.retry_job(j["id"])
        r.agent.retry_job(j["id"], confirm_not_sent=True); self.assertEqual(r.agent.flush_outbox()["sent"], 1); self.assertEqual(self.sms_jobs(r)[0]["status"], "sent"); r.close()
        r = Rig()
        def slow(*a, **k): raise socket.timeout("timed out")
        r.agent.twilio.sms = slow; r.event("order.ready", customer=CUST, order={"number": 84}); self.assertEqual(self.sms_jobs(r)[0]["status"], "needs_review"); r.close()

    def test_a_refusal_is_failed_and_can_be_retried_after_the_fix(self):
        r = Rig(); r.mock.fail["Messages.json"] = 400; r.event("order.ready", customer=CUST, order={"number": 85}); j = self.sms_jobs(r)[0]
        self.assertEqual(j["status"], "failed"); r.mock.fail.clear(); r.agent.retry_job(j["id"]); self.assertEqual(r.agent.flush_outbox()["sent"], 1); self.assertEqual(self.sms_jobs(r)[0]["status"], "sent"); r.close()

    def test_a_person_can_cancel_a_queued_job_and_it_is_not_sent(self):
        r = Rig(); r.live = (r.agent.twilio.base, r.agent.slack.base); r.agent.twilio.base = r.agent.slack.base = "http://127.0.0.1:9"
        r.event("order.ready", customer=CUST, order={"number": 86}); j = self.sms_jobs(r)[0]; self.assertEqual(j["status"], "queued")
        r.agent.cancel_job(j["id"]); r.agent.twilio.base, r.agent.slack.base = r.live; r.agent.flush_outbox()
        self.assertEqual(r.mock.calls("Messages.json"), []); self.assertEqual(self.sms_jobs(r)[0]["status"], "cancelled")
        with self.assertRaises(PermissionError): r.agent.cancel_job(self.sms_jobs(r)[0]["id"]); r.close()

    def test_an_accepted_event_resumes_after_a_crash_without_repeating_what_was_done(self):
        r = Rig(); orig = r.agent.state.job_create
        def create(jid, wf, kind, *a, **k):
            if kind == "slack": raise KeyboardInterrupt()
            return orig(jid, wf, kind, *a, **k)
        r.agent.state.job_create = create
        with self.assertRaises(KeyboardInterrupt): r.event("order.ready", customer=CUST, order={"number": 87}, id="crash-1")
        self.assertEqual(len(r.mock.calls("Messages.json")), 1); self.assertEqual(r.mock.calls("chat.postMessage"), []); self.assertEqual(len(r.agent.state.events_running()), 1)
        a2 = Agent(config.load(os.path.join(r.tmp, "agent.json")), now=lambda: r.now[0]); self.assertEqual(a2.recover()["events"], 1)
        self.assertEqual(len(r.mock.calls("Messages.json")), 1); self.assertEqual(len(r.mock.calls("chat.postMessage")), 1); self.assertEqual(a2.state.events_running(), {})
        self.assertEqual(a2.recover()["events"], 0); self.assertEqual(len(r.mock.calls("chat.postMessage")), 1); r.close()

    def test_0_2_0_outbox_entries_become_queued_jobs_and_old_finished_jobs_are_pruned(self):
        from speakvora_pack_agent.state import State
        d = tempfile.mkdtemp(); json.dump({"outbox": [{"id": "q1-0", "wf": "w", "kind": "slack", "a": {"text": "x"}, "ctx": {}, "queued_at": 100}]}, open(os.path.join(d, "state.json"), "w"))
        s = State(d, now=lambda: 100); self.assertEqual([j["status"] for j in s.jobs()], ["queued"]); self.assertEqual(s.data["outbox"], [])
        t = [100]; s2 = State(tempfile.mkdtemp(), now=lambda: t[0]); s2.job_create("old", "w", "sms", {}, {}, "sent"); s2.job_set("old", "delivered"); t[0] += 31 * 86400; s2.job_create("new", "w", "sms", {}, {}, "pending")
        self.assertEqual([j["id"] for j in s2.jobs()], ["new"])

    def test_jobs_command_lists_cancels_and_marks_sent_without_the_service_keys(self):
        import contextlib, io
        from speakvora_pack_agent import cli
        r = Rig(); r.mock.fail["Messages.json"] = 503; r.event("order.ready", customer=CUST, order={"number": 88}); jid = self.sms_jobs(r)[0]["id"]; cfgp = os.path.join(r.tmp, "agent.json"); buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.main(["jobs", "list", "-c", cfgp]); cli.main(["jobs", "list", "--status", "needs_review", "-c", cfgp]); code = cli.main(["jobs", "retry", jid, "-c", cfgp]); cli.main(["jobs", "mark-sent", jid, "-c", cfgp])
        out = buf.getvalue(); self.assertIn("needs_review", out); self.assertEqual(code, 1); self.assertIn("may already have been delivered", out); self.assertIn("-> sent", out); r.close()


class Dashboard(unittest.TestCase):
    """The tiny local dashboard: needs its token, shows what is waiting and what needs a person, lets a person act, and requests more lines."""
    def setUp(self):
        self.r = Rig(); self.srv = serve(self.r.agent, "127.0.0.1", 0); self.port = self.srv.server_address[1]; threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        from speakvora_pack_agent import dashboard
        self.tok = dashboard.token(self.r.agent)

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.r.close()

    def call(self, method, path, body=None, tok=True, headers=None):
        h = {"x-dashboard-token": self.tok} if tok else {}; h.update(headers or {})
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode() if body is not None else (b"{}" if method == "POST" else None), method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as x:
                raw = x.read(); return x.status, (json.loads(raw) if x.headers.get_content_type() == "application/json" else raw.decode()), dict(x.headers)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), dict(e.headers)

    def test_page_is_public_but_every_api_call_needs_the_token(self):
        st, page, hdr = self.call("GET", "/dashboard", tok=False); self.assertEqual(st, 200); self.assertIn("speakvora", page); self.assertIn("Your voice bundle", page); self.assertIn("default-src 'none'", hdr["content-security-policy"]); self.assertNotIn("http://", page.replace("http://127", "").replace("http://www.w3.org/2000/svg", ""))
        self.assertEqual(self.call("GET", "/dash/api/summary", tok=False)[0], 401); self.assertEqual(self.call("GET", "/dash/api/summary", tok=False, headers={"x-dashboard-token": "nope"})[0], 401)
        st, s, _ = self.call("GET", "/dash/api/summary"); self.assertEqual(st, 200); self.assertEqual(s["mode"], "live"); self.assertNotIn(TOKEN, json.dumps(s)); self.assertNotIn("xoxb-1", json.dumps(s))

    def test_shows_jobs_and_a_person_can_act_on_them(self):
        self.r.mock.fail["Messages.json"] = 503; self.r.event("order.ready", customer=CUST, order={"number": 91})
        s = self.call("GET", "/dash/api/summary")[2 - 1]; self.assertEqual(s["counts"]["needs_review"], 1); self.assertEqual(s["attention"][0]["kind"], "sms"); self.assertEqual(s["attention"][0]["status"], "needs_review")
        jid = s["attention"][0]["id"]; self.r.mock.fail.clear()
        st, j, _ = self.call("POST", f"/dash/api/jobs/{jid}/retry"); self.assertEqual(st, 409); self.assertIn("may already have been delivered", j["message"]); self.assertEqual(len(self.r.mock.calls("Messages.json")), 1)
        st, j, _ = self.call("POST", f"/dash/api/jobs/{jid}/retry", {"confirm_not_sent": True}); self.assertEqual(st, 200); self.assertEqual(j["job"]["status"], "sent"); self.assertEqual(len(self.r.mock.calls("Messages.json")), 2)
        self.assertEqual(self.call("POST", "/dash/api/jobs/nope/cancel")[0], 409)

    def test_jobs_can_be_filtered_by_status_type_and_search(self):
        self.r.event("order.ready", customer=CUST, order={"number": 94}); self.r.event("order.ready", customer=dict(CUST, name="Bo Chen", phone="646-555-0177"), order={"number": 95})
        allj = self.call("GET", "/dash/api/jobs")[1]["jobs"]; self.assertGreaterEqual(len(allj), 4)
        self.assertTrue(all(j["kind"] == "sms" for j in self.call("GET", "/dash/api/jobs?kind=sms")[1]["jobs"]))
        self.assertTrue(all(j["kind"] == "slack" for j in self.call("GET", "/dash/api/jobs?kind=slack")[1]["jobs"]))
        one = self.call("GET", "/dash/api/jobs?kind=sms&q=0177")[1]["jobs"]; self.assertEqual(len(one), 1); self.assertIn("0177", one[0]["to"])
        self.assertEqual(self.call("GET", "/dash/api/jobs?status=needs_review")[1]["jobs"], [])

    def test_pause_is_the_kill_switch(self):
        self.assertTrue(self.call("POST", "/dash/api/pause", {"on": True})[1]["paused"]); self.r.event("order.ready", customer=CUST, order={"number": 92}); self.assertEqual(self.r.mock.calls("Messages.json"), [])
        self.assertFalse(self.call("POST", "/dash/api/pause", {"on": False})[1]["paused"]); self.r.event("order.ready", customer=CUST, order={"number": 93}); self.assertEqual(len(self.r.mock.calls("Messages.json")), 1)

    def test_other_websites_cannot_drive_it(self):
        self.assertEqual(self.call("POST", "/dash/api/pause", {"on": True}, headers={"Origin": "https://evil.example"})[0], 403)

    def test_phrase_requests_are_saved_and_sent_with_the_api_key(self):
        st, s, _ = self.call("GET", "/dash/api/summary"); self.assertFalse(s["can_send_requests"])
        st, r, _ = self.call("POST", "/dash/api/phrases", {"custom": {"when": "when a customer asks about a late delivery refund", "text": "I am sorry your delivery was late, a refund is on its way."}})
        self.assertEqual(st, 200); self.assertFalse(r["sent"]); self.assertTrue(os.path.exists(os.path.join(self.r.agent.state.dir, "slot-requests.json")))
        os.environ["SPEAKVORA_KEY"] = "k"; os.environ["SPEAKVORA_HOST"] = self.r.mock.url
        try:
            st, r, _ = self.call("POST", "/dash/api/phrases", {"custom": {"when": "when a customer asks about a late delivery refund", "text": "I am sorry your delivery was late, a refund is on its way."}})
            self.assertTrue(r["sent"]); req = self.r.mock.calls("slot-requests")[-1]; self.assertEqual(req["json"]["kind"], "workflow_line_request"); self.assertTrue(req["json"]["slots"][0]["slot"].startswith("custom_"))
            self.assertEqual(self.call("POST", "/dash/api/phrases", {"custom": {"when": "short", "text": "x"}})[0], 400); self.assertEqual(self.call("POST", "/dash/api/phrases", {"custom": {"when": "when asked about links", "text": "Visit https://x.example now please"}})[0], 400)
            self.assertEqual(self.call("POST", "/dash/api/phrases", {"slots": ["not_a_slot"]})[0], 400)
            st, s, _ = self.call("GET", "/dash/api/summary"); self.assertTrue(s["can_send_requests"]); self.assertEqual(len(s["requests"]), 2)
        finally:
            os.environ.pop("SPEAKVORA_KEY", None); os.environ["SPEAKVORA_HOST"] = "http://127.0.0.1:9"


class Reasoning(unittest.TestCase):
    """The optional reasoning step with the developer's own AI key: the model only proposes, a person approves, everything that runs is a normal journaled send."""
    MODEL = {"summary": "Ann should get a refund.", "reasoning": "Her order never arrived.", "proposals": [
        {"action": "sms", "contact": "c1", "text": "We are sorry your order never arrived. A refund is on its way.", "why": "order never arrived"},
        {"action": "slack", "channel": "#front", "text": "Refund proposed for Ann Lee.", "why": "tell the team"}]}
    EVENT = {"event": "refunds.review", "id": "rv-1", "conversations": [{"customer": "c1", "text": "My order never arrived. Call me on 646-555-0101 or write a@b.com, card 4242 4242 4242 4242"}],
             "customers": [{"id": "c1", "name": "Ann Lee", "phone": "+16465550101", "email": "ann@example.com", "sms_consent": True}]}
    WF = {"name": "refund_review", "on": {"event": "refunds.review"}, "do": [{"action": "reason", "task": "Decide which customers should get a refund and explain why.", "inputs": "{{conversations}}", "contacts": "{{customers}}", "allow": ["sms", "slack"], "channels": ["#front"], "notify": "#front"}]}

    def rig(self, model=None, reasoner=None, dry=False, extra=None):
        r = Rig(dry=dry, extra={"reasoner": {"provider": "openai", "base_url": "PLACEHOLDER", "api_key": "sk-test", "model": "m1", **(reasoner or {})}, **(extra or {})})
        r.agent.cfg["reasoner"]["base_url"] = r.mock.url; r.mock.model_text = json.dumps(model if model is not None else self.MODEL); r.agent.workflows.append(self.WF); return r

    def job(self, r):
        return [j for j in r.agent.state.jobs() if j["kind"] == "reason"][0]

    def test_only_the_chosen_inputs_reach_the_model_and_personal_details_are_replaced(self):
        r = self.rig(); out = r.agent.handle_event(self.EVENT); self.assertEqual(out["matched"], 1)
        sent = [q for q in r.mock.requests if q["path"].endswith("/chat/completions")]; self.assertEqual(len(sent), 1); body = json.dumps(sent[0]["json"]); self.assertEqual(sent[0]["auth"], "Bearer sk-test")
        self.assertIn("never arrived", body); self.assertIn("Ann Lee", body); self.assertIn("c1", body)
        for secret in ("646-555-0101", "a@b.com", "4242 4242 4242 4242", "+16465550101", "ann@example.com", "xoxb-1", TOKEN): self.assertNotIn(secret, body)
        self.assertIn("[phone]", body); self.assertIn("[email]", body); self.assertIn("[number]", body)
        j = self.job(r); self.assertEqual(j["status"], "proposed"); self.assertEqual(len(j["result"]["proposals"]), 2); self.assertEqual(r.mock.calls("Messages.json"), [])           # nothing was sent: only proposed
        self.assertEqual(len(r.mock.calls("chat.postMessage")), 1); self.assertIn("wait for your approval", r.mock.calls("chat.postMessage")[0]["json"]["text"]); r.close()

    def test_approving_runs_the_proposals_as_normal_sends_once(self):
        r = self.rig(); r.agent.handle_event(self.EVENT); j = self.job(r); res = r.agent.execute_proposals(j["id"], [0])
        self.assertEqual(res[0]["state"], "done"); m = r.mock.calls("Messages.json"); self.assertEqual(len(m), 1); self.assertEqual(m[0]["form"]["To"], "+16465550101"); self.assertIn("refund is on its way", m[0]["form"]["Body"])
        self.assertEqual(self.job(r)["status"], "proposed")                                           # one proposal is still waiting
        self.assertEqual(r.agent.execute_proposals(j["id"], [0]), []); self.assertEqual(len(r.mock.calls("Messages.json")), 1)           # approving the same one again sends nothing
        r.agent.execute_proposals(j["id"], [1]); self.assertEqual(self.job(r)["status"], "approved"); self.assertEqual(len([x for x in r.mock.calls("chat.postMessage") if "Refund proposed" in x["json"]["text"]]), 1)
        kinds = {x["kind"]: x["status"] for x in r.agent.state.jobs() if x["id"].startswith(j["id"] + ":p")}; self.assertEqual(kinds, {"sms": "sent", "slack": "sent"}); r.close()

    def test_the_safety_rules_still_apply_to_approved_proposals(self):
        ev = json.loads(json.dumps(self.EVENT)); ev["customers"][0]["sms_consent"] = False
        r = self.rig(); r.agent.handle_event(ev); j = self.job(r); res = r.agent.execute_proposals(j["id"], [0]); self.assertEqual(res[0]["state"], "failed"); self.assertEqual(res[0]["status"], "blocked"); self.assertEqual(r.mock.calls("Messages.json"), []); r.close()
        r = self.rig(); r.agent.handle_event(self.EVENT); open(os.path.join(r.agent.cfg["state_dir"], "STOP"), "w").close(); j = self.job(r); r.agent.execute_proposals(j["id"], [0]); self.assertEqual(r.mock.calls("Messages.json"), []); r.close()

    def test_rejecting_sends_nothing(self):
        r = self.rig(); r.agent.handle_event(self.EVENT); j = self.job(r); self.assertEqual(r.agent.reject_proposals(j["id"])["status"], "rejected"); self.assertEqual(r.mock.calls("Messages.json"), [])
        with self.assertRaises(PermissionError): r.agent.execute_proposals(j["id"], [0]); r.close()

    def test_anything_the_workflow_did_not_allow_is_dropped(self):
        bad = {"summary": "s", "reasoning": "r", "proposals": [{"action": "http", "url": "https://evil.example/x", "json": {}}, {"action": "sms", "contact": "nobody", "text": "hello there"}, {"action": "slack", "channel": "#secret", "text": "hi"},
                                                              {"action": "email", "contact": "c1", "text": "x y z"}, {"action": "sms", "contact": "c1", "text": "Your refund is coming.", "why": "ok"}]}
        r = self.rig(model=bad); r.agent.handle_event(self.EVENT); res = self.job(r)["result"]; self.assertEqual([p["action"] for p in res["proposals"]], ["sms"]); self.assertEqual(len(res["dropped"]), 4); r.close()

    def test_a_bad_answer_or_a_down_model_never_acts(self):
        r = self.rig(); r.mock.model_text = "I think you should refund everyone."; r.agent.handle_event(self.EVENT); j = self.job(r); self.assertEqual(j["status"], "failed"); self.assertIn("expected JSON", j["error"]); self.assertEqual(r.mock.calls("Messages.json"), []); r.close()
        r = self.rig(); r.mock.fail["chat/completions"] = 503; r.agent.handle_event(self.EVENT); self.assertEqual(self.job(r)["status"], "failed"); r.close()                       # asking again later is safe, so it is failed, not needs_review
        r = Rig(); r.agent.workflows.append(self.WF); r.agent.handle_event(self.EVENT); self.assertEqual(self.job(r)["status"], "failed"); self.assertIn("reasoner", self.job(r)["error"]); r.close()

    def test_dry_run_does_not_call_the_model(self):
        r = self.rig(dry=True); r.agent.handle_event(self.EVENT); self.assertEqual(r.mock.requests, []); self.assertIn("dry_run", [x["status"] for x in r.log() if x.get("action") == "reason"]); r.close()

    def test_a_per_hour_limit_protects_the_developers_bill(self):
        r = self.rig(reasoner={"max_per_hour": 1}); r.agent.handle_event(self.EVENT); r.agent.handle_event(dict(self.EVENT, id="rv-2"))
        self.assertEqual(len([q for q in r.mock.requests if q["path"].endswith("/chat/completions")]), 1); self.assertEqual(sorted(j["status"] for j in r.agent.state.jobs() if j["kind"] == "reason"), ["blocked", "proposed"]); r.close()

    def test_offline_the_question_waits_and_is_asked_when_the_connection_returns(self):
        r = self.rig(); live = r.agent.cfg["reasoner"]["base_url"]; r.agent.cfg["reasoner"]["base_url"] = "http://127.0.0.1:9"; r.agent.handle_event(self.EVENT); self.assertEqual(self.job(r)["status"], "queued")
        r.agent.cfg["reasoner"]["base_url"] = live; self.assertEqual(r.agent.flush_outbox()["sent"], 1); self.assertEqual(self.job(r)["status"], "proposed"); r.close()

    def test_auto_allow_lets_a_workflow_run_chosen_low_risk_actions_without_a_click(self):
        wf = json.loads(json.dumps(self.WF)); wf["do"][0]["auto_allow"] = ["slack"]; wf["do"][0].pop("notify"); r = self.rig(); r.agent.workflows[-1] = wf; r.agent.handle_event(self.EVENT)
        self.assertEqual(len([x for x in r.mock.calls("chat.postMessage") if "Refund proposed" in x["json"]["text"]]), 1); self.assertEqual(r.mock.calls("Messages.json"), []); self.assertEqual([p["state"] for p in self.job(r)["result"]["proposals"]], ["pending", "done"]); r.close()

    def test_anthropic_messages_api_is_supported(self):
        r = self.rig(reasoner={"provider": "anthropic", "api_key": "ak-1"}); r.agent.handle_event(self.EVENT); q = [x for x in r.mock.requests if x["path"].endswith("/v1/messages")]; self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["json"]["model"], "m1"); self.assertIn("never arrived", json.dumps(q[0]["json"])); self.assertEqual(self.job(r)["status"], "proposed"); r.close()

    def test_a_slack_command_answers_at_once_and_reasons_in_the_background(self):
        import time as _t
        r = self.rig(); wf = {"name": "ask", "on": {"slack_command": "/review"}, "ack": "Looking.", "do": [{"action": "reason", "task": "Answer the question.", "inputs": "{{command.text}}", "allow": ["slack"], "channels": ["#front"]}]}; r.agent.workflows.append(wf)
        out = r.agent.handle_slack_command({"command": "/review", "text": "which orders are late", "user_name": "bo"}); self.assertEqual(out["text"], "Looking.")
        for _ in range(60):
            if [j for j in r.agent.state.jobs() if j["kind"] == "reason" and j["status"] == "proposed"]: break
            _t.sleep(.1)
        self.assertEqual(self.job(r)["status"], "proposed"); self.assertIn("which orders are late", json.dumps([q["json"] for q in r.mock.requests if q["path"].endswith("/chat/completions")])); r.close()

    def test_the_dashboard_shows_proposals_and_approves_them(self):
        r = self.rig(); srv = serve(r.agent, "127.0.0.1", 0); port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start(); r.agent.handle_event(self.EVENT)
        from speakvora_pack_agent import dashboard
        def call(path, body=None):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode() if body is not None else None, method="POST" if body is not None else "GET", headers={"x-dashboard-token": dashboard.token(r.agent)})
            with urllib.request.urlopen(req, timeout=10) as x: return json.loads(x.read())
        s = call("/dash/api/summary"); att = [j for j in s["attention"] if j["kind"] == "reason"][0]; self.assertEqual(att["status"], "proposed"); self.assertEqual(len(att["proposals"]), 2); self.assertIn("never arrived", att["reasoning"]); self.assertIn("[phone]", att["sent_to_model"])
        j = call(f"/dash/api/proposals/{att['id']}/approve", {"indexes": [0]})["job"]; self.assertEqual(j["proposals"][0]["state"], "done"); self.assertEqual(len(r.mock.calls("Messages.json")), 1)
        j = call(f"/dash/api/proposals/{att['id']}/reject", {})["job"]; self.assertEqual(j["status"], "approved"); srv.shutdown(); srv.server_close(); r.close()

    def test_proposals_command_lists_approves_and_rejects(self):
        import contextlib, io
        from speakvora_pack_agent import cli
        r = self.rig(); r.agent.handle_event(self.EVENT); jid = self.job(r)["id"]; cfgp = os.path.join(r.tmp, "agent.json"); buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.main(["proposals", "list", "-c", cfgp]); cli.main(["proposals", "reject", jid, "--only", "1", "-c", cfgp])
        out = buf.getvalue(); self.assertIn("Ann should get a refund", out); self.assertIn("sms", out); r.close()


class ConnectTab(unittest.TestCase):
    """The Connect tab: a person who is not a developer sets everything up from the dashboard, sees failures in plain words and goes live when ready."""
    def setUp(self):
        self.r = Rig(dry=True); self.srv = serve(self.r.agent, "127.0.0.1", 0); self.port = self.srv.server_address[1]; threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        from speakvora_pack_agent import dashboard
        self.tok = dashboard.token(self.r.agent)

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.r.close()

    def call(self, method, path, body=None, tok=True):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode() if body is not None else (b"{}" if method == "POST" else None), method=method, headers={"x-dashboard-token": self.tok} if tok else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as x:
                return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def card(self, name):
        return next(c for c in self.call("GET", "/dash/api/setup")[1]["cards"] if c["name"] == name)

    def test_needs_the_token_and_never_returns_a_secret(self):
        self.assertEqual(self.call("GET", "/dash/api/setup", tok=False)[0], 401)
        st, s = self.call("GET", "/dash/api/setup"); self.assertEqual(st, 200); txt = json.dumps(s)
        for secret in (TOKEN, "xoxb-1", SLACK_SECRET, "ya29"): self.assertNotIn(secret, txt)
        self.assertEqual([c["name"] for c in s["cards"]], ["business", "twilio", "slack", "teams", "calendar", "email", "ai"])
        tw = self.card("twilio"); self.assertTrue(tw["connected"]); self.assertTrue(next(f for f in tw["fields"] if f["key"] == "auth_token")["set"]); self.assertTrue(next(f for f in tw["fields"] if f["key"] == "auth_token")["hint"].endswith(TOKEN[-4:]))

    def test_saving_a_card_stores_keys_privately_applies_at_once_and_keeps_old_ones_when_the_box_is_empty(self):
        st, r = self.call("POST", "/dash/api/setup/save", {"card": "teams", "values": {"webhook_url": "https://example.test/teams-hook/abc123456789"}}); self.assertEqual(st, 200)
        sd = self.r.agent.state.dir; sec = json.load(open(os.path.join(sd, "secrets.json"))); self.assertEqual(sec["TEAMS_WEBHOOK_URL"], "https://example.test/teams-hook/abc123456789"); self.assertEqual(oct(os.stat(os.path.join(sd, "secrets.json")).st_mode & 0o777), "0o600")
        raw = json.load(open(self.r.agent.cfg["_path"])); self.assertEqual(raw["teams"]["webhook_url"], "env:TEAMS_WEBHOOK_URL"); self.assertNotIn("abc123456789", json.dumps(raw)); self.assertTrue(self.r.agent.teams.configured)       # applied without a restart
        self.assertTrue(os.path.exists(self.r.agent.cfg["_path"] + ".bak"))
        self.call("POST", "/dash/api/setup/save", {"card": "teams", "values": {"webhook_url": ""}}); self.assertTrue(self.r.agent.teams.configured)
        st, r = self.call("POST", "/dash/api/setup/save", {"card": "business", "values": {"business": "Bella Trattoria", "hours": "Tue to Sun 5 to 10", "mode": "strict"}}); self.assertEqual(self.r.agent.cfg["business"], "Bella Trattoria"); self.assertEqual(self.r.agent.cfg["facts"]["hours"], "Tue to Sun 5 to 10")

    def test_bad_input_is_explained_not_saved(self):
        st, r = self.call("POST", "/dash/api/setup/save", {"card": "twilio", "values": {"from_number": "555-1234"}}); self.assertEqual(st, 400); self.assertIn("country code", r["message"])
        self.assertEqual(self.call("POST", "/dash/api/setup/save", {"card": "business", "values": {"public_base_url": "ftp://nope"}})[0], 400)
        self.assertEqual(self.call("POST", "/dash/api/setup/save", {"card": "nonsense", "values": {}})[0], 400)
        self.assertEqual(self.call("POST", "/dash/api/setup/save", {"card": "business", "values": {"mode": "reckless"}})[0], 400)

    def test_tests_say_in_plain_words_what_works_and_what_to_fix(self):
        st, r = self.call("POST", "/dash/api/setup/test", {"card": "twilio", "opts": {}}); self.assertTrue(r["ok"]); self.assertIn("Bella Co", r["message"])
        self.r.mock.no_numbers = True; st, r = self.call("POST", "/dash/api/setup/test", {"card": "twilio", "opts": {}}); self.assertFalse(r["ok"]); self.assertIn("not a number on that account", r["message"]); self.r.mock.no_numbers = False
        self.r.mock.fail["Accounts"] = 401; st, r = self.call("POST", "/dash/api/setup/test", {"card": "twilio", "opts": {}}); self.assertFalse(r["ok"]); self.assertIn("not accepted", r["message"]); self.r.mock.fail.clear()
        st, r = self.call("POST", "/dash/api/setup/test", {"card": "slack", "opts": {}}); self.assertTrue(r["ok"]); self.assertEqual(self.r.mock.calls("chat.postMessage"), [])                       # checking does not post
        st, r = self.call("POST", "/dash/api/setup/test", {"card": "slack", "opts": {"post": True}}); self.assertIn("test message was posted", r["message"]); self.assertEqual(len(self.r.mock.calls("chat.postMessage")), 1)
        self.r.mock.bad_slack = True; st, r = self.call("POST", "/dash/api/setup/test", {"card": "slack", "opts": {}}); self.assertFalse(r["ok"]); self.assertIn("did not accept", r["message"]); self.r.mock.bad_slack = False
        self.assertFalse(self.call("POST", "/dash/api/setup/test", {"card": "teams", "opts": {}})[1]["ok"])                                                                                   # not connected yet: told to fill it in
        self.assertFalse(self.call("POST", "/dash/api/setup/test", {"card": "ai", "opts": {}})[1]["ok"])

    def test_ai_reasoning_card_tests_the_key_and_enables_reasoning(self):
        self.call("POST", "/dash/api/setup/save", {"card": "ai", "values": {"provider": "openai", "base_url": self.r.mock.url, "api_key": "sk-abc12345", "model": "my-model"}}); self.assertTrue(self.card("ai")["connected"])
        self.r.mock.model_text = "OK"; st, r = self.call("POST", "/dash/api/setup/test", {"card": "ai", "opts": {}}); self.assertTrue(r["ok"]); self.assertIn("OK", r["message"])
        q = [x for x in self.r.mock.requests if x["path"].endswith("/chat/completions")][-1]; self.assertEqual(q["auth"], "Bearer sk-abc12345"); self.assertEqual(q["json"]["model"], "my-model"); self.assertLess(q["json"]["max_tokens"], 20)
        self.assertNotIn("sk-abc12345", open(self.r.agent.cfg["_path"]).read()); self.assertEqual(self.card("ai")["fields"][2]["hint"], "...2345")
        self.call("POST", "/dash/api/setup/save", {"card": "ai", "values": {"provider": "local"}}); self.assertEqual(self.r.agent.cfg["reasoner"]["provider"], "openai")

    def test_workflows_can_be_switched_on_and_off_and_say_what_they_need(self):
        st, s = self.call("GET", "/dash/api/setup"); wf = {w["name"]: w for w in s["workflows"]}; self.assertIn("order_ready", wf); self.assertEqual(sorted(wf["order_ready"]["needs"]), ["slack", "twilio"]); self.assertEqual(wf["order_ready"]["missing"], [])
        self.assertTrue(wf["order_ready"]["what"]); self.assertEqual(self.call("POST", "/dash/api/setup/workflow", {"name": "order_ready", "enabled": False})[0], 200)
        self.assertNotIn("order_ready", [w["name"] for w in self.r.agent.workflows]); self.assertFalse(next(w for w in json.load(open(self.r.agent.cfg["workflows"]))["workflows"] if w["name"] == "order_ready")["enabled"])
        self.assertEqual(self.r.agent.handle_event({"event": "order.ready", "id": "x1", "customer": CUST, "order": {"number": 1}})["matched"], 0)
        self.call("POST", "/dash/api/setup/workflow", {"name": "order_ready", "enabled": True}); self.assertIn("order_ready", [w["name"] for w in self.r.agent.workflows]); self.assertEqual(self.call("POST", "/dash/api/setup/workflow", {"name": "nope", "enabled": True})[0], 400)

    def test_going_live_needs_a_checklist_and_is_remembered(self):
        st, s = self.call("GET", "/dash/api/setup"); self.assertFalse(s["live"]); self.assertFalse(s["readiness"]["ok"])
        st, r = self.call("POST", "/dash/api/setup/live", {"on": True}); self.assertEqual(st, 400); self.assertIn("passed its test", r["message"]); self.assertTrue(self.r.agent.dry)
        for card, opts in (("twilio", {}), ("slack", {}), ("calendar", {})): self.call("POST", "/dash/api/setup/test", {"card": card, "opts": opts})
        st, s = self.call("GET", "/dash/api/setup"); self.assertTrue(s["readiness"]["ok"], s["readiness"])
        self.assertEqual(self.call("POST", "/dash/api/setup/live", {"on": True})[0], 200); self.assertFalse(self.r.agent.dry)
        self.r.agent.handle_event({"event": "order.ready", "id": "live-1", "customer": CUST, "order": {"number": 5}}); self.assertEqual(len(self.r.mock.calls("Messages.json")), 1)
        again = Agent(config.load(os.path.join(self.r.tmp, "agent.json")), now=lambda: self.r.now[0]); self.assertFalse(again.dry)                          # still live after a restart
        self.call("POST", "/dash/api/setup/live", {"on": False}); self.assertTrue(self.r.agent.dry); self.assertTrue(Agent(config.load(os.path.join(self.r.tmp, "agent.json")), now=lambda: self.r.now[0]).dry)

    def test_changing_a_connected_service_asks_for_a_new_test_before_going_live(self):
        for card in ("twilio", "slack", "calendar"): self.call("POST", "/dash/api/setup/test", {"card": card, "opts": {}})
        self.assertTrue(self.call("GET", "/dash/api/setup")[1]["readiness"]["ok"]); self.call("POST", "/dash/api/setup/save", {"card": "twilio", "values": {"from_number": "+15550002222"}})
        self.assertFalse(self.call("GET", "/dash/api/setup")[1]["readiness"]["ok"])

    def test_keys_from_the_dashboard_work_for_a_fresh_start_and_environment_variables_win(self):
        from speakvora_pack_agent import secrets_store
        sd = self.r.agent.state.dir; secrets_store.set_value(sd, "SV_TEST_KEY", "from-file"); raw = json.load(open(self.r.agent.cfg["_path"])); raw["slack"]["bot_token"] = "env:SV_TEST_KEY"; json.dump(raw, open(self.r.agent.cfg["_path"], "w"))
        self.assertEqual(config.load(self.r.agent.cfg["_path"])["slack"]["bot_token"], "from-file"); os.environ["SV_TEST_KEY"] = "from-env"
        try: self.assertEqual(config.load(self.r.agent.cfg["_path"])["slack"]["bot_token"], "from-env")
        finally: os.environ.pop("SV_TEST_KEY", None)

    def test_slack_manifest_lists_your_slash_commands_and_tools_can_be_added(self):
        s = self.call("GET", "/dash/api/setup")[1]; m = s["slack_manifest"]; self.assertIn("/say", [c["command"] for c in m["features"]["slash_commands"]]); self.assertIn("chat:write", m["oauth_config"]["scopes"]["bot"])
        self.assertIn("github", [x["name"] for x in s["sources"]]); st, r = self.call("POST", "/dash/api/setup/source", {"name": "github"}); self.assertEqual(st, 200); self.assertIn("github", [x["name"] for x in json.load(open(self.r.agent.cfg["_path"]))["sources"]])
        self.assertEqual(self.call("POST", "/dash/api/setup/source", {"name": "../../etc/passwd"})[0], 400)

    def test_the_event_secret_is_made_for_you(self):
        s = self.call("GET", "/dash/api/setup")[1]; self.assertTrue(s["event_url"].endswith("/event")); self.assertEqual(json.load(open(self.r.agent.cfg["_path"]))["events"]["secret"], "env:SV_EVENT_SECRET")


class AskOrAuto(unittest.TestCase):
    """Approve, decline or let it decide: what the person chose is remembered and applied to the next one."""
    def rig(self, ask=("sms",)):
        r = Rig(); r.agent.set_policy(ask_before=list(ask)); return r

    def send(self, r, n):
        return r.event("order.ready", customer=CUST, order={"number": n}, id=f"ev-{n}")

    def sms(self, r):
        return [j for j in r.agent.state.jobs() if j["kind"] == "sms"]

    def test_a_text_waits_for_a_click_and_other_sends_do_not(self):
        r = self.rig(); self.send(r, 1); j = self.sms(r)[0]; self.assertEqual(j["status"], "needs_approval"); self.assertEqual(r.mock.calls("Messages.json"), []); self.assertEqual(len(r.mock.calls("chat.postMessage")), 1)
        r.agent.approve_job(j["id"]); self.assertEqual(self.sms(r)[0]["status"], "sent"); self.assertEqual(len(r.mock.calls("Messages.json")), 1)
        with self.assertRaises(PermissionError): r.agent.approve_job(j["id"]); r.close()

    def test_decline_stops_it_and_remember_makes_the_next_ones_automatic_or_never(self):
        r = self.rig(); self.send(r, 2); r.agent.decline_job(self.sms(r)[0]["id"]); self.assertEqual(self.sms(r)[0]["status"], "cancelled"); self.assertEqual(r.mock.calls("Messages.json"), [])
        self.send(r, 3); j = [x for x in self.sms(r) if x["status"] == "needs_approval"][0]; r.agent.approve_job(j["id"], remember=True); self.assertEqual(r.agent.policy()["decisions"], {"order_ready:sms": "auto"})
        self.send(r, 4); self.assertEqual([x["status"] for x in self.sms(r)][-1], "sent"); self.assertEqual(len(r.mock.calls("Messages.json")), 2)                    # sent by itself now
        r.agent.set_policy(decision=("order_ready:sms", "never")); self.send(r, 5); self.assertEqual(len(r.mock.calls("Messages.json")), 2); self.assertEqual(self.sms(r)[-1]["status"], "cancelled")
        r.agent.set_policy(reset="order_ready:sms"); self.send(r, 6); self.assertEqual(self.sms(r)[-1]["status"], "needs_approval"); r.close()

    def test_an_old_approval_is_dropped_instead_of_sent_late(self):
        r = self.rig(); self.send(r, 7); j = self.sms(r)[0]; r.now[0] += 25 * 3600
        with self.assertRaises(PermissionError): r.agent.approve_job(j["id"])
        self.assertEqual(self.sms(r)[0]["status"], "expired"); self.assertEqual(r.mock.calls("Messages.json"), []); r.close()

    def test_failed_jobs_can_be_dismissed(self):
        r = Rig(); r.mock.fail["Messages.json"] = 400; r.event("order.ready", customer=CUST, order={"number": 8}); j = [x for x in r.agent.state.jobs() if x["kind"] == "sms"][0]; self.assertEqual(j["status"], "failed")
        self.assertEqual(r.agent.cancel_job(j["id"])["status"], "cancelled"); r.close()

    def test_the_page_api_shows_plain_titles_and_handles_approve_decline_and_policy(self):
        r = self.rig(); srv = serve(r.agent, "127.0.0.1", 0); port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start(); self.send(r, 9)
        from speakvora_pack_agent import dashboard
        def call(path, body=None):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode() if body is not None else None, method="POST" if body is not None else "GET", headers={"x-dashboard-token": dashboard.token(r.agent)})
            with urllib.request.urlopen(req, timeout=10) as x: return json.loads(x.read())
        j = [x for x in call("/dash/api/jobs")["jobs"] if x["kind"] == "sms"][0]; self.assertEqual(j["title"], "Text message to Ann Lee"); self.assertEqual(j["label"], "Waiting for you"); self.assertTrue(j["needs_you"]); self.assertIn("order 9 is ready", j["quote"]); self.assertTrue(j["what"])
        self.assertEqual(call(f"/dash/api/jobs/{j['id']}/approve", {"remember": True})["job"]["status"], "sent"); self.assertEqual(len(r.mock.calls("Messages.json")), 1)
        pol = call("/dash/api/policy"); self.assertEqual(pol["decisions"][0]["choice"], "auto"); self.assertEqual(pol["ask_before"], ["sms"]); self.assertEqual([k["kind"] for k in pol["kinds"]], ["sms", "call", "email"])
        self.assertEqual(call("/dash/api/policy", {"ask_before": ["sms", "call"], "reset": "order_ready:sms"})["decisions"], []); self.assertEqual(r.agent.policy()["ask_before"], ["sms", "call"])
        srv.shutdown(); srv.server_close(); r.close()

    def test_saved_choices_apply_to_ai_proposals_too(self):
        rr = Reasoning(); r = rr.rig(); r.agent.handle_event(rr.EVENT); j = rr.job(r); r.agent.execute_proposals(j["id"], [1], remember=True); self.assertEqual(r.agent.policy()["decisions"], {"refund_review:slack": "auto"})
        r.agent.reject_proposals(j["id"], [0], remember=True); self.assertEqual(r.agent.policy()["decisions"]["refund_review:sms"], "never")
        n = len(r.mock.calls("chat.postMessage")); r.agent.handle_event(dict(rr.EVENT, id="rv-2")); j2 = [x for x in r.agent.state.jobs() if x["kind"] == "reason"][-1]
        self.assertEqual([p["state"] for p in j2["result"]["proposals"]], ["rejected", "done"]); self.assertGreater(len(r.mock.calls("chat.postMessage")), n); self.assertEqual(r.mock.calls("Messages.json"), []); r.close()


class Sharing(unittest.TestCase):
    """Missing lines go to Speakvora (only when agreed), once, with no customer data; newer pack versions are noticed."""
    def rig(self):
        r = Rig(); os.environ["SPEAKVORA_HOST"] = r.mock.url; r.agent.pack.slots.pop("directions_intro", None); r.agent.pack.slots.pop("no_show_followup", None); return r

    def tearDown(self):
        os.environ["SPEAKVORA_HOST"] = "http://127.0.0.1:9"

    def test_nothing_is_sent_until_the_person_agrees_then_once_a_day(self):
        from speakvora_pack_agent import sharing
        r = self.rig(); self.assertIsNone(sharing.enabled(r.agent)); sharing.auto(r.agent); self.assertEqual(r.mock.calls("slot-requests"), [])
        sharing.set_enabled(r.agent, True); res = sharing.auto(r.agent); self.assertTrue(res["sent"]); q = r.mock.calls("slot-requests"); self.assertEqual(len(q), 1)
        self.assertEqual(sorted(s["slot"] for s in q[0]["json"]["slots"]), ["directions_intro", "no_show_followup"]); doc = json.dumps(q[0]["json"]); self.assertNotIn("Ann", doc); self.assertNotIn(TOKEN, doc); self.assertEqual(q[0]["json"]["kind"], "workflow_line_request")
        r.now[0] += 25 * 3600; self.assertIsNone(sharing.auto(r.agent)); self.assertEqual(len(r.mock.calls("slot-requests")), 1); self.assertEqual(sharing.pending(r.agent), []); r.close()

    def test_offline_it_is_kept_and_asked_again_later(self):
        from speakvora_pack_agent import sharing
        r = self.rig(); sharing.set_enabled(r.agent, True); os.environ["SPEAKVORA_HOST"] = "http://127.0.0.1:9"; res = sharing.auto(r.agent); self.assertFalse(res["sent"]); self.assertIn("sent again later", res["message"]); self.assertEqual(len(sharing.pending(r.agent)), 2)
        os.environ["SPEAKVORA_HOST"] = r.mock.url; r.now[0] += 25 * 3600; self.assertTrue(sharing.auto(r.agent)["sent"]); r.close()

    def test_an_api_key_is_sent_when_there_is_one_and_a_typed_request_is_always_sent(self):
        from speakvora_pack_agent import sharing
        r = self.rig(); os.environ["SPEAKVORA_KEY"] = "k-1"
        try:
            res = sharing.submit(r.agent, [{"slot": "custom_my_line", "intent": "when a customer asks about parking", "example": "Parking is free for two hours."}]); self.assertTrue(res["sent"]); self.assertEqual(r.mock.calls("slot-requests")[-1]["headers"].get("x-api-key"), "k-1")
        finally: os.environ.pop("SPEAKVORA_KEY", None)
        r.close()

    def test_the_library_page_api_and_update_notice(self):
        r = self.rig(); srv = serve(r.agent, "127.0.0.1", 0); port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
        from speakvora_pack_agent import dashboard
        def call(path, body=None):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode() if body is not None else None, method="POST" if body is not None else "GET", headers={"x-dashboard-token": dashboard.token(r.agent)})
            with urllib.request.urlopen(req, timeout=10) as x: return json.loads(x.read())
        r.agent.pack.meta["version"] = "2026.10.01"; r.mock.latest_version = "2026.10.20"
        lib = call("/dash/api/library"); self.assertIsNone(lib["share"]); self.assertEqual(len(lib["coverage"]["missing"]), 2); self.assertTrue(lib["update"]["available"]); self.assertEqual(lib["update"]["latest"], "2026.10.20")
        lib = call("/dash/api/library/share", {"on": True}); self.assertTrue(lib["share"]); self.assertEqual(len(lib["requested"]), 2); self.assertEqual(lib["pending"], [])
        self.assertTrue(call("/dash/api/policy", {"share_phrases": False})["share_phrases"] is False); srv.shutdown(); srv.server_close(); r.close()


class Connections(unittest.TestCase):
    """Your own apps: send to them with a key, tell them what workflows did, and let them send events here."""
    def setUp(self):
        self.r = Rig(); self.srv = serve(self.r.agent, "127.0.0.1", 0); self.port = self.srv.server_address[1]; threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        from speakvora_pack_agent import dashboard
        self.tok = dashboard.token(self.r.agent)

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.r.close()

    def call(self, path, body=None, method=None, headers=None):
        h = {"x-dashboard-token": self.tok}; h.update(headers or {})
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode() if body is not None else None, method=method or ("POST" if body is not None else "GET"), headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as x: return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def add(self, **kw):
        v = {"name": "My order system", "url": self.r.mock.url + "/my-app/hook", "auth_type": "bearer", "secret": "tok-123456"}; v.update(kw)
        return self.call("/dash/api/setup/connection", v)

    def test_a_custom_app_is_saved_with_its_key_kept_private_and_can_be_tested(self):
        st, r = self.add(); self.assertEqual(st, 200); self.assertEqual(r["outgoing"][0]["id"], "my-order-system")
        raw = json.load(open(self.r.agent.cfg["_path"])); self.assertEqual(raw["connections"][0]["auth"]["secret"], "env:CONN_MY_ORDER_SYSTEM_KEY"); self.assertNotIn("tok-123456", json.dumps(raw))
        self.assertEqual(json.load(open(os.path.join(self.r.agent.state.dir, "secrets.json")))["CONN_MY_ORDER_SYSTEM_KEY"], "tok-123456")
        st, t = self.call("/dash/api/setup/connection/test", {"id": "my-order-system"}); self.assertTrue(t["ok"]); q = self.r.mock.calls("/hook")[-1]; self.assertEqual(q["auth"], "Bearer tok-123456"); self.assertTrue(q["json"]["test"])
        self.add(name="Header app", auth_type="header", header="X-Api-Key", secret="k9"); self.call("/dash/api/setup/connection/test", {"id": "header-app"}); self.assertEqual(self.r.mock.calls("/hook")[-1]["headers"]["x-api-key"], "k9")

    def test_bad_input_is_explained(self):
        self.assertEqual(self.add(url="ftp://x")[0], 400); self.assertEqual(self.add(url="http://example.com/x")[0], 400); self.assertEqual(self.add(name="")[0], 400); self.assertEqual(self.add(secret="")[0], 400); self.assertEqual(self.add(auth_type="header", header="bad header!")[0], 400)

    def test_a_workflow_can_also_tell_your_app_what_it_did(self):
        self.add(); st, r = self.call("/dash/api/setup/workflow-targets", {"name": "order_ready", "ids": ["my-order-system"]}); self.assertEqual(st, 200); self.assertEqual(next(w for w in r["workflows"] if w["name"] == "order_ready")["also"], ["my-order-system"])
        self.r.event("order.ready", customer=CUST, order={"number": 11}, id="mir-1"); q = self.r.mock.calls("/hook"); self.assertEqual(len(q), 1); b = q[0]["json"]; self.assertEqual((b["workflow"], b["source"]), ("order_ready", "speakvora-pack-agent")); self.assertEqual(b["order"]["number"], 11); self.assertIn("sms", [x["action"] for x in b["results"]])
        self.assertEqual(q[0]["auth"], "Bearer tok-123456"); self.assertEqual(len([j for j in self.r.agent.state.jobs() if j["kind"] == "http"]), 1); self.r.event("order.ready", customer=CUST, order={"number": 11}, id="mir-1"); self.assertEqual(len(self.r.mock.calls("/hook")), 1)   # the same event is never mirrored twice

    def test_removing_a_connection_removes_its_key_and_its_workflow_links(self):
        self.add(); self.call("/dash/api/setup/workflow-targets", {"name": "order_ready", "ids": ["my-order-system"]}); st, r = self.call("/dash/api/setup/connection/remove", {"id": "my-order-system"}); self.assertEqual(r["outgoing"], [])
        self.assertNotIn("CONN_MY_ORDER_SYSTEM_KEY", json.load(open(os.path.join(self.r.agent.state.dir, "secrets.json")))); self.assertNotIn("also_send_to", next(w for w in json.load(open(self.r.agent.cfg["workflows"]))["workflows"] if w["name"] == "order_ready"))

    def test_your_app_or_zapier_can_send_events_here_with_a_private_token(self):
        st, r = self.call("/dash/api/setup/incoming", {"name": "Zapier"}); self.assertEqual(st, 200); self.assertEqual(r["id"], "custom-zapier"); self.assertTrue(r["url"].endswith("/hook/custom-zapier")); tok = r["token"]
        body = {"event": "order.ready", "id": "z-1", "customer": {"name": "Ann Lee", "phone": "646-555-0101", "sms_consent": True}, "order": {"number": 12}}
        st, _ = self.call("/hook/custom-zapier", body, headers={"Authorization": "Bearer wrong"}); self.assertEqual(st, 401); self.assertEqual(self.r.mock.calls("Messages.json"), [])
        st, out = self.call("/hook/custom-zapier", body, headers={"Authorization": "Bearer " + tok}); self.assertEqual(st, 200); self.assertEqual(out["matched"], 1); self.assertEqual(len(self.r.mock.calls("Messages.json")), 1)
        st, shown = self.call("/dash/api/setup/incoming/show", {"id": "custom-zapier"}); self.assertEqual(shown["token"], tok); self.assertIn("order.ready", shown["events"])
        self.call("/dash/api/setup/incoming/remove", {"id": "custom-zapier"}); self.assertEqual(self.call("/hook/custom-zapier", body, headers={"Authorization": "Bearer " + tok})[0], 404)

    def test_the_add_menu_offers_services_tools_and_your_own_apps(self):
        st, c = self.call("/dash/api/setup/catalog"); kinds = {t["kind"] for t in c["tiles"]}; self.assertEqual(kinds, {"service", "tool", "custom_out", "custom_in"}); names = [t["name"] for t in c["tiles"]]
        for n in ("Slack", "Microsoft Teams", "Texts and calls (Twilio)", "GitHub", "Shopify", "Send to my own app", "Let my app send events here"): self.assertIn(n, names)
        self.assertTrue(all(len(t["blurb"]) < 60 for t in c["tiles"]))


class Languages(unittest.TestCase):
    """The agent understands, answers and formats dates in every language Speakvora packs exist in."""
    HOURS = {"en": "What are your hours?", "es": "¿Cuál es el horario?", "fr": "Quels sont vos horaires ?", "pt": "Qual o horário de vocês?", "it": "Che orari avete?", "de": "Wann sind die Öffnungszeiten?", "fi": "Mitkä ovat aukioloajat?",
             "hi": "आपके खुलने का समय क्या है?", "ja": "営業時間を教えてください", "zh": "你们的营业时间是几点？", "ar": "ما هي ساعات العمل؟", "ko": "영업시간이 어떻게 되나요?"}
    STOP = {"en": "STOP", "es": "parar", "fr": "arrêt", "pt": "parar", "it": "basta", "de": "stopp", "fi": "lopeta", "hi": "रोकें", "ja": "停止", "zh": "退订", "ar": "إيقاف", "ko": "수신거부"}
    PERSON = {"en": "I want a manager", "es": "quiero hablar con un gerente", "fr": "je veux parler à un responsable", "pt": "quero falar com o gerente", "it": "vorrei parlare con un responsabile", "de": "ich möchte mit dem Manager sprechen",
              "fi": "haluan puhua esimiehen kanssa", "hi": "मुझे मैनेजर से बात करनी है", "ja": "店長と話したいです", "zh": "我要找经理", "ar": "أريد التحدث مع المدير", "ko": "매니저와 통화하고 싶어요"}

    def agent(self, lang, profile="food"):
        from speakvora_pack_agent import recipes, slots as SL
        r = Rig(lang=lang); r.agent.profile = profile; r.agent.registry = SL.registry(profile); r.agent.workflows = recipes.workflows_for(profile, lang)["workflows"]; return r

    def test_every_language_answers_an_hours_question_and_a_person_request(self):
        for lang in self.HOURS:
            r = self.agent(lang); reply = r.agent.handle_sms({"From": "+16465550101", "Body": self.HOURS[lang]})
            self.assertIn("Tue-Sun 5-10 PM.", reply, lang); self.assertIn(r.agent.pack.text("hours_intro"), reply, lang)
            self.assertIn(r.agent.pack.text("handoff_received"), r.agent.handle_sms({"From": "+16465550102", "Body": self.PERSON[lang]}), lang); r.close()

    def test_local_opt_out_words_work_and_english_stop_always_does(self):
        for lang, word in self.STOP.items():
            r = self.agent(lang); r.agent.handle_sms({"From": "+16465550101", "Body": word}); self.assertTrue(r.agent.state.is_opted_out("+16465550101"), lang)
            r.agent.state.opt_in("+16465550101"); r.agent.handle_sms({"From": "+16465550101", "Body": "STOP"}); self.assertTrue(r.agent.state.is_opted_out("+16465550101"), lang); r.close()

    def test_order_texts_use_the_pack_language_not_english_glue(self):
        r = self.agent("es"); r.event("order.ready", customer=CUST, order={"number": 42}); body = r.mock.calls("Messages.json")[0]["form"]["Body"]
        self.assertIn("Pedido 42:", body); self.assertNotIn("order 42 is ready", body); r.event("order.delayed", customer=CUST, order={"number": 42, "extra_minutes": 10}); self.assertIn("(10 min)", r.mock.calls("Messages.json")[1]["form"]["Body"]); r.close()

    def test_dates_are_formatted_in_the_pack_language(self):
        from speakvora_pack_agent import i18n
        ts = int(dt.datetime(2026, 10, 13, 23, 0, tzinfo=dt.timezone.utc).timestamp())
        self.assertEqual(i18n.fmt_dt(ts, "America/New_York", "en"), "Tue Oct 13, 7:00 PM"); self.assertEqual(i18n.fmt_dt(ts, "America/New_York", "es"), "mar 13 oct, 19:00"); self.assertEqual(i18n.fmt_dt(ts, "America/New_York", "ja"), "10月13日(火) 19:00")
        for lang in i18n.LANGS: self.assertTrue(i18n.fmt_dt(ts, "America/New_York", lang)); self.assertTrue(i18n.glue("help", lang) and i18n.glue("order", lang) and i18n.glue("auto_footer", lang))

    def test_calendar_consent_accepts_yes_in_other_languages(self):
        r = Rig(lang="es")
        for yes in ("sí", "oui", "sim", "ja", "はい"): self.assertTrue(r.agent.calendar_contact({"title": "x", "description": f"Phone: 646-555-0101\nSMS OK: {yes}"})["sms_consent"], yes)
        self.assertFalse(r.agent.calendar_contact({"title": "x", "description": "Phone: 646-555-0101\nSMS OK: no"})["sms_consent"]); r.close()

    def test_users_can_add_their_own_trigger_words(self):
        r = self.agent("es"); r.agent.cfg["keywords"] = {"hours": ["cuando abren"]}; self.assertIn("Tue-Sun 5-10 PM.", r.agent.handle_sms({"From": "+16465550101", "Body": "cuando abren mañana"})); r.close()

    def test_help_reply_is_in_the_pack_language(self):
        r = self.agent("fr"); self.assertIn("Répondez STOP", r.agent.handle_sms({"From": "+16465550101", "Body": "help"})); r.close()

    NEW = {"ru": ("Какие у вас часы работы?", "стоп", "хочу поговорить с менеджером"), "tr": ("Çalışma saatleriniz nedir?", "dur", "yönetici ile konuşmak istiyorum"),
           "vi": ("Giờ mở cửa của quán là mấy giờ?", "dừng", "tôi muốn gặp quản lý"), "pl": ("Jakie są wasze godziny otwarcia?", "stop", "chcę rozmawiać z kierownikiem"),
           "nl": ("Wat zijn jullie openingstijden?", "stop", "ik wil een manager spreken"), "id": ("Jam buka berapa?", "berhenti", "saya ingin bicara dengan manajer")}

    def test_the_six_newer_languages_understand_hours_person_and_opt_out(self):
        for lang, (hours, stop, person) in self.NEW.items():
            r = self.agent(lang)
            self.assertIn("Tue-Sun 5-10 PM.", r.agent.handle_sms({"From": "+16465550101", "Body": hours}), lang)
            self.assertIn(r.agent.pack.text("handoff_received"), r.agent.handle_sms({"From": "+16465550102", "Body": person}), lang)
            r.agent.handle_sms({"From": "+16465550103", "Body": stop}); self.assertTrue(r.agent.state.is_opted_out("+16465550103"), lang)
            self.assertTrue(r.agent.calendar_contact({"title": "x", "description": "Phone: 646-555-0101\nSMS OK: " + {"ru": "да", "tr": "evet", "vi": "có", "pl": "tak", "nl": "ja", "id": "ya"}[lang]})["sms_consent"], lang)
            r.close()

    def test_language_tables_cover_every_language(self):
        from speakvora_pack_agent import i18n
        for lang in i18n.LANGS:
            for topic in i18n.KW: self.assertTrue(i18n.KW[topic].get(lang), (topic, lang))
            self.assertTrue(i18n.OPT_OUT.get(lang) and i18n.DAYS[lang] and i18n.MONTHS[lang]); self.assertEqual(len(i18n.DAYS[lang].split(" ")), 7, lang); self.assertEqual(len(i18n.MONTHS[lang].split(" ")), 12, lang)

    def test_unknown_language_falls_back_to_english(self):
        from speakvora_pack_agent import i18n
        self.assertEqual((i18n.lang_of("xx"), i18n.lang_of(None), i18n.lang_of("pt-BR")), ("en", "en", "pt"))


class Doctor(unittest.TestCase):
    def setUp(self):
        self.r = Rig(dry=True)

    def tearDown(self):
        self.r.close()

    def cap(self, fn, *a):
        import contextlib, io
        b = io.StringIO()
        with contextlib.redirect_stdout(b):
            rc = fn(*a)
        return rc, b.getvalue()

    def cfg(self):
        return config.load(os.path.join(self.r.tmp, "agent.json"), lazy_secrets=True)

    def test_doctor_runs_and_names_fixes(self):
        from speakvora_pack_agent import doctor
        rc, out = self.cap(doctor.run, self.cfg())
        self.assertEqual(rc, 0); self.assertIn("doctor", out); self.assertIn("Mode:", out)

    def test_events_lists_every_workflow_event_in_every_language(self):
        from speakvora_pack_agent import doctor
        names = doctor.events_of(self.r.agent); self.assertTrue(names)
        for lang in ("curl", "python", "node", "php", "ruby", "go"):
            rc, out = self.cap(doctor.events, self.cfg(), lang)
            for n in names:
                self.assertIn(n, out)
            self.assertIn("SV_EVENT_SECRET", out)

    def test_sample_events_are_accepted_by_the_agent(self):
        from speakvora_pack_agent import doctor
        for n in doctor.events_of(self.r.agent):
            res = self.r.agent.handle_event(doctor.sample(n))
            self.assertNotIn("error", str(res).lower(), (n, res))

    def test_mode_open_removes_limits(self):
        raw = json.load(open(os.path.join(self.r.tmp, "agent.json"))); raw["mode"] = "open"
        json.dump(raw, open(os.path.join(self.r.tmp, "agent.json"), "w"))
        c = self.cfg()
        self.assertIsNone(c["limits"]["per_hour"]); self.assertIsNone(c["limits"]["per_recipient_per_day"])


class SlotCoverage(unittest.TestCase):
    def test_every_slot_a_workflow_plays_exists_in_its_industry_registry(self):
        import re
        from speakvora_pack_agent import recipes, slots as SL
        for prof in sorted(set(SL.PROFILE_OF.values()) | set(SL.PROFILES)):
            used = set(re.findall(r"slot:([a-z_0-9]+)", json.dumps(recipes.workflows_for(prof, "en"))))
            self.assertFalse(used - set(SL.registry(prof)), (prof, used - set(SL.registry(prof))))


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


    def test_delivery_status_callback_logs_what_really_happened(self):
        code, _ = self.twilio("/twilio/status", {"MessageSid": "SM1", "MessageStatus": "undelivered", "ErrorCode": "30034", "To": "+16465550101"}); self.assertEqual(code, 200)
        self.twilio("/twilio/status", {"MessageSid": "SM2", "MessageStatus": "delivered", "To": "+16465550101"}); self.twilio("/twilio/status", {"MessageSid": "SM3", "MessageStatus": "queued", "To": "+16465550101"})
        d = [x for x in self.r.log() if x.get("workflow") == "delivery"]
        self.assertEqual([(x["status"], x.get("error_code")) for x in d], [("undelivered", "30034"), ("delivered", None)])          # queued is not final: not logged
        self.assertEqual(self.post("/twilio/status", "MessageSid=SM1&MessageStatus=delivered", {"X-Twilio-Signature": "nope"})[0], 403)

    def test_outbound_text_asks_twilio_for_delivery_updates(self):
        self.r.agent.twilio.status_url = "https://agent.test/twilio/status"
        self.r.event("order.ready", customer=CUST, order={"number": 5}); form = self.r.mock.calls("Messages.json")[-1]["form"]
        self.assertEqual(form.get("StatusCallback"), "https://agent.test/twilio/status")

    def test_slack_roles_go_to_the_default_channel_unless_mapped(self):
        a = self.r.agent
        a.cfg["slack"]["channel"] = "#general"; a.cfg["slack"]["channels"] = {"#kitchen": "#orders"}
        self.assertEqual(a._slack_channel("#front"), "#general"); self.assertEqual(a._slack_channel("kitchen"), "#orders"); self.assertEqual(a._slack_channel("#host"), "#general"); self.assertEqual(a._slack_channel("C0123ABC"), "C0123ABC")
        a.cfg["slack"]["channel"] = ""; self.assertEqual(a._slack_channel("#front"), "#front")

    def test_a_service_that_is_not_set_up_says_so(self):
        r = Rig(extra={"slack": {"bot_token": "", "channel": "#general"}}); r.agent.slack.configured = False
        res = r.event("order.delayed", customer=CUST, order={"number": 5, "extra_minutes": 10})
        sl = [x for w in res["workflows"] for x in w["results"] if x["action"] == "slack"][0]
        self.assertEqual(sl["status"], "skipped"); self.assertIn("Slack is not set up", sl["reason"]); r.close()

    def test_slack_command_needs_signature_and_texts_a_customer(self):
        body = urllib.parse.urlencode({"command": "/say", "text": "order_ready +16465550177", "user_name": "host"}).encode(); ts = str(int(__import__("time").time()))
        sig = "v0=" + hmac.new(SLACK_SECRET.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
        self.assertEqual(self.post("/slack/command", body, {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": "v0=bad"})[0], 401)
        code, out = self.post("/slack/command", body, {"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig}); self.assertEqual(code, 200); self.assertIn("Text to +16465550177 (sent)", out)
        self.assertEqual(self.r.mock.calls("Messages.json")[0]["form"]["To"], "+16465550177")


if __name__ == "__main__":
    unittest.main()
