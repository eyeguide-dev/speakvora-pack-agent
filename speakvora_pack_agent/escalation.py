"""Getting a person on the line fast. Two things end an automated conversation at once and send the caller to a person:
  1. the caller asks for one: "support", "customer service", "a person", "a manager", "technical support", "billing department"...
  2. the caller is frustrated: anger, swearing, "you're not listening", "this is a joke", "I want a refund", the same sentence said twice...
Everything here runs on this computer from the words the caller said (no cloud, no AI needed), so it works even when the AI is slow or off. It decides; engine.py does the connecting.
The owner can switch it off and add their own frustration phrases (Settings, AI controls, Built-in safeguards)."""
import re, time

# Words and phrases that always mean "get me a person", wherever they are in the sentence.
PERSON_STRONG = [
    "customer service", "customer services", "customer support", "customer care", "technical support", "tech support", "help desk", "helpdesk", "service desk",
    "real person", "live person", "real human", "live human", "human being", "live agent", "real agent", "a representative", "representative", "operator",
    "supervisor", "manager", "team member", "staff member", "an employee", "somebody else", "someone else", "a real person",
    "speak to someone", "speak with someone", "talk to someone", "talk with someone", "speak to somebody", "speak with somebody", "talk to somebody", "talk with somebody", "get someone", "get somebody",
    "put me through", "transfer me", "connect me", "get me a", "i need a human", "i need a person", "i want a human", "i want a person",
    # other languages the bundles come in
    "hablar con una persona", "hablar con alguien", "servicio al cliente", "atencion al cliente", "un humano", "una persona", "un agente", "el gerente", "un representante",
    "parler a quelqu un", "parler a une personne", "service client", "un humain", "un conseiller", "le directeur", "le responsable",
    "mit einem menschen", "mit jemandem sprechen", "kundendienst", "kundenservice", "einen mitarbeiter", "den manager", "den chef",
    "falar com uma pessoa", "falar com alguem", "atendimento ao cliente", "um humano", "um atendente", "o gerente",
    "parlare con una persona", "parlare con qualcuno", "assistenza clienti", "servizio clienti", "un operatore", "il responsabile",
]
# Single words that mean a person only when the caller says little or says what they want to do ("support please", "I need to talk to an agent"), so "do you support Apple Pay" does not transfer.
PERSON_BARE = ["support", "agent", "person", "human", "someone", "somebody", "rep", "staff", "billing", "sales", "accounts", "accounting", "reception", "receptionist", "front desk", "owner", "department", "persona", "humano", "agente", "personne", "humain", "mensch", "pessoa", "persona", "umano"]
INTENT = re.compile(r"\b(speak|talk|connect|transfer|put me|get me|need|want|let me|can i|could i|may i|i would like|i d like|give me|call|ring|reach|through to|escalate|take me|send me|hablar|parler|sprechen|falar|parlare|quiero|necesito|je veux|ich will|ich brauche|quero|preciso|voglio)\b")
NOT_A_REQUEST = re.compile(r"\b(do|does|did|will|would|can|could|is|are) (you|it|this|that|your|they)\b.*\b(support|supports|supported)\b")

# What a caller says that names a department. The first match decides what the agent says; the phone menu decides where the call goes.
DEPARTMENTS = [("customer service", ["customer service", "customer services", "customer support", "customer care", "servicio al cliente", "atencion al cliente", "service client", "kundendienst", "kundenservice", "atendimento ao cliente", "assistenza clienti", "servizio clienti"]),
               ("technical support", ["technical support", "tech support"]),
               ("support", ["help desk", "helpdesk", "service desk", "support"]),
               ("billing", ["billing", "accounts", "accounting"]), ("sales", ["sales"]), ("front desk", ["front desk", "reception", "receptionist"]),
               ("manager", ["manager", "supervisor", "owner", "gerente", "directeur", "responsable", "chef", "responsabile"])]

