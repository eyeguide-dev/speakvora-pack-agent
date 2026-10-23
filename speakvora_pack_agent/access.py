"""Callers and texters who are deaf, hard of hearing, or find speaking hard (a stutter, slow or effortful speech, a speech condition). This is for the business's own customers: the agent that answers their calls and texts.
What it does, with no AI needed and nothing leaving this computer:
  - A stutter or hesitation ("b-b-book a t-t-table, um, f-for four") is cleaned to what was meant ("book a table for four"); the call record keeps both what was heard and what it was understood as.
  - A caller who is still speaking or stops mid-sentence is given time: the agent says "Take your time, I'm listening", waits longer, and joins the parts together before answering. Then it answers as it would anyone.
  - A caller who is hard of hearing ("speak up", "I can't hear you") gets slower, louder speech for the rest of the call and an offer of a text.
  - A caller who is deaf, or asks for a text, is texted at once and the conversation continues in writing (escalation.accessibility).
How it is handled depends on the business: a clinic or a law office puts a person first and alerts the team; a restaurant or a shop offers text first; an app's support line offers text or a ticket. The owner sees and can change the choice (Settings, AI controls)."""
import json, os, re, time

PRESETS = {
    "text_first": {"label": "Offer a text first", "what": "A caller who is deaf or finds speaking hard is texted straight away. Slow speakers get extra time. After two missed words the agent offers a text, then a person."},
    "person_first": {"label": "A person first", "what": "Used where being understood really matters (clinics, pharmacies, legal, finance, public services). The caller is texted, your team is told at once, and after one missed word a person is connected."},
    "support_app": {"label": "Text or a ticket", "what": "For app and product support lines. The caller is texted a way to continue in writing, a ticket is raised for your team, and slow speakers get extra time."},
}
PROFILE_PRESET = {"clinic": "person_first", "pharmacy": "person_first", "dispensary": "person_first", "legal": "person_first", "finance": "person_first", "public": "person_first", "education": "person_first", "corrections": "person_first", "collections": "person_first",
                  "support": "support_app", "devops": "support_app"}
FILLERS = re.compile(r"\b(?:u+m+|u+h+|e+r+m*|h+m+|a+h+|uh+m+|ehm+|euh+|eh+|[bcdfgjklmnprstvwz]uh)\b")
DANGLING = {"a", "an", "the", "for", "to", "and", "at", "on", "with", "my", "your", "i", "we", "can", "could", "would", "like", "want", "need", "is", "are", "of", "in", "or", "but", "so", "about", "from", "if", "when", "how", "i'd", "i'll", "i'm", "its", "it's", "do", "does", "have", "has", "be", "been", "some", "any", "than", "then", "because", "also", "into", "onto", "by", "as", "was", "were"}
HARD_OF_HEARING = ["hard of hearing", "hearing impaired", "hearing loss", "hearing problem", "speak up", "louder", "can t hear you", "cannot hear you", "i can t hear", "i cannot hear", "cant hear you", "say that again", "what did you say", "pardon", "could you repeat", "can you repeat", "speak slower", "slow down", "too fast", "too quiet", "can t hear well"]
SPEECH_DIFFICULTY = ["stutter", "stammer", "speech impediment", "speech difficulty", "speech problem", "speech disability", "difficulty speaking", "trouble speaking", "take my time", "give me a moment", "give me a minute", "bear with me", "i speak slowly", "i talk slowly", "slow speaker", "relay", "tty"]


def _norm(t):
    from . import escalation as E
    return E.norm(t)


def _has(t, phrases):
    return any(" " + _norm(p).strip() + " " in t for p in phrases)


