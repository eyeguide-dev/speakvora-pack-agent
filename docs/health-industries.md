# Clinics and hospitals, pharmacies and dispensaries

These businesses handle the most sensitive customers, so the agent is deliberately narrow: **office information, scheduling help and order texts, by default. Anything private comes only from your own connected system, only after you approve it.** This is not legal advice or a compliance certificate: a regulated business still needs its own review and a signed agreement with every provider that touches regulated data (for HIPAA, a business associate agreement).

## What every health bundle does
* **General questions, answered from facts you typed:** hours, address, directions, parking, visiting hours, departments, billing phone (put these in **Connect, Your business, Other things customers ask**). A text containing parking, visiting, departments or billing gets that answer. No patient detail is ever requested for these.
* **A person for anything clinical.** A caller or texter who raises symptoms, results, medicines, doses, interactions, side effects, conditions, treatment, pregnancy, certification or a reaction is connected to staff (call) or told a team member will call (text), and your team is notified. The assistant never gives clinical advice or judgment.
* **Emergencies stop everything.** Someone describing an emergency hears "hang up and call 911" and the menu ends. A child, pet or person who may have swallowed something harmful hears Poison Control (1-800-222-1222) and 911 or a vet, never home advice (speech input must be on).
* **Texts never say why.** Clinic texts give times and places only. Pharmacy and dispensary texts say an order is placed, ready or picked up and never name what is in it. An AI-written message containing a health or product claim is never sent.
* **The assistant says it is automated** and that it can only help with office information.

## Clinics and hospitals
Confirmations, reminders and follow-ups carry the time and place only. A hospital answers general administrative questions the same way (hours, departments, directions, visitor information from your facts). For **patient-specific status** (an appointment, a balance), connect your own system (below). Nothing is read from a chart by the agent.

## Pharmacy
Customers get a plain text when an order is **placed** (with a tracking link if you switched order pages on), **ready for pickup** and **picked up**, and can reach staff by pressing 0 or saying "person". A text with "refill" gets how to ask (call or the pharmacy's app) and tells your team, with no details taken. Dose, interaction, side-effect and substitution questions go to a pharmacist (staff).

## Dispensary
Its own profile. Order texts at **placed, ready and picked up**; the ready text includes a reminder to bring valid photo ID, because **ready is not pickup clearance**: your staff check ID and the order before anything is handed over. The agent never approves an ID, an age or a patient or caregiver status, never talks about dosing, potency advice, effects, conditions or pregnancy (staff do), and never names products in a text. Hours, directions and order updates only.

## Private details from your own system (optional, off until you approve)
To let a verified person ask about their own appointment or order status, connect your records system: **Connect, Your apps**, a connection with the id `records`. The agent sends it `{"phone": "...", "text": "<what they typed>", "channel": "text"|"call"}` and passes on the reply **only if your system answers** `{"found": true, "verified": true, "message": "...", "allowed_phones": ["+1..."]}`, **and** the asking number is on that list, **and** you have approved the policy settings (Settings, Call handling controls: named reviewer, identity method, privacy notice, jurisdiction profile, transfer roster, `phi_enabled`, go-live approval). `verified` means YOUR system checked who is asking (caller ID alone never counts); `allowed_phones` lists the patient's number and any caregiver or representative your system authorised.
On a text the answer goes straight back as the reply. On a call nothing private is spoken: the details are texted to the number on file and erased from the agent's records as soon as they are sent. If your system is unreachable or says no, the person is told staff will help and nothing is guessed from earlier calls.

## The call-handling controls
Settings shows the draft control rules for your industry (Clinics and hospitals, Pharmacy or Cannabis dispensary) and marks the ones the agent already enforces in code. Every rule is a draft until you review it.
