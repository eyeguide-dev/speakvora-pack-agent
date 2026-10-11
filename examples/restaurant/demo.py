#!/usr/bin/env python3
"""End-to-end demo with NO real accounts: a fake restaurant app + the pack agent + fake Twilio, Slack and Google servers on your machine.
Usage: python3 demo.py [PATH_TO_UNZIPPED_PACK]     (with no path it uses a silent demo pack, so it runs anywhere)
It runs the restaurant through a day and prints exactly what the agent did (and what it refused to do)."""
import json, os, shutil, sys, tempfile, threading, time, urllib.parse, urllib.request, hmac, hashlib, base64
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..", "..")); sys.path.insert(0, os.path.join(HERE, "..", "..", "tests")); sys.path.insert(0, HERE)
from mocks import Mock

def synthetic_pack(dest):
    """A pack folder made of silent placeholder clips, so the demo runs with no Speakvora pack and no accounts. The words are real (lines/restaurants.en.json); the audio is silence."""
    lines = json.load(open(os.path.join(HERE, "..", "..", "lines", "restaurants.en.json"), encoding="utf-8"))["lines"]
    os.makedirs(os.path.join(dest, "workflow_lines"), exist_ok=True); items = []
    for i, ln in enumerate(lines, 1):
        f = f"workflow_lines/w{i:02d}.mp3"; open(os.path.join(dest, f), "wb").write(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 413); items.append({"id": f"w{i:02d}", "slot": ln["slot"], "text": ln["text"], "file": f})
    json.dump({"items": items}, open(os.path.join(dest, "workflow_lines.json"), "w"))
    json.dump({"pack": "en-restaurants-food-demo", "title": "Demo restaurant pack (silent)", "language": "en", "voice": "demo", "items": []}, open(os.path.join(dest, "manifest.json"), "w"))
    return dest


pack_dir = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else synthetic_pack(tempfile.mkdtemp())
tmp = tempfile.mkdtemp(); mock = Mock(); SECRET = "demo-secret"
os.environ["SV_EVENT_SECRET"] = SECRET
from speakvora_pack_agent import config as C
from speakvora_pack_agent.engine import Agent
from speakvora_pack_agent.server import serve


def start_agent(dry):
    raw = json.load(open(os.path.join(HERE, "agent.json"))); raw.update(dry_run=dry, pack=pack_dir, workflows=os.path.join(HERE, "workflows.json"), state_dir=os.path.join(tmp, "dry" if dry else "live"), quiet_hours={"start": "00:00", "end": "00:00", "applies_to": []})
    raw["events"] = {"secret": SECRET}; raw["listen"] = {"host": "127.0.0.1", "port": 0}
    raw["twilio"] = {"account_sid": "ACdemo", "auth_token": "demo-token", "from_number": "+15550001111", "api_base": mock.url}
    raw["slack"] = {"bot_token": "xoxb-demo", "signing_secret": "demo-signing", "channel": "#front", "api_base": mock.url}
    raw["google_calendar"] = {"mode": "oauth", "client_id": "c", "client_secret": "s", "refresh_token": "r", "api_base": mock.url, "token_url": mock.url + "/token", "allow_create": True}
    p = os.path.join(tmp, f"agent-{dry}.json"); json.dump(raw, open(p, "w")); cfg = C.load(p); a = Agent(cfg); srv = serve(a, "127.0.0.1", 0, tick_seconds=3600)
    port = srv.server_address[1]; cfg["public_base_url"] = a.audio.base = f"http://127.0.0.1:{port}"; threading.Thread(target=srv.serve_forever, daemon=True).start(); return a, srv, port


def run_app(port):
    os.environ["SV_AGENT_URL"] = f"http://127.0.0.1:{port}"
    import importlib, agent_hook, app; importlib.reload(agent_hook); importlib.reload(app)
    srv = app.serve(0); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv.server_address[1]


def post(url, data):
    body = urllib.parse.urlencode(data).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=10))


def twilio_post(agent, port, path, params):
    url = f"http://127.0.0.1:{port}{path}"; sig = base64.b64encode(hmac.new(b"demo-token", (url + "".join(k + params[k] for k in sorted(params))).encode(), hashlib.sha1).digest()).decode()
    req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method="POST", headers={"X-Twilio-Signature": sig}); return urllib.request.urlopen(req, timeout=10).read().decode()


