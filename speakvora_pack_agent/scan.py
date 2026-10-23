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
PHRASE_SYSTEM = ("You write short phrases a business says to customers, from its profile and price list. Reply with ONE JSON object only: {\"lines\": [\"...\"]}. Up to 50 lines, each 20 to 170 characters, plain spoken sentences a receptionist "
                 "would say. Make them specific to THIS business: name its real products, dishes or services and say their prices exactly as written, describe current offers and specials, give the hours and address, say how booking or ordering works, "
                 "its policies, thanks and hand-offs. One fact per phrase, so each can be played on its own. Use ONLY facts that are in the profile and price list; never invent a price, offer or name. No names of people, no email addresses, no web links, no card or account numbers.")
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


def apply(agent, facts=(), profile=True, menu=True, faqs=True, daily=False):
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
    d.update(step="approved", error=""); d["consent"]["approved"] = int(time.time()); d.pop("text", None); d["daily"] = {"on": bool(daily), "last": time.time()}; _log(d, "Saved: " + "; ".join(done) + (". I will check your website every day." if daily else ".")); save(agent, d)
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
    src_lines = [x for x in re.split(r"[\n.;]", (prof + "\n" + menu_text(ext)).lower()) if x.strip()]
    good = [l for l in out if grounded(l, src_lines)]                      # a price, time or number in a phrase must sit in the same line of what the business approved as the thing it is about
    d["phrases"] = good[:50]; d["step"] = "phrases" if good else d.get("step", "approved"); d["phrase_chars"] = sum(len(x) for x in d["phrases"]); d["phrase_cost_usd"] = round(d["phrase_chars"] * 3 / 1e6, 4); _log(d, f"{len(d['phrases'])} phrase ideas ready."); save(agent, d)
    return d


ANTICIPATE_SYSTEM = ("You prepare a small business's phone and text assistant BEFORE customers ask. From the business facts below, think of the questions real customers of this kind of business ask most "
                     "(hours, where, prices, what is offered, booking or ordering, policies, how long, payment, parking, accessibility, hand-offs). Reply with ONE JSON object only: "
                     '{"questions": ["up to 25 likely customer questions"], "lines": ["up to 25 phrases"]}. Mix for 25: about 15 short fact answers, 5 acknowledgements of a request (booking, order, issue), 3 clarifying prompts and 2 hand-offs to a person; leave greetings and thanks out, the bundle already has them. Each line is 20 to 170 characters, one plain spoken sentence a receptionist would say, answering one question or handling one moment '
                     "(greeting, one moment, thanks, taking a booking, handing to a person). Use ONLY facts that appear below: real names, real prices exactly as written, real hours. Where the business has not said, write a safe line that "
                     "promises nothing, such as offering to check and get back to them, and put that question in no numbers. Only promise an action (booking, cancelling, changing, taking an order, calling back) if it appears under \"Things the assistant can do\" below; otherwise offer to pass it to a person. Never invent a price, offer, name or time. No people's names, emails, links, card or account numbers.")


STOPW = set("the and for with from open close closed every each day days week daily today tonight only just now here there please will have has are our you your this that dollars dollar price prices cost costs person people per about around hours hour".split())
NUMBER_WORDS = set("two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty hundred thousand".split())
COMMON = set("""about above after again against allow always another answer anything because before being below between booking bookings bring business check checking could customer customers details email follow found getting great happy having help helping here
information inside later looking might minute minutes moment number order orders other outside patience please present provide question questions reservation reservations restaurant right should something sorry still table tables team thank thanks their there these thing think those through today
tonight update various wanted wants welcome which while would write your yours
located location preference prefer seating options option takeout request requests cancel change changes accessibility accessible vegetarian message messages party someone somebody taking confirm confirmed confirms
person people reserve reserved details detail callback follow follows ahead right away flag noted note notes passing paying payment payments delivery menu items item special specials contact moment waiting
available availability happy glad certain sorry unable """.split())


