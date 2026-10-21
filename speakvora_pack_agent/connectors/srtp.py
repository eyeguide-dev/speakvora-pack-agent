"""SRTP (RFC 3711) for phone calls whose provider requires encrypted audio: AES-128 counter mode with HMAC-SHA1 authentication, keys exchanged in the call setup (SDES, a=crypto lines). Standard library only: a small AES-128
(table version, fast enough for a few calls at once) is built in; if the optional 'cryptography' package is installed it is used instead. Only what a G.711 phone call needs: no RTCP protection, no replay lists beyond a sliding window."""
import base64, hashlib, hmac, os, struct

SUITES = {"AES_CM_128_HMAC_SHA1_80": 10, "AES_CM_128_HMAC_SHA1_32": 4}            # auth tag length in bytes

# ---- AES-128 (encrypt only) ------------------------------------------------------------------------------------------------
def _build_tables():
    sbox = [0] * 256; p = q = 1
    while True:                                                                    # multiplicative inverse in GF(2^8) plus the affine transform
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= q << 1; q ^= q << 2; q ^= q << 4; q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) & 0xFF ^ ((q << 2) | (q >> 6)) & 0xFF ^ ((q << 3) | (q >> 5)) & 0xFF ^ ((q << 4) | (q >> 4)) & 0xFF
        sbox[p] = (x ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    def xt(a): return ((a << 1) ^ 0x11B) & 0xFF if a & 0x80 else a << 1
    t0 = [0] * 256
    for i in range(256):
        s = sbox[i]; s2 = xt(s); s3 = s2 ^ s
        t0[i] = (s2 << 24) | (s << 16) | (s << 8) | s3
    ror = lambda v, n: ((v >> n) | (v << (32 - n))) & 0xFFFFFFFF
    return sbox, t0, [ror(v, 8) for v in t0], [ror(v, 16) for v in t0], [ror(v, 24) for v in t0]


SBOX, T0, T1, T2, T3 = _build_tables()


class AES128:
    def __init__(self, key):
        assert len(key) == 16
        w = list(struct.unpack(">4I", key)); rcon = 1
        for i in range(4, 44):
            t = w[i - 1]
            if i % 4 == 0:
                t = ((SBOX[(t >> 16) & 0xFF] << 24) | (SBOX[(t >> 8) & 0xFF] << 16) | (SBOX[t & 0xFF] << 8) | SBOX[(t >> 24) & 0xFF]) ^ (rcon << 24)
                rcon = ((rcon << 1) ^ 0x11B) & 0xFF if rcon & 0x80 else rcon << 1
            w.append(w[i - 4] ^ t)
        self.w = w

    def encrypt(self, block):
        w = self.w; s0, s1, s2, s3 = (a ^ b for a, b in zip(struct.unpack(">4I", block), w[0:4])); k = 4
        for _ in range(9):
            t0 = T0[s0 >> 24] ^ T1[(s1 >> 16) & 0xFF] ^ T2[(s2 >> 8) & 0xFF] ^ T3[s3 & 0xFF] ^ w[k]
            t1 = T0[s1 >> 24] ^ T1[(s2 >> 16) & 0xFF] ^ T2[(s3 >> 8) & 0xFF] ^ T3[s0 & 0xFF] ^ w[k + 1]
            t2 = T0[s2 >> 24] ^ T1[(s3 >> 16) & 0xFF] ^ T2[(s0 >> 8) & 0xFF] ^ T3[s1 & 0xFF] ^ w[k + 2]
            t3 = T0[s3 >> 24] ^ T1[(s0 >> 16) & 0xFF] ^ T2[(s1 >> 8) & 0xFF] ^ T3[s2 & 0xFF] ^ w[k + 3]
            s0, s1, s2, s3 = t0, t1, t2, t3; k += 4
        r0 = ((SBOX[s0 >> 24] << 24) | (SBOX[(s1 >> 16) & 0xFF] << 16) | (SBOX[(s2 >> 8) & 0xFF] << 8) | SBOX[s3 & 0xFF]) ^ w[k]
        r1 = ((SBOX[s1 >> 24] << 24) | (SBOX[(s2 >> 16) & 0xFF] << 16) | (SBOX[(s3 >> 8) & 0xFF] << 8) | SBOX[s0 & 0xFF]) ^ w[k + 1]
        r2 = ((SBOX[s2 >> 24] << 24) | (SBOX[(s3 >> 16) & 0xFF] << 16) | (SBOX[(s0 >> 8) & 0xFF] << 8) | SBOX[s1 & 0xFF]) ^ w[k + 2]
        r3 = ((SBOX[s3 >> 24] << 24) | (SBOX[(s0 >> 16) & 0xFF] << 16) | (SBOX[(s1 >> 8) & 0xFF] << 8) | SBOX[s2 & 0xFF]) ^ w[k + 3]
        return struct.pack(">4I", r0, r1, r2, r3)


def _block_cipher(key):
    try:                                                                            # faster, when the optional package happens to be installed
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        return lambda b: enc.update(b)
    except Exception:  # noqa: BLE001
        return AES128(key).encrypt


# ---- key derivation and packet protection ---------------------------------------------------------------------------------
def aes_cm_keystream(encrypt, iv_int, nbytes):
    out = bytearray()
    for i in range((nbytes + 15) // 16):
        out += encrypt(((iv_int + i) & ((1 << 128) - 1)).to_bytes(16, "big"))
    return bytes(out[:nbytes])


def derive(master_key, master_salt):
    """RFC 3711 section 4.3 with a key derivation rate of 0: (cipher key, cipher salt, auth key)."""
    enc = _block_cipher(master_key); salt = int.from_bytes(master_salt, "big")
    def prf(label, n):
        x = salt ^ (label << 48)                                                    # the label sits just above the (zero) 48-bit index in the 112-bit salt
        return aes_cm_keystream(enc, x << 16, n)
    return prf(0, 16), prf(2, 14), prf(1, 20)


class Context:
    """One direction of one call: encrypts (protect) or checks and decrypts (unprotect) RTP packets."""
    def __init__(self, master_key, master_salt, suite="AES_CM_128_HMAC_SHA1_80"):
        self.tag_len = SUITES[suite]; ck, self.salt, self.auth_key = derive(master_key, master_salt)
        self.encrypt = _block_cipher(ck); self.salt_int = int.from_bytes(self.salt, "big")
        self.roc = 0; self.s_l = None; self.suite = suite; self.bad = 0

    @staticmethod
    def _payload_offset(pkt):
        off = 12 + 4 * (pkt[0] & 0x0F)
        if pkt[0] & 0x10:
            off += 4 + 4 * struct.unpack("!H", pkt[off + 2:off + 4])[0]
        return off

    def _crypt(self, pkt, ssrc, index):
        off = self._payload_offset(pkt); n = len(pkt) - off
        iv = (self.salt_int << 16) ^ (ssrc << 64) ^ (index << 16)
        ks = aes_cm_keystream(self.encrypt, iv, n)
        return pkt[:off] + (int.from_bytes(pkt[off:], "big") ^ int.from_bytes(ks, "big")).to_bytes(n, "big") if n else pkt

    def _tag(self, data, roc):
        return hmac.new(self.auth_key, data + struct.pack("!I", roc), hashlib.sha1).digest()[:self.tag_len]

    def protect(self, pkt):
        seq = struct.unpack("!H", pkt[2:4])[0]; ssrc = struct.unpack("!I", pkt[8:12])[0]
        if self.s_l is not None and seq < self.s_l and self.s_l - seq > 0x8000:
            self.roc += 1                                                          # the 16-bit sequence number wrapped
        self.s_l = seq if self.s_l is None or seq > self.s_l or self.s_l - seq > 0x8000 else self.s_l
        enc = self._crypt(pkt, ssrc, (self.roc << 16) | seq)
        return enc + self._tag(enc, self.roc)

    def unprotect(self, pkt):
        """The decrypted RTP packet, or None when it is too short or fails authentication."""
        if len(pkt) < 12 + self.tag_len:
            return None
        body, tag = pkt[:-self.tag_len], pkt[-self.tag_len:]
        seq = struct.unpack("!H", body[2:4])[0]; ssrc = struct.unpack("!I", body[8:12])[0]
        roc = self.roc
        if self.s_l is not None:                                                    # RFC 3711 appendix A: pick the rollover counter closest to the last sequence number
            if self.s_l < 0x8000:
                roc = self.roc - 1 if seq - self.s_l > 0x8000 else self.roc
            else:
                roc = self.roc + 1 if self.s_l - 0x8000 > seq else self.roc
        if roc < 0 or not hmac.compare_digest(self._tag(body, roc), tag):
            self.bad += 1; return None
        if self.s_l is None or roc > self.roc or (roc == self.roc and seq > self.s_l):
            self.roc, self.s_l = roc, seq
        return self._crypt(body, ssrc, (roc << 16) | seq)


# ---- SDP crypto lines ---------------------------------------------------------------------------------------------------
def parse_crypto(sdp):
    """All a=crypto lines of the offer that use a suite we can do: [(tag, suite, key, salt)]."""
    out = []
    for line in sdp.splitlines():
        line = line.strip()
        if line.startswith("a=crypto:"):
            parts = line[9:].split()
            if len(parts) >= 3 and parts[1] in SUITES and parts[2].startswith("inline:"):
                try:
                    raw = base64.b64decode(parts[2][7:].split("|")[0] + "==")
                except ValueError:
                    continue
                if len(raw) >= 30:
                    out.append((parts[0], parts[1], raw[:16], raw[16:30]))
    return out


def new_key():
    return os.urandom(16), os.urandom(14)


def crypto_line(tag, suite, key, salt):
    return f"a=crypto:{tag} {suite} inline:{base64.b64encode(key + salt).decode()}"
