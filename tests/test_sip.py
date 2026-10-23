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
            self.on_message(SIPMOD.parse(d), a)

    def on_message(self, m, a):
        self.msgs.append(m)
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

    def out(self, data, addr):
        self.s.sendto(data, addr)

    def respond(self, m, a, code, extra):
        lines = [f"SIP/2.0 {code} X"] + [f"Via: {v}" for v in m["h"]["via"]] + [f"From: {SIPMOD.hv(m, 'from')}", f"To: {SIPMOD.hv(m, 'to')};tag=pbx", f"Call-ID: {SIPMOD.hv(m, 'call-id')}", f"CSeq: {SIPMOD.hv(m, 'cseq')}"] + ([extra] if extra else []) + ["Content-Length: 0", "", ""]
        self.out("\r\n".join(lines).encode(), a)

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
        self.out(inv.encode(), self.agent_addr)
        end = time.time() + 5
        while time.time() < end:                                       # wait for the 200 OK
            for m in self.msgs:
                if m["first"].startswith("SIP/2.0 200") and "INVITE" in SIPMOD.hv(m, "cseq") and SIPMOD.hv(m, "call-id") == call_id:
                    self.ok = m; ip, port, codec, te = SIPMOD.sdp_offer(m["body"]); self.agent_rtp = (ip, port)
                    ack = "\r\n".join([f"ACK sip:101@127.0.0.1:{self.agent_addr[1]} SIP/2.0", f"Via: SIP/2.0/UDP 127.0.0.1:{self.port};branch=z9hG4bKack1", f"From: <sip:{number}@pbx>;tag=caller1", f"To: {SIPMOD.hv(m, 'to')}", f"Call-ID: {call_id}", "CSeq: 1 ACK", "Content-Length: 0", "", ""])
                    self.out(ack.encode(), self.agent_addr); return m
            time.sleep(0.05)
        raise AssertionError("the agent never answered the call")

    def dtmf(self, digit, ts=1000):
        ev = "0123456789*#".index(digit)
        for end in (0, 0x80):
            self.rtp.sendto(struct.pack("!BBHII", 0x80, 101, 1, ts, 7) + bytes([ev, end | 10, 0, 160]), self.agent_rtp)
            time.sleep(0.02)

    def call_srtp(self, number="+16465550101", call_id="srtp-1", offer_plain=False):
        """Offers encrypted audio (RTP/SAVP with an SDES key) the way hosted phone systems do. Returns (answer message, key context for what the agent sends, key context to protect what we send)."""
        mk, ms = SRTP.new_key()
        sdp = (f"v=0\r\no=pbx 1 1 IN IP4 127.0.0.1\r\ns=-\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\nm=audio {self.rtp_port} {'RTP/AVP' if offer_plain else 'RTP/SAVP'} 0 101\r\na=rtpmap:0 PCMU/8000\r\na=rtpmap:101 telephone-event/8000\r\n"
               + ("" if offer_plain else SRTP.crypto_line(1, "AES_CM_128_HMAC_SHA1_80", mk, ms) + "\r\n"))
        inv = "\r\n".join([f"INVITE sip:101@127.0.0.1 SIP/2.0", f"Via: SIP/2.0/UDP 127.0.0.1:{self.port};branch=z9hG4bKsr1", f"From: <sip:{number}@pbx>;tag=caller9", "To: <sip:101@pbx>", f"Call-ID: {call_id}", "CSeq: 1 INVITE", f"Contact: <sip:{number}@127.0.0.1:{self.port}>", "Content-Type: application/sdp", f"Content-Length: {len(sdp)}", "", sdp])
        self.out(inv.encode(), self.agent_addr); end = time.time() + 5
        while time.time() < end:
            for m in self.msgs:
                if m["first"].startswith("SIP/2.0 ") and SIPMOD.hv(m, "call-id") == call_id and "INVITE" in SIPMOD.hv(m, "cseq") and not m["first"].startswith("SIP/2.0 100"):
                    if m["first"].startswith("SIP/2.0 200"):
                        ip, port, codec, te = SIPMOD.sdp_offer(m["body"]); self.agent_rtp = (ip, port)
                        ack = "\r\n".join([f"ACK sip:101@127.0.0.1:{self.agent_addr[1]} SIP/2.0", f"Via: SIP/2.0/UDP 127.0.0.1:{self.port};branch=z9hG4bKsra", f"From: <sip:{number}@pbx>;tag=caller9", f"To: {SIPMOD.hv(m, 'to')}", f"Call-ID: {call_id}", "CSeq: 1 ACK", "Content-Length: 0", "", ""]); self.out(ack.encode(), self.agent_addr)
                    return m, mk, ms
            time.sleep(0.05)
        raise AssertionError("no answer")

    def wait(self, fn, t=6):
        end = time.time() + t
        while time.time() < end:
            if fn():
                return True
            time.sleep(0.05)
        return False

    def close(self):
        self.stop = True; self.s.close(); self.rtp.close()