def unverified(line, src):
    """Words in a phrase that are not in anything the business gave (and are not everyday receptionist words): the owner should check these before the line is recorded."""
    have = set(re.findall(r"[a-z]{5,}", src))
    return sorted({w for w in re.findall(r"[a-z]{5,}", line.lower()) if w not in have and w not in COMMON and w not in STOPW})[:4]


ABSOLUTE = r"\b(free|always|never|guaranteed|complimentary|no charge)\b"


def grounded(line, src_lines):
    """A phrase is kept only if every number in it sits in ONE line of the business's own text together with a content word the phrase is about (so '$20 lunch' and '$35 dinner' in the source cannot become
    'dinner is $20'), and every absolute (free, always, never, guaranteed) is in the source too. Still not proof of truth: the owner reviews before anything is recorded."""
    low = line.lower()
    words = {w for w in re.findall(r"[a-z]{4,}", low) if w not in STOPW}
    spelled = [w for w in re.findall(r"[a-z]+", low) if w in NUMBER_WORDS]
    if spelled and not all(any(w in sl for sl in src_lines) for w in spelled):
        return False                                                    # "twelve tables" is a number too
    for n in [n.strip(".,:") for n in re.findall(r"\d[\d.,:]*", line)]:
        if not any(n in sl and (not words or words & set(re.findall(r"[a-z]{4,}", sl))) for sl in src_lines):
            return False
    return all(any(w in sl for sl in src_lines) for w in re.findall(ABSOLUTE, low))


def _context(agent):
    """Everything the agent already holds about the business, as plain text for the owner's own AI (redacted first)."""
    from . import brain
    out = [f"{i['label']}: {i['value']}" for i in known(agent) if i["label"] != "Already read"]
    prof = brain.for_prompt(agent)
    if prof:
        out.append(prof)
    d = load(agent); ext = d.get("extracted") or {}
    if ext:
        out.append(menu_text(ext)[:4000])
    try:
        wf = sorted({str((w.get("on") or {}).get("event") or w.get("name")) for w in agent.workflows if w.get("enabled", True)})[:30]
        out.append("Things the assistant can do for customers: " + ", ".join(wf))
    except Exception:
        pass
    try:
        out.append("Notes the owner added (menu, prices, policies):\n" + KN.text_all(agent, 5000))
    except Exception:
        pass
    return "\n".join(x for x in out if x)


def anticipate(agent):
    """The moment the owner's AI works: think ahead about what customers will ask and prepare phrase ideas from what is already known. Nothing is voiced and nothing leaves the owner's AI provider; recording needs the owner's OK."""
    from . import learned
    if not ai_ready(agent):
        raise ValueError("Connect your AI first (Connect, Your AI).")
    d = load(agent)
    if d.get("auto_busy"):
        return d
    d["auto_busy"] = True; save(agent, d)
    try:
        ctx = _context(agent)
        raw, _u = R._chat(agent.cfg["reasoner"], ANTICIPATE_SYSTEM, R.redact(ctx[:9000], None), 3600)
        m = re.search(r"\{.*\}", raw or "", re.S)
        try:
            j = json.loads(m.group(0)) if m else {}
        except ValueError:
            j = {}
        if not j.get("lines") and raw:                                  # a long answer can be cut off: keep the complete lines that arrived
            part = re.search(r'"lines"\s*:\s*\[(.*)', raw, re.S)
            j = {"lines": re.findall(r'"((?:[^"\\]|\\.){20,190})"', part.group(1)) if part else [], "questions": j.get("questions", [])}
        have = {learned.norm(i["text"]) for i in learned.load(agent).get("items", [])}
        src = ctx.lower(); src_lines = [x for x in re.split(r"[\n.;]", src) if x.strip()]; good = []
        for l in j.get("lines", []):
            l = re.sub(r"\s+", " ", str(l)).strip()
            if not (20 <= len(l) <= 190) or learned.USER_BAD.search(l) or learned.norm(l) in have or l in good:
                continue
            if grounded(l, src_lines):                                      # every number must sit in the same line of the business's own text as the item it is about
                good.append(l)
        d = load(agent)
        d["phrases"] = good[:30]; d["phrase_chars"] = sum(len(x) for x in d["phrases"]); d["phrase_cost_usd"] = round(d["phrase_chars"] * 3 / 1e6, 4)
        d["flags"] = {l: unverified(l, src) for l in d["phrases"] if unverified(l, src)}
        d["anticipated"] = {"at": int(time.time()), "questions": [str(q)[:140] for q in j.get("questions", [])][:25], "count": len(d["phrases"])}
        d["auto_ready"] = bool(good); _log(d, f"Thought ahead about customer questions: {len(good)} phrase ideas ready." if good else "Thought ahead, but there was not enough business information yet for safe phrases.")
        save(agent, d)
        agent.state.log(workflow="scan", action="anticipate", status="ok", dry_run=False, ideas=len(good))
    finally:
        d = load(agent); d.pop("auto_busy", None); save(agent, d)
    return load(agent)


