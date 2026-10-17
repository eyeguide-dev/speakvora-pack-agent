"""Industry call-handling controls: a reviewed-by-you catalog (1,140 draft rules for 23 industries, 49 policy settings, source references) that ships with the agent, and the few controls the agent already ENFORCES in code.
Honest scope: every catalog rule is a DRAFT guideline for your team and your system design until you review it. Only the rules in ENFORCED change what the agent does today; the dashboard says which. Nothing here is legal advice or a compliance certificate.
Private records (health, orders tied to a person) stay OFF until the policy settings that make them safe are filled in and you approve go-live: see private_lookups_ready()."""
import json, os, re

from . import connect as SU

HERE = os.path.dirname(os.path.abspath(__file__))
_cache = {}

# our profile -> catalog industries that apply (the catalog's "All industries" always applies)
INDUSTRIES = {"food": ["Restaurants"], "clinic": ["Clinics and hospitals"], "pharmacy": ["Pharmacy", "Cannabis dispensary"], "lodging": ["Hotels"], "beauty": ["Salons and spas", "Fitness studios"], "laundry": ["Salons and spas"],
              "retail": ["Retail stores", "E-commerce"], "trades": ["Home services"], "auto": ["Auto repair"], "legal": ["Legal services"], "finance": ["Banking and payments"], "collections": ["Banking and payments"],
              "education": ["Education and childcare"], "devops": ["IT and SaaS support"], "support": ["IT and SaaS support"], "generic": []}
HEALTH = ("Clinics and hospitals", "Pharmacy", "Cannabis dispensary", "Dental", "Behavioral health")

# controls the agent enforces in code today (each has a test): id -> what happens
ENFORCED = {
    "UNI-001": "Caller ID is never treated as identity: private lookups need your records system to say it verified the person.",
    "UNI-007": "A spoken password or login code is refused and the caller is pointed to staff; it is never recorded.",
    "UNI-088": "Card numbers and security codes are refused on the call and never stored.",
    "UNI-031": "Every call starts by saying it is automated.",
    "UNI-033": "When speech is not understood the caller is asked again, never guessed at.",
    "UNI-038": "A caller who cannot use the keypad can speak, and is never looped: two misses connect a person.",
    "UNI-061": "Asking for a person connects the staff phone right away.",
    "UNI-062": "A caller describing an emergency is told to call 911 and the business flow stops (speech input must be on).",
    "UNI-082": "Keys, passwords and system instructions are never read out.",
    "UNI-083": "Webhook and API calls go only to hosts written in the workflow or connection, never to a caller-supplied address.",
    "UNI-093": "Lookups are logged by outcome only, never the private content.",
}
EMERGENCY = re.compile(r"\b(emergency|911|nine one one|heart attack|chest pain|can'?t breathe|cannot breathe|not breathing|overdose|overdosed|suicide|kill myself|bleeding|unconscious|gas leak|on fire|fire in|someone is hurt|being attacked)\b", re.I)
SECRET = re.compile(r"\b(password|passcode|one[- ]time (?:code|password)|verification code|security code|cvv|card number|credit card|debit card|social security|pin number)\b", re.I)


def catalog():
    if "c" not in _cache:
        try:
            _cache["c"] = json.load(open(os.path.join(HERE, "data", "call_controls.json"), encoding="utf-8"))
        except (OSError, ValueError):
            _cache["c"] = {"rules": [], "boundaries": {}, "policy": [], "sources": {}, "codes": {}}
    return _cache["c"]


def industries(agent):
    return INDUSTRIES.get(getattr(agent, "profile", "generic"), [])


def policy(agent):
    """Every policy setting with your value (or the draft default)."""
    mine = agent.cfg.get("call_policy") or {}
    out = {}
    for p in catalog()["policy"]:
        out[p["setting"]] = mine.get(p["setting"], p["default"])
    return out


def _truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes", "on")


