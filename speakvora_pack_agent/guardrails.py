"""Limits on what the owner's AI may do. Two layers: HARD limits that live in this code and cannot be turned off from any dashboard (they are what keeps an automated assistant honest and safe),
and adjustable limits the owner sets inside a ceiling. Stored in agent.json under "guardrails". The live-conversation features read these; nothing here makes the agent send anything by itself."""
import re

HARD = [
    "It tells people it is an automated assistant at the start of every call and text conversation.",
    "It never takes card numbers, passwords, ID numbers or other secrets, and never gives medical, legal, financial or emergency advice (for an emergency it tells the caller to call the local emergency number).",
    "It only answers from what the business has approved (your business profile and approved lines). It says so when it does not know and offers a person.",
    "It can never refund, charge, cancel, change a record or delete anything. It can only answer, and do the specific actions you allow below.",
    "A caller who asks for a person is connected to your staff phone right away; two unanswered questions in a row do the same.",
    "Consent, STOP, quiet hours, per-person limits and the pause switch are checked on every message and call, exactly as for every other send.",
]
CEILING = {"max_turns": 40, "max_call_minutes": 20, "max_ai_replies_per_hour": 200, "phrase_chars_per_month": 20000}
FLOOR = {"learn_after": (2, 20)}
DEFAULTS = {"sms_replies": False, "voice_calls": False, "max_turns": 12, "max_call_minutes": 6, "max_ai_replies_per_hour": 30, "allowed_actions": [], "blocked_topics": ["medical advice", "legal advice", "emergencies"],
            "handoff_words": ["person", "human", "agent", "operator", "manager", "representative", "someone"], "after_hours": "message", "auto_learn_phrases": False, "learn_after": 3, "phrase_chars_per_month": 3000}
ACTIONS = {"notify": "Tell my team in Slack or Teams", "sms": "Send a confirmation text", "calendar_create": "Add a booking to my calendar"}      # nothing that moves money or changes a customer record


def view(agent):
    cur = {**DEFAULTS, **(agent.cfg.get("guardrails") or {})}
    return {"settings": cur, "hard": HARD, "ceiling": CEILING, "actions": ACTIONS, "staff_phone_set": bool(re.sub(r"\D", "", str((agent.cfg.get("facts") or {}).get("oncall_phone", ""))) and "YOUR-" not in str((agent.cfg.get("facts") or {}).get("oncall_phone", "")))}


def clean(v):
    cur = dict(DEFAULTS)
    for k in ("sms_replies", "voice_calls"):
        cur[k] = bool((v or {}).get(k))
    for k, hi in CEILING.items():
        try:
            cur[k] = max(1, min(int((v or {}).get(k, DEFAULTS[k])), hi))
        except (TypeError, ValueError):
            raise ValueError(f"{k.replace('_', ' ').capitalize()} must be a number up to {hi}.")
    cur["auto_learn_phrases"] = bool((v or {}).get("auto_learn_phrases"))
    try:
        cur["learn_after"] = max(2, min(int((v or {}).get("learn_after", 3)), 20))
    except (TypeError, ValueError):
        raise ValueError("Repeat count must be a number from 2 to 20.")
    cur["allowed_actions"] = [a for a in ((v or {}).get("allowed_actions") or []) if a in ACTIONS]
    cur["blocked_topics"] = [re.sub(r"\s+", " ", str(x)).strip()[:60] for x in ((v or {}).get("blocked_topics") or DEFAULTS["blocked_topics"]) if str(x).strip()][:20]
    cur["handoff_words"] = [re.sub(r"\s+", " ", str(x)).strip().lower()[:30] for x in ((v or {}).get("handoff_words") or DEFAULTS["handoff_words"]) if str(x).strip()][:30]
    cur["after_hours"] = "message" if (v or {}).get("after_hours") not in ("message", "transfer") else v["after_hours"]
    return cur


def wants_human(agent, text):
    """True when what a caller or texter said asks for a person."""
    words = {**DEFAULTS, **(agent.cfg.get("guardrails") or {})}["handoff_words"]
    t = " " + re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()) + " "
    return any(f" {w} " in t for w in words) or "speak to someone" in t or "talk to someone" in t
