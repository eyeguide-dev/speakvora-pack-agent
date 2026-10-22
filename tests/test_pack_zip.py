"""A real unzipped pack folder with the kit inside works from the command line: init -> check -> run (dry) -> signed event -> slots request file. Uses the same code that build_packs.py uses to add the kit to every pack."""
import io, json, os, subprocess, sys, tempfile, threading, time, unittest, urllib.request, zipfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "scripts"))
try:
    import pack_kit
except ImportError:                                               # the standalone open-source repo has no pack builder
    raise unittest.SkipTest('pack_kit (the Speakvora pack builder) is not part of this repository')


def make_zip(pid="en-restaurants-food-af_heart"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps({"pack": pid, "title": "Restaurants and food", "language": "en", "voice": "af_heart", "items": [{"id": 1, "text": "Thank you for choosing us.", "file": "audio/00001.m4a", "category": "closing"}]}))
        z.writestr("audio/00001.m4a", b"X")
        for fp, fb in pack_kit.extra_files(pid, "en", "af_heart", "restaurants-food").items():
            z.writestr(fp, fb)
    return buf.getvalue()


class PackZip(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); zipfile.ZipFile(io.BytesIO(make_zip())).extractall(self.d)
        self.env = dict(os.environ, SV_EVENT_SECRET="zip-secret", TWILIO_ACCOUNT_SID="AC1", TWILIO_AUTH_TOKEN="t", TWILIO_FROM="+15550001111", SLACK_BOT_TOKEN="x", SLACK_SIGNING_SECRET="y", CALENDAR_ICS_URL="http://127.0.0.1:9/none.ics")

    def sv(self, *a, **kw):
        return subprocess.run(["sh", "sv-agent", *a], cwd=self.d, env=self.env, capture_output=True, text=True, timeout=60, **kw)

    def test_bundle_contents_and_first_run(self):
        names = set(os.listdir(self.d)); self.assertTrue({"agent", "sv-agent", "AGENT-README.md", "workflows.json", "agent.json", "manifest.json"} <= names)
        r = self.sv("init", "--pack", ".", "--force"); self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("food", r.stdout)
        cfg = json.load(open(os.path.join(self.d, "agent.json"))); self.assertTrue(cfg["dry_run"]); self.assertEqual(cfg["pack"], ".")
        for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "SLACK_BOT_TOKEN"): self.env.pop(k, None)
        r = self.sv("check"); self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("environment variables not set yet", r.stdout)             # inspecting a pack needs no keys
        self.env.update(TWILIO_ACCOUNT_SID="AC1", TWILIO_AUTH_TOKEN="t", SLACK_BOT_TOKEN="x")
        r = self.sv("check"); self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("workflows:", r.stdout); self.assertIn("missing slots", r.stdout); self.assertIn("dry_run: True", r.stdout)
        r = self.sv("slots", "--write"); self.assertEqual(r.returncode, 0, r.stderr); req = json.load(open(os.path.join(self.d, "slot-requests.json")))
        self.assertEqual((req["kind"], req["industry_profile"], req["language"]), ("workflow_line_request", "food", "en")); self.assertIn("order_ready", [s["slot"] for s in req["slots"]])
        self.assertEqual(self.sv("phrases", "thank", "--pack", ".").returncode, 0)

    def test_runs_dry_and_records_but_sends_nothing(self):
        cfg = json.load(open(os.path.join(self.d, "agent.json"))); cfg.update(listen={"host": "127.0.0.1", "port": 18999}, public_base_url="http://127.0.0.1:18999", facts={"hours": "9-5", "address": "x", "review_url": "https://r.test"}, business="Bella", quiet_hours={"start": "00:00", "end": "00:00", "applies_to": []})            # quiet hours would block the text at night; this test checks dry-run behaviour at any hour
        json.dump(cfg, open(os.path.join(self.d, "agent.json"), "w"))
        p = subprocess.Popen(["sh", "sv-agent", "run"], cwd=self.d, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(50):
                try:
                    h = json.load(urllib.request.urlopen("http://127.0.0.1:18999/health", timeout=2)); break
                except Exception:  # noqa: BLE001
                    time.sleep(0.2)
            self.assertTrue(h["dry_run"]); self.assertGreater(h["workflows"], 5)
            json.dump({"event": "order.ready", "id": "z1", "customer": {"name": "A", "phone": "6465550101", "sms_consent": True}, "order": {"number": 5}}, open(os.path.join(self.d, "ev.json"), "w"))
            r = self.sv("event", "ev.json"); self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(json.loads(r.stdout)["matched"], 1)
            log = [json.loads(x) for x in open(os.path.join(self.d, "agent-state", "agent.log.jsonl"))]; self.assertTrue(log and all(x["status"] in ("dry_run", "skipped", "warning") for x in log if x.get("action")))
        finally:
            p.terminate(); p.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
