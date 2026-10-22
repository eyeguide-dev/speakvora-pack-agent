"""Answer calls on your existing office phone system (3CX, FreePBX/Asterisk, RingCentral/8x8/Zoom Phone SIP lines, Ooma, Vonage, Telnyx, a $30 analog adapter...): the agent signs in to it as an ordinary extension and answers calls sent to that extension,
with no Twilio. Pure standard library: SIP over UDP, digest sign-in, G.711 audio (PCMU/PCMA) over RTP, keypad digits (RFC 2833 and SIP INFO), and transfers to your staff (SIP REFER).
Create an extension on the phone system (an hour at most), put its details in the dashboard, and send the calls you want the agent to handle to that extension (a ring group, queue, or an after-hours rule).
Out of scope here: placing calls, video, TLS/SRTP-only providers, and speech recognition (callers use the keypad)."""
import base64, hashlib, os, random, re, secrets, shutil, socket, ssl, struct, subprocess, threading, time
from . import srtp as SRTP
from xml.etree import ElementTree as ET

CRLF = "\r\n"


# ---------------------------------------------------------------- message helpers
def parse(data):
    """Raw bytes -> dict(first, headers{lower: [values]}, body). Compact header names are expanded."""
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode("utf-8", "replace").split("\r\n"); h = {}
    full = {"v": "via", "f": "from", "t": "to", "i": "call-id", "m": "contact", "c": "content-type", "l": "content-length"}
    for ln in lines[1:]:
        if ":" in ln:
            k, v = ln.split(":", 1); k = k.strip().lower(); h.setdefault(full.get(k, k), []).append(v.strip())
    return {"first": lines[0], "h": h, "body": body.decode("utf-8", "replace")}


def hv(m, name, default=""):
    return (m["h"].get(name) or [default])[0]


def tag_of(v):
    r = re.search(r";\s*tag=([^;>\s]+)", v or ""); return r.group(1) if r else ""


def uri_of(v):
    r = re.search(r"<([^>]+)>", v or ""); return r.group(1) if r else (v or "").split(";")[0].strip()


def user_of(v):
    r = re.search(r"sips?:([^@;>]+)@", v or ""); return r.group(1) if r else ""


def digest(user, password, realm, nonce, method, uri, qop="", opaque="", algo="", cnonce=None):
    md5 = lambda s: hashlib.md5(s.encode()).hexdigest()
    ha1, ha2 = md5(f"{user}:{realm}:{password}"), md5(f"{method}:{uri}")
    out = f'Digest username="{user}", realm="{realm}", nonce="{nonce}", uri="{uri}"'
    if "auth" in qop:
        cn = cnonce or secrets.token_hex(6); out += f', response="{md5(f"{ha1}:{nonce}:00000001:{cn}:auth:{ha2}")}", qop=auth, nc=00000001, cnonce="{cn}"'
    else:
        out += f', response="{md5(f"{ha1}:{nonce}:{ha2}")}"'
    if opaque:
        out += f', opaque="{opaque}"'
    return out + ", algorithm=MD5"


def parse_challenge(v):
    return {k.lower(): a or b for k, a, b in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]+))', v or "")}


def sdp_media(body):
    """The audio part of an offer: address, port, profile (RTP/AVP plain or RTP/SAVP encrypted), a codec we can play, the keypad-event payload type and any SDES crypto lines."""
    ip = re.search(r"c=IN IP4 (\S+)", body); mm = re.search(r"m=audio (\d+) (\S+) ([\d ]+)", body)
    if not (ip and mm):
        return None
    pts = [int(x) for x in mm.group(3).split()]; codec = 0 if 0 in pts else (8 if 8 in pts else None)
    te = re.search(r"a=rtpmap:(\d+) telephone-event/8000", body)
    return None if codec is None else {"ip": ip.group(1), "port": int(mm.group(1)), "proto": mm.group(2), "codec": codec, "te": int(te.group(1)) if te else None, "crypto": SRTP.parse_crypto(body)}


def sdp_offer(body):
    """-> (ip, port, codec payload type (0 PCMU / 8 PCMA), telephone-event payload type or None)."""
    ip = re.search(r"c=IN IP4 (\S+)", body); mm = re.search(r"m=audio (\d+) \S+ ([\d ]+)", body)
    if not (ip and mm):
        return None
    pts = [int(x) for x in mm.group(2).split()]; codec = 0 if 0 in pts else (8 if 8 in pts else None)
    te = re.search(r"a=rtpmap:(\d+) telephone-event/8000", body)
    return (ip.group(1), int(mm.group(1)), codec, int(te.group(1)) if te else None) if codec is not None else None


# ---------------------------------------------------------------- audio
_pcm_cache = {}


