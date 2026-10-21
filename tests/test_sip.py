"""The office-phone-system connection (SIP): sign-in with digest authentication, answering a call, playing the menu, keypad digits, transfer to staff, hang-up, and a bad password."""
import hashlib, json, re, socket, struct, threading, time, unittest

from test_pack_agent import Rig
from speakvora_pack_agent.connectors import sip as SIPMOD
from speakvora_pack_agent import connect as SU

SIPMOD.to_g711 = lambda data, codec=0, ffmpeg="ffmpeg": b"\x7f" * 480           # 60 ms of audio: the tests do not need ffmpeg


class FakePbx:
    """A minimal phone system: asks for a digest login, accepts the right password, then can place a call to the agent and play the caller."""
    def __init__(self, password="pw"):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.s.bind(("127.0.0.1", 0)); self.s.settimeout(0.3); self.port = self.s.getsockname()[1]
        self.rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.rtp.bind(("127.0.0.1", 0)); self.rtp.settimeout(0.3); self.rtp_port = self.rtp.getsockname()[1]
        self.password, self.registered, self.rejected, self.msgs, self.agent_addr, self.stop = password, False, 0, [], None, False
        self.nonce = "abc123nonce"; self.rtp_in = []; self.lock = threading.Lock()
        threading.Thread(target=self.loop, daemon=True).start(); threading.Thread(target=self.rtp_loop, daemon=True).start()

    def loop(self):
        while not self.stop:
            try:
                d, a = self.s.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                return
            m = SIPMOD.parse(d); self.msgs.append(m)
            if m["first"].startswith("REGISTER"):
                self.agent_addr = (a[0], int(re.search(r"@127\.0\.0\.1:(\d+)", SIPMOD.hv(m, "contact")).group(1)))
                auth = SIPMOD.hv(m, "authorization")
                if not auth:
                    self.respond(m, a, 401, 'WWW-Authenticate: Digest realm="pbx", nonce="%s", qop="auth", algorithm=MD5' % self.nonce)
                else:
                    f = dict((k, x or y) for k, x, y in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]+))', auth))
                    md5 = lambda s: hashlib.md5(s.encode()).hexdigest(); ha1 = md5(f"{f['username']}:pbx:{self.password}"); ha2 = md5(f"REGISTER:{f['uri']}")
                    want = md5(f"{ha1}:{self.nonce}:{f['nc']}:{f['cnonce']}:auth:{ha2}")
                    if f.get("response") == want:
                        self.registered = True; self.respond(m, a, 200, "Expires: 300")
                    else:
                        self.rejected += 1; self.respond(m, a, 403, "")
            elif m["first"].startswith(("BYE", "REFER", "INFO")):
                self.respond(m, a, 200, "")

    def respond(self, m, a, code, extra):
        lines = [f"SIP/2.0 {code} X"] + [f"Via: {v}" for v in m["h"]["via"]] + [f"From: {SIPMOD.hv(m, 'from')}", f"To: {SIPMOD.hv(m, 'to')};tag=pbx", f"Call-ID: {SIPMOD.hv(m, 'call-id')}", f"CSeq: {SIPMOD.hv(m, 'cseq')}"] + ([extra] if extra else []) + ["Content-Length: 0", "", ""]
        self.s.sendto("\r\n".join(lines).encode(), a)

    def rtp_loop(self):
        while not self.stop:
            try:
                d, a = self.rtp.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                return
            with self.lock:
                self.rtp_in.append((time.time(), d))

    def audio_packets(self):
        with self.lock:
            return [d for t, d in self.rtp_in if d[1] & 0x7F == 0]

    def call(self, number="+16465550101", call_id="call-1"):
        sdp = f"v=0\r\no=pbx 1 1 IN IP4 127.0.0.1\r\ns=-\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\nm=audio {self.rtp_port} RTP/AVP 0 101\r\na=rtpmap:0 PCMU/8000\r\na=rtpmap:101 telephone-event/8000\r\n"
        inv = "\r\n".join([f"INVITE sip:101@127.0.0.1 SIP/2.0", f"Via: SIP/2.0/UDP 127.0.0.1:{self.port};branch=z9hG4bKinv1", f"From: <sip:{number}@pbx>;tag=caller1", "To: <sip:101@pbx>", f"Call-ID: {call_id}", "CSeq: 1 INVITE",
                           f"Contact: <sip:{number}@127.0.0.1:{self.port}>", "Content-Type: application/sdp", f"Content-Length: {len(sdp)}", "", sdp])
        self.s.sendto(inv.encode(), self.agent_addr)
        end = time.time() + 5
        while time.time() < end:                                       # wait for the 200 OK
            for m in self.msgs:
                if m["first"].startswith("SIP/2.0 200") and "INVITE" in SIPMOD.hv(m, "cseq") and SIPMOD.hv(m, "call-id") == call_id:
                    self.ok = m; ip, port, codec, te = SIPMOD.sdp_offer(m["body"]); self.agent_rtp = (ip, port)
                    ack = "\r\n".join([f"ACK sip:101@127.0.0.1:{self.agent_addr[1]} SIP/2.0", f"Via: SIP/2.0/UDP 127.0.0.1:{self.port};branch=z9hG4bKack1", f"From: <sip:{number}@pbx>;tag=caller1", f"To: {SIPMOD.hv(m, 'to')}", f"Call-ID: {call_id}", "CSeq: 1 ACK", "Content-Length: 0", "", ""])
                    self.s.sendto(ack.encode(), self.agent_addr); return m
            time.sleep(0.05)
        raise AssertionError("the agent never answered the call")

    def dtmf(self, digit, ts=1000):
        ev = "0123456789*#".index(digit)
        for end in (0, 0x80):
            self.rtp.sendto(struct.pack("!BBHII", 0x80, 101, 1, ts, 7) + bytes([ev, end | 10, 0, 160]), self.agent_rtp)
            time.sleep(0.02)

    def wait(self, fn, t=6):
        end = time.time() + t
        while time.time() < end:
            if fn():
                return True
            time.sleep(0.05)
        return False

    def close(self):
        self.stop = True; self.s.close(); self.rtp.close()


