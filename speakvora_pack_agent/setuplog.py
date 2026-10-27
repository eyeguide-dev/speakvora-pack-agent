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


# ---- how long setup took: pure functions over the log (no network, nothing sent anywhere)
MILESTONES = (("business", "business details saved"), ("connection", "first connection saved"), ("test_passed", "first test passed"), ("workflow_on", "first workflow switched on"),
              ("first_message", "first real message or call handled"), ("live", "went live"))


def read_events(agent):
    """Every readable event of the setup log as dicts with an integer 't', oldest first. Missing file and corrupt lines are skipped."""
    out = []
    try:
        lines = open(_path(agent), encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return out
    for ln in lines:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("t"), (int, float)) and not isinstance(d.get("t"), bool) and d["t"] > 0:
            d["t"] = int(d["t"]); out.append(d)
    out.sort(key=lambda d: d["t"])
    return out


def _milestone(d):
    """Which milestone, if any, one event reaches."""
    k, ok = d.get("kind"), d.get("ok", True) is not False
    if k == "save" and ok:
        return "business" if d.get("card") == "business" else "connection"
    if k == "channel_connect" and ok:
        return "connection"
    if k == "test" and d.get("ok") is True:
        return "test_passed"
    if k == "workflow_on":
        return "workflow_on"
    if k == "first_message":
        return "first_message"
    if k == "go_live" and d.get("on") is True:
        return "live"
    return None


def timeline_of(events, now=None):
    """The setup timeline from a list of events. None when there are no events. Seconds are counted from the first event."""
    ev = [e for e in events if isinstance(e, dict) and isinstance(e.get("t"), int)]
    if not ev:
        return None
    ev.sort(key=lambda d: d["t"]); t0 = ev[0]["t"]; at = {}
    for e in ev:
        m = _milestone(e)
        if m and m not in at:
            at[m] = e["t"] - t0
    steps, prev = [], 0
    for key, label in MILESTONES:
        if key in at:
            steps.append({"id": key, "label": label, "at_seconds": at[key], "took_seconds": max(at[key] - prev, 0)}); prev = max(prev, at[key])
    wins = [at[k] for k in ("test_passed", "first_message") if k in at]
    first_win = min(wins) if wins else None
    last = ev[-1]; idle = None if now is None else max(int(now) - last["t"], 0)
    done = "live" in at
    out = {"first_event_t": t0, "events": len(ev), "milestones": dict(at), "steps": steps, "minutes_to_first_success": None if first_win is None else round(first_win / 60, 1),
           "finished": done, "total_seconds": last["t"] - t0}
    out["stopped"] = None if done else {"after": last.get("kind", ""), "card": last.get("card", ""), "idle_seconds": idle, "last_event_t": last["t"], "next_step": next((lb for k, lb in MILESTONES if k not in at), "")}
    return out


def timeline(agent, now=None):
    """The timeline of this agent's setup log (None before anything was recorded). Never raises."""
    try:
        return timeline_of(read_events(agent), time.time() if now is None else now)
    except Exception:  # noqa: BLE001
        return None


def _dur(sec):
    sec = int(sec or 0)
    return f"{sec}s" if sec < 90 else f"{round(sec / 60)} min" if sec < 5400 else f"{sec / 3600:.1f} h"


def timeline_lines(tl):
    """Plain lines for the support report."""
    if not tl:
        return ["  no setup steps recorded yet"]
    out = [f"  first step recorded: {time.strftime('%Y-%m-%d %H:%M', time.localtime(tl['first_event_t']))}"]
    m = tl["minutes_to_first_success"]
    out.append("  minutes from first step to first success: " + ("not yet" if m is None else str(m)))
    out += [f"  {s['label']}: after {_dur(s['at_seconds'])} (this step took {_dur(s['took_seconds'])})" for s in tl["steps"]]
    st = tl.get("stopped")
    if st:
        out.append(f"  not live yet; last step '{st['after']}{' ' + st['card'] if st['card'] else ''}'" + (f", {_dur(st['idle_seconds'])} ago" if st["idle_seconds"] is not None else "") + (f"; next: {st['next_step']}" if st["next_step"] else ""))
    return out


def set_up_text(tl):
    """'Set up in N minutes' for the Home screen, or '' when there is no first success yet."""
    m = tl and tl.get("minutes_to_first_success")
    if m is None:
        return ""
    return "Set up in under a minute" if m < 1 else "Set up in %d minute%s" % (round(m), "" if round(m) == 1 else "s")


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
    lines += ["", "Setup timing:"] + timeline_lines(timeline(agent)) + ["", "Setup steps (newest last):"]
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
