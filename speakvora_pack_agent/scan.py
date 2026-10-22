"""Learn my business: once the owner's AI is connected, the agent can look at everything it already knows about the business, find the business's website on the web if nobody gave one, read the whole site
(menu, products, services, hours, policies, PDFs), and turn it into a profile, a price list and phrase ideas. It asks first at every step and keeps everything on this computer until the owner agrees:
  1. what the agent already knows (no network)            2. "Search the web for your website?"  (a web search, only when asked)
  3. "Is this your site?"                                 4. "Read it, up to N pages, and have your AI organise it?"  (the text goes to the owner's own AI provider, nothing to Speakvora)
  5. "Is this accurate?"  (facts to fill, profile, menu and prices; the owner ticks what to keep)      6. "Voice these phrases?"  (it spends the owner's speech allowance, so it asks)
Nothing is changed until step 5 is approved, nothing is voiced until step 6, and a site's own robots.txt is respected. Everything is plain Python standard library."""
import html as _htm, json, os, re, threading, time, urllib.parse, urllib.request, urllib.robotparser

from . import knowledge as KN, reasoner as R

FILE = "scan.json"
UA = "SpeakvoraAgent/0.35 (reads the business's own website once, on the owner's computer)"
LISTING_HOSTS = ("facebook.", "instagram.", "yelp.", "tripadvisor.", "doordash.", "ubereats.", "grubhub.", "opentable.", "yellowpages.", "mapquest.", "google.", "linkedin.", "twitter.", "x.com", "tiktok.", "youtube.", "pinterest.",
                 "bbb.org", "foursquare.", "zomato.", "seamless.", "postmates.", "wikipedia.", "reddit.", "nextdoor.", "groupon.", "booksy.", "mindbody.", "fresha.", "vagaro.", "slicelife.", "restaurantji.", "menupix.", "allmenus.", "beyondmenu.", "chownow.", "toasttab.", "squareup.com/", "alignable.", "manta.", "chamberofcommerce.", "tripadvisor", "patch.com", "timeout.")
PRIORITY = ("menu", "food", "drink", "product", "shop", "store", "service", "price", "pricing", "hour", "about", "contact", "faq", "polic", "cater", "reserv", "order", "location", "special", "wine", "book", "class", "rate")
SYSTEM = ("You organise what a small business's own website says into ONE JSON object and nothing else: "
          '{"business": {"name": "", "address": "", "hours": "", "website": ""}, "summary": "2 sentences", "tone": "a few words", '
          '"categories": [{"name": "menu section, product group or service group", "items": [{"name": "", "price": "exactly as written or empty", "description": "short"}]}], '
          '"policies": ["rules customers should know, only if stated"], "faqs": [{"q": "question a customer would ask", "a": "answer taken ONLY from the pages"}], "unknowns": ["things customers likely ask that the pages do not answer"]}. '
          "Use only what is on the pages. Never invent a price, hour, address or policy: leave it empty or list it under unknowns. Keep prices exactly as written. No emails, no phone numbers, nothing about customers.")
PHRASE_SYSTEM = ("You write short phrases a business says to customers, from its profile. Reply with ONE JSON object only: {\"lines\": [\"...\"]}. Up to 30 lines, each 20 to 160 characters, plain spoken sentences a receptionist would say "
                 "(greetings, what you offer, hours, where to find you, how booking or ordering works, policies, thanks, hand-offs), using ONLY facts in the profile. No names of people, no email addresses, no web links, no card or account numbers.")
_lock = threading.Lock()


def _path(agent):
    return os.path.join(agent.state.dir, FILE)


def load(agent):
    try:
        return json.load(open(_path(agent), encoding="utf-8"))
    except (OSError, ValueError):
        return {"step": "idle", "site": "", "candidates": [], "pages": [], "extracted": {}, "fact_suggestions": [], "phrases": [], "consent": {}, "error": "", "log": []}


def save(agent, d):
    os.makedirs(agent.state.dir, exist_ok=True)
    tmp = _path(agent) + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, _path(agent))


def _log(d, text):
    d.setdefault("log", []).append({"t": int(time.time()), "text": text}); d["log"] = d["log"][-40:]


def ai_ready(agent):
    rc = agent.cfg.get("reasoner") or {}
    return bool(rc.get("model") and (rc.get("api_key") or rc.get("base_url")))


def _real(v):
    return bool(v) and "YOUR-" not in str(v)