def start_anticipating(agent, force=False):
    """Only after the owner says OK (their business details go to their own AI provider): runs in the background so the dashboard never waits."""
    d = load(agent)
    if d.get("auto_busy") or (d.get("anticipated") and not force):
        return False
    def go():
        try:
            anticipate(agent)
        except Exception as e:
            dd = load(agent); dd.pop("auto_busy", None); _log(dd, "Could not think ahead: " + str(e)[:120]); save(agent, dd)
    threading.Thread(target=go, daemon=True).start()
    return True


def add_phrases(agent, lines):
    """Step 6: the owner chose lines. They are added to the library and voiced (this spends the owner's own allowance)."""
    from . import learned
    chosen = [str(x) for x in (lines or []) if str(x).strip()]
    if not chosen:
        raise ValueError("Choose at least one phrase.")
    res = {"added": [], "skipped": []}
    for i in range(0, min(len(chosen), 60), 30):                              # the library takes up to 30 lines at a time
        part = learned.add_lines(agent, "\n".join(chosen[i:i + 30])); res["added"] += part["added"]; res["skipped"] += part["skipped"]
        if any("budget" in str(x.get("reason", "")) for x in part["skipped"]):
            break
    d = load(agent); said = {a["text"] for a in res["added"]}
    d["voiced"] = (d.get("voiced") or []) + [{"text": t, "at": int(time.time())} for t in chosen if t in said]
    d["phrases"] = [p for p in d.get("phrases", []) if p not in set(chosen)]; d["auto_ready"] = bool(d["phrases"] and d.get("auto_ready")); d["step"] = "done" if not d["phrases"] and d.get("step") == "phrases" else d.get("step"); d["consent"]["voiced"] = int(time.time()); _log(d, f"Added {len(res['added'])} phrases to the library."); save(agent, d)
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
            "checks": d.get("checks", []), "daily": (d.get("daily") or {"on": False}), "updates": d.get("updates"), "stale": d.get("stale", []), "phrase_cost_usd": d.get("phrase_cost_usd", 0), "budget": __import__("speakvora_pack_agent.learned", fromlist=["budget"]).budget(agent), "auto_ready": bool(d.get("auto_ready")), "flags": d.get("flags") or {}, "auto_busy": bool(d.get("auto_busy")), "anticipated": d.get("anticipated"), "provider": str((agent.cfg.get("reasoner") or {}).get("provider") or "your AI provider")}


# ---- 7. checking what the AI now says (the owner confirms the data) ----------------------------------------------------------------------------------------------------------------------------
def make_checks(agent):
    """Questions a customer would ask, taken from what was just learned. The owner asks the AI each one, sees the answer and its sources, and says whether it is right; a wrong answer is fixed in the owner's own words."""
    d = load(agent); ext = d.get("extracted") or {}; qs = ["What are your hours?", "Where are you located?"]
    for c in (ext.get("categories") or [])[:6]:
        for it in c["items"][:1]:
            if it.get("price"):
                qs.append(f"How much is the {it['name']}?")
    qs += [f["q"] for f in (ext.get("faqs") or [])[:4]]
    qs += [u for u in (ext.get("unknowns") or [])[:2]]
    seen, out = set(), []
    for q in qs:
        k = re.sub(r"\W", "", q.lower())
        if k not in seen and q.strip():
            seen.add(k); out.append({"q": q.strip()[:200], "answer": "", "sources": [], "status": "new"})
    d["checks"] = out[:10]; _log(d, f"{len(d['checks'])} questions ready to check."); save(agent, d)
    return d


