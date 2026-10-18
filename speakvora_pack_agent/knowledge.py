"""Knowledge: the business's own documents, pages and notes that the live AI answers from. Everything is stored and searched on this computer (agent-state/knowledge/); only the few short passages that match a
customer's question are sent to the owner's own AI, with that one question. Sources: a pasted note, an uploaded file (txt, md, csv, json, html, docx, and pdf when it has selectable text) or a website (its own pages only).
Passages that look like secrets or personal records (card or ID numbers, passwords, long lists of emails) are dropped when a source is added. Standard library only, no model or index service."""
import base64, hashlib, io, json, math, os, re, time, zipfile
from urllib.parse import urljoin, urlparse

MAX_FILE = 3_000_000
MAX_CHARS = 120_000                      # per source
MAX_SOURCES = 60
CHUNK = 650
STOP = set("a an and are as at be but by can do does for from had has have how i if in is it its me my of on or our so than that the their them then there they this to us was we were what when where which who will with would you your".split())
SECRET = re.compile(r"\b(?:\d[ -]?){13,19}\b|\b\d{3}-\d{2}-\d{4}\b|\b(?:password|passcode|pin|api[_ -]?key|secret|token)\s*[:=]\s*\S+", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _dir(agent):
    d = os.path.join(agent.state.dir, "knowledge"); os.makedirs(d, exist_ok=True); return d


def _idx(agent):
    try:
        with open(os.path.join(_dir(agent), "index.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"sources": [], "gaps": []}


def _save(agent, d):
    p = os.path.join(_dir(agent), "index.json"); tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, p)


def _words(t):
    return [w for w in re.findall(r"[a-z0-9']+", str(t).lower()) if w not in STOP and len(w) > 1]


# ---- reading files --------------------------------------------------------------------------------------------------------------------------
def _html(h):
    h = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<(br|/p|/div|/li|/h\d|/tr)[^>]*>", "\n", h)
    t = re.sub(r"<[^>]+>", " ", h)
    for a, b in (("&amp;", "&"), ("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&rsquo;", "'")):
        t = t.replace(a, b)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def _docx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml); xml = re.sub(r"<w:tab/>", "\t", xml)
    return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "", xml).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")).strip()


def _pdf_filters(head):
    m = re.search(rb"/Filter\s*(\[[^\]]*\]|/\w+)", head)
    return re.findall(rb"/(\w+)", m.group(1)) if m else []


def _pdf_stream(head, raw):
    """One content stream decoded through its filters (ASCII85, hex, Flate), or None when a filter is not supported."""
    import zlib
    for f in _pdf_filters(head):
        try:
            if f in (b"ASCII85Decode", b"A85"):
                raw = base64.a85decode(raw.strip(), adobe=raw.strip().startswith(b"<~"))
            elif f in (b"ASCIIHexDecode", b"AHx"):
                raw = bytes.fromhex(re.sub(rb"[^0-9A-Fa-f]", b"", raw.split(b">")[0]).decode())
            elif f in (b"FlateDecode", b"Fl"):
                raw = zlib.decompress(raw)
            else:
                return None
        except Exception:  # noqa: BLE001
            return None
    return raw


def _pdf_text_ops(x):
    """Text from the show-text operators of a decoded content stream: (..) Tj, [..] TJ, and '"' too, with a new line at each BT block and each line move."""
    out = []
    for blk in re.findall(rb"BT(.*?)ET", x, re.S):
        line = []
        for tok in re.finditer(rb"\[(.*?)\]\s*TJ|\(((?:\\.|[^\\)])*)\)\s*(?:Tj|'|\")|<([0-9A-Fa-f\s]+)>\s*Tj|(T\*|Td|TD|Tm)", blk, re.S):
            if tok.group(4):
                if line and not line[-1].endswith("\n"):
                    line.append("\n")
                continue
            if tok.group(1) is not None:
                src = tok.group(1)
                for part in re.finditer(rb"\(((?:\\.|[^\\)])*)\)|<([0-9A-Fa-f\s]+)>|(-?\d+\.?\d*)", src):
                    if part.group(1) is not None:
                        line.append(_pdf_str(part.group(1)))
                    elif part.group(2):
                        line.append(_pdf_hex(part.group(2)))
                    elif part.group(3) and float(part.group(3)) < -200:
                        line.append(" ")
            elif tok.group(2) is not None:
                line.append(_pdf_str(tok.group(2)))
            elif tok.group(3):
                line.append(_pdf_hex(tok.group(3)))
        t = "".join(line)
        if t.strip():
            out.append(t)
    return "\n".join(out)