def known(agent):
    """What the agent already knows, with no network: shown first so the owner sees what it will and will not need to ask."""
    c = agent.cfg; f = c.get("facts") or {}
    items = []
    if _real(c.get("business")):
        items.append({"label": "Business name", "value": str(c["business"])})
    for k, label in (("hours", "Opening hours"), ("address", "Address"), ("info", "Other information"), ("review_url", "Review link"), ("website", "Website")):
        if _real(f.get(k)):
            items.append({"label": label, "value": str(f[k])[:200]})
    items.append({"label": "Industry bundle", "value": str(agent.pack.meta.get("title", ""))})
    src = [s for s in KN._idx(agent).get("sources", [])]
    items += [{"label": "Already read", "value": s.get("title") or s.get("origin") or s.get("kind", "")} for s in src[:6]]
    return items


def known_site(agent):
    f = agent.cfg.get("facts") or {}
    for k in ("website", "site", "url"):
        if _real(f.get(k)) and str(f[k]).startswith("http"):
            return str(f[k])
    for s in KN._idx(agent).get("sources", []):
        if s.get("kind") == "site" and str(s.get("origin", "")).startswith("http"):
            return s["origin"]
    return ""


# ---- 2. finding the website ---------------------------------------------------------------------------------------------------------------------------------------------------------------
def _get(url, data=None, timeout=15, limit=600_000):
    req = urllib.request.Request(url, data=data, headers={"user-agent": UA, "accept-language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit), r.headers.get("content-type", "")


def web_search(query):
    """A web search with no account or key (DuckDuckGo's plain page). Returns [{url, title, snippet}]. Only ever called after the owner pressed Search."""
    raw, _ct = _get("https://html.duckduckgo.com/html/", data=urllib.parse.urlencode({"q": query}).encode())
    html = raw.decode("utf-8", "replace"); out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?(?:class="result__snippet"[^>]*>(.*?)</a>)?', html, re.S):
        href = m.group(1)
        if "uddg=" in href:
            href = urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlparse(href if href.startswith("http") else "https:" + href).query).get("uddg", [""])[0])
        strip = lambda s: re.sub(r"\s+", " ", _htm.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()  # noqa: E731
        if href.startswith("http"):
            out.append({"url": href, "title": strip(m.group(2))[:140], "snippet": strip(m.group(3))[:240]})
        if len(out) >= 10:
            break
    return out


def candidates(agent, results):
    """Own sites first, directory and social listings last (still shown: a listing is sometimes all a small business has)."""
    seen, own, listing = set(), [], []
    for r in results:
        p = urllib.parse.urlparse(r["url"]); host = (p.hostname or "").lower().removeprefix("www.")
        if not host or host in seen:
            continue
        seen.add(host); site = f"{p.scheme}://{p.hostname}/"
        (listing if any(h in host for h in LISTING_HOSTS) else own).append({"url": site if not any(h in host for h in LISTING_HOSTS) else r["url"], "title": r["title"], "snippet": r["snippet"], "host": host, "listing": any(h in host for h in LISTING_HOSTS)})
    return (own + listing)[:6]


def search(agent):
    """Step 2. The owner pressed 'Search the web for my website'."""
    with _lock:
        d = load(agent); c = agent.cfg; f = c.get("facts") or {}
        name = str(c.get("business") or "").strip()
        if not _real(name):
            raise ValueError("Add your business name first (Settings, Your business details).")
        q = " ".join(x for x in (name, str(f.get("address") or "") if _real(f.get("address")) else "") if x).strip()
        try:
            res = web_search(q) or web_search(name + " " + str(agent.pack.meta.get("title", "")))
        except Exception as e:  # noqa: BLE001
            d.update(error="The web search did not work (" + type(e).__name__ + "). You can type your website address instead."); save(agent, d); return d
        d.update(step="candidates", candidates=candidates(agent, res), error="", query=q); d["consent"]["search"] = int(time.time()); _log(d, "Searched the web for: " + q)
        if not d["candidates"]:
            d["error"] = "No website was found. Type your website address, or skip it and tell the agent about the business another way."
        save(agent, d); return d


def set_site(agent, url):
    u = str(url or "").strip()
    if u and not re.match(r"^https?://", u):
        u = "https://" + u
    p = urllib.parse.urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname:
        raise ValueError("Type the website address, like https://yourbusiness.com")
    d = load(agent); d.update(site=u, step="site", error=""); _log(d, "Website chosen: " + (p.hostname or u)); save(agent, d); return d


# ---- 4. reading the whole site ------------------------------------------------------------------------------------------------------------------------------------------------------------
def _robots(base):
    rp = urllib.robotparser.RobotFileParser()
    try:
        raw, _ = _get(base + "/robots.txt", timeout=8, limit=100_000); rp.parse(raw.decode("utf-8", "replace").splitlines())
    except Exception:  # noqa: BLE001 - no robots.txt means everything is allowed
        rp.parse([])
    return rp


def _sitemap(base):
    urls = []
    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        try:
            raw, _ = _get(base + path, timeout=8, limit=400_000)
        except Exception:  # noqa: BLE001
            continue
        urls += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", raw.decode("utf-8", "replace"))
        if urls:
            break
    return urls[:300]


def _score(url):
    path = urllib.parse.urlparse(url).path.lower()
    return -sum(2 for w in PRIORITY if w in path) + path.count("/") * 0.1


def crawl(agent, url, max_pages=40, fetch=None, delay=0.6):
    """Reads up to max_pages pages of this one website (its own links and sitemap, menu and product pages first, a few PDFs), politely and only where robots.txt allows. Returns [{url, title, text}]."""
    fetch = fetch or _get
    p0 = urllib.parse.urlparse(url); base = f"{p0.scheme}://{p0.netloc}"; host = p0.hostname; rp = _robots(base)
    todo = [url] + sorted([u for u in _sitemap(base) if urllib.parse.urlparse(u).hostname == host], key=_score)
    seen, pages, pdfs, total, digests = set(), [], 0, 0, set()
    while todo and len(pages) + pdfs < max_pages and total < 160_000:
        u = todo.pop(0).split("#")[0]
        key = u.rstrip("/")                                             # the same page with and without a trailing slash is one page
        if key in seen or not rp.can_fetch(UA, u):
            continue
        seen.add(key)
        try:
            raw, ct = fetch(u)
        except Exception:  # noqa: BLE001 - a page that will not load is skipped
            continue
        path = urllib.parse.urlparse(u).path.lower()
        if "pdf" in ct or path.endswith(".pdf"):
            if pdfs < 5:
                try:
                    text = KN.read_file(os.path.basename(path) or "menu.pdf", raw)
                    pages.append({"url": u, "title": os.path.basename(path), "text": text[:30000]}); pdfs += 1; total += len(text)
                except Exception:  # noqa: BLE001
                    pass
            continue
        if "html" not in ct and "text" not in ct:
            continue
        html = raw.decode("utf-8", "replace"); text = KN._html(html); t = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        digest = hash(text[:2000])
        if len(text) > 80 and digest not in digests:
            digests.add(digest)
            pages.append({"url": u, "title": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t.group(1))).strip()[:120] if t else u, "text": text[:30000]}); total += len(text)
        new = []
        for href in re.findall(r'href=["\']([^"\'#]+)', html):
            nu = urllib.parse.urljoin(u, href); pu = urllib.parse.urlparse(nu)
            if pu.hostname == host and pu.scheme in ("http", "https") and not re.search(r"\.(jpg|jpeg|png|gif|svg|css|js|zip|ico|mp4|webp)$", pu.path, re.I) and nu.split("#")[0].rstrip("/") not in seen and nu not in todo and nu not in new:
                new.append(nu)
        todo = sorted(todo + new, key=_score)
        if delay:
            time.sleep(delay)
    return pages


