"""The Home screen's feed and the Library's phrase list, as plain data the dashboard draws.
activity(): calls and texts, messages the agent sent, and order steps, newest first, each with a title a business owner would say aloud.
phrases(): the lines in this bundle's library (the ones that came with it and the ones you added) for the Library tab, with search."""
import re, time

from . import conversations as CV, learned, tracker

LABEL = {"sent": "Sent", "delivered": "Delivered", "failed": "Failed", "undelivered": "Not delivered", "blocked": "Held back", "queued": "Waiting", "needs_review": "Needs a look", "expired": "Expired", "cancelled": "Dismissed"}
KIND_TITLE = {"sms": "Text sent", "call": "Call placed", "slack": "Team updated", "teams": "Team updated", "email": "Email sent", "http": "Sent to your app", "webhook": "Sent to your app", "calendar_create": "Calendar entry added", "reason": "AI suggestion"}


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