def to_g711(data, codec=0, ffmpeg="ffmpeg"):
    """Any audio file's bytes (mp3, wav, m4a) -> raw 8 kHz G.711 (mu-law for 0, A-law for 8), through ffmpeg. Cached by content."""
    key = (hashlib.sha1(data).hexdigest(), codec)
    if key in _pcm_cache:
        return _pcm_cache[key]
    if not shutil.which(ffmpeg):
        raise RuntimeError("ffmpeg is needed to play recordings on phone-system calls")
    r = subprocess.run([ffmpeg, "-loglevel", "error", "-i", "pipe:0", "-ar", "8000", "-ac", "1", "-f", "mulaw" if codec == 0 else "alaw", "pipe:1"], input=data, capture_output=True, timeout=60)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("ffmpeg could not convert that recording")
    if len(_pcm_cache) > 300:
        _pcm_cache.clear()
    _pcm_cache[key] = r.stdout; return r.stdout


def _ulaw(b):
    b = ~b & 0xFF; t = ((b & 0x0F) << 3) + 0x84; t <<= (b & 0x70) >> 4
    return (0x84 - t) if b & 0x80 else (t - 0x84)


def _alaw(b):
    b ^= 0x55; t = (b & 0x0F) << 4; seg = (b & 0x70) >> 4
    t = t + 8 if seg == 0 else (t + 0x108) << (seg - 1)
    return t if b & 0x80 else -t


_ULAW = [_ulaw(i) for i in range(256)]; _ALAW = [_alaw(i) for i in range(256)]


def g711_to_pcm16(data, codec=0):
    """Raw G.711 bytes -> 16-bit little-endian PCM (8 kHz mono), by lookup table. Python 3.13 removed audioop, so this is our own."""
    tab = _ULAW if codec == 0 else _ALAW
    return struct.pack("<%dh" % len(data), *[tab[b] for b in data])


def wav_8k(pcm16):
    return b"RIFF" + struct.pack("<I", 36 + len(pcm16)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16) + b"data" + struct.pack("<I", len(pcm16)) + pcm16


class Listener:
    """Hears one caller utterance: waits for speech to start (4 loud 20 ms frames in a row, above a level that adapts to the line's own noise), keeps a little audio from just before it, and finishes after `silence` seconds of quiet or `max_s` seconds in all."""
    def __init__(self, codec, silence=1.2, max_s=15.0):
        self.codec, self.silence, self.max_frames = codec, float(silence), int(max_s * 50)
        self.buf = b""; self.pre = []; self.frames = []; self.floor = 150.0; self.loud = 0; self.quiet = 0
        self.started = threading.Event(); self.done = threading.Event(); self.lock = threading.Lock(); self.last_feed = time.time()

    def idle(self, now=None):
        """Some phone systems stop sending audio packets while the caller is silent. After speech, no packets for longer than the pause means the caller finished."""
        if self.started.is_set() and not self.done.is_set() and (now or time.time()) - self.last_feed > self.silence + 0.2:
            self.done.set()
        return self.done.is_set()

    def feed(self, payload):
        if self.done.is_set():
            return
        self.last_feed = time.time()
        with self.lock:
            self.buf += payload
            while len(self.buf) >= 160 and not self.done.is_set():
                fr, self.buf = self.buf[:160], self.buf[160:]; self._frame(fr)

    def _frame(self, fr):
        tab = _ULAW if self.codec == 0 else _ALAW; e = sum(abs(tab[b]) for b in fr) / len(fr); thr = max(300.0, self.floor * 3.5)
        if not self.started.is_set():
            self.pre.append(fr); del self.pre[:-30]                                        # keep the last 0.6 s: the soft first sound of a word ("Can", "to") is below the loudness threshold
            if e < thr:
                self.floor = 0.95 * self.floor + 0.05 * e; self.loud = 0
            else:
                self.loud += 1
                if self.loud >= 3:
                    self.started.set(); self.frames = list(self.pre); self.pre = []
            return
        self.frames.append(fr); self.quiet = 0 if e >= thr else self.quiet + 1
        if self.quiet * 0.02 >= self.silence or len(self.frames) >= self.max_frames:
            self.done.set()

    def audio(self):
        return b"".join(self.frames)