def read_site(agent, max_pages=40, fetch=None, delay=0.6):
    """Steps 4 and 5 (background): read the site, have the owner's AI organise it, and leave the result waiting for the owner's review. Nothing is changed in the agent yet."""
    d = load(agent); url = d.get("site")
    if not url:
        raise ValueError("Choose your website first.")
    if not ai_ready(agent):
        raise ValueError("Connect your AI first (Connect, Your AI).")
    d.update(step="reading", error="", pages=[], extracted={}); d["consent"]["read"] = int(time.time()); _log(d, f"Reading up to {max_pages} pages of {urllib.parse.urlparse(url).hostname}"); save(agent, d)
    threading.Thread(target=_run, args=(agent, url, max_pages, fetch, delay), daemon=True).start()
    return d


def _run(agent, url, max_pages, fetch, delay):
    d = load(agent)
    try:
        pages = crawl(agent, url, max_pages, fetch, delay)
        if not pages:
            raise ValueError("That website could not be read. Check the address, or tell the agent about the business another way.")
        d.update(step="organising", pages=[{"url": p["url"], "title": p["title"], "chars": len(p["text"])} for p in pages]); _log(d, f"Read {len(pages)} pages. Asking your AI to organise them."); save(agent, d)
        ext = extract(agent, pages)
        d.update(step="review", extracted=ext, fact_suggestions=fact_suggestions(agent, ext), error="", text=_joined(pages)[:300000]); _log(d, "Ready for your review.")
    except Exception as e:  # noqa: BLE001 - a problem is shown, never hidden
        d.update(step="site" if d.get("site") else "idle", error=str(e)[:300]); _log(d, "Stopped: " + str(e)[:160])
    save(agent, d)


