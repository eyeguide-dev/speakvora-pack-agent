"""Fix verification: after a ticket is marked fixed, one small web check you wrote can say whether the problem is really gone.

agent.json "bug_checks": [{"name": "Checkout page", "match": "checkout pay", "url": "https://shop.example.com/api/health/checkout", "method": "GET", "body": {}, "expect_status": 200, "expect_text": "", "allow_private": false}]
  * match: words that must ALL appear in the ticket's summary, page or action (any capital letters). A ticket with no matching check is never checked.
  * one request, 8 second limit, only the first 20 KB of the answer is read.
  * only http and https; the address must be a public one (not this computer, not a private network, not a cloud metadata address) unless that check has allow_private true;
    a redirect to another host is not followed.
Two facts are always kept apart: "Marked fixed by NAME at TIME" (a person said so) and "Verified by check NAME: passed" (a check ran and passed). A failed check never changes the ticket by itself.
Guardrails: bug_verify = ask (default: run only when someone says verify) | auto (run right after closing) | auto_reopen (like auto; a failed check asks to reopen, and reopens by itself only if bug_close is auto) | off.
bug_tell_after_verify (default false): when true the customers who reported the bug are told "fixed" only after a check passed.
"""
import http.client, ipaddress, json, re, socket, time
from urllib.parse import urljoin, urlsplit

from . import bugdesk
from .connectors import atlassian as AT

TIMEOUT, MAX_BYTES, HOPS = 8.0, 20 * 1024, 3
MODES = ("ask", "auto", "auto_reopen", "off")
VERIFY = re.compile(r"\b(verify|re-?verify|run (the )?check|re-?run (the )?check|check (it )?again|run the test)\b", re.I)


def mode(agent):
    m = str((agent.cfg.get("guardrails") or {}).get("bug_verify", "ask")).lower()
    return m if m in MODES else "ask"


def tell_after_verify(agent):
    return str((agent.cfg.get("guardrails") or {}).get("bug_tell_after_verify", False)).lower() in ("true", "1", "yes", "on")


# ---- choosing a check -----------------------------------------------------------------------------------------------------------------------------------------------------------------------
def _checks(agent):
    return [c for c in (agent.cfg.get("bug_checks") or []) if isinstance(c, dict) and c.get("url") and c.get("name")]


def _words(match):
    return [w.lower() for w in (match if isinstance(match, list) else re.split(r"[\s,;]+", str(match or ""))) if str(w).strip()]


def find(agent, text):
    """The check whose match words all appear in `text` (the ticket's summary, page, action). The one with the most words wins; None when no check fits."""
    t = str(text or "").lower(); best, score = None, 0
    for c in _checks(agent):
        ws = _words(c.get("match"))
        if ws and all(w in t for w in ws) and len(ws) > score:
            best, score = c, len(ws)
    return best