# Signs the caller is frustrated. Phrases, not single everyday words, so "what are your hours" or "thank you" never match.
FRUSTRATION = [
    # anger and disgust
    "ridiculous", "unacceptable", "not acceptable", "this is stupid", "so stupid", "useless", "worthless", "pathetic", "terrible service", "terrible", "awful", "horrible", "disgusting", "disgraceful", "outrageous", "absurd",
    "worst service", "worst experience", "worst company", "this sucks", "you suck", "hate this", "i hate", "so angry", "i am angry", "i m angry", "furious", "livid", "pissed", "i am upset", "i m upset", "so upset", "very upset",
    "frustrated", "frustrating", "so annoying", "this is annoying", "annoyed", "irritated", "fed up", "sick of", "sick and tired", "had enough", "ive had enough", "i have had enough", "enough is enough", "losing my patience", "out of patience", "my patience",
    "this is a joke", "you must be kidding", "you have got to be kidding", "are you kidding", "are you serious", "unbelievable", "i can t believe", "i cannot believe", "what is wrong with you", "what s wrong with you", "what kind of",
    # not being heard
    "not listening", "you don t listen", "you do not listen", "you don t understand", "you do not understand", "you never understand", "that s not what i asked", "that is not what i asked", "that s not what i said", "that is not what i said",
    "i didn t ask that", "i did not ask that", "not helpful", "not helping", "you re not helping", "you are not helping", "no help", "isn t helping", "is not helping", "won t help", "can t help me", "cannot help me", "you never help", "stop repeating",
    "you keep saying", "you keep repeating", "same thing again", "i already told you", "i just told you", "i have told you", "i ve told you", "i told you", "like i said", "as i said", "i said", "for the third time", "third time", "second time i", "how many times", "over and over",
    "again and again", "going in circles", "in circles", "round and round", "talking to a wall", "talking to a machine", "stupid robot", "dumb robot", "stupid machine", "this robot", "stop talking", "shut up", "let me finish", "let me talk",
    # demands that need a person
    "i want a refund", "want a refund", "give me a refund", "refund me", "my money back", "money back", "i want to complain", "i want to make a complaint", "file a complaint", "make a complaint", "complaint", "i am complaining", "i m complaining", "complain",
    "report you", "report this", "report your", "lawyer", "attorney", "sue you", "i will sue", "lawsuit", "legal action", "chargeback", "dispute this", "scam", "scammer", "fraud", "rip off", "ripped off", "ripping me off", "cheated", "you lied", "lying to me", "liar",
    "never again", "never coming back", "never using", "take my business elsewhere", "taking my business", "going to your competitor", "cancel my account", "close my account", "i will never", "last chance", "i m done", "i am done", "done with you", "done with this",
    # waiting and urgency
    "waiting forever", "been waiting", "waiting for hours", "waiting for days", "waiting for weeks", "waited long enough", "taking forever", "what s taking so long", "what is taking so long", "no one is helping", "nobody is helping", "nobody helps", "no one helps",
    "no one answers", "nobody answers", "no one has called", "nobody called me back", "nobody has called", 
    # giving up
    "forget it", "never mind", "this is pointless", "pointless", "i give up", "give up", "what s the point", "what is the point", "waste of time", "wasting my time", "waste my time", "wasted my time",
    # sarcasm
    "great just great", "thanks for nothing", "real helpful", "oh great", "wow thanks", "very helpful not", "brilliant not", "thanks a lot not",
    # swearing and insults (kept short; the owner can add more)
    "damn", "dammit", "goddamn", "god damn", "crap", "bullshit", "shit", "shitty", "fuck", "fucking", "fuckin", "wtf", "what the hell", "what the fuck", "go to hell", "screw this", "screw you", "asshole", "bastard", "bitch", "idiot", "idiots", "moron", "morons", "dumb", "jerk", "freaking", "friggin",
    "piss off", "pissing me off", "pissed off",
    # other languages
    "esto es ridiculo", "no me escuchas", "no me entiendes", "estoy harto", "estoy enojado", "estoy molesto", "queja", "quiero un reembolso", "quiero mi dinero", "inutil", "que verguenza", "mierda", "carajo",
    "c est ridicule", "vous ne m ecoutez pas", "vous ne comprenez pas", "j en ai marre", "je suis furieux", "je veux un remboursement", "inutile", "nul", "merde", "putain",
    "das ist lacherlich", "sie horen nicht zu", "sie verstehen nicht", "ich habe genug", "ich bin wutend", "ich will mein geld", "nutzlos", "scheisse", "scheiße",
    "isso e ridiculo", "voce nao escuta", "voce nao entende", "estou farto", "estou com raiva", "quero reembolso", "quero meu dinheiro", "inutil", "merda", "porra",
    "e ridicolo", "non mi ascolti", "non capisci", "sono stufo", "sono arrabbiato", "voglio un rimborso", "inutile", "merda", "cazzo",
]
# A caller who cannot hear or cannot speak easily gets the same help by text, and more time. These phrases switch that on.
ACCESS = ["i am deaf", "i m deaf", "im deaf", "deaf", "i can t speak", "i cannot speak", "unable to speak", "cant speak", "can t talk", "cannot talk",
          "speech impediment", "speech difficulty", "speech disability", "speech problem", "difficulty speaking", "trouble speaking", "stutter", "stammer", "non verbal", "nonverbal", "i am mute", "i m mute", "relay service", "relay operator", "relay call", "this is a relay", "tty", "text relay",
          "text me", "send me a text", "send a text", "message me", "text instead", "can we text", "can you text", "by text", "via text", "sms me", "write to me", "write me", "email me instead",
          "soy sordo", "soy sorda", "no puedo hablar", "mandame un mensaje", "envieme un mensaje", "je suis sourd", "je suis sourde", "je ne peux pas parler", "envoyez moi un sms", "ich bin taub", "ich kann nicht sprechen", "schicken sie mir eine sms",
          "sou surdo", "sou surda", "nao posso falar", "me mande uma mensagem", "sono sordo", "sono sorda", "non posso parlare", "mandami un messaggio"]