import base64, shutil, subprocess
from speakvora_pack_agent.connectors import srtp as SRTP


class Srtp(unittest.TestCase):
    def test_aes_matches_fips_197(self):
        self.assertEqual(SRTP.AES128(bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")).encrypt(bytes.fromhex("3243f6a8885a308d313198a2e0370734")).hex(), "3925841d02dc09fbdc118597196a0b32")

    def test_key_derivation_and_keystream_match_rfc_3711_vectors(self):
        ck, cs, ak = SRTP.derive(bytes.fromhex("E1F97A0D3E018BE0D64FA32C06DE4139"), bytes.fromhex("0EC675AD498AFEEBB6960B3AABE6"))
        self.assertEqual((ck.hex().upper(), cs.hex().upper(), ak.hex().upper()), ("C61E7A93744F39EE10734AFE3FF7A087", "30CBBC08863D8C85D49DB34A9AE1", "CEBE321F6FF7716B6FD4AB49AF256A156D38BAA4"))
        ks = SRTP.aes_cm_keystream(SRTP.AES128(bytes.fromhex("2B7E151628AED2A6ABF7158809CF4F3C")).encrypt, int.from_bytes(bytes.fromhex("F0F1F2F3F4F5F6F7F8F9FAFBFCFD"), "big") << 16, 32)
        self.assertEqual(ks.hex().upper(), "E03EAD0935C95E80E166B16DD92B4EB4D23513162B02D0F72A43A2FE4A5F97AB")

    def test_round_trip_across_a_sequence_rollover_and_tampering_is_rejected(self):
        mk, ms = SRTP.new_key(); a, b = SRTP.Context(mk, ms), SRTP.Context(mk, ms)
        for s in range(65530, 65546):
            pkt = struct.pack("!BBHII", 0x80, 0, s & 0xFFFF, s * 160, 77) + bytes([s & 0xFF]) * 160; enc = a.protect(pkt)
            self.assertNotEqual(enc[12:172], pkt[12:]); self.assertEqual(b.unprotect(enc), pkt)
        bad = bytearray(a.protect(pkt)); bad[30] ^= 1; self.assertIsNone(b.unprotect(bytes(bad)))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
    def test_interoperates_with_ffmpeg_srtp_in_both_directions(self):
        import tempfile
        mk, ms = SRTP.new_key(); key = base64.b64encode(mk + ms).decode()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("127.0.0.1", 0)); s.settimeout(3); port = s.getsockname()[1]
        p = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-re", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-ar", "8000", "-ac", "1", "-acodec", "pcm_mulaw", "-f", "rtp", "-payload_type", "0", "-srtp_out_suite", "AES_CM_128_HMAC_SHA1_80", "-srtp_out_params", key, f"srtp://127.0.0.1:{port}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ctx = SRTP.Context(mk, ms); good = bad = 0; t = time.time()
        while time.time() - t < 4:
            try:
                d, _ = s.recvfrom(2048)
            except socket.timeout:
                break
            if 192 <= d[1] <= 223:
                continue                                                              # ffmpeg's own RTCP reports
            if ctx.unprotect(d) is None: bad += 1
            else: good += 1
        p.wait(); s.close(); self.assertGreater(good, 30); self.assertEqual(bad, 0)               # packets made by libsrtp decrypt with ours
        mk2, ms2 = SRTP.new_key(); tmp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); tmp.bind(("127.0.0.1", 0)); port2 = tmp.getsockname()[1]; tmp.close()
        with tempfile.TemporaryDirectory() as d:
            open(d + "/rx.sdp", "w").write(f"v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=x\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\nm=audio {port2} RTP/SAVP 0\r\na=rtpmap:0 PCMU/8000\r\na=crypto:1 AES_CM_128_HMAC_SHA1_80 inline:{base64.b64encode(mk2 + ms2).decode()}\r\n")
            tone = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=700:duration=1", "-ar", "8000", "-ac", "1", "-f", "mulaw", "pipe:1"], capture_output=True).stdout
            rec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-protocol_whitelist", "file,udp,rtp,crypto", "-i", d + "/rx.sdp", "-t", "2", d + "/out.wav"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.0)
            ctx2 = SRTP.Context(mk2, ms2); o = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); seq = 500
            for i in range(0, len(tone), 160):
                o.sendto(ctx2.protect(struct.pack("!BBHII", 0x80, 0, seq, seq * 160, 99) + tone[i:i + 160].ljust(160, b"\xff")), ("127.0.0.1", port2)); seq += 1; time.sleep(0.02)
            rec.wait(timeout=20); vol = subprocess.run(["ffmpeg", "-hide_banner", "-i", d + "/out.wav", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
        mx = float(re.search(r"max_volume: (-?[\d.]+) dB", vol).group(1)); self.assertGreater(mx, -30)       # our packets decrypt in libsrtp and come out as the tone


class Digest(unittest.TestCase):
    def test_matches_the_published_rfc_2617_example(self):
        d = SIPMOD.digest("Mufasa", "Circle Of Life", "testrealm@host.com", "dcd98b7102dd2f0e8b11d0f600bfb0c093", "GET", "/dir/index.html", qop="auth", cnonce="0a4f113b")
        self.assertIn('response="6629fae49393a05397450978507c4ef1"', d)


import ssl, tempfile


class FakePbxTls(FakePbx):
    """The same fake phone system, but over TLS on TCP (a throwaway self-signed certificate)."""
    def __init__(self, password="pw"):
        self.dir = tempfile.mkdtemp(); self.conn = None; self.connections = 0; self.last_error = ''; self.tlock = threading.Lock()
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", self.dir + "/k.pem", "-out", self.dir + "/c.pem", "-days", "2", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"], capture_output=True, check=True)
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); self.ctx.load_cert_chain(self.dir + "/c.pem", self.dir + "/k.pem")
        self.ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM); self.ls.bind(("127.0.0.1", 0)); self.ls.listen(5); self.ls.settimeout(0.3); self.port = self.ls.getsockname()[1]
        self.s = None; self.rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.rtp.bind(("127.0.0.1", 0)); self.rtp.settimeout(0.3); self.rtp_port = self.rtp.getsockname()[1]
        self.password, self.registered, self.rejected, self.msgs, self.agent_addr, self.stop = password, False, 0, [], None, False
        self.nonce = "abc123nonce"; self.rtp_in = []; self.lock = threading.Lock(); self.keepalives = 0
        threading.Thread(target=self.loop, daemon=True).start(); threading.Thread(target=self.rtp_loop, daemon=True).start()

    def loop(self):
        while not self.stop:
            try:
                raw, _ = self.ls.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                c = self.ctx.wrap_socket(raw, server_side=True)
            except (ssl.SSLError, OSError) as e:
                self.last_error = "handshake: " + repr(e); continue
            self.conn = c; self.connections += 1; buf = b""; c.settimeout(0.3)
            while not self.stop and self.conn is c:
                try:
                    with self.tlock:                                    # one SSL connection is never read and written at the same moment from two threads
                        d = c.recv(65535)
                except socket.timeout:
                    time.sleep(0.005); continue
                except (OSError, ssl.SSLError) as e:
                    self.last_error = "recv: " + repr(e); break
                if not d:
                    self.last_error = "recv: closed by the agent"; break
                buf += d
                while True:
                    if buf.startswith(b"\r\n\r\n"):
                        self.keepalives += 1; buf = buf[4:]; continue
                    i = buf.find(b"\r\n\r\n")
                    if i < 0:
                        break
                    cl = re.search(rb"(?im)^content-length\s*:\s*(\d+)", buf[:i]); n = int(cl.group(1)) if cl else 0
                    if len(buf) < i + 4 + n:
                        break
                    msg, buf = buf[:i + 4 + n], buf[i + 4 + n:]; self.on_message(SIPMOD.parse(msg), ("127.0.0.1", 0))

    def out(self, data, addr):
        with self.tlock:
            self.conn.sendall(data)

    def drop(self):
        c, self.conn = self.conn, None; c.close()

    def close(self):
        self.stop = True
        for x in (self.ls, self.rtp):
            try:
                x.close()
            except OSError:
                pass


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

    def test_encrypted_call_plays_the_menu_and_takes_an_encrypted_key_press(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); m, mk, ms = self.pbx.call_srtp()
        self.assertIn("RTP/SAVP", m["body"]); crypto = SRTP.parse_crypto(m["body"]); self.assertEqual(len(crypto), 1)
        from_agent = SRTP.Context(crypto[0][2], crypto[0][3], crypto[0][1]); to_agent = SRTP.Context(mk, ms)
        self.assertTrue(self.pbx.wait(lambda: len(self.pbx.audio_packets()) >= 3), "no encrypted menu audio")
        raw = [d for _, d in self.pbx.rtp_in if d[1] & 0x7F == 0]; self.assertTrue(all(from_agent.unprotect(d) is not None for d in raw[:5]))          # every packet authenticates
        self.assertNotEqual(raw[0][12:20], b"\xff" * 8); n = len(self.pbx.audio_packets())
        ev = struct.pack("!BBHII", 0x80, 101, 1, 1000, 7) + bytes([1, 0x80 | 10, 0, 160]); self.pbx.rtp.sendto(to_agent.protect(ev), self.pbx.agent_rtp)
        self.assertTrue(self.pbx.wait(lambda: len(self.pbx.audio_packets()) > n + 3), "an encrypted key press got no answer")

    def test_a_forged_unencrypted_packet_is_ignored_on_an_encrypted_call(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); self.pbx.call_srtp(); self.assertTrue(self.pbx.wait(lambda: len(self.pbx.audio_packets()) >= 3)); n = len(self.pbx.audio_packets())
        self.pbx.rtp.sendto(struct.pack("!BBHII", 0x80, 101, 1, 1000, 7) + bytes([1, 0x80 | 10, 0, 160]) + b"\x00" * 10, self.pbx.agent_rtp); time.sleep(2.5)
        self.assertLess(len(self.pbx.audio_packets()) - n, 160 * 3)                                         # no answer to a key press that was not authenticated (the menu simply goes on repeating)
        self.assertEqual([x for x in self.a.sip.calls.values()][0].digit_count, 0)

    def test_an_encrypted_offer_is_refused_when_encryption_is_off_and_plain_when_required_is_refused(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); self.a.sip.cfg["srtp"] = "off"
        mk, ms = SRTP.new_key(); sdp = f"v=0\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\nm=audio {self.pbx.rtp_port} RTP/SAVP 0\r\n" + SRTP.crypto_line(1, "AES_CM_128_HMAC_SHA1_80", mk, ms) + "\r\n"
        def invite(cid): return "\r\n".join(["INVITE sip:101@x SIP/2.0", f"Via: SIP/2.0/UDP 127.0.0.1:{self.pbx.port};branch=z9hG4bK{cid}", "From: <sip:1@x>;tag=t", "To: <sip:101@x>", f"Call-ID: {cid}", "CSeq: 1 INVITE", "Contact: <sip:1@127.0.0.1>", f"Content-Length: {len(sdp)}", "", sdp])
        self.pbx.s.sendto(invite("off-1").encode(), self.pbx.agent_addr); self.assertTrue(self.pbx.wait(lambda: any(m["first"].startswith("SIP/2.0 488") and SIPMOD.hv(m, "call-id") == "off-1" for m in self.pbx.msgs)))
        self.a.sip.cfg["srtp"] = "required"; plain = sdp.replace("RTP/SAVP", "RTP/AVP").split("a=crypto")[0]
        self.pbx.s.sendto(invite("req-1").replace(sdp, plain).replace(f"Content-Length: {len(sdp)}", f"Content-Length: {len(plain)}").encode(), self.pbx.agent_addr)
        self.assertTrue(self.pbx.wait(lambda: any(m["first"].startswith("SIP/2.0 488") and SIPMOD.hv(m, "call-id") == "req-1" for m in self.pbx.msgs)))

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


@unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
class SipTls(unittest.TestCase):
    def setUp(self):
        self.pbx = FakePbxTls(); self.r = Rig(extra={"sip": {"server": "127.0.0.1", "server_port": self.pbx.port, "username": "101", "password": "pw", "transport": "tls", "tls_ca_file": self.pbx.dir + "/c.pem", "rtp_start": 41400, "rtp_end": 41500}})
        self.a = self.r.agent; self.a._serving = True; self.a.sip_sync()

    def tearDown(self):
        self.a.sip_stop(); self.pbx.close(); self.r.close()

    def test_signs_in_over_tls_and_says_it_is_tls(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered), 'not signed in: ' + str(self.a.sip.err_code) + ' ' + str(self.a.sip.error) + f' | pbx connections={self.pbx.connections} messages={len(self.pbx.msgs)} first={[m["first"][:30] for m in self.pbx.msgs[:3]]} pbx_error={self.pbx.last_error} agent_reg_sent={self.a.sip.reg_sent} last_reply={self.a.sip.last_reply}'); m = self.pbx.msgs[0]
        self.assertIn("SIP/2.0/TLS", SIPMOD.hv(m, "via")); self.assertIn("transport=tls", SIPMOD.hv(m, "contact")); self.assertTrue(self.a.sip.registered)

    def test_an_untrusted_certificate_is_refused_with_a_plain_reason(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered), 'not signed in: ' + str(self.a.sip.err_code) + ' ' + str(self.a.sip.error) + f' | pbx connections={self.pbx.connections} messages={len(self.pbx.msgs)} first={[m["first"][:30] for m in self.pbx.msgs[:3]]} pbx_error={self.pbx.last_error} agent_reg_sent={self.a.sip.reg_sent} last_reply={self.a.sip.last_reply}'); self.a.sip_stop(); self.pbx.registered = False; self.r.agent.cfg["sip"].pop("tls_ca_file"); self.a.sip_sync()
        self.assertTrue(self.pbx.wait(lambda: self.a.sip.err_code == "tls_certificate", t=10)); self.assertFalse(self.pbx.registered)
        self.assertEqual(SU.sip_status(self.a)["problem"]["title"], "The phone system's certificate isn't trusted")
        self.a.sip_stop(); self.r.agent.cfg["sip"]["tls_verify"] = False; self.a.sip_sync()
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered, t=10))                      # checking switched off for a test on your own network

    def test_encrypted_call_over_an_encrypted_connection(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered), 'not signed in: ' + str(self.a.sip.err_code) + ' ' + str(self.a.sip.error) + f' | pbx connections={self.pbx.connections} messages={len(self.pbx.msgs)} first={[m["first"][:30] for m in self.pbx.msgs[:3]]} pbx_error={self.pbx.last_error} agent_reg_sent={self.a.sip.reg_sent} last_reply={self.a.sip.last_reply}'); m, mk, ms = self.pbx.call_srtp(call_id="tls-1"); crypto = SRTP.parse_crypto(m["body"])
        self.assertTrue(self.pbx.wait(lambda: len(self.pbx.audio_packets()) >= 3)); from_agent = SRTP.Context(crypto[0][2], crypto[0][3], crypto[0][1])
        self.assertTrue(all(from_agent.unprotect(d) is not None for _, d in self.pbx.rtp_in[:4] if d[1] & 0x7F == 0))
        n = len(self.pbx.audio_packets()); self.pbx.rtp.sendto(SRTP.Context(mk, ms).protect(struct.pack("!BBHII", 0x80, 101, 1, 1000, 7) + bytes([0, 0x80 | 10, 0, 160])), self.pbx.agent_rtp)
        self.assertTrue(self.pbx.wait(lambda: any(m["first"].startswith("REFER") for m in self.pbx.msgs) or len(self.pbx.audio_packets()) > n + 2))

    def test_it_reconnects_and_signs_in_again_after_the_connection_drops(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered), 'not signed in: ' + str(self.a.sip.err_code) + ' ' + str(self.a.sip.error) + f' | pbx connections={self.pbx.connections} messages={len(self.pbx.msgs)} first={[m["first"][:30] for m in self.pbx.msgs[:3]]} pbx_error={self.pbx.last_error} agent_reg_sent={self.a.sip.reg_sent} last_reply={self.a.sip.last_reply}'); self.pbx.registered = False; self.pbx.drop()
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered and self.pbx.connections >= 2, t=25), "did not reconnect")


