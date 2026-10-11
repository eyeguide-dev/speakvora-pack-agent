"""The ONLY change a restaurant app needs: call notify() where something happens. It sends one signed web request to the agent, never waits more than two seconds and never raises, so the agent being down can not break your app."""
import hashlib, hmac, json, os, time, urllib.request, uuid

AGENT_URL = os.environ.get("SV_AGENT_URL", "http://127.0.0.1:8787")
SECRET = os.environ.get("SV_EVENT_SECRET", "")


def notify(event, **payload):
    try:
        body = json.dumps({"event": event, "id": f"{event}-{uuid.uuid4().hex[:12]}", **payload}).encode()
        ts = str(int(time.time()))
        sig = "sha256=" + hmac.new(SECRET.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        urllib.request.urlopen(urllib.request.Request(AGENT_URL + "/event", data=body, method="POST", headers={"content-type": "application/json", "X-SV-Timestamp": ts, "X-SV-Signature": sig}), timeout=2).read()
    except Exception:  # noqa: BLE001  never break the app
        pass
