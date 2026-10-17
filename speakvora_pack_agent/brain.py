"""The business brain: when the owner connects their own AI, the agent learns the business right away and keeps what it learned as a small, editable profile on this computer (agent-state/business_profile.json).
What it reads, and nothing else: the business name and facts you typed, your bundle's industry, the names of your workflows, the titles of upcoming calendar events (digits removed), any website address and notes you choose to give it.
It never reads customer names, phone numbers, messages or payment details. Everything goes to YOUR AI provider with emails, phone numbers and card-like numbers replaced first, and nothing goes to Speakvora.
The profile starts as 'needs review'. Only after the owner approves it does the agent use it: today to inform AI suggestions; the same profile is what live conversations will answer from."""
import json, os, re, threading, time
from urllib.parse import urlparse

from . import reasoner as R, recipes, web

FILE = "business_profile.json"
SYSTEM = ("You are helping a small business set up its automated assistant. From the facts and notes you are given, write a short business profile as ONE JSON object and nothing else: "
          '{"summary": "2 sentences", "tone": "how the business talks, a few words", "hours": "opening hours if stated, else empty", "services": ["what they offer"], "policies": ["rules customers should know, only if stated"], '
          '"faqs": [{"q": "question a customer would ask", "a": "answer taken ONLY from the facts"}], "unknowns": ["things a customer is likely to ask that the facts do not answer"]}. '
          "Use only what is in the input. Never invent prices, hours, addresses, names or policies; if something is not stated, put it in unknowns. Do not include phone numbers, emails or any personal data.")
_lock = threading.Lock()


def _path(agent):
    return os.path.join(agent.state.dir, FILE)


def load(agent):
    try:
        return json.load(open(_path(agent), encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "none", "profile": {}, "sources": [], "learned_at": 0, "error": ""}


def save(agent, d):
    os.makedirs(agent.state.dir, exist_ok=True)
    tmp = _path(agent) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path(agent))


def configured(agent):
    rc = agent.cfg.get("reasoner") or {}
    return bool(rc.get("model") and (rc.get("api_key") or rc.get("base_url")))


