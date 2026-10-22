import base64, hashlib, json, os, stat, sys, tempfile, textwrap, threading, time, unittest, urllib.error, urllib.request
from test_pack_agent import Rig, Web
from speakvora_pack_agent import address as AD, secrets_store as SS, web

TOK = base64.b64encode(json.dumps({"a": "acct123", "t": "11111111-2222-3333-4444-555555555555", "s": "c2VjcmV0c2VjcmV0c2VjcmV0"}).encode()).decode().rstrip("=")


def script(body):
    f = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False); f.write("#!" + sys.executable + "\n" + textwrap.dedent(body)); f.close(); os.chmod(f.name, 0o755); return f.name


class Pieces(unittest.TestCase):
    def test_a_good_token_is_accepted_and_bad_ones_get_plain_reasons(self):
        self.assertEqual(AD.parse_token(TOK), TOK); self.assertEqual(AD.parse_token("  " + TOK[:30] + "\n" + TOK[30:] + " "), TOK)
        self.assertEqual(AD.parse_token(f"sudo cloudflared service install {TOK}"), TOK); self.assertEqual(AD.parse_token(f"cloudflared tunnel run --token {TOK}"), TOK)
        for bad in ("", "hello", "https://example.com", base64.b64encode(b'{"x":1}').decode()):
            with self.assertRaises(AD.AddressError): AD.parse_token(bad)

    def test_addresses_are_cleaned_and_checked(self):
        self.assertEqual(AD.clean_host("https://Hooks.YourBusiness.com/"), "hooks.yourbusiness.com"); self.assertEqual(AD.clean_host(""), "")
        for bad in ("localhost", "hooks", "a b.com", "http://127.0.0.1:8787", "x..com"):
            with self.assertRaises(AD.AddressError): AD.clean_host(bad)

    def test_the_helper_is_downloaded_only_when_it_matches_cloudflares_checksum(self):
        r = Rig(); self.addCleanup(r.close); data = b"#!/bin/sh\necho hi\n"; name = AD._asset_name()
        rel = lambda digest: (lambda *a, **k: (200, {"assets": [{"name": name, "digest": digest, "browser_download_url": "https://example.test/c"}]}))  # noqa: E731
        if name.endswith(".tgz"):
            import io, tarfile
            buf = io.BytesIO(); t = tarfile.open(fileobj=buf, mode="w:gz"); ti = tarfile.TarInfo("cloudflared"); ti.size = len(data); t.addfile(ti, io.BytesIO(data)); t.close(); data = buf.getvalue()
        good = "sha256:" + hashlib.sha256(data).hexdigest()
        p = AD.install_cloudflared(r.agent, request=rel(good), download=lambda u: data); self.assertTrue(os.path.exists(p)); self.assertTrue(os.access(p, os.X_OK))
        with self.assertRaises(AD.AddressError) as cm: AD.install_cloudflared(r.agent, request=rel("sha256:" + "0" * 64), download=lambda u: data)
        self.assertIn("checksum", str(cm.exception))
        with self.assertRaises(AD.AddressError): AD.install_cloudflared(r.agent, request=rel(""), download=lambda u: data)             # no checksum to compare: nothing is installed
        with self.assertRaises(AD.AddressError): AD.install_cloudflared(r.agent, request=lambda *a, **k: (500, {}), download=lambda u: data)