def readiness(agent):
    """What is still missing before private records may be used: [{'setting', 'why'}]. Empty = ready."""
    pol, miss = policy(agent), []
    need = {"human_review_owner": "A named person responsible for this industry profile", "identity_method": "How your records system verifies who is asking (never caller ID, never a password said aloud)",
            "privacy_notice": "Your approved explanation of where data goes", "jurisdiction_profile": "The rules profile you reviewed for your business and location", "transfer_roster": "Who the call is passed to, when, and the fallback"}
    if (agent.cfg.get("facts") or {}).get("oncall_phone") and "YOUR-" not in str((agent.cfg.get("facts") or {}).get("oncall_phone")):
        pol["transfer_roster"] = pol.get("transfer_roster") if pol.get("transfer_roster") not in ("UNSET", "", None) else "staff phone (facts.oncall_phone)"
    for k, why in need.items():
        if str(pol.get(k, "UNSET")).strip() in ("UNSET", "", "None"):
            miss.append({"setting": k, "why": why})
    if any(i in HEALTH for i in industries(agent)) and not _truthy(pol.get("phi_enabled")):
        miss.append({"setting": "phi_enabled", "why": "Turn on only after your HIPAA review, a signed agreement with each provider that touches health data, and secure access"})
    if not _truthy(pol.get("go_live_approval")):
        miss.append({"setting": "go_live_approval", "why": "Your sign-off after testing failures and fallbacks"})
    return miss


def private_lookups_ready(agent):
    return not readiness(agent)


def set_policy(agent, values):
    known = {p["setting"] for p in catalog()["policy"]}
    raw = SU._raw(agent); cur = dict(raw.get("call_policy") or {})
    for k, v in (values or {}).items():
        if k not in known:
            raise ValueError(f"Unknown setting '{k}'.")
        cur[k] = str(v).strip()[:300]
    raw["call_policy"] = cur
    SU._write_raw(agent, raw); SU._reload(agent)
    return view(agent)


def rules(agent, priority="", q="", offset=0, limit=40):
    inds = ["All industries"] + industries(agent)
    rs = [r for r in catalog()["rules"] if r["industry"] in inds and (not priority or r["priority"].lower().startswith(priority.lower())) and (not q or q.lower() in (r["trigger"] + " " + r["control"] + " " + r["category"]).lower())]
    return {"total": len(rs), "rules": [dict(r, enforced=r["id"] in ENFORCED, how=ENFORCED.get(r["id"], "")) for r in rs[offset:offset + limit]]}


def view(agent):
    c, inds = catalog(), industries(agent)
    mine = [r for r in c["rules"] if r["industry"] in ["All industries"] + inds]
    pri = lambda p: sum(1 for r in mine if r["priority"].startswith(p))  # noqa: E731
    pol = policy(agent)
    scopes = ("All", "Private records", "Outbound calls/texts") + (("Healthcare",) if any(i in HEALTH for i in inds) else ())
    return {"industries": inds, "counts": {"rules": len(mine), "critical": pri("Critical"), "high": pri("High"), "enforced": sum(1 for r in mine if r["id"] in ENFORCED)}, "enforced": [{"id": k, "how": v} for k, v in ENFORCED.items()],
            "boundaries": {i: c["boundaries"].get(i) for i in inds}, "readiness": readiness(agent), "ready": private_lookups_ready(agent),
            "policy": [dict(p, value=pol[p["setting"]]) for p in c["policy"] if p["scope"] in scopes or p["scope"].startswith(("Optional", "Teams", "Multi"))],
            "note": "Every catalog rule is a draft until you review it. Only the controls marked enforced change what the agent does today."}


def guard_speech(said):
    """'emergency', 'secret' or '' for what a caller said. Emergency wins."""
    if EMERGENCY.search(said or ""):
        return "emergency"
    if SECRET.search(said or ""):
        return "secret"
    return ""
