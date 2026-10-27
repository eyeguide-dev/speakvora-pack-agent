"""Release awareness: what changed on your app, and when. Deploys, releases and merged merge or pull requests from GitLab and GitHub are remembered (kept on this computer),
so a new bug can say "the newest production deploy before the first report was v2.4.1, 35 minutes earlier". It is timing only: a hint for the team, never a diagnosis.
Settings (agent.json "changes"): window_hours (default 48), environments (default production, prod, live; a deploy with no environment name counts), enabled (default true)."""
import datetime as _dt, re, time

KINDS = {"deploy.succeeded": "deploy", "release.published": "release", "pull_request.merged": "merge"}
PROD = ("production", "prod", "live")
MAX = 200


def _cfg(agent):
    c = agent.cfg.get("changes") or {}
    return {"enabled": c.get("enabled", True), "window": float(c.get("window_hours", 48)) * 3600, "envs": [str(x).lower() for x in c.get("environments", PROD)],
            "map": {str(k).lower(): str(v).lower() for k, v in (c.get("map") or {}).items() if k and v}}


def parse_time(v):
    """A deploy's own time from the payload (ISO 8601, 'YYYY-MM-DD HH:MM:SS +0200', 'YYYY-MM-DD HH:MM:SS UTC' or epoch seconds) -> epoch seconds, or None when it is missing, unreadable, in the future or older than 60 days."""
    if v in (None, ""):
        return None
    try:
        if isinstance(v, (int, float)) or re.fullmatch(r"\d{9,11}(\.\d+)?", str(v).strip()):
            t = float(v)
        else:
            x = str(v).strip().replace("UTC", "+0000").replace("Z", "+0000")
            x = re.sub(r"([+-]\d\d):(\d\d)$", r"\1\2", x)
            t = None
            for f in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S.%f %z", "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S%z"):
                try:
                    t = _dt.datetime.strptime(x, f).timestamp(); break
                except ValueError:
                    continue
            if t is None:
                return None
    except (ValueError, OverflowError):
        return None
    now = time.time()
    return t if now - 60 * 86400 <= t <= now + 300 else None


def record(agent, name, ev, now=None):
    """Remembers one change event (called for every event the agent receives). Never raises."""
    try:
        kind = KINDS.get(name)
        if not kind or not _cfg(agent)["enabled"]:
            return False
        got = parse_time(ev.get("time") or ev.get("deployed_at"))                         # the deploy's own time, not the time this computer heard about it (a delayed or retried delivery must not move it)
        e = {"t": float(now or got or time.time()), "received": time.time(), "kind": kind, "repo": str(ev.get("repo") or ""), "env": str(ev.get("environment") or ""), "ref": str(ev.get("branch") or ""),
             "sha": str(ev.get("sha") or "")[:8], "title": " ".join(str(ev.get("title") or (ev.get("release") or {}).get("name") or "").split())[:140], "url": str(ev.get("url") or "")[:300], "by": str(ev.get("author") or "")[:60]}
        with agent.state.lock:
            lst = agent.state.data.setdefault("changes", [])
            if any(x.get("kind") == kind and x.get("sha") and x.get("sha") == e["sha"] and x.get("env") == e["env"] and x.get("repo") == e["repo"] and abs(x["t"] - e["t"]) < 600 for x in lst):
                return False                                  # the same deploy reported twice
            lst.append(e); del lst[:-MAX]; agent.state.save()
        return True
    except Exception as ex:  # noqa: BLE001 - a bad payload must never stop an event
        agent.state.log(workflow="changes", status="error", error=type(ex).__name__ + ": " + str(ex)[:140]); return False