_STRIP = re.compile(r"[^a-z0-9À-ɏ' ]+")


def norm(text):
    t = str(text or "").lower().replace("'", " ").replace("’", " ")
    t = _STRIP.sub(" ", t)
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")          # señor = senor, cliente = cliente
    return " " + re.sub(r"\s+", " ", t).strip() + " "


def _has(t, phrase):
    return " " + norm(phrase).strip() + " " in t


def enabled(agent):
    from . import guardrails as G
    return bool(({**G.DEFAULTS, **(agent.cfg.get("guardrails") or {})}).get("escalate", True))


def extra_words(agent):
    from . import guardrails as G
    return [str(x) for x in (({**G.DEFAULTS, **(agent.cfg.get("guardrails") or {})}).get("frustration_words") or []) if str(x).strip()]


def department(t):
    for label, words in DEPARTMENTS:
        if any(_has(t, w) for w in words):
            return label
    return ""


def asks_for_person(t):
    """The caller asks for support, customer service, a person, a manager or a department. t is norm()ed text."""
    if any(_has(t, p) for p in PERSON_STRONG):
        return True
    words = t.split()
    bare = any(_has(t, b) for b in PERSON_BARE)
    if not bare:
        return False
    if NOT_A_REQUEST.search(t.strip()) and not INTENT.search(t):
        return False
    return len(words) <= 4 or bool(INTENT.search(t))


def frustrated(agent, t):
    """Anger, swearing, a demand for a refund or complaint, or one of the owner's own phrases. t is norm()ed text."""
    return any(_has(t, p) for p in FRUSTRATION) or any(_has(t, p) for p in extra_words(agent))


def line(kind, dept, channel):
    """What the caller hears (or reads) right before being connected."""
    if channel == "sms":
        return "I'm sorry about that. I'm asking a team member to text you back right away." if kind == "frustrated" else "Ok, I'm asking a team member to text you back right away."
    if kind == "frustrated":
        return "I'm sorry about that. Ok, I'll be connecting you to a team member now."
    if dept in ("manager",):
        return "Ok, I'll be connecting you to a manager now."
    if dept:
        return f"Ok, I'll be connecting you to our {dept} department now."
    return "Ok, I'll be connecting you to a team member now."


def check(agent, key, text, channel="call"):
    """None, or {kind, dept, why, say}: this turn must go to a person now. Remembers the last thing said on this call or text thread to catch someone repeating themselves."""
    if not enabled(agent):
        return None
    t = norm(text)
    if not t.strip():
        return None
    kind = ""
    if asks_for_person(t):
        kind = "asked"
    elif frustrated(agent, t):
        kind = "frustrated"
    else:
        last = agent.__dict__.setdefault("_esc_last", {}); prev = last.get(key) or ("", 0); words = t.split()
        if prev[0] == t and len(words) >= 4 and time.time() - prev[1] > 2.0:
            kind = "frustrated"                                              # the same sentence twice in a row (not the same turn looked at twice): the agent did not help
    last = agent.__dict__.setdefault("_esc_last", {})
    if not last.get(key) or last[key][0] != t:
        last[key] = (t, time.time())
    if len(last) > 2000:
        last.clear()
    if not kind:
        return None
    dept = department(t) if kind == "asked" else ""
    return {"kind": kind, "dept": dept, "why": "asked for a person" if kind == "asked" else "frustrated caller", "say": line(kind, dept, channel)}


def accessibility(agent, text):
    """None, or {say}: the caller says they are deaf, hard of hearing, cannot speak easily, is using a relay service, or asks for a text instead. The agent texts them and the conversation continues in writing."""
    if not enabled(agent):
        return None
    t = norm(text)
    if t.strip() and any(_has(t, p) for p in ACCESS):
        return {"why": "asked for text", "say": "Ok. I'll text you now so we can continue by text. Please reply to that message."}
    return None