def _joined(pages):
    return "\n\n".join(f"=== {p['url']} ===\n{p['text']}" for p in pages)


def _chunks(pages, size=22000):
    pages = sorted(pages, key=lambda p: _score(p["url"])); out, cur = [], ""
    for p in pages:
        block = f"=== {p['url']} ===\n{p['text'][:9000]}\n\n"
        if len(cur) + len(block) > size and cur:
            out.append(cur); cur = ""
        cur += block
    return (out + [cur])[:3] if cur else out[:3]


def extract(agent, pages):
    """The owner's AI turns the pages into one structured result (up to three passes for a big site, merged). Private data is replaced before anything is sent."""
    merged = {"business": {}, "summary": "", "tone": "", "categories": [], "policies": [], "faqs": [], "unknowns": []}
    for chunk in _chunks(pages):
        raw, _u = R._chat(agent.cfg["reasoner"], SYSTEM, R.redact(chunk, None), 3500)
        m = re.search(r"\{.*\}", raw or "", re.S)
        try:
            j = json.loads(m.group(0)) if m else {}
        except ValueError:
            j = {}
        for k, v in (j.get("business") or {}).items():
            if v and not merged["business"].get(k):
                merged["business"][k] = str(v)[:300]
        merged["summary"] = merged["summary"] or str(j.get("summary") or "")[:700]; merged["tone"] = merged["tone"] or str(j.get("tone") or "")[:200]
        have = {c["name"].lower(): c for c in merged["categories"]}
        for c in (j.get("categories") or []):
            if not isinstance(c, dict) or not c.get("name"):
                continue
            tgt = have.setdefault(str(c["name"]).lower(), {"name": str(c["name"])[:80], "items": []})
            if tgt not in merged["categories"]:
                merged["categories"].append(tgt)
            names = {i["name"].lower() for i in tgt["items"]}
            for it in (c.get("items") or [])[:80]:
                if isinstance(it, dict) and it.get("name") and str(it["name"]).lower() not in names:
                    tgt["items"].append({"name": str(it["name"])[:100], "price": str(it.get("price") or "")[:30], "description": str(it.get("description") or "")[:200]}); names.add(str(it["name"]).lower())
        for k, n in (("policies", 240), ("unknowns", 200)):
            merged[k] += [str(x)[:n] for x in (j.get(k) or []) if str(x).strip() and str(x)[:n] not in merged[k]][:15]
        merged["faqs"] += [{"q": str(x["q"])[:200], "a": str(x["a"])[:500]} for x in (j.get("faqs") or []) if isinstance(x, dict) and x.get("q") and x.get("a")][:20]
    merged["categories"] = merged["categories"][:30]; merged["faqs"] = merged["faqs"][:30]
    if not (merged["summary"] or merged["categories"] or merged["faqs"]):
        raise ValueError("Your AI could not make sense of that site. Add your website's menu or services page, or tell the agent about the business another way.")
    return merged


def fact_suggestions(agent, ext):
    """Only what the owner has not already told the agent (or tells differently): hours, address, a few lines of other information."""
    f = agent.cfg.get("facts") or {}; b = ext.get("business") or {}; out = []
    for key, label, val in (("hours", "Opening hours", b.get("hours")), ("address", "Address", b.get("address"))):
        if val and str(val).strip():
            cur = f.get(key) if _real(f.get(key)) else ""
            out.append({"key": key, "label": label, "value": str(val).strip()[:300], "current": str(cur), "differs": bool(cur) and re.sub(r"\W", "", str(cur).lower()) != re.sub(r"\W", "", str(val).lower())})
    pol = "; ".join(ext.get("policies") or [])[:600]
    if pol and not _real(f.get("info")):
        out.append({"key": "info", "label": "Other information (policies)", "value": pol, "current": "", "differs": False})
    return out


# ---- 5. the owner reviews and approves --------------------------------------------------------------------------------------------------------------------------------------------------------
def menu_text(ext):
    lines = []
    for c in ext.get("categories") or []:
        lines.append(c["name"] + ":")
        lines += [f"- {i['name']}" + (f", {i['price']}" if i.get("price") else "") + (f". {i['description']}" if i.get("description") else "") for i in c["items"]]
    return "\n".join(lines)


