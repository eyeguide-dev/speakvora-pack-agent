"""The assistant box on the Connect tab: the owner asks or tells their own connected AI things ("which calls needed a person today?", "write six friendly reminder lines", "make this greeting warmer").
It can ANSWER from short summaries of recent calls and texts (never the words said), PROPOSE phrases (they wait on the suggestions list until the owner presses Add) and REWRITE wording the owner pastes. It cannot send anything, change a setting, approve an action or see customer details: the buttons do those.
Each message goes to the business's own AI provider with emails, phone numbers and card-like numbers replaced first. At most 30 messages an hour."""
import json, re, time

from . import brain, conversations as CV, industry_rules, learned, reasoner as R

SYSTEM = ("You are the assistant inside a small business's dashboard for its automated phone and text agent. You can: answer questions about the recent calls and texts using ONLY the summaries given; "
          "suggest new short spoken phrases the business could add to its library; rewrite wording the owner pastes. You cannot send messages, place calls, change settings or approve anything: if asked, say the owner uses the buttons in the dashboard. "
          "Never invent facts, prices or hours. Never include phone numbers, emails or personal details in phrases. Phrases must be one plain sentence, 20 to 160 characters, no digits or names. "
          'Reply with ONE JSON object only: {"reply": "short, friendly answer", "phrases": ["optional list of up to 8 phrases"]}.')
MAX_PER_HOUR, KEEP = 30, 40


def history(agent):
    return list(agent.state.data.get("chat") or [])[-KEEP:]


def _context(agent):
    items = CV.list_(agent, limit=15)["items"]; now = int(agent.now())
    rows = [f"- {'today' if now - x['updated'] < 86400 else 'earlier'}, {x['channel']}: {x['outcome_label']}. {x['summary']}" for x in items]
    return (f"Business: {agent.cfg.get('business', '')}. Industry rules the agent follows: {industry_rules.prompt(agent).strip()}\n" + (brain.for_prompt(agent) or "") +
            ("Recent calls and texts (summaries only):\n" + "\n".join(rows) if rows else "No calls or texts yet.") + "\n")


def ask(agent, message):
    message = re.sub(r"\s+", " ", str(message or "")).strip()[:1200]
    if not message:
        raise ValueError("Type something to ask or tell your assistant.")
    if not brain.configured(agent):
        raise ValueError("Connect your AI first (the AI card below), then ask again.")
    now = time.time(); times = [t for t in (agent.state.data.get("chat_times") or []) if now - t < 3600]
    if len(times) >= MAX_PER_HOUR:
        raise ValueError("That is 30 messages this hour. Try again a little later.")
    raw, _u = R._chat(agent.cfg["reasoner"], SYSTEM, R.redact(_context(agent) + "\nOwner: " + message, None), 700)
    m = re.search(r"\{.*\}", raw or "", re.S); reply, lines = "", []
    try:
        j = json.loads(m.group(0)) if m else {}
        reply, lines = " ".join(str(j.get("reply") or "").split())[:1200], [str(x) for x in (j.get("phrases") or [])]
    except ValueError:
        pass
    if not reply:
        reply = " ".join(str(raw or "").split())[:1200] or "I could not answer that. Try asking it another way."
    phrases = learned.add_suggestions(agent, lines)
    with agent.state.lock:
        h = list(agent.state.data.get("chat") or []) + [{"role": "you", "text": message, "t": int(now)}, {"role": "assistant", "text": reply, "phrases": phrases, "t": int(now)}]
        agent.state.data["chat"] = h[-KEEP:]; agent.state.data["chat_times"] = times + [now]; agent.state.save()
    return {"reply": reply, "phrases": phrases, "history": history(agent)}


def clear(agent):
    with agent.state.lock:
        agent.state.data["chat"] = []; agent.state.save()
    return {"history": []}
