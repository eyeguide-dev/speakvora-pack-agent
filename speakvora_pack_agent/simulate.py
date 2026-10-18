"""Test my agent: type what a customer would text, or pick something that happens in your app, and see exactly what your agent would do, without sending anything.
It uses the agent's real workflows, your own words, your AI and your knowledge, with a made-up customer number. Nothing is sent, nothing is recorded as a real conversation, and the made-up customer never touches a real person's opt-out list.
While a test runs the agent is held in practice mode for a moment, so even a live agent cannot send anything from here."""
import json, os, threading, time

from . import i18n, recipes
from .builder import EVENTS as BE

WHO = "+15555550100"
_LOCK = threading.Lock()
SHOW = ("workflow", "action", "status", "to", "text", "channel", "reason", "error", "title")
SAMPLE = {"customer": {"name": "Sample Customer", "phone": WHO, "email": "sample@example.com", "sms_consent": True}, "order": {"number": "1049", "total": "24.50", "items": "2 items"},
          "reservation": {"time": "7:00 PM", "party": 2}, "payment": {"amount": "49.00"}}


def _title(agent, name):
    for w in agent.workflows:
        if w["name"] == name:
            return w.get("title") or recipes.NICE.get(name) or name.replace("_", " ")
    return {"sms_ai": "Your AI answers"}.get(name, name.replace("_", " "))


def _sources(agent):
    from . import converse
    return {"text": True, "ai": converse.enabled(agent, "sms"), "live": not agent.dry}


def view(agent):
    from . import converse
    ev = sorted({(w.get("on") or {}).get("event") for w in agent.workflows if (w.get("on") or {}).get("event") and w.get("enabled", True)})
    words = []
    for w in agent.workflows:
        for k in (agent._triggers((w.get("on") or {}).get("sms")) or []):
            if len(words) < 6 and k not in words and w.get("enabled", True):
                words.append(k)
    custom = []
    for w in agent.workflows:
        if w.get("custom") and w.get("enabled", True):
            custom += [k for k in (agent._triggers((w.get("on") or {}).get("sms")) or []) if k not in custom][:2]
    ask = ["What are your hours?", "Where are you located?", "I want to talk to a person"] + custom[:3]
    return {"events": [{"id": e, "label": BE.get(e, e)} for e in ev], "ideas": ask[:6], "ai": converse.enabled(agent, "sms"), "live": not agent.dry}


def _tail(agent, start):
    out = []
    try:
        with open(agent.state.log_path, "rb") as f:
            f.seek(start); data = f.read().decode("utf-8", "replace")
    except OSError:
        return out
    for line in data.splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("action") or r.get("status") in ("error", "blocked", "skipped"):
            out.append({k: (str(v)[:300] if not isinstance(v, bool) else v) for k, v in r.items() if k in SHOW and v not in ("", None)})
    return out[:12]


def _size(agent):
    try:
        return os.path.getsize(agent.state.log_path)
    except OSError:
        return 0


def reset(agent):
    agent.state.data.setdefault("converse", {}).pop("sms:" + WHO, None)


def text(agent, body, new=False):
    body = " ".join(str(body or "").split())[:500]
    if not body:
        raise ValueError("Type what a customer would text.")
    with _LOCK:
        was, start = agent.dry, _size(agent)
        agent.dry = True
        try:
            if new:
                reset(agent)
            agent._m().clear()
            low = body.lower()
            reply = agent._handle_sms({"From": WHO, "Body": body})
            m = dict(agent._m())
        finally:
            agent.dry = was
            try:
                agent.state.opt_in(WHO)
            except Exception:  # noqa: BLE001
                pass
    wf = m.get("wf") or ""
    if low in i18n.opt_out_words(agent.lang):
        who = "The opt-out words"; note = "A real customer who texts this is removed from your texts, as carriers require. (Not applied to anyone here.)"
    elif low in ("start", "unstop", "yes", "help"):
        who = "The built-in answer"; note = ""
    else:
        who = _title(agent, wf) if wf else "Nothing matched"
        note = "" if wf else "No workflow matched and your AI is off, so a real customer would get no automatic reply. Add a workflow for these words, or switch your AI on."
    if m.get("handoff"):
        note = "A real customer would be handed to your team (your staff phone or Slack), and the AI would say it is getting someone."
    did = _tail(agent, start)
    bad = next((x for x in did if x.get("status") in ("skipped", "error") and x.get("reason") or x.get("error")), None)
    if wf and not reply and bad and not note:
        note = "It matched, but could not answer yet: " + str(bad.get("reason") or bad.get("error"))
    if wf == "sms_ai" and not note:
        note = "Your AI answered from your business facts and knowledge."
    return {"kind": "text", "you": body, "reply": reply or "", "matched": who, "ai": wf == "sms_ai", "did": did, "note": note, "sent": False}


def event(agent, name):
    name = str(name or "").strip()
    if not name:
        raise ValueError("Choose what happens.")
    with _LOCK:
        was, start = agent.dry, _size(agent)
        agent.dry = True
        try:
            agent._m().clear()
            payload = {"event": name, "id": "sim-" + str(int(time.time() * 1000)), **json.loads(json.dumps(SAMPLE))}
            r = agent.handle_event(payload)
        finally:
            agent.dry = was
    names = [_title(agent, x["workflow"]) for x in r.get("workflows", [])]
    return {"kind": "event", "you": name, "matched": ", ".join(names) or "Nothing matched", "did": _tail(agent, start), "sent": False,
            "note": "" if names else "No switched-on workflow reacts to this event."}
