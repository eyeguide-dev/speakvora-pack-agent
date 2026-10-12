"""Optional reasoning for requests the rules cannot handle ("review these conversations, decide which customers need refunds and explain why"), with the developer's OWN AI key.
Nothing here runs unless a workflow has a `reason` action and agent.json has a `reasoner` section. Rules stay the default: offline, no AI, no cost.

How it is kept safe:
* Only what the workflow puts in `inputs` (plus the task and the contact names) is sent to the model, with emails, phone numbers and card-like numbers replaced by placeholders first. The model never sees phone numbers or addresses.
* The model can only PROPOSE. It answers in a fixed JSON shape; every proposal is checked against the actions, channels and hosts the workflow allows. Customers are named by a contact id the workflow supplied, so the model cannot invent a recipient.
* Proposals wait in the dashboard ("Needs you") for a person to approve. Approved proposals run like any other send: consent, STOP, quiet hours, limits and the kill switch are checked again, and every send is a journaled job.
* A model that is wrong, unreachable or answers in the wrong shape produces a failed job, never an action.
Providers: any OpenAI-compatible chat endpoint (OpenAI, Azure, Groq, Together, OpenRouter, DeepInfra, vLLM, Ollama on localhost for fully offline use) and Anthropic's Messages API. Standard library only."""
import json, re

from . import web

KINDS = ("sms", "email", "slack", "teams", "http", "calendar_create")
DEFAULT_MAX_CHARS = 12000
REDACT = {"card": (re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?!\d)"), "[number]"),             # card-like numbers first: they would also look like a phone number
          "email": (re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+"), "[email]"),
          "phone": (re.compile(r"(?<!\d)\+?\d[\d\-\s().]{8,}\d(?!\d)"), "[phone]")}

SYSTEM = ("You are a careful analyst inside a small business automation agent. You are given a task and some input. You analyse it and PROPOSE actions; you never perform them, and a person approves every proposal. "
          "Answer with ONE JSON object and nothing else: {\"summary\": \"one or two sentences\", \"reasoning\": \"why, in plain words, citing the input\", "
          "\"proposals\": [{\"action\": \"" + "|".join(KINDS) + "\", \"contact\": \"id from the contact list\", \"channel\": \"allowed channel\", \"text\": \"message text\", \"subject\": \"email subject\", \"url\": \"allowed URL\", \"json\": {}, \"title\": \"\", \"start\": 0, \"minutes\": 30, \"why\": \"reason for this proposal\"}]}. "
          "Use only the contact ids, channels and URLs you are given; if the input does not support an action, propose nothing. Do not invent facts, amounts or people. Do not give medical, legal or financial advice. Keep messages short and honest.")


def redact(text, kinds=None):
    for k in (kinds if kinds is not None else list(REDACT)):
        if k in REDACT:
            text = REDACT[k][0].sub(REDACT[k][1], text)
    return text


def as_text(v):
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1)


def build_user(task, inputs, contacts, allow, channels, hosts, max_chars, redact_kinds):
    """The ONE message sent to the model, and nothing else. Returns the text."""
    cl = [{"id": c["id"], "name": c.get("name", "")} for c in contacts]
    body = (f"TASK: {task}\n\nALLOWED ACTIONS: {', '.join(allow) or 'none (analysis only)'}\n" + (f"ALLOWED CHANNELS: {', '.join(channels)}\n" if channels else "") + (f"ALLOWED URLS: {', '.join(hosts)}\n" if hosts else "")
            + (f"CONTACTS (use the id): {json.dumps(cl, ensure_ascii=False)}\n" if cl else "") + "\nINPUT:\n" + as_text(inputs))
    return redact(body, redact_kinds)[:max_chars]


