"""`doctor` (is my setup right?) and `events` (what do I send from my app?). Both work before any key is set."""
import json, os, shutil, sys, urllib.request

from .engine import Agent

SAMPLE = {
    "order": {"order": {"number": 42, "extra_minutes": 10}}, "table": {"party": 2}, "reservation": {"party": 4, "start_epoch": 1791900000, "start_text": "Tue 7:00 PM"},
    "appointment": {"start_epoch": 1791900000, "start_text": "Tue 9:00 AM", "minutes": 30}, "visit": {}, "pipeline": {"repo": "acme/app", "branch": "main", "author": "dev1", "url": "https://example.com/run/1"},
    "deploy": {"repo": "acme/app", "branch": "main", "url": "https://example.com/deploy/1"}, "incident": {"incident": {"title": "Database down"}, "url": "https://example.com/inc/1"}, "security": {"repo": "acme/app", "url": "https://example.com/alert/1"},
    "pull_request": {"repo": "acme/app", "title": "Add feature", "author": "dev1", "url": "https://example.com/pr/1"}, "release": {"repo": "acme/app", "title": "v1.2.0", "url": "https://example.com/r/1"}, "issue": {"repo": "acme/app", "title": "Bug", "url": "https://example.com/i/1"},
    "ticket": {"ticket": {"summary": "We fixed it"}}, "account": {}, "payment": {}, "callback": {"start_text": "Tue 3:00 PM"}, "customer": {"reason": "needs a person"}, "facility": {},
}
CUSTOMER = {"name": "Ann Lee", "phone": "+16465550101", "sms_consent": True}


def events_of(agent):
    return sorted({(w.get("on") or {}).get("event") for w in agent.workflows if (w.get("on") or {}).get("event")})


def sample(event):
    body = {"event": event, "id": "evt-" + event.replace(".", "-") + "-1", "customer": dict(CUSTOMER)}
    body.update(SAMPLE.get(event.split(".")[0], {}))
    return body


def snippet(lang, base, body):
    j = json.dumps(body, separators=(",", ":"))
    if lang == "curl":
        return ("BODY='%s'\nTS=$(date +%%s)\nSIG=$(printf '%%s.%%s' \"$TS\" \"$BODY\" | openssl dgst -sha256 -hmac \"$SV_EVENT_SECRET\" | sed 's/^.* //')\n"
                "curl -X POST %s/event -H \"content-type: application/json\" -H \"X-SV-Timestamp: $TS\" -H \"X-SV-Signature: sha256=$SIG\" -d \"$BODY\"" % (j, base))
    if lang == "python":
        return ("import hashlib, hmac, json, os, time, urllib.request\nbody = json.dumps(%s).encode()\nts = str(int(time.time()))\nsig = hmac.new(os.environ['SV_EVENT_SECRET'].encode(), ts.encode() + b'.' + body, hashlib.sha256).hexdigest()\n"
                "urllib.request.urlopen(urllib.request.Request('%s/event', data=body, headers={'content-type': 'application/json', 'X-SV-Timestamp': ts, 'X-SV-Signature': 'sha256=' + sig}), timeout=2)" % (body, base))
    if lang == "node":
        return ("import crypto from 'node:crypto';\nconst body = JSON.stringify(%s);\nconst ts = String(Math.floor(Date.now() / 1000));\nconst sig = crypto.createHmac('sha256', process.env.SV_EVENT_SECRET).update(ts + '.' + body).digest('hex');\n"
                "await fetch('%s/event', { method: 'POST', body, headers: { 'content-type': 'application/json', 'X-SV-Timestamp': ts, 'X-SV-Signature': 'sha256=' + sig }, signal: AbortSignal.timeout(2000) });" % (j, base))
    if lang == "php":
        return ("<?php\n$body = '%s';\n$ts = (string) time();\n$sig = hash_hmac('sha256', $ts . '.' . $body, getenv('SV_EVENT_SECRET'));\n$ctx = stream_context_create(['http' => ['method' => 'POST', 'timeout' => 2, 'header' => \"content-type: application/json\\r\\nX-SV-Timestamp: $ts\\r\\nX-SV-Signature: sha256=$sig\", 'content' => $body]]);\n"
                "@file_get_contents('%s/event', false, $ctx);" % (j, base))
    if lang == "ruby":
        return ("require 'net/http'; require 'openssl'; require 'json'\nbody = '%s'\nts = Time.now.to_i.to_s\nsig = OpenSSL::HMAC.hexdigest('SHA256', ENV['SV_EVENT_SECRET'], \"#{ts}.#{body}\")\n"
                "Net::HTTP.post(URI('%s/event'), body, 'content-type' => 'application/json', 'X-SV-Timestamp' => ts, 'X-SV-Signature' => \"sha256=#{sig}\")" % (j, base))
    return ("package main\n\nimport (\n\t\"crypto/hmac\"\n\t\"crypto/sha256\"\n\t\"encoding/hex\"\n\t\"fmt\"\n\t\"net/http\"\n\t\"os\"\n\t\"strings\"\n\t\"time\"\n)\n\nfunc main() {\n\tbody := `%s`\n\tts := fmt.Sprint(time.Now().Unix())\n"
            "\tm := hmac.New(sha256.New, []byte(os.Getenv(\"SV_EVENT_SECRET\")))\n\tm.Write([]byte(ts + \".\" + body))\n\treq, _ := http.NewRequest(\"POST\", \"%s/event\", strings.NewReader(body))\n\treq.Header.Set(\"content-type\", \"application/json\")\n"
            "\treq.Header.Set(\"X-SV-Timestamp\", ts)\n\treq.Header.Set(\"X-SV-Signature\", \"sha256=\"+hex.EncodeToString(m.Sum(nil)))\n\t(&http.Client{Timeout: 2 * time.Second}).Do(req)\n}" % (j, base))