# ---------------------------------------------------------------- one call
class Call:
    def __init__(self, ua, invite, addr):
        self.ua, self.invite, self.addr = ua, invite, addr
        self.call_id = hv(invite, "call-id"); self.from_hdr, self.to_hdr = hv(invite, "from"), hv(invite, "to")
        self.my_tag = secrets.token_hex(4); self.remote_tag = tag_of(self.from_hdr)
        self.remote_target = uri_of(hv(invite, "contact")) or uri_of(self.from_hdr)
        self.route = [r for x in reversed(invite["h"].get("record-route", [])) for r in [x]]
        self.caller = user_of(self.from_hdr) or "unknown"; self.cseq = 1
        self.ended = threading.Event(); self.acked = threading.Event(); self.digits = []; self.dlock = threading.Condition()
        self.rtp = None; self.remote_rtp = None; self.codec = 0; self.te_pt = None; self.seq = random.randint(0, 60000); self.ts = random.randint(0, 2**31); self.ssrc = random.getrandbits(32)
        self.last_te_ts = None; self.stop_play = threading.Event()
        self.listener = None; self.speech_count = 0; self.started = time.time(); self.rx_audio = 0; self.tx = 0; self.digit_count = 0; self.transferred = False; self.problem = ""

    # -- media
    def open_media(self, offer):
        ip, port, codec, te = offer["ip"], offer["port"], offer["codec"], offer["te"]; self.codec, self.te_pt, self.remote_rtp = codec, te, (ip, port)
        self.srtp_in = self.srtp_out = None; self.crypto_answer = ""
        if offer["proto"] == "RTP/SAVP":                                                          # encrypted audio: keys travel in the call setup (SDES)
            tag, suite, key, salt = offer["crypto"][0]; k2, s2 = SRTP.new_key()
            self.srtp_in = SRTP.Context(key, salt, suite); self.srtp_out = SRTP.Context(k2, s2, suite); self.crypto_answer = SRTP.crypto_line(tag, suite, k2, s2)
        lo, hi = self.ua.rtp_range
        for p in random.sample(range(lo, hi, 2), min(40, (hi - lo) // 2)):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.bind(("0.0.0.0", p)); self.rtp = s; self.rtp_port = p; break
            except OSError:
                s.close()
        if not self.rtp:
            raise RuntimeError("no free audio port")
        self.rtp.settimeout(0.5); threading.Thread(target=self._rx, daemon=True).start()

    def _rx(self):
        while not self.ended.is_set():
            try:
                pkt, src = self.rtp.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                return
            if len(pkt) < 12:
                continue
            if not self.remote_rtp_latched(src):
                continue
            if self.srtp_in is not None:
                pkt = self.srtp_in.unprotect(pkt)
                if pkt is None:
                    continue
            pt = pkt[1] & 0x7F
            if pt == self.codec:
                self.rx_audio += 1
                lis = self.listener
                if lis is not None:
                    lis.feed(pkt[12:])
            if self.te_pt is not None and pt == self.te_pt and len(pkt) >= 16:
                ev, endbit = pkt[12], pkt[13] & 0x80; ts = struct.unpack("!I", pkt[4:8])[0]
                if ts != self.last_te_ts and ev <= 15 and (endbit or True):
                    self.last_te_ts = ts; self.push_digit("0123456789*#ABCD"[ev])

    def remote_rtp_latched(self, src):
        if src[0] != self.remote_rtp[0]:                           # symmetric RTP: only the address the call negotiated may send us audio
            return False
        self.remote_rtp = src; return True

    def log(self, what, **kw):
        try:
            self.ua.agent.state.log(workflow="sip", status=what, dry_run=False, caller=self.caller[-4:].rjust(4, "*"), **kw)
        except Exception:  # noqa: BLE001
            pass

    def push_digit(self, d):
        self.digit_count += 1; self.log("digit", digit=d)
        with self.dlock:
            self.digits.append(d); self.dlock.notify_all()
        self.stop_play.set()                                         # a key press interrupts the recording (barge-in)

    def wait_input(self, n, timeout, lis=None):
        """Waits for n keypad digits or (when a Listener is given) one spoken sentence. Returns the digits, or '' for speech or silence; once the caller starts talking it waits for them to finish."""
        end = time.time() + timeout
        with self.dlock:
            while not self.ended.is_set() and len(self.digits) < n:
                if lis is not None and lis.idle():
                    break
                if time.time() > end and not (lis is not None and lis.started.is_set()):
                    break
                self.dlock.wait(0.05)
            got, self.digits = "".join(self.digits[:n]), self.digits[n:]
        return got

    def wait_digits(self, n, timeout):
        end = time.time() + timeout
        with self.dlock:
            while len(self.digits) < n and not self.ended.is_set():
                left = end - time.time()
                if left <= 0:
                    break
                self.dlock.wait(min(left, 0.25))
            got, self.digits = "".join(self.digits[:n]), self.digits[n:]
        return got

    def send_audio(self, pcm, interruptible=True):
        """Plays raw G.711 at real time, 20 ms per packet. Stops at once on hang-up or (when interruptible) a key press."""
        self.stop_play.clear() if not self.digits else None
        nxt = time.time()
        for i in range(0, len(pcm), 160):
            if self.ended.is_set() or (interruptible and (self.digits or (self.listener is not None and self.listener.started.is_set()))):
                return False
            chunk = pcm[i:i + 160].ljust(160, b"\xff" if self.codec == 0 else b"\xd5")
            hdr = struct.pack("!BBHII", 0x80, self.codec, self.seq & 0xFFFF, self.ts & 0xFFFFFFFF, self.ssrc)
            try:
                self.rtp.sendto((self.srtp_out.protect(hdr + chunk) if self.srtp_out is not None else hdr + chunk), self.remote_rtp)
            except OSError:
                return False
            self.seq += 1; self.ts += 160; self.tx += 1; nxt += 0.02
            d = nxt - time.time()
            if d > 0:
                time.sleep(d)
        return True

    # -- signalling
    def reply(self, code, text, sdp=None, extra=()):
        h = [f"SIP/2.0 {code} {text}"] + [f"Via: {v}" for v in self.invite["h"].get("via", [])] + [f"Record-Route: {r}" for r in self.invite["h"].get("record-route", [])]
        h += [f"From: {self.from_hdr}", f"To: {self.to_hdr}" + ("" if code == 100 or tag_of(self.to_hdr) else f";tag={self.my_tag}"), f"Call-ID: {self.call_id}", f"CSeq: {hv(self.invite, 'cseq')}", f"Contact: <sip:{self.ua.user}@{self.ua.local_ip}:{self.ua.port}{self.ua.contact_params}>"] + list(extra)
        body = sdp or ""
        if body:
            h.append("Content-Type: application/sdp")
        self.ua.send(CRLF.join(h + [f"Content-Length: {len(body)}", "", body]), self.addr)

    def sdp(self):
        pts = f"{self.codec} {self.te_pt}" if self.te_pt is not None else f"{self.codec}"
        lines = ["v=0", f"o=speakvora {self.ssrc} 1 IN IP4 {self.ua.media_ip}", "s=speakvora", f"c=IN IP4 {self.ua.media_ip}", "t=0 0", f"m=audio {self.rtp_port} {'RTP/SAVP' if self.srtp_out is not None else 'RTP/AVP'} {pts}",
                 f"a=rtpmap:{self.codec} {'PCMU' if self.codec == 0 else 'PCMA'}/8000", "a=ptime:20", "a=sendrecv"]
        if self.te_pt is not None:
            lines += [f"a=rtpmap:{self.te_pt} telephone-event/8000", f"a=fmtp:{self.te_pt} 0-15"]
        if self.crypto_answer:
            lines.append(self.crypto_answer)
        return CRLF.join(lines) + CRLF

    def request(self, method, extra=(), body="", ctype=""):
        self.cseq += 1; branch = "z9hG4bK" + secrets.token_hex(6)
        h = [f"{method} {self.remote_target} SIP/2.0", f"Via: SIP/2.0/{self.ua.via_proto} {self.ua.local_ip}:{self.ua.port};branch={branch};rport" + (";alias" if self.ua.transport == "tls" else ""), "Max-Forwards: 70"] + [f"Route: {r}" for r in self.route]
        h += [f"From: {self.to_hdr}" + ("" if tag_of(self.to_hdr) else f";tag={self.my_tag}"), f"To: {self.from_hdr}", f"Call-ID: {self.call_id}", f"CSeq: {self.cseq} {method}", f"Contact: <sip:{self.ua.user}@{self.ua.local_ip}:{self.ua.port}{self.ua.contact_params}>"] + list(extra)
        if ctype:
            h.append(f"Content-Type: {ctype}")
        self.ua.send(CRLF.join(h + [f"Content-Length: {len(body)}", "", body]), self.addr)

    def hangup(self):
        if not self.ended.is_set():
            try:
                self.request("BYE")
            finally:
                self.finish()

    def transfer(self, number):
        self.transferred = True; self.log("transfer", to=number[-4:].rjust(4, "*"))
        dom = self.ua.domain
        self.request("REFER", [f"Refer-To: <sip:{number.lstrip('+') if self.ua.strip_plus else number}@{dom}>", f"Referred-By: <sip:{self.ua.user}@{dom}>"])

    def finish(self):
        if not self.ended.is_set():
            self.log("call_end", secs=int(time.time() - self.started), audio_in=self.rx_audio, audio_out=self.tx, keys=self.digit_count, transferred=self.transferred, problem=self.problem)
            self.ua.history.append({"t": int(self.started), "secs": int(time.time() - self.started), "audio_in": self.rx_audio, "audio_out": self.tx, "keys": self.digit_count, "transferred": self.transferred, "problem": self.problem, "caller": self.caller[-4:].rjust(4, "*")})
            del self.ua.history[:-20]
            try:                                                                                 # what has been proven survives a restart
                d = self.ua.agent.state.data; now = int(time.time())
                if self.rx_audio > 0 and self.tx > 0:
                    d["sip_test_ok"] = now
                if self.digit_count:
                    d["sip_keys_ok"] = now
                if self.transferred:
                    d["sip_transfer_ok"] = now
                if self.speech_count:
                    d["sip_speech_ok"] = now
                self.ua.agent.state.save()
            except Exception:  # noqa: BLE001
                pass
        self.ended.set(); self.stop_play.set()
        with self.dlock:
            self.dlock.notify_all()
        try:
            self.rtp and self.rtp.close()
        except OSError:
            pass
        self.ua.calls.pop(self.call_id, None)


# ---------------------------------------------------------------- the phone-system connection
class Sip:
    stt_error = ""

    def speech_ok(self, agent):
        """Callers may speak when it is not switched off and a Speakvora key is there to turn their words into text (the audio goes to Speakvora only for that, about $0.0015 a minute)."""
        from .. import sharing
        return str(self.cfg.get("speech", "on")).lower() not in ("off", "no", "false", "0") and bool(sharing._key(agent))

    def transcribe(self, agent, g711, codec):
        """Words in a caller's G.711 audio, or '' (and a plain reason in stt_error) when the service could not hear them."""
        from .. import sharing, web
        st, r = web.request("POST", sharing.host() + "/api/v1/listen", {"x-api-key": sharing._key(agent)}, body={"audio_base64": base64.b64encode(wav_8k(g711_to_pcm16(g711, codec))).decode(), "format": "wav", "language": "en"}, timeout=20)
        if st == 200 and isinstance(r, dict):
            self.stt_error = ""; return str(r.get("text") or "").strip()
        self.stt_error = {401: "key_refused", 402: "free_minutes_used"}.get(st, "stt_unavailable"); return ""

    def __init__(self, cfg):
        c = self.cfg = dict(cfg or {})
        self.transport = "tls" if str(c.get("transport") or "").lower() == "tls" else "udp"
        self.server, self.port_srv = str(c.get("server", "")), int(c.get("server_port") or (5061 if self.transport == "tls" else 5060))
        self.via_proto = "TLS" if self.transport == "tls" else "UDP"; self.contact_params = ";transport=tls" if self.transport == "tls" else ""
        self.user, self.auth_user, self.password = str(c.get("username", "")), str(c.get("auth_username") or c.get("username", "")), str(c.get("password", ""))
        self.domain = str(c.get("domain") or self.server); self.strip_plus = bool(c.get("strip_plus"))
        self.rtp_range = (int(c.get("rtp_start") or 40000), int(c.get("rtp_end") or 40200))
        self.max_calls = int(c.get("max_calls") or 20); self.max_seconds = int(c.get("max_call_minutes") or 30) * 60
        self.configured = bool(self.server and self.user and self.password) and not self.password.startswith("env:")
        self.calls, self.sock, self.registered, self.agent, self.error = {}, None, False, None, ""
        self.err_code = ""; self.history = []; self.last_reply = 0.0; self.reg_sent = 0.0; self.running = False; self._wlock = threading.Lock(); self._tlock = threading.Lock(); self._gen = 0; self._wake = threading.Event()
        self.local_ip, self.media_ip, self.port = "0.0.0.0", "0.0.0.0", 0
        self._stop = threading.Event(); self._reg_cseq = 1; self._reg_call = secrets.token_hex(8); self._auth = None

    # -- life cycle
    def start(self, agent):
        """Opens the UDP port, signs in, and keeps signing in. Returns at once; calls are handled on their own threads."""
        self.agent = agent; self.running = True
        if self.transport == "tls":
            self._try_connect()
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("0.0.0.0", int(self.cfg.get("local_port") or 0))); self.sock = s; self.port = s.getsockname()[1]
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect((self.server, self.port_srv)); self.local_ip = probe.getsockname()[0]
            finally:
                probe.close()
            self.media_ip = str(self.cfg.get("external_ip") or self.local_ip)
            threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._keepalive, daemon=True).start()

    def _try_connect(self):
        """One attempt to open the encrypted connection; a refusal is remembered in plain words and retried by the keep-alive loop."""
        try:
            self._connect_tls(); return True
        except ssl.SSLCertVerificationError as e:
            self.registered = False; self.err_code = "tls_certificate"; self.error = f"The phone system's certificate is not trusted: {getattr(e, 'verify_message', e)}"
        except (OSError, AttributeError) as e:
            self.registered = False; self.err_code = "tls_failed" if isinstance(e, ssl.SSLError) else "cannot_send"; self.error = str(e)
        self.sock = None; return False

    def _connect_tls(self):
        """Opens an encrypted connection to the phone system (TLS 1.2 or newer, certificate checked unless tls_verify is false) and starts reading from it."""
        ctx = ssl.create_default_context(cafile=self.cfg.get("tls_ca_file") or None); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        if self.cfg.get("tls_verify") is False or str(self.cfg.get("tls_verify")).lower() == "false":
            ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        raw = socket.create_connection((self.server, self.port_srv), timeout=10)
        s = ctx.wrap_socket(raw, server_hostname=self.server); s.settimeout(None)
        self.local_ip, self.port = s.getsockname()[0], s.getsockname()[1]; self.media_ip = str(self.cfg.get("external_ip") or self.local_ip)
        self._gen += 1; self.sock = s
        threading.Thread(target=self._loop_tls, args=(s, self._gen), daemon=True).start()

    def _loop_tls(self, s, gen):
        buf = b""
        while not self._stop.is_set():
            try:
                with self._tlock:                                                                  # an SSL connection must not be read and written at the same moment from two threads (that corrupts the stream), so every read and write takes turns
                    s.settimeout(0.25)
                    try:
                        data = s.recv(65535)
                    except (socket.timeout, ssl.SSLWantReadError):
                        data = None
                if data is None:
                    time.sleep(0.005); continue                                                    # lets a waiting write go first
            except (OSError, ssl.SSLError):
                break
            if not data:
                break
            buf += data
            while True:
                buf = buf.lstrip(b"\r\n")                                                          # keep-alive replies are bare line breaks
                i = buf.find(b"\r\n\r\n")
                if i < 0:
                    break
                cl = re.search(rb"(?im)^(?:content-length|l)\s*:\s*(\d+)", buf[:i]); n = int(cl.group(1)) if cl else 0
                if len(buf) < i + 4 + n:
                    break
                raw, buf = buf[:i + 4 + n], buf[i + 4 + n:]
                try:
                    self._handle(parse(raw), (self.server, self.port_srv))
                except Exception as e:  # noqa: BLE001
                    self.error = f"{type(e).__name__}: {e}"[:200]
        if gen == self._gen and not self._stop.is_set():                                         # the connection dropped: sign in again on a new one
            self.registered = False; self.err_code = "connection_lost"; self.error = "The connection to the phone system was lost; reconnecting."; self.sock = None; self._wake.set()
            try:
                s.close()
            except OSError:
                pass

    def _note(self, kind):
        try:
            from .. import setuplog
            setuplog.record(self.agent, kind, server=self.server, user=self.user)
        except Exception:  # noqa: BLE001
            pass

    def stop(self):
        self._stop.set(); self._wake.set()
        for c in list(self.calls.values()):
            try:
                c.hangup()
            except Exception:  # noqa: BLE001
                pass
        try:
            self._register(0)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.1)
        try:
            self.sock.close()
        except (OSError, AttributeError):
            pass
        self.sock = None; self.registered = False; self.running = False

    def send(self, text, addr):
        if self.transport == "tls":
            self._tls_write(text.encode())
        else:
            self.sock.sendto(text.encode(), addr)

    def _tls_write(self, data):
        with self._wlock:
            with self._tlock:
                s = self.sock
                s.settimeout(10); s.sendall(data)

    def _register(self, expires=300, auth=None):
        if auth is None:
            self._auth = None                                                              # a fresh sign-in: the phone system may repeat a nonce it gave earlier, which is not a wrong password
        self.reg_sent = time.time(); branch = "z9hG4bK" + secrets.token_hex(6); uri = f"sip:{self.domain}"
        h = [f"REGISTER {uri} SIP/2.0", f"Via: SIP/2.0/{self.via_proto} {self.local_ip}:{self.port};branch={branch};rport" + (";alias" if self.transport == "tls" else ""), "Max-Forwards: 70", f"From: <sip:{self.user}@{self.domain}>;tag={self._reg_call[:8]}", f"To: <sip:{self.user}@{self.domain}>",
             f"Call-ID: {self._reg_call}", f"CSeq: {self._reg_cseq} REGISTER", f"Contact: <sip:{self.user}@{self.local_ip}:{self.port}{self.contact_params}>;expires={expires}", f"Expires: {expires}", "User-Agent: speakvora-agent"]
        if auth:
            h.append(f"{'Proxy-' if auth.get('proxy') else ''}Authorization: " + digest(self.auth_user, self.password, auth["realm"], auth["nonce"], "REGISTER", uri, auth.get("qop", ""), auth.get("opaque", "")))
        self._reg_cseq += 1
        self.send(CRLF.join(h + ["Content-Length: 0", "", ""]), (self.server, self.port_srv))

    def _nap(self, seconds):
        """Sleeps, but wakes at once when the connection drops or the line is stopped."""
        self._wake.wait(seconds); self._wake.clear()

    def _keepalive(self):
        while not self._stop.is_set():
            try:
                if self.transport == "tls" and self.sock is None and not self._try_connect():
                    self._nap(15); continue
                self._register(300)
            except ssl.SSLCertVerificationError as e:
                self.registered = False; self.err_code = "tls_certificate"; self.error = f"The phone system's certificate is not trusted: {e.verify_message if hasattr(e, 'verify_message') else e}"; self.sock = None
            except (OSError, AttributeError) as e:
                self.registered = False; self.err_code = "tls_failed" if isinstance(e, ssl.SSLError) else "cannot_send"; self.error = str(e); self.sock = None
            sent = self.reg_sent
            self._nap(6)
            if self.last_reply < sent and not self._stop.is_set():                      # nothing came back at all: wrong address or port, or a firewall
                self.registered = False; self.err_code = "no_response"; self.error = f"No answer from {self.server}:{self.port_srv}."
            waited = 0
            while waited < (144 if self.registered else 9) and not self._stop.is_set():
                self._nap(15 if self.transport == "tls" else 144); waited += 15 if self.transport == "tls" else 144
                if self.transport == "tls" and self.sock is None:
                    break
                if self.transport == "tls" and self.sock is not None:
                    try:
                        self.send("\r\n\r\n", None)                                                  # a keep-alive so the connection is not closed as idle
                    except (OSError, AttributeError, ssl.SSLError):
                        break

    def _loop(self):
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(65535)
            except (OSError, AttributeError):
                return
            try:
                self._handle(parse(data), addr)
            except Exception as e:  # noqa: BLE001 - a bad packet never stops the phone line
                self.error = f"{type(e).__name__}: {e}"[:200]

    def _handle(self, m, addr):
        first = m["first"]
        if first.startswith("SIP/2.0"):
            code = int(first.split()[1]); cs = hv(m, "cseq"); self.last_reply = time.time()
            if cs.endswith("REGISTER"):
                if code in (401, 407):
                    ch = parse_challenge(hv(m, "www-authenticate") or hv(m, "proxy-authenticate")); ch["proxy"] = code == 407
                    if self._auth_tried(ch):
                        self.registered = False; self.err_code = "login_refused"; self.error = "The phone system did not accept the username and password."; self._note("sip_login_refused")
                    else:
                        self._register(300, ch)
                elif code == 200:
                    if not self.registered:
                        self._note("sip_registered")
                    self.registered = True; self.error = ""; self.err_code = ""
                elif code >= 300:
                    self.registered = False; self.err_code = "login_refused"; self.error = f"The phone system refused the sign-in ({code}): check the extension, username and password."
            return
        method = first.split()[0]
        if method == "INVITE":
            return self._invite(m, addr)
        cid = hv(m, "call-id"); call = self.calls.get(cid)
        if method == "ACK" and call:
            call.acked.set()
        elif method == "BYE" and call:
            self._ok(m, addr, call); call.finish()
        elif method == "CANCEL" and call:
            self._ok(m, addr, call); call.finish()
        elif method == "INFO" and call:
            self._ok(m, addr, call)
            r = re.search(r"Signal\s*=\s*([0-9*#A-D])", m["body"], re.I)
            if r:
                call.push_digit(r.group(1).upper())
        elif method in ("OPTIONS", "NOTIFY", "UPDATE") or call:
            self._ok(m, addr, call)

    def _auth_tried(self, ch):
        key = (ch.get("nonce"), ch.get("realm")); again = self._auth == key; self._auth = key; return again

    def _ok(self, m, addr, call=None):
        h = ["SIP/2.0 200 OK"] + [f"Via: {v}" for v in m["h"].get("via", [])] + [f"From: {hv(m, 'from')}", f"To: {hv(m, 'to')}" + ("" if tag_of(hv(m, 'to')) else f";tag={secrets.token_hex(3)}"), f"Call-ID: {hv(m, 'call-id')}", f"CSeq: {hv(m, 'cseq')}", "Content-Length: 0", "", ""]
        self.send(CRLF.join(h), addr)

    def _invite(self, m, addr):
        call = Call(self, m, addr)
        if call.call_id in self.calls:
            return                                                    # a repeated INVITE (the system retries until it hears back)
        offer = sdp_media(m["body"]); mode = str(self.cfg.get("srtp") or "optional")
        if len(self.calls) >= self.max_calls:
            return call.reply(486, "Busy Here")
        if not offer or (offer["proto"] == "RTP/SAVP" and (not offer["crypto"] or mode == "off")) or (offer["proto"] != "RTP/SAVP" and mode == "required"):
            return call.reply(488, "Not Acceptable Here")
        self.calls[call.call_id] = call
        try:
            call.log("call_start", codec="PCMU" if offer["codec"] == 0 else "PCMA", dtmf="rfc2833" if offer["te"] is not None else "sip-info", media="srtp" if offer["proto"] == "RTP/SAVP" else "rtp")
            call.reply(100, "Trying"); call.open_media(offer); call.reply(200, "OK", call.sdp())
        except Exception as e:  # noqa: BLE001
            self.error = str(e)[:200]; call.reply(500, "Server Error"); call.finish(); return
        threading.Thread(target=self._run, args=(call,), daemon=True).start()

    # -- what the caller hears: the agent's normal call flow, played over this line
    def _run(self, call):
        started = time.time()
        threading.Timer(self.max_seconds, call.hangup).start()
        call.acked.wait(3)
        def watch():
            if not call.ended.wait(7) and call.rx_audio == 0 and not call.transferred:                                       # the caller's audio never arrived: usually a firewall or NAT
                call.problem = "no_inbound_audio"; call.log("problem", code="no_inbound_audio")
        threading.Thread(target=watch, daemon=True).start()
        try:
            Flow(self.agent, call, self).run()
        except Exception as e:  # noqa: BLE001
            self.agent.state.log(workflow="sip", status="error", error=f"{type(e).__name__}: {e}"[:200]); self._fallback(call)
        finally:
            if not call.ended.is_set():
                call.hangup()

    def _fallback(self, call):
        """Something went wrong mid-call: never leave the caller in silence. Hand them to a person if a fallback number is set, else end the call."""
        num = str(self.cfg.get("fallback_number") or "").strip()
        if num and not call.ended.is_set():
            call.transfer(num); call.ended.wait(8)