def _chat(cfg, system, user, max_tokens=None):
    prov = str(cfg.get("provider") or "openai").lower(); timeout = int(cfg.get("timeout", 45)); key = cfg.get("api_key", ""); mt = int(max_tokens or cfg.get("max_tokens", 900))
    if prov == "anthropic":
        base = str(cfg.get("base_url") or "https://api.anthropic.com").rstrip("/")
        _st, r = web.request("POST", base + "/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"},
                             body={"model": cfg["model"], "max_tokens": mt, "temperature": 0, "system": system, "messages": [{"role": "user", "content": user}]}, timeout=timeout)
        return "".join(b.get("text", "") for b in (r or {}).get("content", []) if b.get("type") == "text"), (r or {}).get("usage") or {}
    base = str(cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    h = {"authorization": "Bearer " + key} if key else {}
    _st, r = web.request("POST", base + "/chat/completions", h, body={"model": cfg["model"], "temperature": 0, "max_tokens": mt,
                                                                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=timeout)
    ch = ((r or {}).get("choices") or [{}])[0]
    return (ch.get("message") or {}).get("content") or "", (r or {}).get("usage") or {}


def ask(cfg, user):
    """One model call. Returns (text, usage). Raises web.HttpError / web.NetworkDown like every other send."""
    return _chat(cfg, SYSTEM, user)


def ping(cfg):
    """The dashboard's AI test: a tiny harmless question, a few tokens. Returns the model's short answer."""
    return _chat(cfg, "You are a connection test.", "Reply with the single word OK.", 8)[0]


class BadAnswer(ValueError):
    pass


def parse(text):
    """The model's JSON object, or BadAnswer. Tolerates a code fence or a sentence around it."""
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    if not m:
        raise BadAnswer("The model did not answer with the expected JSON.")
    try:
        d = json.loads(m.group(0))
    except ValueError:
        raise BadAnswer("The model's answer was not valid JSON.")
    if not isinstance(d, dict) or not isinstance(d.get("proposals", []), list):
        raise BadAnswer("The model's answer had the wrong shape.")
    return {"summary": str(d.get("summary") or "")[:600], "reasoning": str(d.get("reasoning") or "")[:3000], "proposals": d.get("proposals") or []}


def _s(v, n):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def validate(props, allow, contacts, channels, hosts, max_n=8):
    """Keeps only proposals the workflow allows, with every recipient and destination resolved from the workflow's own lists. Returns (kept, dropped reasons). A kept proposal is a plain dict: action, args (what will really be sent), why, state."""
    ids = {c["id"]: c for c in contacts}; kept, dropped = [], []
    for p in props[:max_n]:
        if not isinstance(p, dict):
            dropped.append("not an object"); continue
        k = str(p.get("action") or "").lower(); why = _s(p.get("why"), 300)
        if k not in KINDS or k not in allow:
            dropped.append(f"action '{k}' is not allowed here"); continue
        if k in ("sms", "email"):
            c = ids.get(str(p.get("contact") or ""))
            if not c:
                dropped.append(f"{k}: unknown contact"); continue
            text = _s(p.get("text"), 1500 if k == "email" else 320)
            if not text:
                dropped.append(f"{k}: no text"); continue
            if k == "sms" and not c.get("phone"):
                dropped.append("sms: that contact has no phone"); continue
            if k == "email" and not c.get("email"):
                dropped.append("email: that contact has no email"); continue
            args = {"contact": c["id"], "name": c.get("name", ""), "text": text, **({"subject": _s(p.get("subject"), 150) or "Update"} if k == "email" else {})}
        elif k in ("slack", "teams"):
            ch = str(p.get("channel") or "")
            if channels and ch not in channels:
                dropped.append(f"{k}: channel '{ch}' is not allowed"); continue
            text = _s(p.get("text"), 1500)
            if not text:
                dropped.append(f"{k}: no text"); continue
            args = {"channel": ch or (channels[0] if channels else ""), "text": text}
        elif k == "http":
            url = str(p.get("url") or "")
            if url not in hosts and not any(url.startswith(h.rstrip("/") + "/") or url == h for h in hosts):
                dropped.append("http: URL is not on the allowed list"); continue
            body = p.get("json") if isinstance(p.get("json"), (dict, list)) else {}
            args = {"url": url, "method": "POST", "json": body}
        else:                                                              # calendar_create
            try:
                start, minutes = int(p.get("start")), max(5, min(int(p.get("minutes") or 30), 480))
            except (TypeError, ValueError):
                dropped.append("calendar_create: start must be a Unix time"); continue
            args = {"title": _s(p.get("title"), 120) or "Event", "start": start, "minutes": minutes}
        kept.append({"action": k, "args": args, "why": why, "state": "pending", "job": None})
    return kept, dropped