def events(cfg, lang="curl"):
    ag = Agent(cfg); base = f"http://{cfg['listen']['host']}:{cfg['listen']['port']}"; names = events_of(ag)
    print(f"This pack's workflows react to {len(names)} events from your app. Send one when it happens (the signature uses your SV_EVENT_SECRET):\n")
    for n in names:
        print(f"## {n}\n{snippet(lang, base, sample(n))}\n")
    print("Texts, calls and email also work without any code from your app: customers text or call your number, and calendar events trigger reminders. Webhooks from other tools are mapped in agent.json (sh sv-agent source list).")
    return 0


def run(cfg):
    ok = lambda b, msg, fix="": print(("  ok   " if b else "  FIX  ") + msg + ("" if b or not fix else "\n         -> " + fix))  # noqa: E731
    print("speakvora-pack-agent doctor\n")
    ok(sys.version_info >= (3, 9), f"Python {sys.version.split()[0]}", "install Python 3.9 or newer")
    try:
        ag = Agent(cfg)
    except Exception as e:  # noqa: BLE001
        ok(False, "agent.json and the pack load", str(e)); return 1
    ok(True, f"pack: {ag.pack.meta.get('title')} ({ag.pack.language}, {len(ag.pack.items)} lines), industry profile {ag.profile}")
    miss = [i for i in ag.pack.missing_audio() if i in set(ag.pack.slots.values())]
    ok(not miss, "workflow-line audio files are all there", f"{len(miss)} missing: unzip the pack again")
    ok(not ag.missing_required, "required notices have audio", "they will be spoken in your phone provider's voice until added (sh sv-agent slots --send)")
    ok(not ag.missing_slots, "no missing spoken lines for your workflows", "sh sv-agent slots --send asks Speakvora to write them")
    m4a = any(i["file"].endswith(".m4a") for i in ag.pack.items[:3])
    ok(not m4a or shutil.which("ffmpeg") is not None, "phone calls can play the audio (mp3 or ffmpeg installed)", "install ffmpeg so the pack's .m4a lines can play on calls (brew install ffmpeg / apt install ffmpeg)")
    if cfg.get("_missing_env"):
        ok(False, "environment variables for your services", "set: " + ", ".join(cfg["_missing_env"]))
    else:
        ok(True, "all environment variables referenced in agent.json are set")
    for n, svc in (("Twilio (texts and calls)", ag.twilio), ("Slack", ag.slack), ("Microsoft Teams", ag.teams), ("Google Calendar", ag.gcal), ("Microsoft 365 calendar", ag.outlook), ("email (SMTP)", ag.mail), ("inbound email (IMAP)", ag.inbox)):
        print(f"  {'conn' if svc.configured else '--  '} {n}: {'configured' if svc.configured else 'not configured (optional)'}")
    base = cfg.get("public_base_url", "")
    placeholder = "YOUR-" in base or not base
    ok(not placeholder, "public_base_url is set", "this is the public https address that Twilio, Slack and your webhooks use to reach the agent (a tunnel such as cloudflared or ngrok works while testing)")
    if cfg["listen"]["host"] != "127.0.0.1":
        print("  note listening on all interfaces: put it behind HTTPS (a reverse proxy or tunnel)")
    local = f"http://{cfg['listen']['host']}:{cfg['listen']['port']}/health"
    try:
        h = json.load(urllib.request.urlopen(local, timeout=2)); ok(True, f"the agent is running ({'DRY RUN' if h.get('dry_run') else 'LIVE'})")
        if not placeholder:
            try:
                urllib.request.urlopen(base.rstrip("/") + "/health", timeout=6); ok(True, "the public address reaches the agent")
            except Exception as e:  # noqa: BLE001
                ok(False, "the public address reaches the agent", f"{type(e).__name__}: check your tunnel/proxy forwards to port {cfg['listen']['port']}")
    except Exception:  # noqa: BLE001
        print("  --   the agent is not running yet: start it with  sh sv-agent run   then run doctor again to test the public address")
    if not placeholder:
        print(f"\nPoint your services at: Twilio texts {base}/twilio/sms | Twilio calls {base}/twilio/call | Slack command {base}/slack/command | app events {base}/event | webhooks {base}/hook/<name>")
    print(f"\nMode: {cfg.get('mode', 'standard')}  | dry_run: {cfg.get('dry_run', True)}.  Next: sh sv-agent events  (copy-paste examples for your app)")
    return 0
