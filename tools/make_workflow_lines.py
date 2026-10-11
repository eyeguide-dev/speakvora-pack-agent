#!/usr/bin/env python3
"""Builds a pack's 'workflow lines' (the notification sentences packs do not contain: order ready, table ready, reminders...) as mp3 files plus workflow_lines.json.
Usage: SPEAKVORA_KEY=... python3 make_workflow_lines.py lines/restaurants.en.json OUT_DIR --voice af_heart [--host https://speakvora.com]
Each line is generated once through the Speakvora speak API (a few cents for the whole set) and then lives in the pack, offline."""
import argparse, concurrent.futures as cf, json, os, urllib.request

ap = argparse.ArgumentParser(); ap.add_argument("spec"); ap.add_argument("out"); ap.add_argument("--voice", default="af_heart"); ap.add_argument("--host", default="https://speakvora.com"); ap.add_argument("--lang")
a = ap.parse_args()
spec = json.load(open(a.spec, encoding="utf-8")); lang = a.lang or spec["language"]; key = os.environ["SPEAKVORA_KEY"]
os.makedirs(os.path.join(a.out, "workflow_lines"), exist_ok=True)


def one(args):
    i, ln = args
    req = urllib.request.Request(a.host + "/api/v1/speak", data=json.dumps({"text": ln["text"], "voice": a.voice, "lang": lang}).encode(), headers={"x-api-key": key, "content-type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=120)); url = r["url"] if r["url"].startswith("http") else a.host + r["url"]
    ext = ".mp3" if ".mp3" in url else os.path.splitext(url.split("?")[0])[1] or ".mp3"
    rel = f"workflow_lines/w{i:02d}{ext}"
    open(os.path.join(a.out, rel), "wb").write(urllib.request.urlopen(url, timeout=120).read())
    return {"id": f"w{i:02d}", "slot": ln["slot"], "text": ln["text"], "file": rel}


with cf.ThreadPoolExecutor(6) as ex:
    items = list(ex.map(one, list(enumerate(spec["lines"], 1))))
json.dump({"language": lang, "voice": a.voice, "industry": spec.get("industry"), "items": items}, open(os.path.join(a.out, "workflow_lines.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(items), "lines written to", a.out)