def _text_from_html(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", html)
    t = re.sub(r"&nbsp;|&amp;|&quot;|&#39;|&lt;|&gt;", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def fetch_site(url):
    p = urlparse(str(url or "").strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Type the website address starting with https://")
    import urllib.request
    req = urllib.request.Request(p.geturl(), headers={"user-agent": "SpeakvoraAgent/0.7 (reads your own site once, on your computer)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            raise ValueError("That address is not a web page.")
        return _text_from_html(r.read(400_000).decode("utf-8", "replace"))[:12000]


def gather(agent, website="", notes=""):
    """(text for the model, list of what was used). Nothing about customers."""
    cfg, used, parts = agent.cfg, [], []
    facts = {k: v for k, v in (cfg.get("facts") or {}).items() if k != "oncall_phone" and v and "YOUR-" not in str(v)}
    if cfg.get("business") and "YOUR-" not in str(cfg["business"]):
        parts.append("Business name: " + str(cfg["business"])); used.append("business name")
    for k, v in facts.items():
        parts.append(f"{k.replace('_', ' ').capitalize()}: {v}"); used.append(f"fact: {k}")
    parts.append("Industry bundle: " + str(agent.pack.meta.get("title", ""))); used.append("industry bundle")
    names = [recipes.NICE.get(w.get("name"), (w.get("name") or "").replace("_", " ")) for w in agent.workflows]
    names = [n if isinstance(n, str) else str(n[0]) for n in names][:25]
    if names:
        parts.append("Things the assistant is set up to do: " + "; ".join(names)); used.append("workflow names")
    try:
        evs = agent._events(agent.now(), agent.now() + 14 * 86400) if agent.gcal.configured or agent.outlook.configured else []
        titles = sorted({re.sub(r"\d+", "", str(e.get("title", ""))).strip() for e in evs if e.get("title")})[:15]
        if titles:
            parts.append("Types of upcoming calendar events: " + "; ".join(titles)); used.append("calendar event types")
    except Exception:  # noqa: BLE001
        pass
    if website:
        parts.append("From the business website:\n" + fetch_site(website)); used.append("website " + urlparse(website).hostname)
    if notes and notes.strip():
        parts.append("Notes from the owner:\n" + notes.strip()[:6000]); used.append("your notes")
    return R.redact("\n".join(parts), None)[:24000], used


def _clean(p):
    s = lambda v, n: re.sub(r"\s+", " ", str(v or "")).strip()[:n]
    lst = lambda v, n, m: [s(x, n) for x in (v if isinstance(v, list) else []) if s(x, n)][:m]
    faqs = [{"q": s(x.get("q"), 200), "a": s(x.get("a"), 500)} for x in (p.get("faqs") if isinstance(p.get("faqs"), list) else []) if isinstance(x, dict) and s(x.get("q"), 200) and s(x.get("a"), 500)][:30]
    return {"summary": s(p.get("summary"), 700), "tone": s(p.get("tone"), 200), "hours": s(p.get("hours"), 300), "services": lst(p.get("services"), 140, 25), "policies": lst(p.get("policies"), 240, 15), "faqs": faqs, "unknowns": lst(p.get("unknowns"), 200, 12)}


def learn(agent, website="", notes=""):
    """Reads the allowed sources, asks the owner's AI for a profile, stores it for review. Never raises: problems are saved as an error the dashboard shows."""
    with _lock:
        d = load(agent); prev = d.get("profile") or {}
        if not configured(agent):
            d.update(status="error", error="Connect your AI first (Connect, AI reasoning).") ; save(agent, d); return d
        d.update(status="learning", error=""); save(agent, d)
        try:
            text, used = gather(agent, website, notes)
            raw, _usage = R._chat(agent.cfg["reasoner"], SYSTEM, text, 1400)
            m = re.search(r"\{.*\}", raw or "", re.S)
            prof = _clean(json.loads(m.group(0))) if m else None
            if not prof or not (prof["summary"] or prof["services"] or prof["faqs"]):
                raise ValueError("The AI did not return a usable profile. Add more detail (your website or notes) and try again.")
            d = {"status": "needs_review", "profile": prof, "sources": used, "learned_at": int(agent.now()), "error": "", "website": website or d.get("website", ""), "previous": prev}
        except Exception as e:  # noqa: BLE001
            d.update(status="error" if not prev else "approved", error=str(e)[:300])
        save(agent, d); agent.state.log(workflow="brain", action="learn", status=d["status"], dry_run=False, sources=len(d.get("sources", [])))
        return d


def start_learning(agent, website="", notes=""):
    """Right after the owner's AI is connected and tested: learn in the background so the dashboard never waits."""
    d = load(agent)
    if d.get("status") in ("learning", "needs_review", "approved"):
        return False
    threading.Thread(target=learn, args=(agent, website, notes), daemon=True).start()
    return True


def start_learning_now(agent, website="", notes=""):
    """The owner pressed Learn (or Learn again): run in the background so the page answers at once."""
    d = load(agent)
    if d.get("status") == "learning":
        return False
    d.update(status="learning", error=""); save(agent, d)
    threading.Thread(target=learn, args=(agent, website, notes), daemon=True).start()
    return True


def approve(agent):
    d = load(agent)
    if d.get("status") not in ("needs_review", "approved"):
        raise ValueError("There is nothing to approve yet.")
    d.update(status="approved", approved_at=int(agent.now())); save(agent, d)
    return d


def edit(agent, profile):
    d = load(agent); d["profile"] = _clean(profile or {}); d["status"] = "needs_review"; d["error"] = ""; save(agent, d)
    return d


def forget(agent):
    try:
        os.remove(_path(agent))
    except OSError:
        pass
    return load(agent)


def for_prompt(agent):
    """The approved profile as text for the AI's input; empty until the owner has approved it."""
    d = load(agent)
    if d.get("status") != "approved":
        return ""
    p = d.get("profile") or {}
    out = ["BUSINESS PROFILE (approved by the owner; rely on it and never go beyond it):", "Summary: " + p.get("summary", ""), "Tone: " + p.get("tone", ""), "Hours: " + p.get("hours", "")]
    out += ["Service: " + x for x in p.get("services", [])] + ["Policy: " + x for x in p.get("policies", [])] + [f"Q: {f['q']} A: {f['a']}" for f in p.get("faqs", [])]
    return "\n".join(out) + "\n\n"
