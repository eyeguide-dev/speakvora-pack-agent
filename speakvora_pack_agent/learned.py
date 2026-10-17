"""Phrases your AI keeps saying become library lines, so they are instant and free from then on.
When your connected AI writes the same customer-facing line again and again (text or email you approved), the agent counts it. At the repeat count you chose (default 3) it becomes a candidate. Voicing it ONCE through your Speakvora key (speak API, billed once, in the pack's own voice) saves the audio on this computer
(agent-state/learned/) and adds it to your library as a line any workflow can play, the same as the lines that came with your bundle. After that, saying it costs nothing and needs no internet.
Only generic lines qualify: anything with digits, emails, links or a person's name is skipped, because it would not repeat and may hold customer data. Nothing is sent to Speakvora except the line to voice. Adding is by your button, or automatically if you switch that on, inside a monthly character budget you set (fixed ceiling in guardrails.py)."""
import hashlib, json, os, re, time, urllib.request

from . import reasoner as R, sharing

FILE = "learned_phrases.json"
BAD = re.compile(r"(?i:\d|@|https?:|www\.|\{\{)|[A-Z][a-z]+ [A-Z][a-z]+")
DAY = 86400


def _path(agent):
    return os.path.join(agent.state.dir, FILE)


def load(agent):
    try:
        return json.load(open(_path(agent), encoding="utf-8"))
    except (OSError, ValueError):
        return {"counts": {}, "items": [], "spent": {}}


def save(agent, d):
    os.makedirs(agent.state.dir, exist_ok=True)
    tmp = _path(agent) + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, _path(agent))


def norm(text):
    return re.sub(r"[^\w ]+", "", re.sub(r"\s+", " ", str(text or "").lower())).strip()


def eligible(text):
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return 20 <= len(t) <= 220 and not BAD.search(t) and R.redact(t, None) == t


def _settings(agent):
    from . import guardrails as G
    return {**G.DEFAULTS, **(agent.cfg.get("guardrails") or {})}


def attach(agent):
    """Adds the learned lines to the pack so workflows can play them by id (learned:<hash>) or search."""
    for it in load(agent)["items"]:
        if os.path.exists(it["file"]) and it["id"] not in agent.pack.by_id:
            agent.pack._add({"id": it["id"], "text": it["text"], "file": it["file"], "category": "learned_phrases"})
            agent.pack.slots.setdefault("learned_" + it["id"].split(":")[1][:8], it["id"])


def observe(agent, text):
    """Called when an AI-written customer line was approved and sent. Returns True when it just became a candidate."""
    if not eligible(text):
        return False
    d, k = load(agent), norm(text)
    if any(norm(i["text"]) == k for i in d["items"]):
        return False
    c = d["counts"].setdefault(k, {"text": re.sub(r"\s+", " ", text).strip(), "count": 0, "first": int(agent.now())})
    c["count"] += 1; c["last"] = int(agent.now())
    if len(d["counts"]) > 300:                                             # keep the most recent 300 lines only
        for old in sorted(d["counts"], key=lambda x: d["counts"][x].get("last", 0))[:-300]:
            d["counts"].pop(old)
    save(agent, d)
    return c["count"] == _settings(agent)["learn_after"]


def candidates(agent):
    d, n = load(agent), _settings(agent)["learn_after"]
    out = [{"id": hashlib.sha1(k.encode()).hexdigest()[:12], "text": c["text"], "count": c["count"]} for k, c in d["counts"].items() if c["count"] >= n]
    return sorted(out, key=lambda x: -x["count"])[:30]


def month_key(agent):
    return time.strftime("%Y-%m", time.gmtime(agent.now()))


def budget(agent):
    s, d = _settings(agent), load(agent)
    used = int((d.get("spent") or {}).get(month_key(agent), 0))
    return {"month_chars": s["phrase_chars_per_month"], "used": used, "left": max(0, s["phrase_chars_per_month"] - used)}


def _voice(agent, text):
    """Voices one line through the owner's Speakvora key. Returns audio bytes and the file extension."""
    key = sharing._key()
    if not key:
        raise ValueError("Add your Speakvora API key (SPEAKVORA_KEY) so the agent can voice new lines.")
    voice = agent.pack.meta.get("voice")
    if not voice:
        raise ValueError("This bundle does not name a voice.")
    st, r = sharing.web.request("POST", sharing.host() + "/api/v1/speak", {"x-api-key": key}, body={"text": text, "voice": voice, "lang": agent.pack.language}, timeout=60)
    url = (r or {}).get("url")
    if not url:
        raise ValueError("Speakvora did not return audio for that line.")
    with urllib.request.urlopen(url, timeout=60) as x:
        data = x.read(5_000_000)
    return data, (".mp3" if str((r or {}).get("format")) == "mp3" or url.endswith(".mp3") else ".m4a")


def _store(agent, text, source, auto=False):
    """Voices one line once, saves it, adds it to the library. Raises ValueError when it does not fit the monthly budget."""
    d = load(agent); k = norm(text)
    if any(norm(i["text"]) == k for i in d["items"]):
        raise ValueError("That line is already in your library.")
    b = budget(agent)
    if len(text) > b["left"]:
        raise ValueError(f"This month's budget for new lines ({b['month_chars']} characters) is used up. Raise it in Settings, or add the line next month.")
    data, ext = _voice(agent, text)
    cid = hashlib.sha1(k.encode()).hexdigest()[:12]
    os.makedirs(os.path.join(agent.state.dir, "learned"), exist_ok=True)
    f = os.path.join(agent.state.dir, "learned", cid + ext); open(f, "wb").write(data)
    d = load(agent)
    d["items"].append({"id": "learned:" + cid, "text": text, "file": f, "added": int(agent.now()), "auto": bool(auto), "source": source})
    d["counts"].pop(k, None); (d.get("suggested") or {}).pop(cid, None)
    d.setdefault("spent", {})[month_key(agent)] = int((d.get("spent") or {}).get(month_key(agent), 0)) + len(text)
    save(agent, d); attach(agent)
    agent.state.log(workflow="learned", action="add", status="done", dry_run=False, chars=len(text), auto=bool(auto), source=source)
    return {"id": "learned:" + cid, "text": text}


