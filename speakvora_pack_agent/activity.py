"""The Home screen's feed and the Library's phrase list, as plain data the dashboard draws.
activity(): calls and texts, messages the agent sent, and order steps, newest first, each with a title a business owner would say aloud.
phrases(): the lines in this bundle's library (the ones that came with it and the ones you added) for the Library tab, with search."""
import re, time

from . import conversations as CV, learned, tracker

LABEL = {"sent": "Sent", "delivered": "Delivered", "failed": "Failed", "undelivered": "Not delivered", "blocked": "Held back", "queued": "Waiting", "needs_review": "Needs a look", "expired": "Expired", "cancelled": "Dismissed"}
KIND_TITLE = {"sms": "Text sent", "call": "Call placed", "slack": "Team updated", "teams": "Team updated", "jira_bug": "Bug reported to Jira", "confluence_log": "Known-issues page updated", "email": "Email sent", "http": "Sent to your app", "webhook": "Sent to your app", "calendar_create": "Calendar entry added", "calendar_reschedule": "Calendar entry moved", "calendar_cancel": "Calendar entry cancelled", "calendar_delete": "Calendar entry removed", "reason": "AI suggestion"}


def _pretty(s):
    return re.sub(r"\s+", " ", str(s or "").replace("_", " ")).strip().capitalize()


def activity(agent, jobs, kind="", offset=0, limit=30):
    """jobs: the dashboard's job list (already shaped for display). kind: '', call, text, person, order, problem."""
    now = int(agent.now()); out = []
    if kind in ("", "call", "text", "person"):
        for c in CV.list_(agent, kind={"call": "call", "text": "sms", "person": "person"}.get(kind, ""), limit=60)["items"]:
            word = "Call" if c["channel"] == "call" else "Text"
            title = {"staff": word + " connected to staff", "emergency": word + ": told to call 911", "poison": word + ": Poison Control and 911", "secret": word + ": refused a password or card number", "optout": word + ": opted out", "goodbye": word + " handled", "answered": word + " handled",
                     "handoff": word + " handed to a person", "texted": word + " handled", "unanswered": word + " not understood"}.get(c["outcome"], word + " in progress")
            out.append({"id": "c%d" % c["id"], "kind": c["channel"] if c["channel"] == "call" else "text", "title": title, "sub": c["summary"], "t": c["updated"], "tone": "bad" if c["outcome"] in ("emergency", "poison", "secret") else "you" if c["needs_person"] else "good", "conv": c["id"]})
    if kind in ("", "order"):
        for o in tracker.orders(agent, limit=40)["orders"]:
            if o["history"]:
                t, label = o["history"][-1]
                out.append({"id": "o" + o["order"], "kind": "order", "title": "Order #%s %s" % (o["order"], label.lower()), "sub": "Customer link updated", "t": t, "tone": "good"})
    if kind in ("", "problem"):
        for j in jobs or []:
            if kind == "problem" and j.get("status") not in ("failed", "blocked", "undelivered", "expired", "needs_review"):
                continue
            if kind == "" and j.get("status") in ("needs_approval", "proposed"):
                continue
            out.append({"id": "j" + str(j.get("id")), "kind": "problem" if j.get("tone") == "bad" else "sent", "title": KIND_TITLE.get(j.get("kind"), j.get("title") or "Message"), "sub": (j.get("title") or "") + " · " + (j.get("label") or LABEL.get(j.get("status"), "")), "t": j.get("updated", now), "tone": j.get("tone") or "good"})
    out.sort(key=lambda x: -x["t"])
    return {"total": len(out), "items": out[offset:offset + limit]}


GROUPS = [("orders", "Orders", ("order", "deliver", "pickup", "pick up", "delay", "track", "shipment", "package", "repair", "laundry")),
          ("reservations", "Reservations", ("reserv", "table", "booking", "book", "appointment", "waitlist", "wait list", "visit", "check in", "check-in", "reschedul", "cancel")),
          ("hours", "Hours & info", ("hours", "open", "closed", "address", "location", "direction", "park", "menu", "price", "website")),
          ("payments", "Payments", ("pay", "card", "refund", "deposit", "invoice", "charge", "receipt", "balance")),
          ("greetings", "Greetings", ("greet", "hello", "welcome", "goodbye", "thank", "good morning", "good afternoon")),
          ("help", "Help & safety", ("hold", "transfer", "staff", "emergency", "sorry", "repeat", "understand", "manager", "911", "poison", "opt", "stop"))]
MINE = ("mine", "Added by you")


def group_of(slot, category, text):
    """Which Library filter a phrase belongs under: matched on its slot name and category first, then its words."""
    for hay in (str(slot or "") + " " + str(category or ""), str(text or "")):
        h = hay.lower().replace("_", " ")
        for key, _, words in GROUPS:
            if any(w in h for w in words):
                return key
    return "other"