def _pdf_str(s):
    s = re.sub(rb"\\([nrtbf()\\])", lambda m: {b"n": b"\n", b"r": b"", b"t": b" ", b"b": b"", b"f": b""}.get(m.group(1), m.group(1)), s)
    s = re.sub(rb"\\(\d{1,3})", lambda m: bytes([int(m.group(1), 8) % 256]), s)
    return s.decode("latin-1")


def _pdf_hex(h):
    h = re.sub(rb"\s", b"", h)
    if len(h) % 2:
        h += b"0"
    b = bytes.fromhex(h.decode())
    return b.decode("utf-16-be", "replace") if b[:2] == b"\xfe\xff" else b.decode("latin-1")


def _pdf(data):
    """Text from a PDF with selectable text (no scanned images). Uses pdftotext when it is installed (best layout); otherwise reads the text operators of each content stream itself."""
    import shutil, subprocess, tempfile
    exe = shutil.which("pdftotext")
    if exe:
        try:
            with tempfile.TemporaryDirectory() as d:
                src = os.path.join(d, "in.pdf")
                with open(src, "wb") as f:
                    f.write(data)
                r = subprocess.run([exe, "-layout", "-enc", "UTF-8", src, "-"], capture_output=True, timeout=30)
                t = r.stdout.decode("utf-8", "replace").strip()
                if len(t) > 40:
                    return re.sub(r"[ \t]{2,}", "  ", t)
        except Exception:  # noqa: BLE001
            pass
    out = []
    for obj in data.split(b"endobj"):
        m = re.search(rb"stream\r?\n(.*)\r?\nendstream", obj, re.S)
        if not m:
            continue
        x = _pdf_stream(obj[:m.start()], m.group(1))
        if x and (b"BT" in x):
            t = _pdf_text_ops(x)
            if t:
                out.append(t)
    return re.sub(r"[ \t]+", " ", "\n".join(out)).strip()


def read_file(name, data):
    ext = os.path.splitext(str(name).lower())[1]
    if len(data) > MAX_FILE:
        raise ValueError("That file is over 3 MB. Split it, or paste the important parts.")
    try:
        if ext in (".txt", ".md", ".csv", ".json", ".tsv", ".log", ""):
            t = data.decode("utf-8", "replace")
            if ext == ".json":
                t = re.sub(r'[{}\[\]"]', " ", t)
        elif ext in (".html", ".htm"):
            t = _html(data.decode("utf-8", "replace"))
        elif ext == ".docx":
            t = _docx(data)
        elif ext == ".pdf":
            t = _pdf(data)
            if len(t) < 40:
                raise ValueError("This PDF could not be read here (it may be a scan, or made by a tool this agent cannot read). Install the free pdftotext (Mac: brew install poppler; Linux: poppler-utils), export it as text or Word, or paste the text.")
        else:
            raise ValueError("That file type is not supported yet. Use PDF, Word (.docx), text, Markdown, CSV or HTML, or paste the text.")
    except zipfile.BadZipFile:
        raise ValueError("That Word file could not be opened. Save it as .docx again, or paste the text.")
    return t


