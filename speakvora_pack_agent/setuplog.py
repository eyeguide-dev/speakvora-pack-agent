"""A plain-words record of every setup step, so a first customer's setup problems can be fixed fast. Written on this computer only (agent-state/setup-log.jsonl); nothing is sent anywhere unless the owner presses
'Email it to Speakvora support' or downloads the report and sends it. It never holds keys, tokens, passwords, message words or whole phone numbers: secrets are dropped and numbers keep their last four digits."""
import json, os, platform, re, sys, time

from . import __version__

SECRET_KEY = re.compile(r"token|secret|password|passwd|key|authorization|cookie|signature", re.I)
PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
TOKENISH = re.compile(r"\b[A-Za-z0-9_\-]{28,}\b")


def clean(v, depth=0):
    if isinstance(v, dict):
        return {k: ("***" if SECRET_KEY.search(str(k)) and not isinstance(v[k], (bool, int, float)) else clean(x, depth + 1)) for k, x in v.items()} if depth < 4 else "..."
    if isinstance(v, (list, tuple)):
        return [clean(x, depth + 1) for x in list(v)[:20]]
    if isinstance(v, str):
        s = TOKENISH.sub("***", v); s = PHONE.sub(lambda m: "*" * max(len(re.sub(r"\D", "", m.group())) - 4, 0) + re.sub(r"\D", "", m.group())[-4:], s)
        return s[:300]
    return v


def _path(agent):
    return os.path.join(agent.state.dir, "setup-log.jsonl")


def record(agent, kind, **kw):
    """Appends one event. Never raises: logging must not break setup."""
    try:
        line = json.dumps({"t": int(time.time()), "v": __version__, "kind": kind, **clean(kw)}, ensure_ascii=False)
        p = _path(agent)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if os.path.getsize(p) > 400_000:                                         # keep the newest half
            keep = open(p, encoding="utf-8").read().splitlines()[-1500:]
            open(p, "w", encoding="utf-8").write("\n".join(keep) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _tail(path, n):
    try:
        return open(path, encoding="utf-8", errors="replace").read().splitlines()[-n:]
    except OSError:
        return []


def report(agent):
    """The support report: versions, what is connected and tested, the setup steps and the recent problems. Safe to send."""
    from . import connect as SU
    lines = [f"Speakvora agent support report, {time.strftime('%Y-%m-%d %H:%M %Z')}", f"agent {__version__} | python {sys.version.split()[0]} | {platform.platform()}", ""]
    try:
        base = str(agent.cfg.get("public_base_url", ""))
        lines += ["public address: " + (re.sub(r"^(https?://)([^/]+).*$", r"\1\2", base) or "none"), "practice mode: " + ("yes" if agent.dry else "no (live)"), ""]
        st = SU.status(agent)
        lines.append("Connections:")
        for c in st["cards"]:
            if c.get("connected") or c.get("tested"):
                lines.append(f"  {c['name']}: connected={c['connected']} tested={'yes' if c.get('tested') else 'no'}")
        lines += ["", "What the agent can do:"] + [f"  {c['label']}: {'ready via ' + c['via'] if c['ready'] else 'NOT ready (' + c['fix'] + ')'}" for c in st.get("capabilities", [])]
        lines += ["", "Go-live checks:"] + [f"  [{'x' if c['ok'] else ' '}] {c['text']}" for c in st["readiness"]["checks"]]
    except Exception as e:  # noqa: BLE001
        lines.append(f"(could not read the setup: {type(e).__name__})")
    lines += ["", "Setup steps (newest last):"]
    for ln in _tail(_path(agent), 120):
        try:
            d = json.loads(ln); lines.append("  " + time.strftime("%m-%d %H:%M:%S", time.localtime(d.pop("t", 0))) + " " + d.pop("kind", "") + " " + json.dumps({k: v for k, v in d.items() if k != "v"}, ensure_ascii=False))
        except ValueError:
            continue
    lines += ["", "Recent problems and message handling (words of messages are never recorded):"]
    keep = ("error", "rejected", "blocked", "fallback", "no_voice", "call_start", "call_end", "digit", "transfer", "received")
    for ln in _tail(os.path.join(agent.state.dir, "agent.log.jsonl"), 400)[-150:]:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if d.get("status") in keep or d.get("error"):
            d = {k: v for k, v in d.items() if k not in ("text", "body")}; t = d.pop("t", 0)
            lines.append("  " + time.strftime("%m-%d %H:%M:%S", time.localtime(t)) + " " + json.dumps(clean(d), ensure_ascii=False))
    return "\n".join(lines) + "\n"