class TunnelRuns(unittest.TestCase):
    def test_it_starts_the_helper_with_the_token_only_in_its_environment_and_reports_connected(self):
        out = tempfile.mktemp(); b = script(f'''
            import os, sys, time, json
            json.dump({{"argv": sys.argv, "token": os.environ.get("TUNNEL_TOKEN")}}, open({out!r}, "w"))
            print("INF Starting tunnel", flush=True); print("INF Registered tunnel connection connIndex=0", flush=True); time.sleep(30)''')
        t = AD.Tunnel(backoff_max=0.1); self.addCleanup(t.stop); t.start(b, TOK)
        end = time.time() + 10
        while not t.connected and time.time() < end: time.sleep(0.05)
        self.assertTrue(t.connected); self.assertEqual(t.status()["state"], "connected")
        d = json.load(open(out)); self.assertEqual(d["token"], TOK); self.assertNotIn(TOK, " ".join(d["argv"]))                       # never on the command line, where other programs can read it
        self.assertEqual(d["argv"][1:], ["tunnel", "--no-autoupdate", "run"]); self.assertNotIn(TOK, " ".join(t.lines))

    def test_it_restarts_the_helper_when_it_stops_and_stops_it_for_good_on_request(self):
        c = tempfile.mktemp(); b = script(f'''
            import os, time
            n = int(open({c!r}).read()) if os.path.exists({c!r}) else 0; open({c!r}, "w").write(str(n + 1))
            if n == 0: raise SystemExit(3)
            print("INF Registered tunnel connection", flush=True); time.sleep(30)''')
        t = AD.Tunnel(backoff_max=0.1); self.addCleanup(t.stop); t.start(b, TOK); end = time.time() + 10
        while not t.connected and time.time() < end: time.sleep(0.05)
        self.assertTrue(t.connected); self.assertEqual(open(c).read(), "2")
        t.stop(); self.assertFalse(t.connected); self.assertEqual(t.state, "stopped"); time.sleep(0.4); self.assertEqual(open(c).read(), "2")

    def test_a_refused_token_is_explained(self):
        b = script('''
            print("ERR Provided Tunnel token is not valid.", flush=True)
            raise SystemExit(1)''')
        t = AD.Tunnel(backoff_max=0.1); self.addCleanup(t.stop); t.start(b, TOK); end = time.time() + 5
        while "token" not in t.error.lower() and time.time() < end: time.sleep(0.05)
        self.assertIn("did not accept this token", t.error)


def placeholder(agent):
    from speakvora_pack_agent import connect as C
    raw = C._raw(agent); raw["public_base_url"] = "https://YOUR-PUBLIC-ADDRESS-FOR-THIS-AGENT"; C._write_raw(agent, raw); C._reload(agent)


