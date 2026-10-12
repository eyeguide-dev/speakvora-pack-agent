"""A tiny JSON file that remembers what already happened (so a restart never repeats a reminder), who opted out, and how much was sent. Safe for one process with several threads."""
import json, os, threading, time


class State:
    def __init__(self, directory, now=time.time):
        self.dir, self.now, self.lock = directory, now, threading.Lock()
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, "state.json")
        self.data = {"done": {}, "optout": {}, "sent": [], "outbox": [], "jobs": {}, "events": {}}
        if os.path.exists(self.path):
            try:
                self.data.update(json.load(open(self.path, encoding="utf-8")))
            except ValueError:
                pass
        self.log_path = os.path.join(directory, "agent.log.jsonl")
        for q in self.data.get("outbox") or []:                              # 0.2.0 kept queued actions in a plain list: they become queued jobs
            self.data["jobs"].setdefault(q["id"], {"id": q["id"], "wf": q["wf"], "kind": q["kind"], "a": q["a"], "ctx": q.get("ctx") or {}, "status": "queued", "created": q["queued_at"], "queued_at": q["queued_at"], "updated": q["queued_at"], "attempts": 0, "history": []})
        self.data["outbox"] = []

    def save(self):
        tmp = self.path + ".tmp"
        json.dump(self.data, open(tmp, "w", encoding="utf-8"))
        os.replace(tmp, self.path)

    def once(self, key):
        """True the first time a key is seen (and remembers it), False after."""
        with self.lock:
            if key in self.data["done"]:
                return False
            self.data["done"][key] = int(self.now())
            cutoff = self.now() - 45 * 86400
            self.data["done"] = {k: v for k, v in self.data["done"].items() if v > cutoff}
            self.save()
            return True

    def forget(self, key):
        with self.lock:
            self.data["done"].pop(key, None); self.save()

    def opt_out(self, who):
        with self.lock:
            self.data["optout"][who] = int(self.now()); self.save()

    def opt_in(self, who):
        with self.lock:
            self.data["optout"].pop(who, None); self.save()

    def is_opted_out(self, who):
        return who in self.data["optout"]

    def record_send(self, kind, to):
        with self.lock:
            self.data["sent"].append([int(self.now()), kind, to])
            self.data["sent"] = [s for s in self.data["sent"] if s[0] > self.now() - 2 * 86400]; self.save()

    def sent_since(self, seconds, kind=None, to=None):
        t = self.now() - seconds
        return sum(1 for s in self.data["sent"] if s[0] >= t and (kind is None or s[1] == kind) and (to is None or s[2] == to))

    # ---- the job journal: every action that leaves this machine (text, call, Slack/Teams post, email, calendar entry, webhook, API write) is written down BEFORE it is sent, so a crash or power cut never loses it
    # and never repeats it. Statuses: pending (written, not started), sending (network call started: if the agent dies now nobody knows if it arrived), queued (waiting for the connection, see the offline queue),
    # sent (the provider accepted it), delivered / undelivered (the provider's later report), needs_review (we cannot know whether it arrived: a timeout or server error), failed (refused, nothing was sent),
    # blocked (a safety rule said no), expired (too old to be useful), cancelled (stopped by a person).
    LIVE = ("pending", "sending", "queued", "needs_review", "sent")
    FINAL_KEEP_DAYS, MAX_JOBS = 30, 5000

    def _prune(self):
        cutoff, jobs = self.now() - self.FINAL_KEEP_DAYS * 86400, self.data["jobs"]
        for k in [k for k, j in jobs.items() if j["status"] not in ("pending", "sending", "queued", "needs_review", "needs_approval", "proposed") and j["updated"] < cutoff]:
            del jobs[k]
        while len(jobs) > self.MAX_JOBS:
            old = next((k for k, j in jobs.items() if j["status"] not in ("pending", "sending", "queued", "needs_review", "needs_approval", "proposed")), None)
            if old is None:
                break
            del jobs[old]

    def new_job_id(self):
        with self.lock:
            return f"j{int(self.now() * 1000)}-{len(self.data['jobs'])}-{os.urandom(2).hex()}"

    def job_create(self, jid, wf, kind, a, ctx, status="pending"):
        with self.lock:
            n = int(self.now())
            self.data["jobs"][jid] = {"id": jid, "wf": wf, "kind": kind, "a": a, "ctx": ctx or {}, "status": status, "created": n, "updated": n, "queued_at": n if status == "queued" else None, "attempts": 0, "history": [[n, status, ""]]}
            self._prune(); self.save(); return self.data["jobs"][jid]

    def update_proposal(self, jid, i, **fields):
        with self.lock:
            j = self.data["jobs"].get(jid)
            if j and j.get("result") and 0 <= i < len(j["result"]["proposals"]):
                j["result"]["proposals"][i].update(fields); j["updated"] = int(self.now()); self.save()

    def job_get(self, jid):
        with self.lock:
            j = self.data["jobs"].get(jid); return dict(j) if j else None

    def job_set(self, jid, status, note="", **fields):
        with self.lock:
            j = self.data["jobs"].get(jid)
            if not j:
                return None
            n = int(self.now()); j["status"], j["updated"] = status, n
            if status == "queued":
                j["queued_at"] = n
            j.update(fields); j["history"] = (j["history"] + [[n, status, str(note)[:200]]])[-20:]
            self.save(); return dict(j)

    def jobs(self, status=None):
        with self.lock:
            return sorted((dict(j) for j in self.data["jobs"].values() if status is None or j["status"] == status or (isinstance(status, (tuple, list)) and j["status"] in status)), key=lambda j: j["created"])

    def job_by_provider_id(self, pid):
        with self.lock:
            return next((dict(j) for j in self.data["jobs"].values() if pid and j.get("provider_id") == pid), None)

    def job_delete(self, jid):
        with self.lock:
            gone = self.data["jobs"].pop(jid, None) is not None; self.save(); return gone

    def job_counts(self):
        with self.lock:
            out = {}
            for j in self.data["jobs"].values():
                out[j["status"]] = out.get(j["status"], 0) + 1
            return out

    # events accepted from your app: written down before the app gets its answer, removed when every workflow finished, resumed after a restart (jobs already written are skipped, so nothing is sent twice)
    def event_begin(self, key, payload, wf):
        with self.lock:
            self.data["events"][key] = {"payload": payload, "wf": wf, "t": int(self.now())}; self.save()

    def event_done(self, key):
        with self.lock:
            self.data["events"].pop(key, None); self.save()

    def events_running(self):
        with self.lock:
            return dict(self.data["events"])

    # ---- compatibility with 0.2.0: the outbox is the set of queued jobs
    def enqueue(self, item):
        jid = self.new_job_id(); self.job_create(jid, item["wf"], item["kind"], item["a"], item.get("ctx"), "queued"); return jid

    def outbox(self):
        return [{**j, "queued_at": j["queued_at"] or j["created"]} for j in self.jobs("queued")]

    def dequeue(self, qid):
        return self.job_delete(qid)

    def clear_outbox(self):
        with self.lock:
            ids = [k for k, j in self.data["jobs"].items() if j["status"] == "queued"]
            for k in ids:
                del self.data["jobs"][k]
            self.save(); return len(ids)

    def log(self, **rec):
        rec["t"] = int(self.now())
        with self.lock, open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
