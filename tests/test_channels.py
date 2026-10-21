"""Android phone, Telegram and WhatsApp (Meta) text channels: sending, receiving signed webhooks, routing, and the setup helpers."""
import hashlib, hmac, json, threading, time, unittest, urllib.error, urllib.request

from test_pack_agent import Rig, CUST
from speakvora_pack_agent import connect as SU
from speakvora_pack_agent.server import serve


def rig(**extra):
    r = Rig(extra=extra)
    return r


def android(r):
    return {"android_sms": {"username": "u", "password": "p", "signing_key": "sk", "base_url": r.mock.url + "/android/3rdparty/v1", "lines": {"Front desk": "devA", "Billing": "devB"}}}


class Channels(unittest.TestCase):
    def mk(self, twilio=False, **extra):
        r = Rig(extra={"twilio": {"account_sid": "", "auth_token": "", "from_number": ""}} if not twilio else None); r.mock_url = r.mock.url
        raw = {"android_sms": {"username": "u", "password": "p", "signing_key": "sk", "base_url": r.mock.url + "/android/3rdparty/v1", "lines": {"Front desk": "devA", "Billing": "devB"}},
               "telegram": {"bot_token": "TG1", "webhook_secret": "tgsecret", "api_base": r.mock.url}, "whatsapp": {"access_token": "WA1", "phone_number_id": "PID1", "waba_id": "WABA1", "app_secret": "appsec", "verify_token": "vt1", "api_base": r.mock.url}}
        r.agent.cfg.update({k: v for k, v in raw.items()}); r.agent._init_services()
        if not twilio:
            r.agent.twilio.configured = False
        return r

    def test_text_goes_out_through_the_phone_when_twilio_is_not_connected(self):
        r = self.mk(); out = r.agent.run_actions("t", [{"action": "sms", "to": "+16465550101", "text": "hi", "line": "Billing"}], r.agent.ctx(customer=CUST))
        self.assertEqual(out[0]["status"], "sent"); c = r.mock.calls("/3rdparty/v1/message")[0]
        self.assertEqual((c["json"]["phoneNumbers"], c["json"]["deviceId"]), (["+16465550101"], "devB")); self.assertTrue(c["auth"].startswith("Basic ")); self.assertEqual(r.mock.calls("Messages.json"), []); r.close()

    def test_twilio_stays_the_sender_when_both_are_connected_unless_phone_is_preferred(self):
        r = self.mk(twilio=True); r.agent.run_actions("t", [{"action": "sms", "to": "+16465550101", "text": "hi"}], r.agent.ctx(customer=CUST))
        self.assertEqual(len(r.mock.calls("Messages.json")), 1); self.assertEqual(r.mock.calls("/3rdparty/v1/message"), [])
        r.agent.cfg["android_sms"]["outbound"] = "always"; r.agent.run_actions("t", [{"action": "sms", "to": "+16465550102", "text": "hi"}], r.agent.ctx(customer={**CUST, "phone": "+16465550102"}))
        self.assertEqual(len(r.mock.calls("/3rdparty/v1/message")), 1); r.close()

    def test_inbound_text_on_a_line_is_answered_from_the_same_line_and_only_once(self):
        r = self.mk(); srv = serve(r.agent, "127.0.0.1", 0); threading.Thread(target=srv.serve_forever, daemon=True).start()
        body = json.dumps({"deviceId": "devA", "event": "sms:received", "payload": {"messageId": "m1", "message": "what are your hours", "sender": "+16465550101"}}).encode()
        ts = str(int(time.time())); sig = hmac.new(b"sk", body + ts.encode(), hashlib.sha256).hexdigest()
        def post(h):
            q = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/android/sms", data=body, headers=h, method="POST")
            try:
                with urllib.request.urlopen(q, timeout=10) as x: return x.status, json.loads(x.read())
            except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
        self.assertEqual(post({"X-Timestamp": ts, "X-Signature": "0" * 64})[0], 401); self.assertEqual(post({})[0], 401)
        st, o = post({"X-Timestamp": ts, "X-Signature": sig}); self.assertEqual((st, o), (200, {"replied": True}))
        sent = r.mock.calls("/3rdparty/v1/message"); self.assertEqual(len(sent), 1); self.assertEqual(sent[0]["json"]["deviceId"], "devA"); self.assertIn("opening hours", sent[0]["json"]["textMessage"]["text"])
        self.assertEqual(post({"X-Timestamp": ts, "X-Signature": sig})[1], {"ignored": True}); self.assertEqual(len(r.mock.calls("/3rdparty/v1/message")), 1)      # the app retries until it gets a 200
        old = str(int(time.time()) - 900); self.assertEqual(post({"X-Timestamp": old, "X-Signature": hmac.new(b"sk", body + old.encode(), hashlib.sha256).hexdigest()})[0], 401)
        srv.shutdown(); r.close()

    def test_no_signing_key_means_nothing_is_accepted(self):
        r = self.mk(); r.agent.android.signing_key = ""; self.assertFalse(r.agent.android.verify(b"{}", str(int(time.time())), "x")); r.close()

    def test_stop_by_phone_text_is_obeyed_and_replied_to_by_phone(self):
        r = self.mk(); r.agent.handle_chat("android", "+16465550101", "STOP", "Front desk")
        self.assertTrue(r.agent.state.is_opted_out("+16465550101")); self.assertEqual(len(r.mock.calls("/3rdparty/v1/message")), 1); r.close()

    def test_telegram_message_is_answered_in_the_chat_and_checked_by_secret(self):
        r = self.mk(); srv = serve(r.agent, "127.0.0.1", 0); threading.Thread(target=srv.serve_forever, daemon=True).start()
        upd = json.dumps({"update_id": 5, "message": {"message_id": 1, "chat": {"id": 4242, "type": "private"}, "from": {"id": 4242, "first_name": "Ann"}, "text": "what are your hours"}}).encode()
        def post(h, data=upd):
            q = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/telegram/webhook", data=data, headers=h, method="POST")
            try:
                with urllib.request.urlopen(q, timeout=10) as x: return x.status, json.loads(x.read())
            except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
        self.assertEqual(post({"X-Telegram-Bot-Api-Secret-Token": "wrong"})[0], 401)
        self.assertEqual(post({"X-Telegram-Bot-Api-Secret-Token": "tgsecret"}), (200, {"replied": True}))
        c = r.mock.calls("/sendMessage")[0]; self.assertEqual(c["json"]["chat_id"], "4242"); self.assertIn("opening hours", c["json"]["text"])
        self.assertEqual(post({"X-Telegram-Bot-Api-Secret-Token": "tgsecret"})[1], {"ignored": True})                    # same update id twice
        group = json.dumps({"update_id": 6, "message": {"chat": {"id": -9, "type": "group"}, "text": "hours"}}).encode(); self.assertEqual(post({"X-Telegram-Bot-Api-Secret-Token": "tgsecret"}, group)[1], {"ignored": True})
        srv.shutdown(); r.close()

    def test_telegram_chat_id_is_not_mangled_into_a_phone_number(self):
        r = self.mk(); r.agent.run_actions("t", [{"action": "sms", "to": "tg:4242", "text": "your order is ready"}], r.agent.ctx(customer={"sms_consent": True}))
        self.assertEqual(r.mock.calls("/sendMessage")[0]["json"]["chat_id"], "4242"); r.close()

    def test_whatsapp_handshake_signature_and_reply(self):
        r = self.mk(); srv = serve(r.agent, "127.0.0.1", 0); threading.Thread(target=srv.serve_forever, daemon=True).start(); base = f"http://127.0.0.1:{srv.server_address[1]}"
        with urllib.request.urlopen(base + "/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=vt1&hub.challenge=abc123") as x: self.assertEqual(x.read(), b"abc123")
        with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(base + "/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=bad&hub.challenge=abc123")
        hook = json.dumps({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "PID1"}, "messages": [{"from": "16465550101", "type": "text", "text": {"body": "what are your hours"}}]}}]}]}).encode()
        def post(sig):
            q = urllib.request.Request(base + "/whatsapp/webhook", data=hook, headers={"X-Hub-Signature-256": sig}, method="POST")
            try:
                with urllib.request.urlopen(q, timeout=10) as x: return x.status
            except urllib.error.HTTPError as e: return e.code
        self.assertEqual(post("sha256=" + "0" * 64), 401)
        self.assertEqual(post("sha256=" + hmac.new(b"appsec", hook, hashlib.sha256).hexdigest()), 200)
        c = r.mock.calls("/PID1/messages")[0]; self.assertEqual(c["json"]["to"], "16465550101"); self.assertIn("opening hours", c["json"]["text"]["body"]); self.assertEqual(c["auth"], "Bearer WA1")
        srv.shutdown(); r.close()

    def test_practice_mode_sends_nothing_on_any_channel(self):
        r = self.mk(); r.agent.dry = True
        for to in ("+16465550101", "tg:4242"):
            self.assertEqual(r.agent.run_actions("t", [{"action": "sms", "to": to, "text": "hi"}], r.agent.ctx(customer={**CUST, "phone": to}))[0]["status"], "dry_run")
        r.agent.run_actions("t", [{"action": "sms", "to": "+16465550101", "text": "hi", "via": "whatsapp"}], r.agent.ctx(customer=CUST))
        self.assertEqual((r.mock.calls("/3rdparty/v1/message"), r.mock.calls("/sendMessage"), r.mock.calls("/PID1/messages")), ([], [], [])); r.close()

    def test_connect_cards_test_and_register_webhooks(self):
        r = self.mk()
        for card in ("android_sms", "telegram", "whatsapp"):
            self.assertTrue(SU.connected(r.agent, card), card); t = SU.test(r.agent, card); self.assertTrue(t["ok"], t)
        self.assertTrue(SU.connected(r.agent, "texts")); self.assertIn("@bella_bot", SU.test(r.agent, "telegram")["message"])
        self.assertEqual(SU.channel_connect(r.agent, "android_sms")["address"], "https://agent.test/android/sms"); self.assertEqual(r.mock.calls("/3rdparty/v1/webhooks")[0]["json"]["url"], "https://agent.test/android/sms")
        k = SU.channel_connect(r.agent, "whatsapp"); self.assertEqual(k["address"], "https://agent.test/whatsapp/webhook"); self.assertTrue(k["verify_token"])
        self.assertIn("subscribed", k)
        r.close()

    def test_workflow_that_only_texts_is_ready_with_any_channel_but_calls_still_need_twilio(self):
        r = self.mk(); wfs = {w["name"]: w for w in SU.workflows(r.agent)}; kinds = {w["name"]: SU._kinds(w) for w in SU._workflow_file(r.agent)["workflows"]}
        textonly = [n for n, k in kinds.items() if "sms" in k and "call" not in k]; withcall = [n for n, k in kinds.items() if "call" in k]
        self.assertTrue(textonly and withcall)
        self.assertTrue(all("twilio" not in wfs[n]["missing"] for n in textonly)); self.assertTrue(all("twilio" in wfs[n]["missing"] for n in withcall)); r.close()

    def test_telegram_without_a_public_address_polls_for_messages_and_answers(self):
        import os
        os.environ["SV_TEST"] = "1"
        try:
            r = self.mk(); r.agent.cfg["public_base_url"] = ""; r.agent._serving = True
            r.mock.tg_updates = [{"update_id": 9, "message": {"chat": {"id": 55, "type": "private"}, "from": {"first_name": "Bo"}, "text": "what are your hours"}}]
            t = SU.channel_connect(r.agent, "telegram"); self.assertIn("no web address is needed", t["message"])
            end = time.time() + 8
            while time.time() < end and not r.mock.calls("/sendMessage"):
                time.sleep(0.1)
            c = r.mock.calls("/sendMessage"); self.assertEqual(len(c), 1); self.assertEqual(c[0]["json"]["chat_id"], "55"); self.assertTrue(r.mock.calls("/deleteWebhook"))
            time.sleep(0.6); self.assertEqual(len(r.mock.calls("/sendMessage")), 1)               # the same update is never answered twice
            r.agent.telegram_stop(); r.close()
        finally:
            os.environ.pop("SV_TEST", None)

    def test_capabilities_say_exactly_what_is_ready(self):
        r = self.mk(); caps = {c["id"]: c for c in SU.capabilities(r.agent)}
        self.assertTrue(caps["texts_out"]["ready"]); self.assertIn("Your Android phone", caps["texts_out"]["via"]); self.assertTrue(caps["texts_in"]["ready"]); self.assertFalse(caps["calls_in"]["ready"]); self.assertIn("Twilio", caps["calls_in"]["fix"])
        r.agent.cfg["public_base_url"] = ""; caps = {c["id"]: c for c in SU.capabilities(r.agent)}; self.assertEqual(caps["texts_in"]["via"], "Telegram")           # only Telegram can receive without a public address
        r.agent.android.signing_key = ""; r.agent.cfg["public_base_url"] = "https://agent.test"; self.assertNotIn("Your Android phone", {c["id"]: c for c in SU.capabilities(r.agent)}["texts_in"]["via"]); r.close()

    def test_every_channel_has_a_full_guide_and_a_short_version(self):
        r = self.mk(); cards = {c["name"]: c for c in SU.status(r.agent)["cards"]}
        for name, slug in SU.GUIDES.items():
            g = SU.guide(name); self.assertEqual(g["name"], slug); self.assertGreater(len(g["markdown"]), 700); self.assertTrue(cards[name]["guide"]); self.assertLessEqual(len(cards[name]["steps"]), 3)
        with self.assertRaises(SU.SetupError): SU.guide("../../etc/passwd")
        r.close()

    def test_dashboard_never_uses_the_browsers_own_confirm_box(self):
        from speakvora_pack_agent import ui
        self.assertNotRegex(ui.JS, r"(?<![\w.])confirm\(")                  # embedded browsers block it, so Go live and every Remove button would silently do nothing
        self.assertIn("function ask(", ui.JS); self.assertIn("btn=btn||LASTBTN", ui.JS)           # a button handler that waits for the Yes box has lost its event target by then

    def test_the_agent_never_answers_itself_or_one_sender_without_end(self):
        r = self.mk(); self.assertEqual(r.agent.handle_chat("android", "+16465550101", "what are your hours", None, "+16465550101"), ""); self.assertEqual(r.mock.calls("/3rdparty/v1/message"), [])
        for i in range(20):
            r.agent.handle_chat("android", "+16465550102", "what are your hours")
        self.assertEqual(len(r.mock.calls("/3rdparty/v1/message")), 15); r.close()

    def test_guides_open_as_standalone_pages_without_a_sign_in_and_hold_no_secrets(self):
        r = self.mk(); srv = serve(r.agent, "127.0.0.1", 0); threading.Thread(target=srv.serve_forever, daemon=True).start(); base = f"http://127.0.0.1:{srv.server_address[1]}"
        for slug in SU.GUIDES.values():
            with urllib.request.urlopen(f"{base}/guide/{slug}") as x:
                page = x.read().decode(); self.assertEqual(x.status, 200); self.assertIn("text/html", x.headers["content-type"]); self.assertIn("<h1>", page)
        with urllib.request.urlopen(f"{base}/guide/android-sms") as x: page = x.read().decode()
        self.assertGreaterEqual(page.count("<img"), 4)
        with urllib.request.urlopen(f"{base}/guide/telegram?download=1") as x: self.assertIn("attachment", x.headers["content-disposition"])
        with self.assertRaises(urllib.error.HTTPError) as e: urllib.request.urlopen(f"{base}/guide/..%2Fagent")
        self.assertEqual(e.exception.code, 404); srv.shutdown(); r.close()

    def test_dashboard_buttons_open_the_guide_page_and_the_dashboard_shows_no_pictures(self):
        from speakvora_pack_agent import ui
        self.assertIn("Full Guide", ui.JS); self.assertEqual(ui.JS.count("Full Guide"), 1)       # one button, added to every connection that has a guide; business has none; self.assertNotIn("Download instructions", ui.JS); self.assertNotIn("guideSheet", ui.JS); self.assertNotIn("<img", ui.JS.replace("createElement('img')", ""))

    def test_whatsapp_account_subscription_is_made_for_you(self):
        r = self.mk(); self.assertTrue(r.agent.whatsapp.subscribe_account()); self.assertEqual(len(r.mock.calls("/WABA1/subscribed_apps")), 1)      # Meta sends nothing until the app is subscribed to the account
        r.agent.whatsapp.cfg["waba_id"] = ""; self.assertFalse(r.agent.whatsapp.subscribe_account()); r.close()

    def test_a_picture_or_voice_note_gets_one_polite_reply_not_silence(self):
        r = self.mk(); hook = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "PID1"}, "messages": [{"from": "16465550101", "type": "audio"}]}}]}]}
        m = r.agent.whatsapp.parse(hook); self.assertEqual(m, [{"from": "+16465550101", "body": "", "unsupported": "audio"}])
        self.assertIn("only read typed messages", r.agent.handle_unsupported("whatsapp", "+16465550101")); self.assertEqual(r.agent.handle_unsupported("whatsapp", "+16465550101"), "")        # not twice in an hour
        self.assertEqual(len(r.mock.calls("/PID1/messages")), 1); r.close()

    def test_chat_channels_never_stay_silent_and_never_message_after_stop(self):
        r = self.mk(); out = r.agent.handle_chat("telegram", "tg:77", "something nobody planned for")
        self.assertIn("team", out.lower()); self.assertEqual(len(r.mock.calls("/sendMessage")), 1)                     # a polite hand-off instead of silence
        r.agent.handle_chat("telegram", "tg:77", "STOP"); n = len(r.mock.calls("/sendMessage"))
        self.assertEqual(r.agent.handle_chat("telegram", "tg:77", "what are your hours"), ""); self.assertEqual(len(r.mock.calls("/sendMessage")), n)   # blocked after STOP
        self.assertTrue(r.agent.handle_chat("telegram", "tg:77", "START")); r.close()

    def test_an_expired_whatsapp_token_is_flagged_not_silent(self):
        r = self.mk(); r.mock.fail = {"/PID1/messages": 401}
        r.agent.handle_chat("whatsapp", "+16465550101", "what are your hours")
        self.assertTrue(r.agent.state.data.get("wa_token_bad")); self.assertEqual(SU.capabilities(r.agent)[0]["id"], "wa_token")
        self.assertTrue(r.agent.whatsapp.token_expired(__import__("speakvora_pack_agent.web", fromlist=["x"]).HttpError(401, '{"error":{"code":190}}')))
        r.mock.fail = {}; r.agent.handle_chat("whatsapp", "+16465550101", "what are your hours"); self.assertFalse(r.agent.state.data.get("wa_token_bad")); r.close()

    def test_a_failed_send_does_not_use_up_the_voice_note_reply(self):
        r = self.mk(); r.mock.fail = {"/PID1/messages": 401}; self.assertEqual(r.agent.handle_unsupported("whatsapp", "+16465550101"), "")
        r.mock.fail = {}; self.assertIn("only read typed messages", r.agent.handle_unsupported("whatsapp", "+16465550101")); r.close()

    def test_support_report_has_the_setup_story_and_no_secrets(self):
        from speakvora_pack_agent import setuplog
        r = self.mk(); SU.save(r.agent, "telegram", {"bot_token": "123456789:SECRETSECRETSECRETSECRETSECRET1"}); SU.test(r.agent, "telegram")
        r.agent.handle_chat("telegram", "tg:4242", "my card is 4111111111111111 call +16465550101"); rep = setuplog.report(r.agent)
        self.assertIn("save", rep); self.assertIn("bot_token", rep); self.assertIn("telegram: connected=True", rep); self.assertIn("first_message", rep)
        for secret in ("SECRETSECRET", "4111111111111111", "+16465550101", "WA1", "agentpass"): self.assertNotIn(secret, rep)
        self.assertEqual(setuplog.clean({"password": "x", "n": "call 646-555-0101"}), {"password": "***", "n": "call ******0101"}); r.close()


if __name__ == "__main__":
    unittest.main()