class Flow:
    """Plays the agent's TwiML-style call script: Play, Say (with a local voice if the computer has one), Gather (keypad), Redirect, Dial (transfer to staff), Pause, Hangup. The menu, hours, booking, status and hand-off logic is the agent's own."""
    def __init__(self, agent, call, sip):
        self.a, self.c, self.sip = agent, call, sip
        self.params = {"From": "+" + call.caller.lstrip("+") if call.caller.lstrip("+").isdigit() else call.caller, "To": sip.user, "CallSid": "sip-" + call.call_id[:20]}

    def run(self):
        import threading as _t
        self.a._tl = getattr(self.a, "_tl", None) or _t.local(); self.a._tl.sip_call = True; self.a._tl.sip_tts = bool(shutil.which("say") or shutil.which("espeak-ng")); self.a._tl.sip_speech = self.sip.speech_ok(self.a)       # the agent offers "say or press" only when we can hear words
        xml = self.a.handle_call(self.params, "start", "")
        for _ in range(40):                                              # a call script never loops forever
            xml = self.play(xml)
            if xml is None or self.c.ended.is_set():
                return

    def step_for(self, url):
        path = url.split("?")[0].rstrip("/")
        if "/call/wait/" in path:
            return "wait", path.rsplit("/", 1)[1]
        return {"menu2": "menu2", "menu3": "menu3"}.get(path.rsplit("/", 1)[-1], "menu"), ""

    def nxt(self, url, digits="", speech=""):
        step, pid = self.step_for(url)
        if step == "wait":
            return self.a.call_wait(pid, dict(self.params))
        return self.a.handle_call(dict(self.params, Digits=digits, **({"SpeechResult": speech} if speech else {})), step, digits)

    def audio(self, el):
        if el.tag == "Play":
            m = re.search(r"/audio/([^/]+?)(?:\.\w+)?$", (el.text or "").strip())
            got = self.a.audio.serve(m.group(1)) if m else None
            return to_g711(got[0], self.c.codec) if got else b""
        if el.tag == "Say":
            return self.say(el.text or "")
        return b""

    def say(self, text):
        """The recorded lines are the voice; this only covers a line the bundle has no recording for, using the computer's own voice (macOS say / espeak-ng) when it has one."""
        for cmd in (["say", "-o", "{o}.aiff", "{t}"], ["espeak-ng", "-w", "{o}.wav", "{t}"]):
            if shutil.which(cmd[0]):
                import tempfile
                with tempfile.TemporaryDirectory() as d:
                    o = os.path.join(d, "s"); args = [x.replace("{o}", o).replace("{t}", text) for x in cmd]
                    try:
                        subprocess.run(args, capture_output=True, timeout=30, check=True); f = o + (".aiff" if cmd[0] == "say" else ".wav")
                        return to_g711(open(f, "rb").read(), self.c.codec)
                    except Exception:  # noqa: BLE001
                        continue
        self.a.state.log(workflow="sip", status="no_voice", dry_run=False, text=text[:60]); return b""

    def hear(self, lis):
        try:
            said = self.sip.transcribe(self.a, lis.audio(), self.c.codec)
        except Exception:  # noqa: BLE001
            self.sip.stt_error = "stt_unavailable"; said = ""
        self.c.log("heard" if said else "heard_nothing", words=len(said.split()), problem=self.sip.stt_error)
        if said:
            self.c.speech_count += 1
        return said

    def play(self, xml):
        root = ET.fromstring(xml)
        self.c.log("script", steps=",".join(el.tag + (":" + str(len(self.audio(el)) // 8000) + "s" if el.tag in ("Play", "Say") and False else "") for el in root))
        for el in list(root):
            if self.c.ended.is_set():
                return None
            if el.tag in ("Play", "Say"):
                self.c.send_audio(self.audio(el), interruptible=False)
            elif el.tag == "Pause":
                time.sleep(min(float(el.get("length") or 1), 10))
            elif el.tag == "Hangup":
                self.c.hangup(); return None
            elif el.tag == "Redirect":
                return self.nxt(el.text or "")
            elif el.tag == "Dial":
                num = (el.findtext("Number") or "").strip()
                if num:
                    self.c.transfer(num); self.c.ended.wait(30)
                return None
            elif el.tag == "Gather":
                n = int(el.get("numDigits") or 1); self.c.digits.clear(); self.c.stop_play.clear()
                lis = Listener(self.c.codec, silence=1.2 if str(el.get("speechTimeout") or "auto") == "auto" else float(el.get("speechTimeout"))) if "speech" in (el.get("input") or "") and self.sip.speech_ok(self.a) else None
                self.c.listener = lis
                try:
                    for sub in el:
                        if self.c.digits or (lis is not None and lis.started.is_set()):
                            break
                        self.c.send_audio(self.audio(sub), interruptible=True)
                    got = self.c.wait_input(n, float(el.get("timeout") or 6), lis)
                finally:
                    self.c.listener = None
                if got:
                    return self.nxt(el.get("action") or "", got)
                if lis is not None and lis.started.is_set():
                    said = self.hear(lis)
                    if said:
                        return self.nxt(el.get("action") or "", "", said)
        return None