class Wizard(unittest.TestCase):
    def setUp(self):
        self.pbx = FakePbx()
        self.r = Rig(extra={"sip": {"server": "127.0.0.1", "server_port": self.pbx.port, "username": "101", "password": "pw", "rtp_start": 41200, "rtp_end": 41300, "provider": "asterisk", "answer_when": "after_hours"}, "facts": {"oncall_phone": "+16465559999"}})
        self.a = self.r.agent; self.a._serving = True; self.a.sip_sync()

    def tearDown(self):
        self.a.sip_stop(); self.pbx.close(); self.r.close()

    def test_every_provider_has_steps_and_an_honest_label(self):
        ps = {p["id"]: p for p in SU.sip_providers()}
        self.assertEqual(ps["asterisk"]["compat"], "tested"); self.assertEqual(ps["zoom"]["compat"], "encrypted_untested"); self.assertEqual(ps["zoom"]["preset"]["transport"], "tls"); self.assertIn("not tested", ps["zoom"]["compat_text"])
        for p in ps.values(): self.assertTrue(p["where"] and p["name"])
        self.assertIn("unsure", ps)

    def test_admin_message_is_plain_and_has_no_secrets(self):
        m = SU.sip_admin_message(self.a, "3cx")
        for must in ("3CX", "UDP", "G.711", "failover", "outside business hours", "UDP ports 40000 to 40200", "password"): self.assertIn(must, m)
        self.assertNotIn("pw", m.replace("password", "")); self.assertIn("SBC", m)

    def test_status_checklist_is_proven_by_a_real_call_not_by_signing_in(self):
        self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); st = SU.sip_status(self.a)
        self.assertTrue(st["items"][1]["ok"]); self.assertFalse(st["ready"]); self.assertIn("Not ready", st["summary"])                    # signed in alone is not Ready
        self.pbx.call(); self.assertTrue(self.pbx.wait(lambda: len(self.pbx.audio_packets()) >= 3)); self.pbx.dtmf("0")
        self.assertTrue(self.pbx.wait(lambda: any(m["first"].startswith("REFER") for m in self.pbx.msgs)))
        end = time.time() + 8
        while time.time() < end and not self.a.sip.history:
            time.sleep(0.2)
        bye = "\r\n".join([f"BYE sip:101@127.0.0.1:{self.pbx.agent_addr[1]} SIP/2.0", f"Via: SIP/2.0/UDP 127.0.0.1:{self.pbx.port};branch=z9hG4bKb", "From: <sip:+16465550101@pbx>;tag=caller1", f"To: {SIPMOD.hv(self.pbx.ok, 'to')}", "Call-ID: call-1", "CSeq: 2 BYE", "Content-Length: 0", "", ""])
        self.pbx.s.sendto(bye.encode(), self.pbx.agent_addr); self.assertTrue(self.pbx.wait(lambda: self.a.sip.history))
        st = SU.sip_status(self.a); ids = {i["id"]: i for i in st["items"]}
        self.assertTrue(ids["call"]["ok"] and ids["transfer"]["ok"] and ids["fallback"]["ok"]); self.assertEqual(st["last_call"]["keys"], 1)
        self.assertTrue(self.a.state.data.get("sip_transfer_ok"))

    def test_problems_are_translated_into_plain_words(self):
        self.a.sip.err_code = "login_refused"; self.a.sip.registered = False; self.a.sip.error = "401 twice"
        pr = SU.sip_status(self.a)["problem"]; self.assertEqual(pr["title"], "Phone sign-in rejected"); self.assertIn("password", pr["fix"]); self.assertEqual(pr["tech"], "401 twice")
        self.a.sip.err_code = "no_response"; self.assertEqual(SU.sip_status(self.a)["problem"]["title"], "Can't reach your phone system")
        self.a.sip.err_code = ""; self.a.sip.registered = True; self.a.sip.history.append({"t": 1, "secs": 9, "audio_in": 0, "audio_out": 50, "keys": 0, "transferred": False, "problem": "no_inbound_audio", "caller": "***1"})
        self.assertEqual(SU.sip_status(self.a)["problem"]["title"], "Caller audio isn't reaching your computer")

    def test_silent_server_is_reported_as_unreachable(self):
        self.a.sip_stop(); self.pbx.close(); self.r.agent.cfg["sip"]["server_port"] = 5 ; self.pbx = FakePbx(); self.a.sip_sync()
        self.assertTrue(self.pbx.wait(lambda: self.a.sip.err_code == "no_response", t=20)); self.assertIn("No answer", self.a.sip.error)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- callers who speak
