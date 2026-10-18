"""Missing phrases go to Speakvora, so every bundle gets better. When a workflow needs a spoken line the pack does not have, the agent can send Speakvora the request itself: the moment, an example sentence, the industry, the language and the pack name.
Nothing else is sent: no customer data, no messages, no keys. The phrase bot writes, checks and voices the line and adds it to the next version of every pack of that industry and language, which the buyer downloads while their 12-month licence is active.
Automatic sending is opt-in (the dashboard asks once); a request the person types themselves is always sent. Also checks whether a newer version of this pack exists (public information, nothing sent)."""
import json, os, time

from . import secrets_store as SS, slots as SL, web

DAY = 20 * 3600


def host():
    return os.environ.get("SPEAKVORA_HOST", "https://speakvora.com").rstrip("/")


def enabled(agent):
    return agent.state.data.get("share_phrases")                     # True, False, or None = not asked yet


def set_enabled(agent, on):
    agent.state.data["share_phrases"] = bool(on)
    with agent.state.lock:
        agent.state.save()
    return bool(on)


def _wf_names(agent):
    return json.load(open(agent.cfg["workflows"], encoding="utf-8")) if agent.cfg.get("workflows") else {}


def gaps(agent):
    """Lines the workflows use that the pack cannot say yet."""
    reg = SL.registry(agent.profile); want = SL.needed_by(_wf_names(agent))
    return [{"slot": k, **reg[k]} for k in sorted(want) if k in reg and k not in agent.pack.slots]


def requested(agent):
    return dict(agent.state.data.get("requested") or {})


def pending(agent):
    done = requested(agent)
    return [g for g in gaps(agent) if g["slot"] not in done]


def _key(agent=None):
    """Your Speakvora API key: the SPEAKVORA_KEY environment variable, or the one typed into the dashboard (Connect, Speakvora agent)."""
    v = os.environ.get("SPEAKVORA_KEY") or ""
    if not v and agent is not None:
        v = str(((agent.cfg.get("speakvora") or {}).get("api_key")) or "")
        if v.startswith("env:") or "YOUR-" in v:
            v = ""
    return v


def _log(agent, slots, sent, text=""):
    p = os.path.join(agent.state.dir, "phrase-requests.json")
    try:
        log = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        log = []
    log.append({"t": int(agent.now()), "slots": slots, "sent": sent, "text": text})
    json.dump(log[-100:], open(p, "w", encoding="utf-8"))


def submit(agent, picked, text=""):
    """Sends the chosen lines to Speakvora. picked: [{'slot','intent','example'}]. Returns {'sent': bool, 'message': str}."""
    path = os.path.join(agent.state.dir, "slot-requests.json"); doc = SL.request_file(agent.pack, agent.profile, picked, path)
    slots = [p["slot"] for p in picked]
    try:
        h = {"x-api-key": _key(agent)} if _key(agent) else {}
        _st, r = web.request("POST", host() + "/api/v1/packs/slot-requests", {**h, "content-type": "application/json"}, body=doc, timeout=20)
        for s in slots:
            agent.state.data.setdefault("requested", {})[s] = int(agent.now())
        with agent.state.lock:
            agent.state.save()
        _log(agent, slots, True, text)
        return {"sent": True, "message": (r or {}).get("note") or "Sent to Speakvora. The lines arrive in the next version of your bundle."}
    except Exception as e:  # noqa: BLE001
        _log(agent, slots, False, text)
        why = "No internet connection right now." if isinstance(e, web.NetworkDown) else "Speakvora could not take it just now."
        return {"sent": False, "message": why + " It is saved and will be sent again later."}


def auto(agent):
    """Called about once a minute from tick(): when the person agreed, send lines that are missing and not asked for yet, at most once a day. Never raises."""
    try:
        if enabled(agent) is not True or agent.now() - float(agent.state.data.get("share_last", 0)) < DAY:
            return None
        todo = pending(agent)
        if not todo:
            return None
        agent.state.data["share_last"] = agent.now()
        return submit(agent, todo[:60])
    except Exception as e:  # noqa: BLE001
        agent.state.log(workflow="sharing", status="error", error=str(e)[:200]); return None


def update_info(agent, force=False):
    """Is there a newer version of THIS pack? Reads Speakvora's public pack list (nothing is sent). Returns {'current','latest','available','phrases'} or None."""
    cur = agent.pack.meta.get("version"); pid = agent.pack.meta.get("pack")
    cache = agent.state.data.get("update") or {}
    if not force and cache and agent.now() - cache.get("at", 0) < 12 * 3600:
        return cache.get("info")
    try:
        _st, r = web.request("GET", host() + "/api/v1/packs", timeout=15)
        p = next((x for x in (r.get("packs") if isinstance(r, dict) else r) or [] if x.get("id") == pid), None)
        info = None
        if p:
            info = {"current": cur, "latest": p.get("version"), "phrases": p.get("phrases"), "available": bool(cur and p.get("version") and str(p["version"]) > str(cur))}
        agent.state.data["update"] = {"at": agent.now(), "info": info}
        with agent.state.lock:
            agent.state.save()
        return info
    except Exception:  # noqa: BLE001
        return cache.get("info")