def add(agent, cid, auto=False):
    """Adds a candidate (repeated by your AI) or a suggestion (written by your AI from your lines)."""
    d = load(agent)
    cand = next((c for c in candidates(agent) if c["id"] == cid), None)
    if cand:
        return _store(agent, cand["text"], "repeated", auto)
    sug = (d.get("suggested") or {}).get(cid)
    if not sug:
        raise ValueError("That line is not on the list any more.")
    return _store(agent, sug, "suggested", False)


USER_BAD = re.compile(r"(?i:@|https?:|www\.|\{\{)")


def add_lines(agent, text):
    """The box: one phrase per line. Each line becomes a library line. Returns {'added': [...], 'skipped': [{'line', 'reason'}]}. Stops at the budget."""
    lines = [re.sub(r"\s+", " ", l).strip() for l in str(text or "").splitlines() if l.strip()]
    if not lines:
        raise ValueError("Type or paste your phrases, one on each line.")
    if len(lines) > 30:
        raise ValueError("Add up to 30 lines at a time.")
    out = {"added": [], "skipped": []}
    for l in lines:
        why = "too short (at least 8 characters)" if len(l) < 8 else "too long (up to 220 characters)" if len(l) > 220 else "no emails, links or placeholders" if USER_BAD.search(l) else "looks like it holds a card or personal number" if R.redact(l, None) != l else ""
        if why:
            out["skipped"].append({"line": l, "reason": why}); continue
        try:
            out["added"].append(_store(agent, l, "typed"))
        except ValueError as e:
            out["skipped"].append({"line": l, "reason": str(e)})
            if "budget" in str(e):
                break
    return out


SUGGEST_SYSTEM = ("You help a small business build its library of spoken phrases. From the example phrases and the business profile, write NEW short phrases the business is likely to say to customers, in the same voice and language. "
                  'Reply with ONE JSON object only: {"lines": ["..."]}. Up to 10 lines, each 20 to 160 characters, generic (no names, no numbers, no prices, no times, no contact details), nothing that repeats the examples, no medical, legal or financial advice, no promises of refunds.')


def suggest(agent, text):
    """Asks the owner's connected AI for more lines like the typed ones. Nothing is added or voiced: they wait as suggestions for the owner to add."""
    from . import brain
    if not brain.configured(agent):
        raise ValueError("Connect your AI first (Connect tab) so it can suggest more lines.")
    ex = [re.sub(r"\s+", " ", l).strip() for l in str(text or "").splitlines() if l.strip()][:20] or [i["text"] for i in load(agent)["items"]][:20]
    if not ex:
        raise ValueError("Type a few example lines first.")
    raw, _u = R._chat(agent.cfg["reasoner"], SUGGEST_SYSTEM, R.redact(brain.for_prompt(agent) + "Examples:\n" + "\n".join(ex), None), 900)
    m = re.search(r"\{.*\}", raw or "", re.S)
    lines = json.loads(m.group(0)).get("lines", []) if m else []
    d = load(agent); have = {norm(i["text"]) for i in d["items"]} | {norm(x) for x in ex}; sug = d.setdefault("suggested", {})
    for l in lines[:10]:
        l = re.sub(r"\s+", " ", str(l)).strip()
        if eligible(l) and norm(l) not in have:
            sug[hashlib.sha1(norm(l).encode()).hexdigest()[:12]] = l
    d["suggested"] = dict(list(sug.items())[-30:]); save(agent, d)
    return view(agent)


def dismiss(agent, cid):
    d = load(agent); (d.get("suggested") or {}).pop(cid, None); d["counts"].pop(next((k for k in d["counts"] if hashlib.sha1(k.encode()).hexdigest()[:12] == cid), ""), None); save(agent, d)
    return view(agent)


def remove(agent, lid):
    d = load(agent)
    for it in list(d["items"]):
        if it["id"] == lid:
            try:
                os.remove(it["file"])
            except OSError:
                pass
            d["items"].remove(it)
    save(agent, d); agent.pack.by_id.pop(lid, None); agent.pack.items = [i for i in agent.pack.items if i["id"] != lid]
    for s in [s for s, v in agent.pack.slots.items() if v == lid]:
        agent.pack.slots.pop(s)
    return view(agent)


def view(agent):
    s = _settings(agent)
    return {"candidates": candidates(agent), "suggested": [{"id": k, "text": v} for k, v in (load(agent).get("suggested") or {}).items()], "items": [{"id": i["id"], "text": i["text"], "auto": i.get("auto", False)} for i in load(agent)["items"]], "budget": budget(agent), "auto": bool(s["auto_learn_phrases"]), "learn_after": s["learn_after"], "has_key": bool(sharing._key())}


def auto(agent):
    """Once a minute from tick(): when switched on, voice candidates inside the budget, at most 3 a day. Never raises."""
    try:
        if not _settings(agent)["auto_learn_phrases"]:
            return
        d = load(agent)
        today = [i for i in d["items"] if i.get("auto") and agent.now() - i["added"] < DAY]
        if len(today) >= 3 or not sharing._key():
            return
        for c in candidates(agent):
            if len(c["text"]) <= budget(agent)["left"]:
                add(agent, c["id"], auto=True); return
    except Exception as e:  # noqa: BLE001
        agent.state.log(workflow="learned", status="error", error=str(e)[:200], dry_run=False)
