"""Release awareness: what changed on your app, and when. Deploys, releases and merged merge or pull requests from GitLab and GitHub are remembered (kept on this computer),
so a new bug can say "the newest production deploy before the first report was v2.4.1, 35 minutes earlier". It is timing only: a hint for the team, never a diagnosis.
Settings (agent.json "changes"): window_hours (default 48), environments (default production, prod, live; a deploy with no environment name counts), enabled (default true)."""
import time

KINDS = {"deploy.succeeded": "deploy", "release.published": "release", "pull_request.merged": "merge"}
PROD = ("production", "prod", "live")
MAX = 200


def _cfg(agent):
    c = agent.cfg.get("changes") or {}
    return {"enabled": c.get("enabled", True), "window": float(c.get("window_hours", 48)) * 3600, "envs": [str(x).lower() for x in c.get("environments", PROD)]}


def record(agent, name, ev, now=None):
    """Remembers one change event (called for every event the agent receives). Never raises."""
    try:
        kind = KINDS.get(name)
        if not kind or not _cfg(agent)["enabled"]:
            return False
        e = {"t": float(now or time.time()), "kind": kind, "repo": str(ev.get("repo") or ""), "env": str(ev.get("environment") or ""), "ref": str(ev.get("branch") or ""),
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


def latest(agent, when=None):
    """The change a bug that happened at `when` most likely follows: the newest production deploy or release inside the window, else the newest merge. None when there is none."""
    c = _cfg(agent); now = float(when or time.time()); lst = [x for x in (agent.state.data.get("changes") or []) if 0 <= now - x["t"] <= c["window"]]
    live = [x for x in lst if x["kind"] == "release" or (x["kind"] == "deploy" and (not x["env"] or x["env"].lower() in c["envs"]))]
    pick = max(live, key=lambda x: x["t"], default=None)
    if pick:
        return pick
    merges = [x for x in lst if x["kind"] == "merge"]
    return max(merges, key=lambda x: x["t"], default=None)


def line(agent, when=None):
    """One sentence for the ticket and the team message, or ''."""
    when = float(when or time.time()); e = latest(agent, when)
    if not e:
        return ""
    gap = _ago(when - e["t"])
    tail = " It was merged but not seen deployed." if e["kind"] == "merge" else ""
    return f"Timing only, not a diagnosis: the newest change before this report was a {_what(e)}, {gap} earlier.{tail}"


def newer_than(agent, t, when=None):
    """A change that arrived after time `t` (the ticket's first report) and before `when`: the one to mention on a repeat report."""
    when = float(when or time.time()); e = latest(agent, when)
    return e if e and e["t"] > float(t) else None