import os
from unittest import mock


def _loud(n_frames, seq0=1):
    return [bytes([0x10, 0x90] * 80) for _ in range(n_frames)]


class Listening(unittest.TestCase):
    def test_g711_decoding_matches_the_standard_values(self):
        self.assertEqual(struct.unpack("<3h", SIPMOD.g711_to_pcm16(bytes([0xFF, 0x00, 0x80]), 0)), (0, -32124, 32124))
        self.assertEqual(struct.unpack("<2h", SIPMOD.g711_to_pcm16(bytes([0xD5, 0x55]), 8)), (8, -8))

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_decoder_agrees_with_ffmpeg(self):
        raw = bytes(range(256)) * 2
        for codec, fmt in ((0, "mulaw"), (8, "alaw")):
            ff = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", fmt, "-ar", "8000", "-ac", "1", "-i", "pipe:0", "-f", "s16le", "pipe:1"], input=raw, capture_output=True).stdout
            self.assertEqual(SIPMOD.g711_to_pcm16(raw, codec), ff)

    def test_it_waits_for_speech_then_finishes_after_the_pause(self):
        lis = SIPMOD.Listener(0, silence=0.4)
        for _ in range(30):
            lis.feed(b"\xff" * 160)
        self.assertFalse(lis.started.is_set())                                                   # a quiet line is not speech
        for f in _loud(20):
            lis.feed(f)
        self.assertTrue(lis.started.is_set()); self.assertFalse(lis.done.is_set())
        for _ in range(25):
            lis.feed(b"\xff" * 160)
        self.assertTrue(lis.done.is_set()); self.assertGreaterEqual(len(lis.audio()), 160 * 20)

    def test_a_phone_system_that_stops_sending_audio_during_silence_still_ends_the_turn(self):
        lis = SIPMOD.Listener(0, silence=0.4)
        for f in _loud(20):
            lis.feed(f)
        self.assertTrue(lis.started.is_set()); self.assertFalse(lis.idle(lis.last_feed + 0.3))                  # a short gap is not the end
        self.assertTrue(lis.idle(lis.last_feed + 0.7)); self.assertTrue(lis.done.is_set())                    # no packets for longer than the pause: the caller finished

    def test_what_the_caller_says_over_a_filler_is_kept_and_used_as_the_next_answer(self):
        c = SIPMOD.Call.__new__(SIPMOD.Call); c.codec = 0; c.bg = None; c.bg_on = True; c.listener = None
        self.assertIsNone(c.take_bg())                                                       # nothing said: nothing to use
        c.bg = SIPMOD.Listener(0, silence=0.4)
        for f in _loud(20):
            c.bg.feed(f)                                                                      # the caller spoke while the system played "one moment"
        for _ in range(25):
            c.bg.feed(b"\xff" * 160)
        got = c.take_bg(); self.assertIsNotNone(got); self.assertTrue(got.done.is_set()); self.assertGreaterEqual(len(got.audio()), 160 * 20)
        self.assertIsNone(c.take_bg())                                                       # used once, then a fresh listener starts

    def test_a_click_is_not_speech(self):
        lis = SIPMOD.Listener(0)
        for f in _loud(2) + [b"\xff" * 160] * 10 + _loud(2):
            lis.feed(f)
        self.assertFalse(lis.started.is_set())

    def test_it_stops_at_the_longest_utterance(self):
        lis = SIPMOD.Listener(0, silence=5, max_s=1.0)
        for f in _loud(80):
            lis.feed(f)
        self.assertTrue(lis.done.is_set())

    def test_wav_wrapper_is_a_valid_8k_mono_file(self):
        w = SIPMOD.wav_8k(b"\x00\x00" * 800); self.assertEqual(w[:4], b"RIFF"); self.assertEqual(struct.unpack("<HHII", w[20:32]), (1, 1, 8000, 16000)); self.assertEqual(len(w), 44 + 1600)