# ---- cleaning what a stuttering caller said --------------------------------------------------------------------------------------------------------
def clean_speech(text):
    """(cleaned text, number of hesitation marks removed). "b-b-b-book a t-t-table, um, f-for four" -> "book a table for four", 8.
    Repeated sound fragments before the word they belong to, repeated words, fillers (um, uh, er) and stretched letters (boooook) are removed; every real word is kept."""
    t = str(text or "").lower().replace("’", "'")
    marks = 0
    n = len(FILLERS.findall(t)); t = FILLERS.sub(" ", t); marks += n
    t = re.sub(r"(\w)\1{2,}", r"\1\1", t)                                                    # boooook -> book
    NUM = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"}

    def numstut(m):                                                                           # "ff4" is "f-f-four", "tt2" is "t-t-two", "ss6" is "s-s-six"
        w = NUM[m.group(2)]
        return w if w[0] == m.group(1)[0] else m.group(0)
    t = re.sub(r"\b([a-z])\1*(\d)\b", numstut, t)
    toks = [x for x in re.split(r"[\s\-‐-―.,;:!?]+", t) if x]
    out = []
    for i, w in enumerate(toks):
        nxt = toks[i + 1:i + 4]
        if len(w) <= 3 and any(len(x) > len(w) and x.startswith(w) for x in nxt) and not _is_word_before(w, nxt):
            marks += 1; continue                                                             # "b b b book": the fragments before "book"
        out.append(w)
    dedup = []
    for w in out:
        if dedup and dedup[-1] == w and len(w) > 1:
            marks += 1; continue                                                             # "book book a a table" (single letters are kept: "a a" is two fragments below)
        if dedup and dedup[-1] == w and w in ("a", "i"):
            marks += 1; continue
        dedup.append(w)
    return " ".join(dedup).strip(), marks


def _is_word_before(w, nxt):
    """A short real word that happens to start the next word ("a" before "apple", "i" before "if") is a word, not a stutter, unless it is repeated."""
    return w in ("a", "i", "an", "on", "in", "to", "of", "so", "do", "go", "no", "my", "me", "we", "us", "he", "it", "if", "is", "at", "as", "be", "by", "up", "or", "the", "and", "for", "can", "how", "who", "all", "any", "are", "but", "had", "has", "her", "him", "his", "its", "not", "now", "our", "out", "she", "too", "was", "you", "yes", "bit", "get", "got", "let", "may", "new", "one", "say", "see", "two", "way") and not (len(nxt) and nxt[0] == w)


def dangling(text):
    """True when what was said stops in the middle of a sentence: it ends on a joining word, or is only a sound or one short fragment."""
    w = str(text or "").lower().split()
    if not w:
        return False
    return w[-1].strip(".,") in DANGLING or (len(w) == 1 and len(w[0]) <= 2) or len(w) == 0


# ---- the call's state ----------------------------------------------------------------------------------------------------------------------------
def _st(agent, sid):
    d = agent.__dict__.setdefault("_acc", {})
    if len(d) > 500:
        d.clear()
    return d.setdefault(sid or "?", {"holds": 0, "partial": "", "patient": False, "loud": False, "misses": 0})


def mark(agent, sid, **kw):
    _st(agent, sid).update(kw)


def prepare(agent, params, said):
    """Called with what Twilio heard. Returns (text to act on, note, changed). note is 'hold' when the caller has not finished and should be given time."""
    sid = params.get("CallSid") or params.get("From", "")
    st = _st(agent, sid)
    cleaned, marks = clean_speech(said)
    n = _norm(cleaned)
    st["loud_now"] = False
    if _has(n, HARD_OF_HEARING):
        st["loud_now"] = not st["loud"]; st["loud"] = True
    if marks >= 2 or _has(n, SPEECH_DIFFICULTY) or bool((agent.cfg.get("guardrails") or {}).get("patient")):
        st["patient"] = True
    text = (st["partial"] + " " + cleaned).strip() if st["partial"] else cleaned
    held = bool(st["partial"]); st["partial"] = ""
    if not cleaned and held:
        text = (st.get("last_partial") or "").strip()
    if text and st["patient"] and st["holds"] < 3 and cleaned and dangling(text):
        st["partial"] = text; st["last_partial"] = text; st["holds"] += 1
        return text, "hold", True
    if text:
        st["last_partial"] = ""
    return text, "", bool(text != _plain(said))


def _plain(s):
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()


def flags(agent, params):
    st = (agent.__dict__.get("_acc") or {}).get(params.get("CallSid") or params.get("From", ""))
    return {"patient": bool(st and st["patient"]), "loud": bool(st and st["loud"])}


