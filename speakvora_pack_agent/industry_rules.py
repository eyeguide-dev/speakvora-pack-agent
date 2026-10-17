"""Industry rules that sit on top of every workflow and every AI suggestion. They are about WHAT may be said, not what may be stored.
A rule can (1) add instructions the AI must follow, (2) block an AI-written message that contains a blocked term before it is sent, and (3) name the things a caller must be handed to a person for.
These rules reduce risk; they are not legal advice and do not make a business compliant by themselves. A clinic or pharmacy still needs its own compliance review, and a written agreement with any AI provider it connects."""
import re

BASE = {"label": "General", "avoid": ["medical, legal or financial advice", "promising refunds or prices that are not in the approved facts"], "block": [], "person_for": ["complaints", "emergencies", "anything it cannot answer from approved facts"],
        "text_hint": ""}
RULES = {
    "clinic": {"label": "Clinic and health", "avoid": ["diagnoses, test results, symptoms, medications or reasons for a visit", "medical advice of any kind"],
               "block": ["diagnos", "prescription", "medication", "test result", "lab result", "positive", "negative", "cancer", "hiv", "std", "pregnan", "mental health", "therapy"],
               "person_for": ["any health question", "results", "emergencies (say: call the local emergency number)"], "text_hint": "Appointment times and places only. Never why the person is coming."},
    "dispensary": {"label": "Dispensary", "avoid": ["dosing, potency advice or how much to use", "claims that a product treats or cures a condition", "safety during pregnancy, breastfeeding or with other medicines", "approving an ID, an age or a patient or caregiver status", "what a customer ordered"],
                   "block": ["dose", "dosage", "how much to take", "treats", "cure", "cures", "helps with", "good for your", "safe during pregnan", "safe to mix", "stronger", "medical advice", "doctor said"],
                   "person_for": ["any question about a product's effects or use", "pregnancy or medicines", "ID, age, patient or caregiver questions", "an adverse reaction (and for an emergency: call 911)"], "text_hint": "Say an order is ready or picked up. Never name products or give any use advice. Pickup is checked by staff with ID."},
    "pharmacy": {"label": "Pharmacy", "avoid": ["which medicines or products a person ordered", "dosage, interactions or advice", "anything about a person's health"],
                 "block": ["dosage", "dose", "interaction", "side effect", "refill of", "prescription for", "diagnos", "overdose"],
                 "person_for": ["any question about a medicine or product", "emergencies"], "text_hint": "Say an order is ready or not. Never name what is in it."},
    "legal": {"label": "Legal", "avoid": ["legal advice", "case details", "outcomes"], "block": ["you will win", "you should sue", "legal advice", "case number"], "person_for": ["any case question"], "text_hint": "Scheduling and office information only."},
    "finance": {"label": "Finance", "avoid": ["financial or investment advice", "account balances or numbers"], "block": ["invest in", "guaranteed return", "account number", "balance is"], "person_for": ["any account question"], "text_hint": "Hours, appointments and general information only."},
    "collections": {"label": "Collections", "avoid": ["threats", "debt details to anyone but the debtor"], "block": ["lawsuit", "arrest", "garnish", "you owe"], "person_for": ["disputes", "hardship"], "text_hint": "Never state a debt in a message."},
    "corrections": {"label": "Corrections", "avoid": ["details about any person held", "case or charge details"], "block": ["charged with", "sentence", "inmate id"], "person_for": ["any question about a person"], "text_hint": ""},
    "education": {"label": "Education", "avoid": ["grades or records about a student", "anything about a minor beyond the schedule"], "block": ["grade is", "gpa", "disciplin", "iep"], "person_for": ["records", "safety concerns"], "text_hint": "Schedules and office information only."},
    "public": {"label": "Public services", "avoid": ["case or benefit details", "legal or immigration advice"], "block": ["immigration status", "case number", "benefit amount"], "person_for": ["any case question"], "text_hint": ""},
    "trades": {"label": "Service business", "avoid": ["promising a price or time that is not in the approved facts"], "block": [], "person_for": ["complaints", "emergencies such as gas, flooding or fire (say: call the local emergency number)", "anything it cannot answer"], "text_hint": "Say what happens next and when."},
    "beauty": {"label": "Service business", "avoid": ["health or skin-condition advice", "promising results"], "block": ["cure", "guaranteed result"], "person_for": ["reactions or injuries", "complaints"], "text_hint": ""},
}


def for_profile(profile):
    return {**BASE, **RULES.get(profile, {})}


def prompt(agent):
    r = for_profile(getattr(agent, "profile", "generic"))
    out = [f"INDUSTRY RULES ({r['label']}): never say or write: " + "; ".join(r["avoid"]) + ".", "Hand the person to a human for: " + "; ".join(r["person_for"]) + "."]
    if r.get("text_hint"):
        out.append(r["text_hint"])
    return "\n".join(out) + "\n\n"


def violation(agent, text):
    """The blocked term found in an AI-written message, or ''."""
    t = str(text or "").lower()
    for term in for_profile(getattr(agent, "profile", "generic"))["block"]:
        if re.search(r"(?<![a-z])" + re.escape(term), t):
            return term
    return ""
