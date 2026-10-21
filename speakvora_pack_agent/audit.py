"""Who changed what, and a view-only access code.
The audit log (agent-state/audit.jsonl) records every change made from the dashboard: when, by whom (owner or viewer) and what, in plain words. It never records what you typed, so keys, messages and customer details never land in it. It keeps the last 5,000 entries.
The view-only code (agent-state/viewer-token) lets someone look at Home, activity and the library without being able to change anything. It is off until the owner switches it on, can be replaced at any time, and works only where the dashboard itself can be reached."""
import json, os, secrets, threading, time

KEEP = 5000
_LOCK = threading.Lock()
LABELS = {
    "/dash/api/setup/save": "Saved business details", "/dash/api/setup/live": "Switched sending mode", "/dash/api/setup/tool/save": "Connected or changed an app", "/dash/api/setup/tool/remove": "Removed an app", "/dash/api/setup/tool/secret": "Saved an app key",
    "/dash/api/setup/pair": "Paired with Speakvora", "/dash/api/setup/disconnect": "Disconnected something", "/dash/api/setup/connection": "Added a connection", "/dash/api/setup/connection/remove": "Removed a connection", "/dash/api/setup/twilio/point": "Pointed a phone number at the agent", "/dash/api/setup/channel/connect": "Connected a message channel to the agent", "/dash/api/support/send": "Emailed a setup report to Speakvora support",
    "/dash/api/setup/workflow": "Switched a ready-made workflow on or off", "/dash/api/setup/workflow-targets": "Changed where a workflow also tells", "/dash/api/setup/source": "Added a tool that sends events", "/dash/api/setup/incoming": "Changed an incoming connection", "/dash/api/setup/incoming/remove": "Removed an incoming connection",
    "/dash/api/policy": "Changed ask-before-sending rules", "/dash/api/controls/policy": "Changed what the AI may do", "/dash/api/guardrails": "Changed safeguards or privacy", "/dash/api/pause": "Paused or resumed sending",
    "/dash/api/workflows/save": "Saved a workflow", "/dash/api/workflows/delete": "Deleted a workflow", "/dash/api/workflows/toggle": "Switched a workflow on or off",
    "/dash/api/knowledge/text": "Added knowledge text", "/dash/api/knowledge/qa": "Added a quick answer", "/dash/api/knowledge/upload": "Added a document", "/dash/api/knowledge/site": "Added a web page", "/dash/api/knowledge/remove": "Removed knowledge",
    "/dash/api/brain/save": "Changed business details for the AI", "/dash/api/brain/forget": "Cleared what the AI learned", "/dash/api/learned/add": "Added a line to the library", "/dash/api/learned/lines": "Added your own lines", "/dash/api/learned/remove": "Removed a library line",
    "/dash/api/library/share": "Changed sharing of missing lines", "/dash/api/library/submit": "Sent missing lines to Speakvora", "/dash/api/licence": "Entered a licence code", "/dash/api/locations/add": "Added a location", "/dash/api/locations/remove": "Removed a location", "/dash/api/locations/enable": "Changed the locations menu",
    "/dash/api/conversations/delete": "Deleted a conversation", "/dash/api/viewer": "Changed view-only access", "/dash/api/phrases": "Changed library phrases"}
SKIP = ("/dash/api/simulate", "/dash/api/chat", "/dash/api/chat/clear", "/dash/api/workflows/preview", "/dash/api/knowledge/try", "/dash/api/voice/check", "/dash/api/setup/test", "/dash/api/setup/tool/test", "/dash/api/setup/connection/test",
        "/dash/api/setup/public-check", "/dash/api/locations/session", "/dash/api/locations/test", "/dash/api/conversations/switch", "/dash/api/conversations/summary", "/dash/api/orderpages/switch", "/dash/api/learned/suggest", "/dash/api/learned/write", "/dash/api/learned/dismiss")


def _path(agent):
    return os.path.join(agent.state.dir, "audit.jsonl")


def _viewer_path(agent):
    return os.path.join(agent.state.dir, "viewer-token")


def record(agent, who, method, path):
    """One line per change. `path` decides the wording; nothing from the request body is kept."""
    p = path.split("?")[0]
    if method == "GET" or p in SKIP or p.startswith("/dash/api/jobs/") and p.endswith(("/preview",)):
        return
    if p.startswith("/dash/api/jobs/"):
        label = {"approve": "Approved a message", "decline": "Declined a message", "cancel": "Cancelled a message", "retry": "Retried a message", "mark-sent": "Marked a message as sent"}.get(p.rsplit("/", 1)[-1], "Changed a message")
    else:
        label = LABELS.get(p, "Changed settings (" + p.replace("/dash/api/", "") + ")")
    line = json.dumps({"t": int(time.time()), "who": who, "what": label}, ensure_ascii=False)
    with _LOCK:
        os.makedirs(agent.state.dir, exist_ok=True)
        with open(_path(agent), "a", encoding="utf-8") as f:
            f.write(line + "\n")
        try:
            if os.path.getsize(_path(agent)) > KEEP * 120:
                rows = open(_path(agent), encoding="utf-8").read().splitlines()[-KEEP:]
                open(_path(agent), "w", encoding="utf-8").write("\n".join(rows) + "\n")
        except OSError:
            pass


def view(agent, limit=200):
    try:
        rows = [json.loads(x) for x in open(_path(agent), encoding="utf-8").read().splitlines() if x.strip()]
    except (OSError, ValueError):
        rows = []
    return {"entries": rows[-int(limit):][::-1], "viewer": viewer_state(agent)}


def viewer_token(agent):
    """The current view-only code, or '' when view-only access is off."""
    try:
        return open(_viewer_path(agent), encoding="utf-8").read().strip()
    except OSError:
        return ""


def viewer_state(agent):
    return {"on": bool(viewer_token(agent))}


def set_viewer(agent, on, rotate=False):
    """Switch view-only access on or off, or replace the code (the old one stops working at once). Returns {'on', 'token'}: the code is shown only to the owner."""
    p = _viewer_path(agent)
    if not on:
        try:
            os.remove(p)
        except OSError:
            pass
        return {"on": False, "token": ""}
    if rotate or not viewer_token(agent):
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(16))
    return {"on": True, "token": viewer_token(agent)}