def check_ask(agent, i):
    from . import converse
    d = load(agent); ch = d.get("checks") or []
    if not (0 <= int(i) < len(ch)):
        raise ValueError("No such question.")
    r = converse.try_it(agent, ch[int(i)]["q"])
    ch[int(i)].update(answer=r["answer"], sources=[str(s)[:80] for s in (r.get("sources") or [])][:4], handoff=bool(r.get("handoff")), status="asked"); save(agent, d)
    return d


def check_mark(agent, i, ok, fix=""):
    d = load(agent); ch = d.get("checks") or []
    if not (0 <= int(i) < len(ch)):
        raise ValueError("No such question.")
    c = ch[int(i)]
    if ok:
        c["status"] = "right"
    else:
        fix = " ".join(str(fix or "").split())[:500]
        if len(fix) < 3:
            raise ValueError("Type the right answer, in your own words.")
        KN.add_qa(agent, c["q"], fix); c.update(status="fixed", answer=fix)
    _log(d, ("Confirmed: " if ok else "Corrected: ") + c["q"][:80]); save(agent, d)
    return d


# ---- every day: has the website changed? ------------------------------------------------------------------------------------------------------------------------------------------------------
def set_daily(agent, on):
    d = load(agent); dl = d.get("daily") or {"on": False, "last": 0}; dl["on"] = bool(on); d["daily"] = dl; _log(d, "Daily website check " + ("on" if on else "off")); save(agent, d); return d


def _items(ext):
    out = {}
    for c in (ext.get("categories") or []):
        for it in c["items"]:
            out[it["name"].strip().lower()] = {"name": it["name"], "price": it.get("price", ""), "category": c["name"]}
    return out


def _norm(s):
    return re.sub(r"\W", "", str(s or "").lower())


def diff(old, new):
    """What changed between what the owner approved and what the website says now: prices, new and removed items, hours, address, policies."""
    a, b = _items(old), _items(new); out = []
    for k, it in b.items():
        if k not in a:
            out.append({"kind": "new", "item": it["name"], "price": it["price"], "text": f"New: {it['name']}" + (f" ({it['price']})" if it["price"] else "")})
        elif it["price"] and a[k]["price"] and _norm(it["price"]) != _norm(a[k]["price"]):
            out.append({"kind": "price", "item": it["name"], "old": a[k]["price"], "new": it["price"], "text": f"Price change: {it['name']} was {a[k]['price']}, now {it['price']}"})
    out += [{"kind": "removed", "item": it["name"], "text": f"No longer listed: {it['name']}"} for k, it in a.items() if k not in b]
    for key, label in (("hours", "Opening hours"), ("address", "Address")):
        o, n = (old.get("business") or {}).get(key), (new.get("business") or {}).get(key)
        if o and n and _norm(o) != _norm(n):
            out.append({"kind": key, "old": o, "new": n, "text": f"{label} changed: was {o}, now {n}"})
    op = {_norm(x) for x in old.get("policies") or []}
    out += [{"kind": "policy", "text": "New rule: " + x} for x in (new.get("policies") or []) if _norm(x) not in op]
    return out[:60]


def daily_tick(agent, fetch=None):
    """Called every minute by the agent; acts at most once a day, and only if the owner switched the daily check on and approved a site."""
    d = load(agent); dl = d.get("daily") or {}
    if not dl.get("on") or d.get("step") not in ("approved", "phrases", "done") or not d.get("site") or not ai_ready(agent) or time.time() - float(dl.get("last") or 0) < 86400:
        return False
    dl["last"] = time.time(); d["daily"] = dl; save(agent, d)
    threading.Thread(target=daily_run, args=(agent, fetch), daemon=True).start(); return True


