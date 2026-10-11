"""Loads an offline Speakvora pack folder (manifest.json + audio/) and, if present, its workflow lines (workflow_lines.json + audio files). Everything is local; nothing here touches the network."""
import json, os, re


class PackError(Exception):
    pass


class Pack:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        mf = os.path.join(self.path, "manifest.json")
        if not os.path.exists(mf):
            raise PackError(f"No manifest.json in {self.path}. Point 'pack' at the unzipped pack folder.")
        m = json.load(open(mf, encoding="utf-8"))
        self.meta = {k: v for k, v in m.items() if k != "items"}
        self.items, self.by_id, self.slots = [], {}, {}
        for it in m.get("items", []):
            self._add(dict(it, id=str(it["id"])))
        wl = os.path.join(self.path, "workflow_lines.json")
        if os.path.exists(wl):
            for it in json.load(open(wl, encoding="utf-8")).get("items", []):
                self._add(dict(it, id=str(it["id"]), category="workflow_lines"))
                if it.get("slot"):
                    self.slots[it["slot"]] = str(it["id"])

    def _add(self, it):
        self.items.append(it); self.by_id[it["id"]] = it

    @property
    def language(self):
        return self.meta.get("language", "en")

    def get(self, ref):
        """ref: a phrase id, or a slot name."""
        ref = str(ref)
        it = self.by_id.get(ref) or self.by_id.get(self.slots.get(ref, ""))
        if not it:
            raise PackError(f"No phrase or slot '{ref}' in this pack.")
        return it

    def audio_path(self, ref):
        f = self.get(ref)["file"]
        for cand in (f, os.path.basename(f), os.path.join("workflow_lines", os.path.basename(f))):       # tolerate a workflow line unzipped next to the manifest instead of in workflow_lines/
            p = os.path.join(self.path, cand)
            if os.path.exists(p):
                return p
        raise PackError(f"Audio file missing: {os.path.join(self.path, f)}")

    def missing_audio(self):
        """Ids of lines whose audio file is not in the pack (so `check` can say so)."""
        out = []
        for it in self.items:
            try:
                self.audio_path(it["id"])
            except PackError:
                out.append(it["id"])
        return out

    def text(self, ref):
        return self.get(ref)["text"]

    def search(self, query="", category="", limit=10):
        """Plain word search over the text of the lines (case-insensitive, all words must appear)."""
        words = [w for w in re.split(r"\W+", query.lower()) if w]
        out = []
        for it in self.items:
            t = it["text"].lower()
            if category and category not in it.get("category", ""):
                continue
            if all(w in t for w in words):
                out.append(it)
                if len(out) >= limit:
                    break
        return out

    def resolve(self, spec):
        """spec: 'slot_or_id' | {'id':..} | {'slot':..} | {'search':'words','category':'x'} -> an item. Raises PackError if nothing fits."""
        if isinstance(spec, (str, int)):
            return self.get(spec)
        if "id" in spec:
            return self.get(spec["id"])
        if "slot" in spec:
            return self.get(spec["slot"])
        hits = self.search(spec.get("search", ""), spec.get("category", ""), 1)
        if not hits:
            raise PackError(f"No line in the pack matches {spec}.")
        return hits[0]