# ---- the guarded request ----------------------------------------------------------------------------------------------------------------------------------------------------------------------
def _resolve(host, port):
    """Replaced in tests. Every address the name points to."""
    return sorted({ai[4][0] for ai in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


def public_address(ip):
    """True only for an address on the public internet. Loopback, private, link-local (which holds the cloud metadata address), shared, reserved and multicast addresses are refused."""
    try:
        a = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return a.is_global and not (a.is_loopback or a.is_private or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified)


def _guard(url, allow_private):
    """Raises ValueError with a plain reason when the address must not be requested."""
    u = urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("only http and https addresses are allowed")
    if u.username or u.password:
        raise ValueError("an address with a password in it is not allowed")
    if not allow_private:
        addrs = _resolve(u.hostname, u.port or (443 if u.scheme == "https" else 80))
        if not addrs or not all(public_address(a) for a in addrs):
            raise ValueError("that address is not a public one (this computer, a private network or a metadata address)")
    return u


def _fetch(method, url, headers, body, timeout, allow_private):
    """One request, no redirects followed, at most 20 KB read. Returns (status, text, location). The address is checked again at the moment of connecting, so a name that changes its answer is caught."""
    u = urlsplit(url); https = u.scheme == "https"; port = u.port or (443 if https else 80)
    conn = (http.client.HTTPSConnection if https else http.client.HTTPConnection)(u.hostname, port, timeout=timeout)
    if not allow_private:
        def guarded(addr, timeout=timeout, source_address=None):
            err = None
            for ip in _resolve(addr[0], addr[1]):
                if not public_address(ip):
                    raise ValueError("that address is not a public one")
                try:
                    return socket.create_connection((ip, addr[1]), timeout)
                except OSError as e:
                    err = e
            raise err or OSError("no address")
        conn._create_connection = guarded
    try:
        conn.request(method, (u.path or "/") + ("?" + u.query if u.query else ""), body=body, headers=headers)
        r = conn.getresponse(); data = r.read(MAX_BYTES)
        return r.status, data.decode("utf-8", "replace"), r.getheader("location") or ""
    finally:
        conn.close()


def run(agent, check, fetch=None):
    """One check -> {"ok", "status", "ms", "detail"}. Never raises. `fetch(method, url, headers, body, timeout, allow_private)` can be replaced for tests."""
    fetch = fetch or _fetch; t0 = time.time()
    method = str(check.get("method") or "GET").upper(); allow = bool(check.get("allow_private"))
    want = int(check.get("expect_status") or 200); text = str(check.get("expect_text") or "")
    out = lambda ok, status, detail: {"ok": ok, "status": status, "ms": int((time.time() - t0) * 1000), "detail": detail}
    try:
        if method not in ("GET", "POST"):
            return out(False, 0, "method must be GET or POST")
        url = str(check["url"]); body = None; hdr = {"user-agent": "SpeakvoraAgent-check", "accept": "*/*"}
        if method == "POST" and check.get("body") not in (None, ""):
            body = json.dumps(check["body"]).encode(); hdr["content-type"] = "application/json"
        host0 = (urlsplit(url).hostname or "", urlsplit(url).port)
        for _hop in range(HOPS + 1):
            _guard(url, allow)
            left = TIMEOUT - (time.time() - t0)
            if left <= 0:
                return out(False, 0, "no answer within 8 seconds")
            status, got, loc = fetch(method, url, hdr, body, min(TIMEOUT, left), allow)
            if 300 <= status < 400 and loc:
                nxt = urljoin(url, loc); u2 = urlsplit(nxt)
                if (u2.hostname or "", u2.port) != host0 or u2.scheme not in ("http", "https"):
                    return out(False, status, "redirected to another host (not followed)")
                url = nxt; continue
            ms = int((time.time() - t0) * 1000)
            if status != want:
                return out(False, status, f"status {status}")
            if text and text not in got:
                return out(False, status, f"status {status}, expected text not found")
            return {"ok": True, "status": status, "ms": ms, "detail": f"{status} in {ms} ms"}
        return out(False, 0, "too many redirects")
    except ValueError as e:
        return out(False, 0, "refused: " + str(e))
    except TimeoutError:
        return out(False, 0, "no answer within 8 seconds")
    except Exception as e:  # noqa: BLE001 - the reason is the kind of failure, never a message that could hold an address with a key in it
        return out(False, 0, "could not connect (" + type(e).__name__ + ")")


# ---- using it on a ticket ----------------------------------------------------------------------------------------------------------------------------------------------------------------------
def ticket_text(info):
    return " ".join(str(info.get(k) or "") for k in ("summary", "where"))


def _thread_of(agent, key):
    for ref, k in reversed(list((agent.state.data.get("bug_threads") or {}).items())):
        if k == key:
            chan, _, ts = ref.partition(":"); return chan, ts
    return "", ""


def _post(agent, key, text, say=None):
    if say:
        say(text); return
    chan, ts = _thread_of(agent, key)
    if chan and ts:
        bugdesk._say(agent, text, chan, ts)


def fixed_fact(info):
    return f"Marked fixed by {info.get('fixed_by') or 'the team'} at {info.get('fixed_at') or info.get('closed') or 'an unknown time'}."


def verify(agent, key, info, say=None):
    """Runs the matching check for a ticket that was marked fixed, tells the Jira ticket and the thread, and remembers the answer. Returns the check result, or None when nothing was run. Never raises."""
    try:
        if agent.dry or mode(agent) == "off" or not info:
            return None
        check = find(agent, ticket_text(info))
        if not check:
            if not info.get("no_check_said"):
                with agent.state.lock:
                    info["no_check_said"] = True; agent.state.save()
                _post(agent, key, f"No check in Settings (bug_checks) matches {key}, so its fix cannot be verified automatically. It is marked fixed by a person, not verified.", say)
            return None
        res = run(agent, check)
        name = AT.clean(str(check["name"]), 80)
        with agent.state.lock:
            info["verified"] = {"at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "ok": bool(res["ok"]), "check": name}; agent.state.save()
        second = f"Verified by check {name}: passed ({res['detail']})." if res["ok"] else f"Check {name} FAILED ({res['detail']}): the ticket is NOT verified. Reply reopen to reopen it."
        try:
            agent.atlassian.comment(key, [("p", fixed_fact(info)), ("p", second)])
        except Exception as e:  # noqa: BLE001
            agent.record("bug_verify", "jira_comment", "failed", ticket=key, error=str(e)[:160])
        _post(agent, key, f"{key}: {fixed_fact(info)}\n{second}", say)
        agent.record("bug_verify", "check", "sent", ticket=key, passed=bool(res["ok"]), http_status=res["status"])
        if res["ok"]:
            res["told"] = agent._tell_reporters(key, info) if tell_after_verify(agent) else 0
            if res["told"]:
                _post(agent, key, f"Told {res['told']} customer{'s' if res['told'] != 1 else ''} who reported it that it is fixed.", say)
        elif mode(agent) == "auto_reopen":
            _reopen_after_failure(agent, key, info, say)
        return res
    except Exception as e:  # noqa: BLE001 - a check that breaks must never undo a closed ticket
        agent.state.log(workflow="bug_verify", status="error", error=type(e).__name__ + ": " + str(e)[:160]); return None


def _reopen_after_failure(agent, key, info, say):
    """A failed check with bug_verify = auto_reopen: the same rule as every other reopen. bug_close = auto reopens at once; otherwise it asks and waits for approve."""
    if bugdesk.mode(agent) == "off":
        return
    moves = agent.atlassian.transitions(key); tr = bugdesk._pick(moves, "reopen")
    if not tr:
        return
    chan, ts = _thread_of(agent, key)
    item = {"intent": "reopen", "tid": tr["id"], "to": tr["to"], "note": "The fix check failed.", "channel": chan, "thread": ts, "at": time.time()}
    if bugdesk.mode(agent) == "auto":
        bugdesk._apply(agent, key, item, info, lambda t: _post(agent, key, t, say)); return
    with agent.state.lock:
        agent.state.data.setdefault("bug_pending", {})[key] = item; agent.state.save()
    _post(agent, key, f"Reopen {key} (move it to {tr['to']})? Reply approve to do it, or keep it as it is.", say)
