"""Customer details do not stay on this computer longer than you choose.
Speakvora never receives customer names, numbers or messages. This agent does handle them on YOUR computer while it works (a queued text needs the number until it is sent, and the activity list shows who got what), and your own AI provider sees only what is sent to it, with emails, phone numbers and card-like numbers replaced first.
After the days you set (default 7, 0 to 90; 0 = at the next daily clean-up) finished jobs lose their customer details (the record that a text was sent stays) and old activity-log lines have phone numbers and emails masked. Jobs still waiting or needing you are never touched.
This is data minimisation, not a compliance certificate: a regulated business still needs its own review and a written agreement with any AI provider it connects."""
import json, os, re

PHONE = re.compile(r"\+?\d[\d\-\s().]{6,}\d")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
KEEP = ("pending", "sending", "queued", "needs_review", "needs_approval", "proposed")


def days(agent):
    from . import guardrails as G
    return {**G.DEFAULTS, **(agent.cfg.get("guardrails") or {})}["keep_details_days"]


def _mask(v):
    if isinstance(v, str):
        return EMAIL.sub("(email removed)", PHONE.sub(lambda m: "***" + re.sub(r"\D", "", m.group(0))[-2:], v))
    if isinstance(v, dict):
        return {k: _mask(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_mask(x) for x in v]
    return v


def scrub(agent, force=False):
    """Returns how many jobs and log lines were cleaned. Runs about once a day from tick()."""
    st = agent.state; now = agent.now()
    if not force and now - float(st.data.get("privacy_last", 0)) < 20 * 3600:
        return {"jobs": 0, "log_lines": 0}
    cutoff = now - days(agent) * 86400; jobs = lines = 0
    with st.lock:
        for j in st.data["jobs"].values():
            if j["status"] not in KEEP and j["updated"] < cutoff and (j.get("ctx") or j.get("scrubbed") is None):
                j["ctx"] = {}; j["a"] = {k: ("(removed)" if k in ("text", "body", "subject", "json", "description") else _mask(v)) for k, v in (j.get("a") or {}).items()}; j["scrubbed"] = True; jobs += 1
        st.data["privacy_last"] = now; st.save()
        if os.path.exists(st.log_path):
            out = []
            for l in open(st.log_path, encoding="utf-8"):
                try:
                    r = json.loads(l)
                except ValueError:
                    continue
                if r.get("t", now) < cutoff and not r.get("masked"):
                    r = _mask(r); r["masked"] = True; lines += 1
                out.append(json.dumps(r, ensure_ascii=False))
            tmp = st.log_path + ".tmp"; open(tmp, "w", encoding="utf-8").write("\n".join(out) + ("\n" if out else "")); os.replace(tmp, st.log_path)
    return {"jobs": jobs, "log_lines": lines}
