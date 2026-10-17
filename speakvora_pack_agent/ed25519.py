"""Ed25519 signatures (RFC 8032, section 6 reference algorithm), standard library only. The agent uses verify() to check a commercial licence code OFFLINE against Speakvora's public key; the account server uses sign().
Pure Python is slow (a few milliseconds per call), which is fine for one check at start-up and one signature per licence code. Tested against the RFC 8032 test vectors."""
import hashlib

p = 2 ** 255 - 19
q = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x):
    return pow(x, p - 2, p)


d = -121665 * _inv(121666) % p


def _h(s):
    return hashlib.sha512(s).digest()


def _hq(s):
    return int.from_bytes(_h(s), "little") % q


def _add(P, Q):
    A, B = (P[1] - P[0]) * (Q[1] - Q[0]) % p, (P[1] + P[0]) * (Q[1] + Q[0]) % p
    C, D = 2 * P[3] * Q[3] * d % p, 2 * P[2] * Q[2] % p
    E, F, G_, H = B - A, D - C, D + C, B + A
    return (E * F % p, G_ * H % p, F * G_ % p, E * H % p)


def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _eq(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % p == 0


_sqrt_m1 = pow(2, (p - 1) // 4, p)


def _recover_x(y, sign):
    if y >= p:
        return None
    x2 = (y * y - 1) * _inv(d * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p != 0:
        x = x * _sqrt_m1 % p
    if (x * x - x2) % p != 0:
        return None
    if (x & 1) != sign:
        x = p - x
    return x


_gy = 4 * _inv(5) % p
_gx = _recover_x(_gy, 0)
G = (_gx, _gy, 1, _gx * _gy % p)


def _compress(P):
    zi = _inv(P[2]); x, y = P[0] * zi % p, P[1] * zi % p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little"); sign = y >> 255; y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % p)


def _expand(secret):
    if len(secret) != 32:
        raise ValueError("The private key must be 32 bytes.")
    h = _h(secret); a = int.from_bytes(h[:32], "little"); a &= (1 << 254) - 8; a |= (1 << 254)
    return a, h[32:]


def public_key(secret):
    return _compress(_mul(_expand(secret)[0], G))


def sign(secret, msg):
    a, prefix = _expand(secret); A = _compress(_mul(a, G)); r = _hq(prefix + msg); Rs = _compress(_mul(r, G)); hh = _hq(Rs + A + msg)
    return Rs + int.to_bytes((r + hh * a) % q, 32, "little")


def verify(public, msg, signature):
    if len(public) != 32 or len(signature) != 64:
        return False
    A, R = _decompress(public), _decompress(signature[:32])
    if not A or not R:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= q:
        return False
    hh = _hq(signature[:32] + public + msg)
    return _eq(_mul(s, G), _add(R, _mul(hh, A)))