def show(title, since):
    print(f"\n== {title}")
    for r in mock.requests[since:]:
        p = r["path"]
        if p.endswith("Messages.json"): print(f"   TEXT   to {r['form']['To']}: {r['form']['Body']}")
        elif p.endswith("Calls.json"): print(f"   CALL   to {r['form']['To']}: plays {r['form']['Twiml'].count('<Play>')} pack clips")
        elif p.endswith("chat.postMessage"): print(f"   SLACK  {r['json']['channel']}: {r['json']['text']}")
        elif p.endswith("/events") and r["method"] == "POST": print(f"   CAL    created: {r['json']['summary']}")
    if len(mock.requests) == since: print("   (nothing sent)")


# 1) dry run first: the default
a, srv, port = start_agent(dry=True); app_port = run_app(port)
n = len(mock.requests)
post(f"http://127.0.0.1:{app_port}/orders", {"name": "Ann Lee", "phone": "646-555-0101", "sms_consent": "1", "item": "Margherita"}); post(f"http://127.0.0.1:{app_port}/orders/41/ready", {})
time.sleep(0.5); show("DRY RUN: kitchen taps Ready (default mode)", n)
print("   what the agent WOULD have done:", [(x["action"], x["status"]) for x in [json.loads(l) for l in open(a.state.log_path)]])
srv.shutdown()

# 2) live (against the fake services)
a, srv, port = start_agent(dry=False); app_port = run_app(port); A = f"http://127.0.0.1:{app_port}"
n = len(mock.requests)
post(A + "/orders", {"name": "Ann Lee", "phone": "646-555-0101", "sms_consent": "1", "item": "Margherita"}); post(A + "/orders", {"name": "Bo Chen", "phone": "646-555-0102", "item": "Carbonara"})
post(A + "/orders/41/ready", {}); post(A + "/orders/42/ready", {}); time.sleep(0.6)
show("LIVE: kitchen marks two orders ready (Ann said yes to texts, Bo did not)", n)
n = len(mock.requests); post(A + "/orders/41/delayed", {}); post(A + "/orders/41/done", {}); time.sleep(0.6); show("Delay, then pickup completed", n)
n = len(mock.requests); post(A + "/reservations", {"name": "Cy Diaz", "phone": "646-555-0103", "sms_consent": "1", "party": "4", "start_epoch": str(int(time.time()) + 86400)}); time.sleep(0.5); show("A reservation is made in the app", n)
n = len(mock.requests); post(A + "/reservations/1/table", {}); post(A + "/reservations/1/noshow", {}); time.sleep(0.5); show("Host: table ready, then no-show", n)
n = len(mock.requests); mock.events = [{"id": "ev9", "summary": "Reservation: Di Wu party of 2", "description": "Name: Di Wu\nPhone: 646-555-0104\nSMS OK: yes", "start": {"dateTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 24 * 3600 - 300))}, "end": {"dateTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 24 * 3600 + 5000))}}]
a.tick(); show("Google Calendar: a reservation starts in 24 hours", n)
print("\n== Customers text and call the restaurant")
for body in ("What are your hours?", "where are you located", "I want to reserve a table", "get me a manager", "STOP"):
    print(f"   text  '{body}' ->", twilio_post(a, port, "/twilio/sms", {"From": "+16465550109", "Body": body}).replace("<Response>", "").replace("</Response>", "")[:150])
print("   call  start ->", twilio_post(a, port, "/twilio/call", {"From": "+16465550109"})[:110], "...")
print("   call  press 1 ->", twilio_post(a, port, "/twilio/call/menu", {"From": "+16465550109", "Digits": "1"})[:170], "...")
n = len(mock.requests); a.handle_event({"event": "order.ready", "id": "after-stop", "customer": {"name": "Stopper", "phone": "646-555-0109", "sms_consent": True}, "order": {"number": 99}}); show("After that customer replied STOP, an order for them is marked ready", n)
logs = [json.loads(l) for l in open(a.state.log_path)]; blocked = [(x["action"], x.get("reason")) for x in logs if x["status"] == "blocked"]
print("\n== Refused by the safety rules:", blocked)
print("== Totals sent:", {"texts": len(mock.calls('Messages.json')), "calls": len(mock.calls('Calls.json')), "slack": len(mock.calls('chat.postMessage')), "calendar events": len([r for r in mock.requests if r['path'].endswith('/events') and r['method'] == 'POST'])})
srv.shutdown(); mock.close(); shutil.rmtree(tmp, ignore_errors=True)