# ---- chunking and safety --------------------------------------------------------------------------------------------------------------------
def _chunks(text):
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[A-Z0-9#•\-*])", text) if p.strip()]
    n0 = len(paras); paras = [p for p in paras if not SECRET.search(p) and len(EMAIL.findall(p)) <= 3]; _chunks.dropped = n0 - len(paras)
    out, cur = [], ""
    for p in paras:
        p = re.sub(r"\s+", " ", p)
        while len(p) > CHUNK * 1.5:
            cut = p.rfind(". ", 0, CHUNK); cut = cut + 1 if cut > 200 else CHUNK
            if cur:
                out.append(cur); cur = ""
            out.append(p[:cut].strip()); p = p[cut:].strip()
        if len(cur) + len(p) + 1 > CHUNK and cur:
            out.append(cur); cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur:
        out.append(cur)
    return out


def _clean_chunks(chunks):
    """(kept, dropped): passages that look like secrets or personal records never enter the knowledge."""
    kept, dropped = [], 0
    for c in chunks:
        if SECRET.search(c) or len(EMAIL.findall(c)) > 3:
            dropped += 1
        else:
            kept.append(c)
    return kept, dropped


def add_text(agent, title, text, kind="note", origin=""):
    title = re.sub(r"\s+", " ", str(title or "")).strip()[:80] or "Untitled"
    text = str(text or "").strip()[:MAX_CHARS * 2]
    if len(text) < 20:
        raise ValueError("There is not enough text to learn from.")
    d = _idx(agent)
    if len(d["sources"]) >= MAX_SOURCES:
        raise ValueError(f"That is {MAX_SOURCES} sources. Remove one you no longer need first.")
    chunks = _chunks(text[:MAX_CHARS]); chunks, dropped = _clean_chunks(chunks); dropped += getattr(_chunks, "dropped", 0)
    if not chunks:
        raise ValueError("Nothing usable was found. It may contain only card numbers, passwords or personal records, which are never added.")
    sid = hashlib.sha1((title + str(time.time())).encode()).hexdigest()[:10]
    with open(os.path.join(_dir(agent), sid + ".json"), "w", encoding="utf-8") as f:
        json.dump(chunks, f)
    d["sources"] = [s for s in d["sources"] if not (origin and s.get("origin") == origin)] + [{"id": sid, "title": title, "kind": kind, "origin": origin, "added": int(agent.now()), "chunks": len(chunks), "chars": sum(map(len, chunks)), "dropped": dropped}]
    d["gaps"] = [g for g in d.get("gaps", []) if not _covered(chunks, g["q"])]
    _save(agent, d); _cache.pop(agent.state.dir, None)
    return {"id": sid, "title": title, "chunks": len(chunks), "dropped": dropped}


def add_qa(agent, question, answer):
    """A question and the exact answer the owner wants given. When a customer asks something close to it, that answer is used at once, with no AI call: instant, free and exactly the owner's words."""
    q = re.sub(r"\s+", " ", str(question or "")).strip()[:200]; a = re.sub(r"\s+", " ", str(answer or "")).strip()[:320]
    if len(_words(q)) < 1 or len(a) < 8:
        raise ValueError("Write the question and an answer of at least a few words.")
    if SECRET.search(a):
        raise ValueError("The answer looks like it contains a card number or password, which are never added.")
    r = add_text(agent, q[:80], "Q: " + q + "\nA: " + a, "qa")
    d = _idx(agent); d.setdefault("qa", []).append({"id": r["id"], "q": q, "a": a}); d["gaps"] = [g for g in d.get("gaps", []) if len(set(_words(g["q"])) & set(_words(q))) < max(2, len(set(_words(q))) // 2 + 1)]; _save(agent, d)
    return {**r, "q": q, "a": a}


def qa_match(agent, text):
    """(answer, question) when what a customer said is close to a saved question, else None. Needs at least two shared words (unless the saved question is one word), most of the saved question's words, and those words must make up a good part of what the customer said."""
    t = set(_words(text))
    best = None
    for e in _idx(agent).get("qa", []):
        w = set(_words(e["q"]))
        if not w or not t:
            continue
        inter = len(t & w); score = inter / len(w)                       # how much of the saved question the customer's words cover
        if inter >= min(2, len(w)) and score >= 0.8 and inter / len(t) >= 0.3 and (best is None or score > best[0]):
            best = (score, e)
    return (best[1]["a"], best[1]["q"]) if best else None


def add_file(agent, name, b64):
    try:
        data = base64.b64decode(str(b64 or ""), validate=False)
    except Exception:  # noqa: BLE001
        raise ValueError("That file could not be read.")
    return add_text(agent, os.path.splitext(os.path.basename(str(name)))[0].replace("_", " ").replace("-", " "), read_file(name, data), "file", "")


def add_site(agent, url, max_pages=8):
    """The page and up to a few more pages of the same website (its own links only), read once, on this computer."""
    import urllib.request
    p0 = urlparse(str(url or "").strip())
    if p0.scheme not in ("http", "https") or not p0.hostname:
        raise ValueError("Type the website address starting with https://")
    seen, todo, texts = set(), [p0.geturl()], []
    while todo and len(seen) < max_pages:
        u = todo.pop(0).split("#")[0]
        if u in seen:
            continue
        seen.add(u)
        try:
            req = urllib.request.Request(u, headers={"user-agent": "SpeakvoraAgent/0.20 (reads your own site once, on your computer)"})
            with urllib.request.urlopen(req, timeout=12) as r:
                if "html" not in r.headers.get("content-type", "") and "text" not in r.headers.get("content-type", ""):
                    continue
                raw = r.read(500_000).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
        texts.append(_html(raw))
        for href in re.findall(r'href=["\']([^"\'#]+)', raw):
            nu = urljoin(u, href); pu = urlparse(nu)
            if pu.hostname == p0.hostname and pu.scheme in ("http", "https") and not re.search(r"\.(jpg|jpeg|png|gif|svg|css|js|pdf|zip|ico)$", pu.path, re.I) and nu not in seen and nu not in todo:
                todo.append(nu)
    if not texts:
        raise ValueError("That website could not be read. Check the address, or paste the text instead.")
    return add_text(agent, p0.hostname, "\n\n".join(texts), "site", p0.geturl())


def remove(agent, sid):
    d = _idx(agent); d["sources"] = [s for s in d["sources"] if s["id"] != sid]; d["qa"] = [e for e in d.get("qa", []) if e["id"] != sid]; _save(agent, d)
    try:
        os.remove(os.path.join(_dir(agent), re.sub(r"\W", "", sid) + ".json"))
    except OSError:
        pass
    _cache.pop(agent.state.dir, None)


# ---- search ---------------------------------------------------------------------------------------------------------------------------------
_cache = {}


def _all(agent):
    k = agent.state.dir
    if k not in _cache:
        rows = []
        for s in _idx(agent)["sources"]:
            try:
                with open(os.path.join(_dir(agent), s["id"] + ".json"), encoding="utf-8") as f:
                    for c in json.load(f):
                        rows.append((s["title"], s["id"], c, _words(c)))
            except (OSError, ValueError):
                pass
        _cache[k] = rows
    return _cache[k]


def search(agent, query, k=4):
    """The k best passages for a question: [(source title, passage)]. A BM25-style score over the words, no model."""
    q = set(_words(query)); rows = _all(agent)
    if not q or not rows:
        return []
    n = len(rows); df = {w: sum(1 for r in rows if w in r[3]) for w in q}; avg = sum(len(r[3]) for r in rows) / n
    scored = []
    for title, sid, text, ws in rows:
        s = 0.0; hit = 0
        for w in q:
            tf = ws.count(w)
            if tf:
                hit += 1; s += math.log(1 + (n + 1) / (df[w] + 0.5)) * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * len(ws) / avg))
        if hit >= (2 if len(q) >= 3 else 1):
            scored.append((s, title, text))
    scored.sort(key=lambda x: -x[0])
    top = scored[0][0] if scored else 0
    return [(t, c) for s, t, c in scored[:k] if s >= top * 0.35]


def _covered(chunks, question):
    q = set(_words(question))
    return bool(q) and any(len(q & set(_words(c))) >= max(2, len(q) // 2) for c in chunks)


def prompt(agent, question, history=()):
    """The knowledge for the AI's input, and the sources used. A small knowledge base (a few pages) is given whole, because a customer's words rarely match the owner's ('outdoor seating' versus 'patio'); a large one gives the best-matching passages."""
    rows = _all(agent)
    if not rows:
        return "", []
    total = sum(len(r[2]) for r in rows)
    if total <= 6000:
        hits = [(r[0], r[2]) for r in rows]
    else:
        hits = search(agent, question + " " + " ".join(history[-2:]) if history else question, 6)
    if not hits:
        return "", []
    return ("APPROVED DOCUMENTS (the owner's own words; answer only from these, copy prices, times and policies exactly, never go beyond them):\n" + "\n".join(f"[{t}] {c}" for t, c in hits) + "\n", sorted({t for t, _ in hits}))


def text_all(agent, limit=400_000):
    """Everything known, as one string, so a number or a price in the knowledge counts as approved when an answer is checked."""
    return " ".join(r[2] for r in _all(agent))[:limit]


# ---- what customers asked that nothing answers ----------------------------------------------------------------------------------------------
def note_gap(agent, question):
    from . import reasoner as R
    q = R.redact(re.sub(r"\s+", " ", str(question or "")).strip()[:160], None)
    if len(_words(q)) < 2:
        return
    d = _idx(agent); k = " ".join(sorted(set(_words(q))))
    for g in d["gaps"]:
        if g["k"] == k:
            g["n"] += 1; g["last"] = int(agent.now()); break
    else:
        d["gaps"].append({"k": k, "q": q, "n": 1, "last": int(agent.now())})
    d["gaps"] = sorted(d["gaps"], key=lambda g: -g["last"])[:40]; _save(agent, d)


def dismiss_gap(agent, k):
    d = _idx(agent); d["gaps"] = [g for g in d["gaps"] if g["k"] != k]; _save(agent, d)


def view(agent):
    d = _idx(agent)
    return {"sources": sorted(d["sources"], key=lambda s: -s["added"]), "chunks": sum(s["chunks"] for s in d["sources"]), "chars": sum(s["chars"] for s in d["sources"]),
            "gaps": sorted(d.get("gaps", []), key=lambda g: (-g["n"], -g["last"]))[:12], "ai_ready": bool((agent.cfg.get("reasoner") or {}).get("model"))}


def preview(agent, source_id):
    for s in _idx(agent)["sources"]:
        if s["id"] == source_id:
            try:
                with open(os.path.join(_dir(agent), s["id"] + ".json"), encoding="utf-8") as f:
                    return {**s, "text": "\n\n".join(json.load(f))[:6000]}
            except (OSError, ValueError):
                break
    raise ValueError("That source was not found.")