def phrases(agent, q="", offset=0, limit=30, cat=""):
    """{'total', 'saved', 'items': [{id, text, label, mine, group}], 'groups': [{key, label, n}]}: your own lines first, then the bundle's. cat filters by group key ('mine' = lines you added)."""
    mine = {i["id"] for i in learned.load(agent)["items"]}; q = str(q or "").strip().lower()[:60]; cat = str(cat or "")[:20]
    rows = []; counts = {}
    for it in agent.pack.items:
        text = it.get("text", "")
        if not text:
            continue
        slot = next((s for s, i in agent.pack.slots.items() if i == it["id"] and not s.startswith("learned_")), "")
        g = group_of(slot, it.get("category"), text); own = it["id"] in mine
        for k in {"all", g, "mine" if own else None} - {None}:
            counts[k] = counts.get(k, 0) + 1
        if q and q not in text.lower():
            continue
        if cat and cat != "all" and cat != g and not (cat == "mine" and own):
            continue
        rows.append({"id": it["id"], "text": text, "label": "Added by you" if own else _pretty(slot) if slot else _pretty(it.get("category") or "phrase"), "mine": own, "group": g, "workflow": bool(slot)})
    rows.sort(key=lambda r: (not r["mine"], not r["workflow"]))
    groups = [{"key": "all", "label": "All", "n": counts.get("all", 0)}] + [{"key": k, "label": l, "n": counts.get(k, 0)} for k, l, _ in GROUPS] + [{"key": MINE[0], "label": MINE[1], "n": counts.get("mine", 0)}]
    return {"total": len(rows), "saved": len(agent.pack.items), "items": rows[offset:offset + limit], "groups": groups}


def summary_text(agent, days=1):
    """A short plain-words summary for the owner: what the agent handled over the last day(s), what needed a person, and what is waiting. Used by the {{summary}} variable of daily workflows."""
    r = insights(agent, days); label = "Yesterday" if days == 1 else f"The last {days} days"
    if not r["conversations"]:
        head = f"{label}: no customer conversations."
    else:
        bits = [f"{r['texts']} text{'s' if r['texts'] != 1 else ''}"] if r["texts"] else []
        bits += [f"{r['calls']} call{'s' if r['calls'] != 1 else ''}"] if r["calls"] else []
        head = f"{label}: {r['conversations']} conversation{'s' if r['conversations'] != 1 else ''} ({', '.join(bits)})."
        if r["ai_text_answers"]:
            head += f" Your AI answered {r['ai_text_answers']} text{'s' if r['ai_text_answers'] != 1 else ''}."
        head += f" {r['needed_person']} needed a person." if r["needed_person"] else " None needed a person."
    parts = [head]
    if r["gaps"]:
        parts.append("Questions it could not answer: " + "; ".join(g["q"] for g in r["gaps"][:3]) + ".")
    try:
        from .dashboard import jobs_for_display
        waiting = sum(1 for j in jobs_for_display(agent) if j.get("needs_you"))
    except Exception:  # noqa: BLE001
        waiting = 0
    parts.append(f"{waiting} thing{'s' if waiting != 1 else ''} waiting for you on the dashboard." if waiting else "Nothing is waiting for you.")
    return " ".join(parts)


def insights(agent, days=7):
    """How the agent did over the last days: conversations by channel and outcome, how many the AI answered or handed to a person, how fast the AI answered, what it could not answer, and the top topics."""
    import json, os
    now = int(agent.now()); since = now - int(days) * 86400
    c = CV._conn(agent)
    chan = dict(c.execute("select channel, count(*) from conv where updated>=? group by channel", (since,)).fetchall())
    outs = dict(c.execute("select outcome, count(*) from conv where updated>=? group by outcome", (since,)).fetchall())
    total = sum(chan.values()); person = c.execute("select count(*) from conv where updated>=? and (handoff=1 or outcome in ('staff','handoff'))", (since,)).fetchone()[0]
    topics = {}
    for (it,) in c.execute("select intents from conv where updated>=?", (since,)).fetchall():
        for t in json.loads(it or "[]"):
            topics[t] = topics.get(t, 0) + 1
    ai = {"answered": 0, "handed_off": 0, "ms": []}
    try:
        with open(agent.state.log_path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("t", 0) < since or d.get("workflow") != "sms_ai" or d.get("action") != "reply":
                    continue
                ai["handed_off" if d.get("handoff") else "answered"] += 1
                if d.get("ai_ms"):
                    ai["ms"].append(int(d["ai_ms"]))
    except OSError:
        pass
    ms = sorted(ai["ms"]); med = ms[len(ms) // 2] if ms else None
    from . import knowledge
    kv = knowledge.view(agent)
    return {"days": days, "conversations": total, "calls": chan.get("call", 0), "texts": chan.get("sms", 0), "needed_person": person, "person_pct": round(100 * person / total) if total else 0,
            "ai_text_answers": ai["answered"], "ai_text_handoffs": ai["handed_off"], "ai_median_ms": med, "topics": sorted(topics.items(), key=lambda x: -x[1])[:6],
            "gaps": [{"q": g["q"], "n": g["n"]} for g in kv["gaps"][:5]], "knowledge_sources": len(kv["sources"]), "outcomes": outs}