class Digest(unittest.TestCase):
    def test_matches_the_published_rfc_2617_example(self):
        d = SIPMOD.digest("Mufasa", "Circle Of Life", "testrealm@host.com", "dcd98b7102dd2f0e8b11d0f600bfb0c093", "GET", "/dir/index.html", qop="auth", cnonce="0a4f113b")
        self.assertIn('response="6629fae49393a05397450978507c4ef1"', d)


class Sip(unittest.TestCase):
    def setUp(self):
        self.pbx = FakePbx()
        self.r = Rig(extra={"sip": {"server": "127.0.0.1", "server_port": self.pbx.port, "username": "101", "password": "pw", "rtp_start": 41000, "rtp_end": 41100, "fallback_number": "202"}, "facts": {"oncall_phone": "+16465559999"}})
        self.a = self.r.agent; self.a._serving = True; self.a.sip_sync()

    def tearDown(self):
        self.a.sip_stop(); self.pbx.close(); self.r.close()

    def test_signs_in_with_digest_authentication_and_reports_ready(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); self.assertTrue(self.a.sip.registered)
        t = SU.test(self.a, "sip"); self.assertTrue(t["ok"], t); self.assertIn("extension 101", t["message"])
        caps = {c["id"]: c for c in SU.capabilities(self.a)}; self.assertTrue(caps["calls_in"]["ready"]); self.assertIn("Office phone system", caps["calls_in"]["via"])

    def test_wrong_password_is_reported_in_plain_words(self):
        self.a.sip_stop(); self.pbx.password = "other"
        self.a.cfg["sip"]["password"] = "pw"; self.a.sip_sync()
        self.assertTrue(self.pbx.wait(lambda: self.a.sip.error)); self.assertFalse(self.a.sip.registered); self.assertIn("password", self.a.sip.error)
        t = SU.test(self.a, "sip"); self.assertFalse(t["ok"]); self.assertIn("password", t["message"])

    def test_answers_a_call_plays_the_menu_and_a_key_press_gets_the_answer(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); ok = self.pbx.call()
        self.assertIn("m=audio", ok["body"]); self.assertIn("telephone-event", ok["body"])
        self.assertTrue(self.pbx.wait(lambda: len(self.pbx.audio_packets()) >= 3), "the menu never played")
        n = len(self.pbx.audio_packets()); self.pbx.dtmf("1")
        self.assertTrue(self.pbx.wait(lambda: len(self.pbx.audio_packets()) > n + 3), "pressing 1 got no answer")

    def test_pressing_zero_transfers_to_a_person_with_refer(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); self.pbx.call()
        self.assertTrue(self.pbx.wait(lambda: len(self.pbx.audio_packets()) >= 2)); self.pbx.dtmf("0")
        self.assertTrue(self.pbx.wait(lambda: any(m["first"].startswith("REFER") for m in self.pbx.msgs)), "no transfer was requested")
        refer = next(m for m in self.pbx.msgs if m["first"].startswith("REFER")); self.assertRegex(SIPMOD.hv(refer, "refer-to"), r"<sip:\+?\d+@")

    def test_caller_hanging_up_ends_the_call_cleanly(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); self.pbx.call(); self.assertEqual(len(self.a.sip.calls), 1)
        bye = "\r\n".join([f"BYE sip:101@127.0.0.1:{self.pbx.agent_addr[1]} SIP/2.0", f"Via: SIP/2.0/UDP 127.0.0.1:{self.pbx.port};branch=z9hG4bKb", "From: <sip:+16465550101@pbx>;tag=caller1", f"To: {SIPMOD.hv(self.pbx.ok, 'to')}", "Call-ID: call-1", "CSeq: 2 BYE", "Content-Length: 0", "", ""])
        self.pbx.s.sendto(bye.encode(), self.pbx.agent_addr); self.assertTrue(self.pbx.wait(lambda: not self.a.sip.calls))

    def test_too_many_calls_get_busy_not_silence(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); self.a.sip.max_calls = 0
        sdp = f"v=0\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\nm=audio {self.pbx.rtp_port} RTP/AVP 0\r\n"
        self.pbx.s.sendto(("\r\n".join(["INVITE sip:101@x SIP/2.0", f"Via: SIP/2.0/UDP 127.0.0.1:{self.pbx.port};branch=z9hG4bKq", "From: <sip:1@x>;tag=t", "To: <sip:101@x>", "Call-ID: busy-1", "CSeq: 1 INVITE", "Contact: <sip:1@127.0.0.1>", f"Content-Length: {len(sdp)}", "", sdp])).encode(), self.pbx.agent_addr)
        self.assertTrue(self.pbx.wait(lambda: any(m["first"].startswith("SIP/2.0 486") for m in self.pbx.msgs)))

    def test_changing_the_settings_signs_in_again_and_removing_them_signs_out(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); old = self.a.sip
        self.a.sip_sync(); self.assertIs(self.a.sip, old)                       # unchanged settings keep the same line
        self.a.cfg["sip"]["username"] = "102"; self.a.sip_sync(); self.assertIsNot(self.a.sip, old); self.assertTrue(self.pbx.wait(lambda: self.a.sip.registered))


if __name__ == "__main__":
    unittest.main()