# ---- slower, louder speech for a caller who is hard of hearing ----------------------------------------------------------------------------------
def loudify(agent, xml):
    """Every sentence the caller hears is spoken slower and louder (the phone provider's own voice). A recorded line that is still waiting to be voiced from text stays as it is."""
    def say(m):
        attrs, body = m.group(1), m.group(2)
        if "<prosody" in body:
            return m.group(0)
        return f'<Say voice="Polly.Joanna">{_pro(body)}</Say>'

    def play(m):
        item = os.path.basename(m.group(1)).rsplit(".", 1)[0]
        try:
            txt = agent.audio.dynamic_text(item) or str((agent.pack.by_id.get(item) or {}).get("text") or "")
        except Exception:  # noqa: BLE001
            txt = ""
        if not txt:
            return m.group(0)
        from xml.sax.saxutils import escape
        return f'<Say voice="Polly.Joanna">{_pro(escape(txt))}</Say>'
    xml = re.sub(r"<Say([^>]*)>(.*?)</Say>", say, xml, flags=re.S)
    return re.sub(r"<Play>([^<]*?/audio/[^<]*?)</Play>", play, xml)


def _pro(body):
    return f'<prosody volume="x-loud" rate="slow">{body}</prosody>'


# ---- how a business handles it -----------------------------------------------------------------------------------------------------------------
def _path(agent):
    return os.path.join(agent.state.dir, "accessibility.json")


def preset(agent):
    """The way this business handles callers who are deaf or find speaking hard: what the owner chose, otherwise what the AI suggested, otherwise the default for the business type."""
    try:
        with open(_path(agent), encoding="utf-8") as f:
            d = json.load(f)
        if d.get("preset") in PRESETS:
            return d["preset"]
    except (OSError, ValueError):
        pass
    return PROFILE_PRESET.get(getattr(agent, "profile", ""), "text_first")


def view(agent):
    cur = {}
    try:
        with open(_path(agent), encoding="utf-8") as f:
            cur = json.load(f)
    except (OSError, ValueError):
        pass
    p = preset(agent)
    return {"preset": p, "by": cur.get("by") or "business type", "why": cur.get("why") or "", "presets": {k: v for k, v in PRESETS.items()}, "profile": getattr(agent, "profile", "")}


def save(agent, p, by="owner", why=""):
    if p not in PRESETS:
        raise ValueError("Choose one of the listed ways.")
    os.makedirs(agent.state.dir, exist_ok=True)
    with open(_path(agent), "w", encoding="utf-8") as f:
        json.dump({"preset": p, "by": by, "why": str(why)[:240], "at": int(time.time())}, f)
    return view(agent)


def suggest(agent):
    """With the owner's own AI connected: it reads what kind of business this is and picks how deaf and speech-difficulty callers should be helped. Only the business type and one-line profile are sent. The owner can change it."""
    from . import brain, reasoner as R
    if not brain.configured(agent):
        raise ValueError("Connect your AI first (Connect, Your AI).")
    prof = (brain.for_prompt(agent) or "")[:1200]
    system = ("You decide how a small business's automated phone and text assistant should help callers who are deaf, hard of hearing, or find speaking hard. Choose exactly one way: "
              + "; ".join(f'"{k}" = {v["what"]}' for k, v in PRESETS.items()) + '. Reply with ONE JSON object only: {"preset": "text_first" | "person_first" | "support_app", "why": "one short sentence"}.')
    user = f"Business: {agent.cfg.get('business', '')}\nIndustry profile: {getattr(agent, 'profile', '')}\n{prof}"
    raw, _u = R._chat(agent.cfg["reasoner"], system, user, 120)
    m = re.search(r"\{.*\}", raw or "", re.S); j = json.loads(m.group(0)) if m else {}
    if j.get("preset") not in PRESETS:
        raise ValueError("Your AI did not choose one of the ways. Pick one yourself.")
    return save(agent, j["preset"], by="your AI", why=j.get("why") or "")


def settings(agent):
    return {"person_after": {"text_first": 3, "person_first": 1, "support_app": 3}[preset(agent)], "alert_team": preset(agent) in ("person_first", "support_app")}
