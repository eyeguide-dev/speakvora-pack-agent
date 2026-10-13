"""`sv-agent demo`: a 30-second tour that needs no keys, no placeholders and no internet. It fires a sample "order ready" event at your pack in dry run (nothing is sent, nothing is queued),
prints the text it WOULD send, and plays the recorded line it would speak. Your agent.json is not changed and nothing is written to your agent-state folder."""
import json, os, shutil, subprocess, sys, tempfile

from . import config
from .engine import Agent

PLACEHOLDER_FACTS = {"hours": "Daily 9 AM to 5 PM", "address": "1 Demo Street", "review_url": "https://example.com/review", "oncall_phone": ""}


def play(path):
    """Plays an audio file with the first player this computer has. Returns the name of the player used, or None."""
    if sys.platform == "darwin" and shutil.which("afplay"):
        subprocess.run(["afplay", path], check=False); return "afplay"
    if sys.platform.startswith("win"):
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Add-Type -AssemblyName presentationCore; $p=New-Object System.Windows.Media.MediaPlayer; $p.Open('{path}'); $p.Play(); Start-Sleep 1; while($p.NaturalDuration.HasTimeSpan -eq $false){{Start-Sleep -m 100}}; Start-Sleep -s ([int]$p.NaturalDuration.TimeSpan.TotalSeconds + 1)"], check=False); return "powershell"
    for name, args in (("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]), ("mpv", ["--no-video", "--really-quiet"]), ("paplay", []), ("aplay", ["-q"])):
        if shutil.which(name):
            subprocess.run([name, *args, path], check=False); return name
    return None


def run(config_path, speak=True):
    cfg = config.load(config_path, lazy_secrets=True)
    tmp = tempfile.mkdtemp(prefix="sv-demo-")
    cfg["state_dir"] = tmp; cfg["dry_run"] = True
    if "YOUR-" in str(cfg.get("business", "")) or not cfg.get("business"):
        cfg["business"] = "Demo Bistro"
    for k, v in PLACEHOLDER_FACTS.items():
        if "YOUR-" in str(cfg.setdefault("facts", {}).get(k, "YOUR-")):
            cfg["facts"][k] = v
    cfg["quiet_hours"] = {"start": "00:00", "end": "00:00", "applies_to": []}               # the demo must give the same answer at any time of day
    cfg.setdefault("limits", {}).update({"per_recipient_per_day": None, "per_hour": None})
    ag = Agent(cfg)
    ev = {"event": "order.ready", "id": "demo-1", "customer": {"name": "Sam Demo", "phone": "+15555550100", "sms_consent": True}, "order": {"number": 42}}
    if not any((w.get("on") or {}).get("event") == "order.ready" for w in ag.workflows):
        print("This pack's workflows do not include an 'order.ready' event; run  sv-agent events  to see the events it reacts to."); return 0
    print(f"Pack: {ag.pack.meta.get('title')} ({len(ag.pack.items)} recorded lines).  Mode: DRY RUN, so nothing is sent and nothing is queued.\n")
    print("Your order system tells the agent:  order.ready  (order 42, customer Sam Demo, has agreed to texts)\n")
    ag.handle_event(ev)
    rows = []
    if os.path.exists(ag.state.log_path):
        with open(ag.state.log_path, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh]
    for r in rows:
        what = {"sms": "a text message", "slack": "a Slack post", "call": "a phone call", "email": "an email", "teams": "a Teams post"}.get(r.get("action"), r.get("action"))
        if r.get("status") == "dry_run":
            print(f"  WOULD SEND {what}: {r.get('text') or r.get('body') or '(recorded line)'}")
        else:
            print(f"  {what}: {r.get('status')} ({r.get('reason') or ''})")
    try:
        line = ag.pack.get("order_ready")
        print(f"\nThe recorded line that goes with it: \"{line.get('text')}\"")
        path = ag.pack.audio_path("order_ready")
        if speak:
            used = play(path)
            print("(played it for you)" if used else f"(no audio player found; open this file to hear it: {path})")
    except Exception:  # noqa: BLE001
        pass
    print("\nWhat this did NOT do: send anything. Real sends need a connection (texts and calls need your Twilio account) and live mode.")
    print("Next:  sv-agent run   then open the dashboard address it prints, connect a service, switch on Go live.")
    print("Offline queue: dry run never queues. The queue only fills in live mode, when a send fails because the internet is down; see docs/offline-and-queue.md.")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0