class Settings(unittest.TestCase):
    def setUp(self):
        self.r = Rig(); self.a = self.r.agent; self.a._serving = False; placeholder(self.a)

    def tearDown(self):
        self.r.close()

    def test_saving_keeps_the_token_in_the_secrets_file_not_in_agent_json(self):
        v = AD.save(self.a, {"provider": "cloudflare", "hostname": "Hooks.Acme.com", "token": TOK})
        self.assertEqual((v["provider"], v["hostname"], v["token_set"]), ("cloudflare", "hooks.acme.com", True))
        self.assertEqual(SS.read(self.a.state.dir)["TUNNEL_TOKEN"], TOK); self.assertNotIn(TOK, open(self.a.cfg["_path"]).read()); self.assertIn("env:TUNNEL_TOKEN", open(self.a.cfg["_path"]).read())
        with self.assertRaises(AD.AddressError): AD.save(self.a, {"token": "nonsense"})
        with self.assertRaises(AD.AddressError): AD.save(self.a, {"hostname": "hooks.acme.com", "dashboard_hostname": "hooks.acme.com", "remote_dashboard": True})            # one address must not serve both
        with self.assertRaises(AD.AddressError): AD.save(self.a, {"remote_dashboard": True, "dashboard_hostname": ""})

    def test_use_everywhere_replaces_a_placeholder_but_never_silently_a_different_address_you_typed(self):
        AD.save(self.a, {"provider": "cloudflare", "hostname": "hooks.acme.com", "token": TOK})
        self.assertFalse(AD.view(self.a)["in_use"]); r = AD.use_everywhere(self.a); self.assertTrue(r["ok"]); self.assertEqual(self.a.cfg["public_base_url"], "https://hooks.acme.com"); self.assertTrue(AD.view(self.a)["in_use"])
        AD.save(self.a, {"hostname": "other.acme.com"}); self.assertEqual(AD.use_everywhere(self.a)["ok"], True)                         # it replaces the address it set itself
        from speakvora_pack_agent import connect as C
        raw = C._raw(self.a); raw["public_base_url"] = "https://my-own.example.com"; C._write_raw(self.a, raw); C._reload(self.a)
        r = AD.use_everywhere(self.a); self.assertTrue(r["needs_confirm"]); self.assertEqual(self.a.cfg["public_base_url"], "https://my-own.example.com")
        self.assertTrue(AD.use_everywhere(self.a, force=True)["ok"])

    def test_the_checklist_says_exactly_what_is_missing(self):
        c = AD.check(self.a); self.assertFalse(c["ready"]); self.assertEqual(c["items"][0]["id"], "choose")
        AD.save(self.a, {"provider": "cloudflare", "hostname": "hooks.acme.com", "token": TOK}); os.environ.pop("CLOUDFLARED_BIN", None)
        ok = lambda *a, **k: (200, {"home": AD.home_id(self.a)})  # noqa: E731
        items = {i["id"]: i for i in AD.check(self.a, ok)["items"]}; self.assertTrue(items["token"]["ok"]); self.assertFalse(items["tunnel"]["ok"]); self.assertTrue(items["reach"]["ok"]); self.assertFalse(items["use"]["ok"])
        tunnel_down = lambda *a, **k: (_ for _ in ()).throw(web.HttpError(530, "error code: 1033"))  # noqa: E731
        why = {i["id"]: i for i in AD.check(self.a, tunnel_down)["items"]}["reach"]["detail"]; self.assertIn("tunnel is not connected", why)
        gone = lambda *a, **k: (_ for _ in ()).throw(web.NetworkDown("dns"))  # noqa: E731
        self.assertIn("not found on the internet", {i["id"]: i for i in AD.check(self.a, gone)["items"]}["reach"]["detail"])
        other = lambda *a, **k: (200, {"home": "someoneelse"})  # noqa: E731
        self.assertIn("DIFFERENT", {i["id"]: i for i in AD.check(self.a, other)["items"]}["reach"]["detail"])
        access = lambda *a, **k: (200, "<html>cloudflareaccess.com login</html>")  # noqa: E731
        self.assertIn("Cloudflare Access must not sit in front", {i["id"]: i for i in AD.check(self.a, access)["items"]}["reach"]["detail"])

    def test_tailscale_finds_the_fixed_name_and_funnel_problems_are_explained(self):
        b = script('''
            import sys, json
            if sys.argv[1] == "status": print(json.dumps({"BackendState": "Running", "Self": {"DNSName": "agent-mac.tail1234.ts.net."}}))
            elif sys.argv[1] == "funnel":
                print("Funnel is not enabled on your tailnet. https://login.tailscale.com/f/funnel", file=sys.stderr); sys.exit(1)''')
        self.assertEqual(AD.tailscale_name(b), "agent-mac.tail1234.ts.net"); ok, msg = AD.tailscale_funnel(8787, b); self.assertFalse(ok); self.assertIn("switched off", msg)
        self.assertEqual(AD.tailscale_name("/nonexistent/tailscale"), "")