class SipSpeech(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"SPEAKVORA_KEY": "test-key"}); self.env.start()
        self.pbx = FakePbx()
        self.r = Rig(extra={"sip": {"server": "127.0.0.1", "server_port": self.pbx.port, "username": "101", "password": "pw", "rtp_start": 41200, "rtp_end": 41300, "fallback_number": "202"}, "facts": {"oncall_phone": "+16465559999"}})
        self.a = self.r.agent; self.a._serving = True; self.heard = []

    def tearDown(self):
        self.a.sip_stop(); self.pbx.close(); self.r.close(); self.env.stop()

    def speak(self, frames=40, pause=75):
        for i, f in enumerate(_loud(frames)):
            self.pbx.rtp.sendto(struct.pack("!BBHII", 0x80, 0, 100 + i, 5000 + 160 * i, 9) + f, self.pbx.agent_rtp); time.sleep(0.02)
        for i in range(pause):
            self.pbx.rtp.sendto(struct.pack("!BBHII", 0x80, 0, 300 + i, 20000 + 160 * i, 9) + b"\xff" * 160, self.pbx.agent_rtp); time.sleep(0.02)

    def start(self, said="what are your hours"):
        def fake(sip, agent, g711, codec):
            self.heard.append(len(g711)); sip.stt_error = ""; return said
        mock.patch.object(SIPMOD.Sip, "transcribe", fake).start(); self.addCleanup(mock.patch.stopall)
        self.a.sip_sync(); self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); self.pbx.call()
        self.assertTrue(self.pbx.wait(lambda: len(self.pbx.audio_packets()) >= 3), "the menu never played")

    def test_the_greeting_offers_speaking_and_a_spoken_request_is_answered(self):
        self.start(); n = len(self.pbx.audio_packets()); self.speak()
        self.assertTrue(self.pbx.wait(lambda: self.heard, t=10), "nothing was sent to be transcribed"); self.assertGreater(self.heard[0], 160 * 40)
        self.assertTrue(self.pbx.wait(lambda: len(self.pbx.audio_packets()) > n + 4, t=15), "no answer after the caller spoke")
        log = open(self.a.state.log_path, encoding="utf-8").read(); self.assertIn('"heard"', log)

    def test_asking_for_a_person_transfers(self):
        self.start("let me talk to a person"); self.speak()
        self.assertTrue(self.pbx.wait(lambda: any(m["first"].startswith("REFER") for m in self.pbx.msgs), t=15), "no transfer")

    def test_no_key_means_keypad_only(self):
        self.a.sip_stop(); self.env.stop(); self.env.start(); os.environ.pop("SPEAKVORA_KEY", None)
        self.a.cfg.pop("speakvora", None); self.a.sip_sync(); self.assertTrue(self.pbx.wait(lambda: self.pbx.registered)); self.assertFalse(self.a.sip.speech_ok(self.a))

    def test_a_service_failure_does_not_strand_the_caller(self):
        self.start(""); self.speak(); self.assertTrue(self.pbx.wait(lambda: self.heard, t=10))
        n = len(self.pbx.audio_packets()); self.assertTrue(self.pbx.wait(lambda: len(self.pbx.audio_packets()) > n + 5, t=15), "silence after a failed transcription")
