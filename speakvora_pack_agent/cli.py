"""Command line: check, run, phrases, event."""
import argparse, json, sys

from . import __version__, config, signing_cli
from .engine import Agent
from .pack import Pack, PackError
from .server import serve


def main(argv=None):
    ap = argparse.ArgumentParser(prog="speakvora-pack-agent", description="Turn an offline Speakvora pack into a small agent for your calendar, Slack, phone and texts.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="validate agent.json, the pack, the workflows and which services are connected"); c.add_argument("-c", "--config", default="agent.json")
    r = sub.add_parser("run", help="start the agent"); r.add_argument("-c", "--config", default="agent.json"); r.add_argument("--live", action="store_true", help="really send texts, calls and messages (default is dry-run)")
    p = sub.add_parser("phrases", help="search the pack"); p.add_argument("words", nargs="*"); p.add_argument("--pack", default="./pack"); p.add_argument("--category", default="")
    i = sub.add_parser("init", help="write agent.json and workflows.json for this pack's industry"); i.add_argument("--pack", default="./pack"); i.add_argument("--force", action="store_true")
    i.add_argument("--mode", choices=["strict", "standard", "open"], default="standard", help="open = no per-person or hourly limits and no quiet hours (opt-outs, required notices and the kill switch stay on)")
    i.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)
    dm = sub.add_parser("demo", help="a 30-second tour with no keys: fires a sample event in dry run, shows the text it would send and plays the recorded line"); dm.add_argument("-c", "--config", default="agent.json"); dm.add_argument("--silent", action="store_true", help="do not play audio")
    dc = sub.add_parser("doctor", help="check your setup and tell you what to fix next"); dc.add_argument("-c", "--config", default="agent.json")
    ev = sub.add_parser("events", help="list the events this pack reacts to, with ready-to-paste examples for curl, Python, Node, PHP, Ruby and Go"); ev.add_argument("-c", "--config", default="agent.json"); ev.add_argument("--lang", default="curl", choices=["curl", "python", "node", "php", "ruby", "go"])
    so = sub.add_parser("source", help="connect a tool: list the ready-made mappings, or add one (github, gitlab, pagerduty, stripe, shopify, calendly, generic-pos)"); so.add_argument("action", choices=["list", "add"]); so.add_argument("name", nargs="?"); so.add_argument("-c", "--config", default="agent.json")
    sl = sub.add_parser("slots", help="which spoken lines this pack still lacks for your workflows; write or send the request for the missing ones")
    sl.add_argument("-c", "--config", default="agent.json"); sl.add_argument("--all", action="store_true", help="every line the industry normally needs, not only the ones your workflows use")
    sl.add_argument("--write", action="store_true", help="write slot-requests.json"); sl.add_argument("--send", action="store_true", help="send the request to Speakvora (needs SPEAKVORA_KEY)")
    qu = sub.add_parser("queue", help="actions waiting for the internet: list them, send them now, or drop them"); qu.add_argument("action", choices=["list", "flush", "drop"]); qu.add_argument("id", nargs="?", help="a queue id, or 'all' for drop"); qu.add_argument("-c", "--config", default="agent.json")
    jb = sub.add_parser("jobs", help="every send the agent made or waits to make: list, cancel, retry, mark sent"); jb.add_argument("action", choices=["list", "cancel", "retry", "mark-sent"]); jb.add_argument("id", nargs="?"); jb.add_argument("-c", "--config", default="agent.json")
    jb.add_argument("--status", default="", help="list only this status (pending, sending, queued, sent, delivered, undelivered, needs_review, failed, blocked, expired, cancelled)"); jb.add_argument("--confirm-not-sent", action="store_true", help="for retry of a needs_review job: you checked with the provider and it did NOT arrive")
    pr = sub.add_parser("proposals", help="what a reasoning step suggested: list, approve or reject (nothing runs until you approve)"); pr.add_argument("action", choices=["list", "approve", "reject"]); pr.add_argument("id", nargs="?"); pr.add_argument("--only", default="", help="comma-separated proposal numbers, for example 0,2"); pr.add_argument("-c", "--config", default="agent.json")
    sa = sub.add_parser("start", help="the easy way: set everything up the first time, start the agent in practice mode and open the dashboard in your browser"); sa.add_argument("-c", "--config", default="agent.json"); sa.add_argument("--no-browser", action="store_true", help="do not open the browser")
    e = sub.add_parser("event", help="send a signed test event to a running agent"); e.add_argument("-c", "--config", default="agent.json"); e.add_argument("file"); e.add_argument("--url", default="")
    a = ap.parse_args(argv)
    if a.cmd == "phrases":
        for it in Pack(a.pack).search(" ".join(a.words), a.category, 25):
            print(f"{it['id']:>6}  [{it.get('category','')}]  {it['text']}")
        return 0
    if a.cmd == "source":
        import os
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sources"); names = sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))
        if a.action == "list" or not a.name:
            print("ready-made sources:", ", ".join(names)); return 0
        if a.name not in names:
            print("unknown source; choose from:", ", ".join(names)); return 1
        src = json.load(open(os.path.join(d, a.name + ".json"), encoding="utf-8")); cfgd = json.load(open(a.config, encoding="utf-8"))
        cfgd["sources"] = [x for x in cfgd.get("sources", []) if x.get("name") != src["name"]] + [src]; json.dump(cfgd, open(a.config, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"added '{src['name']}' to {a.config}. In that tool, send webhooks to https://YOUR-AGENT{src['path']} and set the environment variable named in auth.secret (or token).")
        return 0
    if a.cmd == "init":
        import os
        from . import recipes, slots as SL
        pk = Pack(a.pack); _lang, slug = SL.pack_slug(str(pk.meta.get("pack", ""))); prof = SL.profile_for(slug)
        for name, doc in (("agent.json", {**recipes.agent_config(), "pack": a.pack, "mode": a.mode}), ("workflows.json", recipes.workflows_for(prof, pk.language))):
            if os.path.exists(name) and not a.force:
                print(f"{name} already exists (use --force to replace)"); continue
            json.dump(doc, open(name, "w", encoding="utf-8"), ensure_ascii=False, indent=1); print("wrote", name)
        if a.quiet:
            return 0
        print(f"industry profile: {prof}. Next: fill in the YOUR-... values in agent.json, then run:  python -m speakvora_pack_agent check")
        return 0
    if a.cmd == "start":
        import os, sys, urllib.request
        if sys.version_info < (3, 9):
            print("Speakvora Agent needs Python 3.9 or newer. Get it free at https://www.python.org/downloads/ and run this again."); return 1
        if not os.path.exists(a.config):
            print("First time here: setting up your agent for this bundle...")
            if main(["init", "--pack", ".", "--quiet"]) != 0:
                return 1
        try:
            lis = json.load(open(a.config, encoding="utf-8")).get("listen", {}); url = f"http://{lis.get('host', '127.0.0.1')}:{lis.get('port', 8787)}/dashboard"
            urllib.request.urlopen(url, timeout=2)                          # something already answers here: it is probably this agent, so just open it
            tok = open(os.path.join("agent-state", "dashboard-token"), encoding="utf-8").read().strip() if os.path.exists(os.path.join("agent-state", "dashboard-token")) else ""
            print("Your agent is already running. Opening the dashboard.")
            if not a.no_browser:
                import webbrowser; webbrowser.open(url + ("#token=" + tok if tok else ""))
            return 0
        except Exception:  # noqa: BLE001 - nothing running yet (or not ours): start it below
            pass
        a.cmd, a.live, a.open = "run", False, not a.no_browser
    if a.cmd == "demo":
        from . import demo
        return demo.run(a.config, speak=not a.silent)
    cfg = config.load(a.config, lazy_secrets=a.cmd in ("check", "slots", "doctor", "events", "run") or a.cmd in ("queue", "jobs", "proposals"))
    if a.cmd == "doctor":
        from . import doctor
        return doctor.run(cfg)
    if a.cmd == "events":
        from . import doctor
        return doctor.events(cfg, a.lang)
    if a.cmd == "check":
        ag = Agent(cfg)
        print(f"pack: {ag.pack.meta.get('title')} ({len(ag.pack.items)} lines, language {ag.pack.language}, {len(ag.pack.slots)} workflow slots)")
        print(f"workflows: {len(ag.workflows)}  | dry_run: {ag.dry}  | waiting in the offline outbox: {len(ag.state.outbox())}")
        wl_missing = [i for i in ag.pack.missing_audio() if i in set(ag.pack.slots.values())]
        print("workflow-line audio files missing:", wl_missing[:10] or "none")
        for n, svc in (("twilio", ag.twilio), ("slack", ag.slack), ("google calendar", ag.gcal), ("email", ag.mail)):
            print(f"  {n:16s} {'connected' if svc.configured else 'not configured'}")
        missing = [s for w in ag.workflows for s in _slots(w) if s not in ag.pack.slots and s not in ag.pack.by_id]
        if cfg.get("_missing_env"):
            print("environment variables not set yet:", ", ".join(cfg["_missing_env"]))
        print("required lines the pack has no audio for (spoken in the phone provider's voice until added):", ag.missing_required or "none")
        print("missing slots:", ag.missing_slots or "none", "(run 'slots --write' or 'slots --send' to request them)" if ag.missing_slots else "")
        return 0
    if a.cmd == "run":
        if a.live:
            cfg["dry_run"] = False
        if cfg.get("_missing_env") and not getattr(a, "open", False):
            print("not connected yet (open the dashboard's Connect tab to add them): " + ", ".join(cfg["_missing_env"]))
        ag = Agent(cfg)
        srv = serve(ag)
        from . import dashboard
        print(f"dashboard: http://{cfg['listen']['host']}:{cfg['listen']['port']}/dashboard#token={dashboard.token(ag)}   (open this address on this machine; the part after # is your access token)")
        print(f"speakvora-pack-agent {__version__} listening on {cfg['listen']['host']}:{cfg['listen']['port']}  | {'LIVE: sending for real' if not ag.dry else 'DRY RUN: nothing is sent'}  | log: {ag.state.log_path}")
        if getattr(a, "open", False):
            import threading, webbrowser
            threading.Timer(1.0, webbrowser.open, [f"http://{cfg['listen']['host']}:{cfg['listen']['port']}/dashboard#token={dashboard.token(ag)}"]).start()
            print("Opening your dashboard in the browser. Leave this window open while the agent runs; close it to stop.")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("stopped")
        return 0
    if a.cmd == "slots":
        return slots_cli(cfg, a)
    if a.cmd == "proposals":
        ag = Agent(cfg)
        if a.action == "list":
            for j in ag.state.jobs(("proposed", "approved", "answered")):
                if j["kind"] != "reason":
                    continue
                r = j["result"]; print(f"{j['id']}  [{j['status']}]  {r['summary'][:100]}   (model {r.get('model')}, {r.get('sent_chars')} chars sent)")
                for i, p in enumerate(r["proposals"]):
                    print(f"   {i}. {p['state']:<8} {p['action']:<16} {str(p['args'].get('name') or p['args'].get('channel') or p['args'].get('url') or p['args'].get('title') or '')[:24]:<24} {str(p['args'].get('text') or '')[:70]}")
            return 0
        if not a.id:
            print("give a proposal id (see 'proposals list')"); return 1
        idx = [int(x) for x in a.only.split(",") if x.strip()] if a.only else None
        try:
            if a.action == "approve":
                res = ag.execute_proposals(a.id, idx if idx is not None else [i for i, p in enumerate((ag.state.job_get(a.id) or {}).get("result", {}).get("proposals", [])) if p["state"] == "pending"]); ag.flush_outbox()
                print(json.dumps(res))
            else:
                print(ag.reject_proposals(a.id, idx)["status"])
        except PermissionError as e:
            print(e); return 1
        return 0
    if a.cmd == "jobs":
        ag = Agent(cfg)
        if a.action == "list":
            rows = ag.state.jobs(a.status or None)
            for j in rows:
                to = str(j["a"].get("to") or j["a"].get("channel") or j["a"].get("url") or "")[:32]
                print(f"{j['id']:<28} {j['status']:<13} {j['kind']:<16} {j['wf']:<22} {to:<32} {int(ag.now() - j['updated'])} s ago" + (f"  {j['error'][:60]}" if j.get("error") else ""))
            print(json.dumps(ag.state.job_counts()) if rows else "no jobs"); return 0
        if not a.id:
            print("give a job id"); return 1
        try:
            j = ag.cancel_job(a.id) if a.action == "cancel" else ag.retry_job(a.id, a.confirm_not_sent) if a.action == "retry" else ag.mark_job_sent(a.id)
        except PermissionError as e:
            print(e); return 1
        print(a.id, "->", j["status"]); return 0
    if a.cmd == "queue":
        ag = Agent(cfg); items = ag.state.outbox()
        if a.action == "list":
            for q in items:
                print(f"{q['id']:>20}  {q['kind']:<16} {q['wf']:<24} waiting {int(ag.now() - q['queued_at'])} s  {str(q['a'].get('to') or q['a'].get('channel') or q['a'].get('url') or '')[:40]}")
            print(f"{len(items)} waiting" if items else "nothing waiting"); return 0
        if a.action == "flush":
            print(json.dumps(ag.flush_outbox())); return 0
        if not a.id:
            print("give a queue id or 'all'"); return 1
        print("dropped", ag.state.clear_outbox() if a.id == "all" else int(ag.state.dequeue(a.id))); return 0
    if a.cmd == "event":
        return signing_cli.send(cfg, a.file, a.url)
    return 1


def slots_cli(cfg, a):
    import os, urllib.request
    from . import slots as SL
    ag = Agent(cfg); reg = SL.registry(ag.profile)
    want = set(reg) if a.all else SL.needed_by(json.load(open(cfg["workflows"], encoding="utf-8")))
    gaps = [{"slot": k, **reg[k]} for k in sorted(want) if k in reg and k not in ag.pack.slots]
    unknown = sorted(x for x in want if x not in reg and x not in ag.pack.slots and x not in ag.pack.by_id)
    print(f"industry profile: {ag.profile}  | pack language: {ag.pack.language}  | slots filled: {len(want) - len(gaps) - len(unknown)} of {len(want)}")
    for g in gaps:
        print(f"  missing  {g['slot']:28s} {g['example']}")
    for u in unknown:
        print(f"  unknown  {u:28s} (not a standard slot: add it to workflow_lines.json yourself)")
    if gaps and (a.write or a.send):
        doc = SL.request_file(ag.pack, ag.profile, gaps, "slot-requests.json"); print("wrote slot-requests.json")
        if a.send:
            req = urllib.request.Request(os.environ.get("SPEAKVORA_HOST", "https://speakvora.com") + "/api/v1/packs/slot-requests", data=json.dumps(doc).encode(), method="POST", headers={"x-api-key": os.environ["SPEAKVORA_KEY"], "content-type": "application/json"})
            print("sent:", urllib.request.urlopen(req, timeout=20).read().decode())
    elif gaps:
        print("Run again with --write (file) or --send (queue it with Speakvora) and the phrase bot will add these lines to the pack.")
    return 0


def _slots(w):
    out = []
    def walk(o):
        if isinstance(o, dict):
            if "slot" in o and isinstance(o["slot"], str):
                out.append(o["slot"])
            for k, v in o.items():
                if k in ("audio", "play", "prompt") and isinstance(v, str):
                    out.append(v)
                walk(v)
        elif isinstance(o, list):
            for x in o:
                if isinstance(x, str):
                    pass
                walk(x)
    walk(w)
    return [s for s in out if not s.isdigit()]


if __name__ == "__main__":
    sys.exit(main())