def apply(agent, facts=(), profile=True, menu=True, faqs=True):
    """Step 5: what the owner ticked is saved. Facts fill the business details; the profile is approved for the AI; the menu and prices and the website text become things the AI may answer from."""
    from . import brain, connect as SU
    d = load(agent)
    if d.get("step") != "review":
        raise ValueError("There is nothing to review yet.")
    ext = d["extracted"]; done = []
    vals = {s["key"]: s["value"] for s in d.get("fact_suggestions", []) if s["key"] in facts}
    if vals:
        SU.save(agent, "business", vals); done.append("business details: " + ", ".join(sorted(vals)))
    if profile:
        prof = {"summary": ext.get("summary", ""), "tone": ext.get("tone", ""), "hours": (ext.get("business") or {}).get("hours", ""), "services": [c["name"] + ": " + ", ".join(i["name"] for i in c["items"][:8]) for c in ext.get("categories", [])][:25],
                "policies": ext.get("policies", []), "faqs": (ext.get("faqs") or []) if faqs else [], "unknowns": ext.get("unknowns", [])}
        brain.edit(agent, prof); brain.approve(agent); done.append("business profile")
    if menu and ext.get("categories"):
        KN.add_text(agent, "Menu and prices from your website", menu_text(ext), "note", d.get("site", "")); done.append("menu and prices")
    if d.get("text"):
        host = urllib.parse.urlparse(d.get("site", "")).hostname or "website"
        KN.add_text(agent, host + " (whole site)", d["text"], "site", d.get("site", "")); done.append("website text")
    d.update(step="approved", error=""); d["consent"]["approved"] = int(time.time()); d.pop("text", None); _log(d, "Saved: " + "; ".join(done)); save(agent, d)
    agent.state.log(workflow="scan", action="apply", status="ok", dry_run=False, saved=len(done))
    return d


# ---- 6. phrases ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
def suggest_phrases(agent):
    """Ideas for library lines from the approved profile. Nothing is voiced here."""
    from . import brain, learned
    d = load(agent)
    if not ai_ready(agent):
        raise ValueError("Connect your AI first (Connect, Your AI).")
    ext = d.get("extracted") or {}
    prof = brain.for_prompt(agent) or ("Summary: " + ext.get("summary", ""))
    raw, _u = R._chat(agent.cfg["reasoner"], PHRASE_SYSTEM, R.redact(prof + "\n" + menu_text(ext)[:4000], None), 1600)
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        lines = json.loads(m.group(0)).get("lines", []) if m else []
    except ValueError:
        lines = []
    have = {learned.norm(i["text"]) for i in learned.load(agent).get("items", [])}
    out = []
    for l in lines:
        l = re.sub(r"\s+", " ", str(l)).strip()
        if 20 <= len(l) <= 190 and not learned.USER_BAD.search(l) and learned.norm(l) not in have and l not in out:
            out.append(l)
    d["phrases"] = out[:30]; d["step"] = "phrases" if out else d.get("step", "approved"); d["phrase_chars"] = sum(len(x) for x in d["phrases"]); _log(d, f"{len(d['phrases'])} phrase ideas ready."); save(agent, d)
    return d


def add_phrases(agent, lines):
    """Step 6: the owner chose lines. They are added to the library and voiced (this spends the owner's own allowance)."""
    from . import learned
    chosen = [str(x) for x in (lines or []) if str(x).strip()]
    if not chosen:
        raise ValueError("Choose at least one phrase.")
    res = learned.add_lines(agent, "\n".join(chosen[:30])); d = load(agent)
    d["phrases"] = [p for p in d.get("phrases", []) if p not in chosen]; d["step"] = "done" if not d["phrases"] else d.get("step"); d["consent"]["voiced"] = int(time.time()); _log(d, f"Added {len(res['added'])} phrases to the library."); save(agent, d)
    return {"result": res, "state": load(agent)}


def reset(agent):
    try:
        os.remove(_path(agent))
    except OSError:
        pass
    return load(agent)


def view(agent):
    d = load(agent)
    return {"step": d.get("step", "idle"), "known": known(agent), "known_site": known_site(agent), "site": d.get("site", ""), "candidates": d.get("candidates", []), "pages": d.get("pages", []), "extracted": d.get("extracted", {}),
            "fact_suggestions": d.get("fact_suggestions", []), "phrases": d.get("phrases", []), "phrase_chars": d.get("phrase_chars", 0), "error": d.get("error", ""), "log": d.get("log", [])[-8:], "ai_ready": ai_ready(agent),
            "provider": str((agent.cfg.get("reasoner") or {}).get("provider") or "your AI provider")}
