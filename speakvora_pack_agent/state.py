"""A tiny JSON file that remembers what already happened (so a restart never repeats a reminder), who opted out, and how much was sent. Safe for one process with several threads."""
import json, os, threading, time


class State:
    def __init__(self, directory, now=time.time):
        self.dir, self.now, self.lock = directory, now, threading.Lock()
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, "state.json")
        self.data = {"done": {}, "optout": {}, "sent": [], "outbox": []}
        if os.path.exists(self.path):
            try:
                self.data.update(json.load(open(self.path, encoding="utf-8")))
            except ValueError:
                pass
        self.log_path = os.path.join(directory, "agent.log.jsonl")

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

    # ---- the outbox: actions that could not leave because the network was down, kept (on disk, so a restart or power cut keeps them) until they can be sent ----
    def enqueue(self, item):
        with self.lock:
            self.data["outbox"].append({**item, "id": f"q{int(self.now() * 1000)}-{len(self.data['outbox'])}", "queued_at": int(self.now())}); self.save()
            return self.data["outbox"][-1]["id"]

    def outbox(self):
        with self.lock:
            return list(self.data["outbox"])

    def dequeue(self, qid):
        with self.lock:
            n = len(self.data["outbox"]); self.data["outbox"] = [q for q in self.data["outbox"] if q["id"] != qid]; self.save(); return n != len(self.data["outbox"])

    def clear_outbox(self):
        with self.lock:
            n = len(self.data["outbox"]); self.data["outbox"] = []; self.save(); return n

    def log(self, **rec):
        rec["t"] = int(self.now())
        with self.lock, open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