class SafetyThroughTheTunnel(unittest.TestCase):
    """The dashboard must never open on the public webhook address, whatever the token."""
    def setUp(self):
        Web.setUp(self); AD.save(self.r.agent, {"provider": "cloudflare", "hostname": "hooks.acme.com", "dashboard_hostname": "agent.acme.com", "remote_dashboard": True, "token": TOK})
        self.tok = __import__("speakvora_pack_agent.dashboard", fromlist=["x"]).token(self.r.agent)

    tearDown = Web.tearDown

    def get(self, path, headers):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=dict(headers, **{"x-dashboard-token": self.tok}))
        try:
            with urllib.request.urlopen(req, timeout=10) as x: return x.status
        except urllib.error.HTTPError as e: return e.code

    def test_the_dashboard_stays_on_this_computer_through_the_webhook_address(self):
        self.assertEqual(self.get("/dashboard", {}), 200)                                                                               # on this computer
        via = {"cf-connecting-ip": "203.0.113.9", "cf-ray": "abc"}
        self.assertEqual(self.get("/dashboard", dict(via, Host="hooks.acme.com")), 403); self.assertEqual(self.get("/dash/api/summary", dict(via, Host="hooks.acme.com")), 403)
        self.assertEqual(self.get("/dashboard", dict(via, Host="hooks.acme.com", **{"cf-access-authenticated-user-email": "me@acme.com"})), 403)     # even with an Access login: wrong address
        self.assertEqual(self.get("/health", dict(via, Host="hooks.acme.com")), 200)                                                  # the public check works

    def test_the_dashboard_address_needs_cloudflare_access_and_the_token(self):
        via = {"cf-connecting-ip": "203.0.113.9", "cf-ray": "abc", "Host": "agent.acme.com"}
        self.assertEqual(self.get("/dashboard", via), 403)                                                                               # no Access login: refused
        self.assertEqual(self.get("/dashboard", dict(via, **{"cf-access-authenticated-user-email": "me@acme.com"})), 200)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/dash/api/summary", headers=dict(via, **{"cf-access-authenticated-user-email": "me@acme.com", "x-dashboard-token": "wrong"}))
        with self.assertRaises(urllib.error.HTTPError) as cm: urllib.request.urlopen(req, timeout=10)
        self.assertEqual(cm.exception.code, 401)                                                                                        # Access alone is not enough: the access token is still needed
        AD.save(self.r.agent, {"remote_dashboard": False}); self.assertEqual(self.get("/dashboard", dict(via, **{"cf-access-authenticated-user-email": "me@acme.com"})), 403)

    def test_a_list_of_allowed_people_is_enforced(self):
        raw = __import__("speakvora_pack_agent.connect", fromlist=["x"]); r = raw._raw(self.r.agent); r["address"]["allowed_emails"] = ["boss@acme.com"]; raw._write_raw(self.r.agent, r); raw._reload(self.r.agent)
        via = {"cf-connecting-ip": "203.0.113.9", "Host": "agent.acme.com"}
        self.assertEqual(self.get("/dashboard", dict(via, **{"cf-access-authenticated-user-email": "intruder@evil.com"})), 403)
        self.assertEqual(self.get("/dashboard", dict(via, **{"cf-access-authenticated-user-email": "Boss@acme.com"})), 200)


class DashboardApi(unittest.TestCase):
    def setUp(self):
        Web.setUp(self); placeholder(self.r.agent); self.tok = __import__("speakvora_pack_agent.dashboard", fromlist=["x"]).token(self.r.agent)

    tearDown = Web.tearDown

    def api(self, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode() if body is not None else None, method="POST" if body is not None else "GET", headers={"x-dashboard-token": self.tok, "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as x: return x.status, json.loads(x.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")

    def test_save_check_use_and_remove_through_the_dashboard(self):
        st, v = self.api("/dash/api/address/save", {"provider": "cloudflare", "hostname": "hooks.acme.com", "token": TOK}); self.assertEqual((st, v["token_set"]), (200, True))
        st, e = self.api("/dash/api/address/save", {"token": "bad"}); self.assertEqual(st, 400); self.assertIn("Cloudflare tunnel token", e.get("message", "") + e.get("error", ""))
        st, u = self.api("/dash/api/address/use", {}); self.assertTrue(u["ok"]); self.assertEqual(self.api("/dash/api/address")[1]["in_use"], True)
        st, cards = self.api("/dash/api/setup"); self.assertIn("address", [c["name"] for c in cards["cards"]])
        st, r = self.api("/dash/api/address/remove", {}); self.assertEqual(r["provider"], ""); self.assertEqual(self.r.agent.cfg["public_base_url"], "https://YOUR-PUBLIC-ADDRESS-FOR-THIS-AGENT"); self.assertNotIn("TUNNEL_TOKEN", SS.read(self.r.agent.state.dir))


if __name__ == "__main__":
    unittest.main()