def _ago(sec):
    m = max(0, int(sec // 60))
    return "less than a minute" if m < 1 else (f"{m} minute{'s' if m != 1 else ''}" if m < 90 else (f"{round(m / 60)} hours" if m < 2880 else f"{round(m / 1440)} days"))


def _what(e):
    kind = {"deploy": "deploy", "release": "release", "merge": "merge"}[e["kind"]]
    bits = [kind, (e["title"] or e["sha"] or e["ref"] or "").strip()]
    if e["env"] and e["kind"] == "deploy":
        bits.append("to " + e["env"])
    if e["sha"] and e["title"]:
        bits.append("(" + e["sha"] + ")")
    if e["by"]:
        bits.append("by " + e["by"])
    return " ".join(b for b in bits if b)


def _blob(hint):
    return " ".join(str(hint.get(k) or "") for k in ("text", "page", "action", "url", "service")).lower() if hint else ""


def pick(agent, when=None, hint=None):
    """(event, note). The change a bug that happened at `when` most likely follows. Order of trust: a report that names the version or commit it came from matches that deploy exactly; a page or app the owner mapped
    to a repository or service (agent.json changes.map) only sees that repository's deploys; with no mapping, several repositories deploying in the window is ambiguous and NO change is named (a deploy of
    something unrelated beside a bug would be wrong); a single repository is taken as before. The note explains an ambiguous or unmapped case so the team knows why nothing is named."""
    c = _cfg(agent); now = float(when or time.time()); lst = [x for x in (agent.state.data.get("changes") or []) if 0 <= now - x["t"] <= c["window"]]
    live = [x for x in lst if x["kind"] == "release" or (x["kind"] == "deploy" and (not x["env"] or x["env"].lower() in c["envs"]))]
    pool = live or [x for x in lst if x["kind"] == "merge"]
    if not pool:
        return None, ""
    ver, sha = str((hint or {}).get("version") or "").strip().lower(), str((hint or {}).get("sha") or "").strip().lower()
    if ver or sha:
        for x in sorted(pool, key=lambda x: -x["t"]):
            if (sha and x.get("sha") and sha[:8] == x["sha"][:8].lower()) or (ver and (ver in str(x.get("title") or "").lower() or ver in str(x.get("ref") or "").lower())):
                return x, ""
    blob = _blob(hint)
    if c["map"]:
        hit = [v for k, v in c["map"].items() if k in blob]
        if not hit:
            return None, "No deploy is named because this report does not match any page or app mapped in Settings (changes.map)."
        pool = [x for x in pool if any(h in (str(x.get("repo") or "") + " " + str(x.get("title") or "")).lower() for h in hit)]
        if not pool:
            return None, "No recent deploy of the mapped service (" + ", ".join(sorted(set(hit))) + ") before this report."
    else:
        repos = sorted({str(x.get("repo") or "") for x in pool if x.get("repo")})
        if len(repos) > 1:
            return None, "Several services deployed recently (" + ", ".join(repos[:4]) + "), so no single change is named. Map this page to its service in Settings (changes.map) to match them."
    return max(pool, key=lambda x: x["t"]), ""


def latest(agent, when=None, hint=None):
    return pick(agent, when, hint)[0]


def line(agent, when=None, hint=None):
    """One sentence for the ticket and the team message, or ''."""
    when = float(when or time.time()); e, note = pick(agent, when, hint)
    if not e:
        return note
    gap = _ago(when - e["t"])
    tail = " It was merged but not seen deployed." if e["kind"] == "merge" else ""
    exact = " This report names that version." if hint and (hint.get("version") or hint.get("sha")) and ((hint.get("sha") and str(hint["sha"])[:8].lower() == str(e.get("sha") or "")[:8].lower()) or (hint.get("version") and str(hint["version"]).lower() in (str(e.get("title") or "") + str(e.get("ref") or "")).lower())) else ""
    return f"Timing only, not a diagnosis: the newest change before this report was a {_what(e)}, {gap} earlier.{exact}{tail}"


def newer_than(agent, t, when=None, hint=None):
    """A change that arrived after time `t` (the ticket's first report) and before `when`: the one to mention on a repeat report."""
    when = float(when or time.time()); e = latest(agent, when, hint)
    return e if e and e["t"] > float(t) else None


def previous(agent, event):
    """The deploy of the same repository (and environment) just before `event`, or None. The code host is asked what changed between the two (see investigate.py)."""
    if not event:
        return None
    same = [x for x in (agent.state.data.get("changes") or [])
            if x.get("kind") == event.get("kind") and x.get("repo") == event.get("repo") and (x.get("env") or "").lower() == (event.get("env") or "").lower()
            and x.get("sha") and x.get("sha") != event.get("sha") and x["t"] < event["t"]]
    return max(same, key=lambda x: x["t"]) if same else None