def daily_run(agent, fetch=None):
    d = load(agent)
    try:
        pages = crawl(agent, d["site"], 40, fetch, 0.6 if fetch is None else 0)
        if not pages:
            raise ValueError("the website could not be read today")
        new = extract(agent, pages); changes = diff(d.get("extracted") or {}, new)
        d = load(agent)
        if changes:
            d["updates"] = {"found": int(time.time()), "changes": changes, "extracted": new, "text": _joined(pages)[:300000], "fact_suggestions": fact_suggestions(agent, new)}; _log(d, f"Your website changed: {len(changes)} changes waiting for your OK.")
        else:
            _log(d, "Checked your website: nothing changed.")
        d["daily"]["checked"] = int(time.time()); save(agent, d)
        agent.state.log(workflow="scan", action="daily", status="changes" if changes else "same", dry_run=False, changes=len(changes))
    except Exception as e:  # noqa: BLE001
        d = load(agent); _log(d, "Daily check could not finish: " + str(e)[:120]); save(agent, d)
    return load(agent)


def apply_updates(agent, facts=()):
    """The owner said yes to the changes: the price list and site text are replaced, hours and address updated if ticked, the profile refreshed, lines that quote an old price are listed to remove, and new phrase ideas are made for what is new."""
    from . import brain, connect as SU, learned
    d = load(agent); up = d.get("updates")
    if not up:
        raise ValueError("There is nothing new to review.")
    old, new = d.get("extracted") or {}, up["extracted"]; done = []
    for s in list(KN._idx(agent).get("sources", [])):
        if (s.get("title") or "") == "Menu and prices from your website" or str(s.get("title") or "").endswith("(whole site)"):
            KN.remove(agent, s["id"])
    if new.get("categories"):
        KN.add_text(agent, "Menu and prices from your website", menu_text(new), "note", d.get("site", "")); done.append("price list")
    if up.get("text"):
        KN.add_text(agent, (urllib.parse.urlparse(d.get("site", "")).hostname or "website") + " (whole site)", up["text"], "site", d.get("site", "")); done.append("website text")
    vals = {s["key"]: s["value"] for s in up.get("fact_suggestions", []) if s["key"] in facts}
    if vals:
        SU.save(agent, "business", vals); done.append("details: " + ", ".join(sorted(vals)))
    prof = {"summary": new.get("summary", ""), "tone": new.get("tone", ""), "hours": (new.get("business") or {}).get("hours", ""), "services": [c["name"] + ": " + ", ".join(i["name"] for i in c["items"][:8]) for c in new.get("categories", [])][:25],
            "policies": new.get("policies", []), "faqs": new.get("faqs", []), "unknowns": new.get("unknowns", [])}
    brain.edit(agent, prof); brain.approve(agent); done.append("profile")
    stale = []
    names = {c["item"].lower() for c in up["changes"] if c["kind"] in ("price", "removed")}
    lib = {learned.norm(i["text"]): i["id"] for i in learned.load(agent).get("items", [])}
    for v in d.get("voiced") or []:
        if any(n in v["text"].lower() for n in names) and learned.norm(v["text"]) in lib:
            stale.append({"text": v["text"], "id": lib[learned.norm(v["text"])]})
    d.update(extracted=new, updates=None, stale=stale); _log(d, "Updated: " + "; ".join(done) + (f". {len(stale)} recorded lines quote an old price." if stale else ".")); save(agent, d)
    try:
        suggest_phrases(agent)
    except Exception:  # noqa: BLE001 - new phrase ideas are optional
        pass
    return load(agent)


def dismiss_updates(agent):
    d = load(agent); d["updates"] = None; _log(d, "Kept what you approved before."); save(agent, d); return d


def remove_stale(agent, ids):
    """The owner chose to remove recorded lines that quote an old price."""
    from . import learned
    d = load(agent); gone = 0
    for s in d.get("stale") or []:
        if s["id"] in (ids or []):
            try:
                learned.remove(agent, s["id"]); gone += 1
            except Exception:  # noqa: BLE001
                pass
    d["stale"] = [s for s in d.get("stale") or [] if s["id"] not in (ids or [])]; _log(d, f"Removed {gone} outdated lines."); save(agent, d); return d
