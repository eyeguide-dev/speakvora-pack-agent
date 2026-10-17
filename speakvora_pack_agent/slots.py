"""Slots: the named moments an industry needs a spoken line for ("order_ready", "appointment_reminder", "handoff_person"...). Workflows ask for slots, never for a phrase number, so the same workflow runs on any pack
of the same industry in any language. A slot is filled, in this order, from (1) the pack's own workflow lines, (2) an existing pack phrase that clearly says the same thing (English packs only), (3) a gap: the agent
writes the gap to slot-requests.json (and can send it to Speakvora) and the phrase bot writes, audits and voices the line for every pack of that industry and language, then ships it in the next pack version."""
import json, os, re

COMMON = {
    "automated_call_notice": ("Said at the start of every outbound call: this call is automated.", "This is an automated call."),
    "call_recorded_notice": ("Tell people the call may be recorded (said first when you record calls).", "This call may be recorded and monitored."),
    "opt_out_footer": ("Added to texts so people can opt out.", "Reply STOP to opt out."),
    "opt_out_ack": ("Confirm the person has been unsubscribed from messages.", "You have been unsubscribed and will not receive more messages from us."),
    "handoff_person": ("Tell a caller a team member is being alerted.", "One moment please, I am letting a team member know you need help."),
    "handoff_received": ("Tell a texter that a team member was notified.", "Thanks, a team member has been notified and will contact you shortly."),
    "hours_intro": ("Lead-in before the business reads its opening hours.", "Here are our opening hours."),
    "directions_intro": ("Lead-in before the business gives its address.", "Here is how to find us."),
    "closed_now": ("Say the business is closed right now.", "We are closed right now. Please try again during our opening hours."),
    "thanks_review": ("Thank the customer after a visit and ask for a review.", "Thank you for choosing us. If you were happy with your visit, a quick review means a lot to our team."),
    "apology_delay": ("Apologise for a delay and promise an update.", "Sorry for the delay. We will update you as soon as we can."),
    "sorry_mixup": ("Apologise for a mix-up and say it is being fixed.", "We are sorry about the mix-up and the team is fixing it right away."),
    "payment_received": ("Confirm a payment arrived.", "Your payment has been received. Thank you."),
    "menu_prompt": ("Phone menu: press 1 hours, 2 booking, 3 status, 0 a person.", "Thanks for calling. Press one for our opening hours, two to book, three to check on something, or zero to reach a person."),
    "track_intro": ("Point the customer to their tracking page.", "You can follow its progress here."),
    "status_help": ("Ask for the reference number to look something up.", "Please tell us your reference number and we will check on it for you."),
}
APPT = {  # appointment-based businesses: {a} is the word for the booking
    "appointment_confirmed": ("Confirm a booking.", "Your {a} is confirmed. We look forward to seeing you."),
    "appointment_reminder": ("Reminder a day before.", "This is a friendly reminder about your {a} with us."),
    "appointment_reminder_today": ("Reminder a couple of hours before.", "Just a reminder that your {a} is coming up soon today."),
    "appointment_changed": ("Confirm a change.", "Your {a} has been updated."),
    "appointment_cancelled": ("Confirm a cancellation.", "Your {a} has been cancelled. We hope to see you another time."),
    "running_late_ok": ("Reassure someone who is running late.", "No problem, we will hold your {a} for a few extra minutes."),
    "no_show_followup": ("Follow up after a missed booking.", "We missed you today. Reply to this message if you would like to book another time."),
    "check_in_prompt": ("Tell someone how to check in.", "When you arrive, please check in at the front desk."),
    "ready_for_you": ("Tell someone staff are ready for them.", "We are ready for you now. Please come on in."),
    "reschedule_help": ("Explain how to change a booking by text.", "To change your {a}, please reply with a new day and time and the team will confirm."),
}
ORDER = {
    "order_received": ("Confirm an order was received.", "Thanks, we have your order and we are already working on it."),
    "order_ready": ("Tell the customer an order is ready for pickup.", "Good news, your order is ready for pickup."),
    "order_ready_delivery": ("Tell the customer a delivery is on its way.", "Your order is on its way and should arrive shortly."),
    "order_delayed": ("Say an order is late and will be updated.", "Sorry, your order is running a little late. We will update you as soon as it is ready."),
    "pickup_instructions": ("Tell the customer where to collect.", "Please come to the pickup counter and give us your name or order number."),
    "order_cancelled": ("Confirm an order was cancelled.", "Your order has been cancelled."),
    "order_preparing": ("Say an order is being prepared.", "We are preparing your order now."),
    "order_picked_up": ("Confirm an order was picked up.", "Your order has been picked up. Thank you."),
    "order_delivered": ("Confirm an order was delivered.", "Your order has been delivered. Thank you."),
}
PROFILES = {   # profile -> (word for a booking, families used, extra slots)
    "food": ("reservation", ("order", "appt"), {
        "table_ready": ("Table is ready.", "Your table is ready. Please check in with the host."), "waitlist_added": ("Added to a waitlist.", "You are on our waitlist. We will message you as soon as a table opens up."),
        "reservation_confirmed": ("Confirm a table booking.", "Your reservation is confirmed. We look forward to seeing you."), "reservation_reminder": ("Reminder a day before.", "This is a friendly reminder about your reservation with us."),
        "reservation_reminder_today": ("Reminder a few hours before.", "Just a reminder that your reservation is coming up soon today."), "reservation_changed": ("Confirm a change.", "Your reservation has been updated."),
        "reservation_cancelled": ("Confirm a cancellation.", "Your reservation has been cancelled. We hope to see you another time."), "hold_table": ("Reassure a late guest.", "No problem, we will hold your table for a few extra minutes."),
        "reservation_help": ("Explain how to book by text.", "To make or change a reservation, please reply with your name, party size and preferred time, and the team will confirm."),
        "allergy_noted": ("Confirm an allergy note.", "We have noted your allergy information for the kitchen."), "occasion_noted": ("Confirm a special occasion note.", "We have noted your special occasion and will do our best to make it memorable."),
        "specials_update": ("Announce new specials.", "Our menu has been updated. Take a look at today's specials."),
        "no_show_followup": ("Follow up after a missed booking.", "We missed you today. Reply to this message if you would like to book another time."),
        "order_status_help": ("Ask for the order number to look it up.", "Please tell us your order number and we will check on it for you.")}),
    "clinic": ("appointment", ("appt",), {"results_ready": ("Tell someone results are ready without details.", "Your results are ready. Please contact us or check your patient portal."), "forms_reminder": ("Remind to complete forms.", "Please complete your forms before your visit to save time."),
                                          "bring_id_insurance": ("Remind to bring ID and insurance card.", "Please bring a photo ID and your insurance card to your visit.")}),
    "pharmacy": ("pickup", ("order",), {"refill_ready": ("A refill is ready.", "Your refill is ready for pickup at the pharmacy counter."), "refill_reminder": ("Reminder to refill.", "It is almost time to refill your prescription."),
                                         "insurance_issue": ("Insurance needs attention.", "We need to check something with your insurance. Please call the pharmacy."), "pickup_deadline": ("Pickup deadline.", "Please pick up your order soon. We can only hold it for a few days.")}),
    "lodging": ("booking", ("appt",), {"booking_confirmed": ("Confirm a stay.", "Your booking is confirmed. We look forward to welcoming you."), "checkin_info": ("Check-in details.", "Check-in is available from the afternoon. Please bring a photo ID."),
                                       "room_ready": ("Room is ready.", "Your room is ready. Please stop by the front desk for your key."), "checkout_reminder": ("Checkout reminder.", "A friendly reminder that checkout is this morning. Thank you for staying with us.")}),
    "laundry": ("pickup", ("order", "appt"), {"garment_ready": ("Garments are ready.", "Your items are cleaned and ready for pickup.")}),
    "retail": ("pickup appointment", ("order", "appt"), {"back_in_stock": ("Item back in stock.", "Good news, the item you asked about is back in stock."), "return_received": ("Return received.", "We have received your return and it is being processed."),
                                      "refund_issued": ("Refund issued.", "Your refund has been issued. It can take a few days to appear.")}),
    "beauty": ("appointment", ("appt",), {"aftercare_tip": ("Aftercare reminder.", "Thank you for visiting. Please follow the aftercare tips we discussed."), "membership_renewal": ("Membership renewal.", "Your membership renews soon. Reply if you would like to make a change."), "quote_followup": ("Check in on a quote or consultation.", "Just checking in on the quote we sent. Reply if you have any questions or would like to go ahead."), "job_followup": ("Follow up after finished work.", "Thank you for choosing us. If anything is not right, reply and we will make it right."), "next_visit_due": ("Remind that the next visit is due.", "It is about time for your next visit. Reply and we will find a time that suits you."), "callback_promise": ("Promise a call back after a call.", "Thanks for calling. We will call you back as soon as we can.")}),
    "trades": ("visit", ("appt",), {"arrival_window": ("Arrival window reminder.", "Our technician will arrive during your scheduled window. We will message you when they are on the way."), "on_the_way": ("Technician on the way.", "Our technician is on the way to you now."),
                                     "estimate_ready": ("Estimate is ready.", "Your estimate is ready. Reply to approve it or ask a question."), "quote_followup": ("Check in on a quote that was sent.", "Just checking in on the quote we sent. Reply if you have any questions or would like to go ahead."), "job_followup": ("Follow up after finished work.", "Thank you for choosing us. If anything is not right, reply and we will make it right."), "next_visit_due": ("Remind that the next visit is due.", "It is about time for your next visit. Reply and we will find a time that suits you."), "callback_promise": ("Promise a call back after a call.", "Thanks for calling. We will call you back as soon as we can.")}),
    "auto": ("service appointment", ("appt",), {"vehicle_ready": ("Vehicle is ready.", "Your vehicle is ready for pickup."), "service_due": ("Service reminder.", "Your vehicle is due for service. Reply to book a time."),
                                                 "estimate_ready": ("Estimate is ready.", "Your repair estimate is ready. Reply to approve it or ask a question."), "repair_received": ("Confirm a vehicle is checked in.", "We have your vehicle and will keep you updated as the work moves along.")}),
    "education": ("class", ("appt",), {"class_reminder": ("Class reminder.", "Your class starts soon. See you there."), "enrolment_open": ("Enrolment open.", "Enrolment is now open. Reply for details."), "payment_due": ("Fee due.", "A payment is due soon for your enrolment.")}),
    "public": ("appointment", ("appt",), {"application_update": ("Application update.", "There is an update on your application. Please check your account."), "outage_notice": ("Service outage notice.", "We are aware of a service issue and are working on it."),
                                           "documents_needed": ("More documents needed.", "We need a few more documents to continue. Please check your account.")}),
    "legal": ("consultation", ("appt",), {"intake_received": ("Intake received.", "Thank you, we have received your information and will be in touch."), "documents_needed": ("More documents needed.", "We need a few more documents. Please send them when you can."),
                                          "case_update": ("A case update exists.", "There is an update on your matter. Please contact our office.")}),
    "finance": ("payment", ("appt",), {"payment_due": ("Payment due soon.", "A payment is due soon on your account."), "payment_failed": ("Payment failed.", "Your payment could not be processed. Please update your payment details."),
                                        "hardship_help": ("Offer help with hardship.", "If you are having trouble paying, please contact us. We have options that may help.")}),
    "support": ("callback", ("appt",), {"ticket_created": ("Ticket created.", "We have created a support ticket for you and will update you soon."), "ticket_update": ("Ticket updated.", "There is an update on your support ticket."),
                                         "callback_scheduled": ("Callback scheduled.", "A team member will call you back at the time we agreed."), "hold_message": ("On hold.", "Thank you for holding. Your call is important to us.")}),
    "corrections": ("visit", ("appt",), {
        "facility_call_notice": ("REQUIRED opening of a call that comes from an inmate.", "This is a call from an inmate at the facility."),
        "call_recorded_notice": ("REQUIRED: tell both parties the call may be recorded and monitored.", "This call may be recorded and monitored."),
        "accept_call_prompt": ("Ask the family member to accept or decline an inmate call.", "To accept this call, press one. To decline, press two."),
        "block_calls_prompt": ("Offer to block future calls from this facility.", "To block future calls from this facility, press nine."),
        "visit_scheduled": ("Confirm a visit.", "Your visit has been scheduled. Please bring a valid photo ID."), "visit_cancelled": ("A visit was cancelled.", "Your scheduled visit has been cancelled."),
        "visit_rules_reminder": ("Remind visitors of rules.", "Please review the visiting rules before you arrive. Visitors must follow the dress code."),
        "account_funded": ("Confirm funds were added to an inmate account.", "Funds have been added to the account. Thank you."), "account_low_balance": ("Low account balance.", "The account balance is low. You can add funds online or by phone."),
        "lockdown_notice": ("Facility-wide notice that visits or calls are paused.", "Visits and calls are temporarily paused. We will update you when normal operations resume."),
        "bail_info_help": ("Point to bail information.", "For bail information, please contact the facility's bail office during business hours.")}),
    "collections": ("payment", ("appt",), {
        "debt_collector_notice": ("REQUIRED statement identifying a debt collection communication.", "This communication is from a debt collector. This is an attempt to collect a debt, and any information obtained will be used for that purpose."),
        "payment_due": ("Payment due soon.", "A payment is due soon on your account."), "payment_failed": ("Payment failed.", "Your payment could not be processed. Please update your payment details."),
        "hardship_help": ("Offer help with hardship.", "If you are having trouble paying, please contact us. We have options that may help."), "payment_plan_offer": ("Offer a payment plan.", "We can set up a payment plan that fits your budget. Reply to learn more.")}),
    "devops": ("meeting", ("appt",), {
        "pipeline_failed": ("A build or deploy pipeline failed.", "A build has failed. Please check your team chat."), "pipeline_succeeded": ("A pipeline passed.", "The build passed."),
        "deploy_succeeded": ("A deployment finished.", "The deployment finished successfully."), "deploy_failed": ("A deployment failed.", "A deployment has failed and may need attention."),
        "incident_opened": ("A production incident was opened.", "A production incident has been opened and needs attention."), "incident_resolved": ("An incident was resolved.", "The incident has been resolved."),
        "oncall_alert": ("Wake the on-call person.", "This is an urgent alert for the on-call engineer. Please check your team chat now."), "oncall_ack_prompt": ("Ask on-call to confirm.", "Please reply to confirm you have seen this alert."),
        "pull_request_ready": ("A pull request needs review.", "A pull request is ready for your review."), "release_published": ("A release shipped.", "A new release has been published."),
        "security_alert": ("A security alert was raised.", "A security alert has been raised on your project. Please review it."), "maintenance_notice": ("Planned maintenance notice.", "Planned maintenance is about to begin."),
        "status_update": ("Service status update.", "Here is an update on the service status."), "ticket_created": ("Ticket created.", "We have created a support ticket for you and will update you soon."),
        "ticket_update": ("Ticket updated.", "There is an update on your support ticket."), "callback_scheduled": ("Callback scheduled.", "A team member will call you back at the time we agreed.")}),
    "generic": ("appointment", ("appt",), {}),
}
# Lines that MUST be said (or texted) in these situations. The agent enforces them: they are added automatically, and if the pack does not have the audio yet the agent says the same words with the phone provider's voice
# and logs a gap, so a required notice is never skipped. These are starting points, not legal advice: have your own counsel review them for your industry and region.
REQUIRED = {
    "*": [{"slot": "automated_call_notice", "applies": ["call_out"]}, {"slot": "opt_out_footer", "applies": ["sms"]}],
    "clinic": [{"slot": "emergency_notice", "applies": ["menu"]}, {"slot": "privacy_notice", "applies": ["menu", "call_out"]}],
    "pharmacy": [{"slot": "emergency_notice", "applies": ["menu"]}, {"slot": "privacy_notice", "applies": ["menu", "call_out"]}],
    "corrections": [{"slot": "facility_call_notice", "applies": ["menu", "call_out"]}, {"slot": "call_recorded_notice", "applies": ["menu", "call_out"]}],
    "collections": [{"slot": "debt_collector_notice", "applies": ["menu", "call_out", "sms"]}],
    "legal": [{"slot": "confidentiality_notice", "applies": ["menu", "call_out", "sms"]}],
}
EXTRA_REQUIRED_LINES = {   # the required lines above that are not in COMMON
    "emergency_notice": ("REQUIRED before a health phone menu.", "If this is an emergency, hang up and call nine one one."),
    "privacy_notice": ("REQUIRED: health details are not shared by text or on this line.", "For your privacy, we cannot share personal health details by text or on this line."),
    "confidentiality_notice": ("REQUIRED for legal communications.", "This message is confidential and meant only for the person it is addressed to."),
}
PROFILE_OF = {"jail-corrections-bail": "corrections", "restaurants-food": "food", "bars-food-trucks": "food", "healthcare": "clinic", "telehealth": "clinic", "pharmacy": "pharmacy", "dispensary": "pharmacy", "hotels-travel": "lodging", "airport-parking-taxi": "lodging",
              "retail-shopping": "retail", "furniture-home-goods": "retail", "fashion-gifts-hobby-stores": "retail", "amazon-marketplace-sellers": "retail", "dropshipping-ecommerce": "retail", "returns-refunds": "retail",
              "beauty-fitness": "beauty", "laundry-dry-cleaning": "laundry", "studios-print-coworking": "beauty", "home-services": "trades", "trades-outdoor-services": "trades", "automotive": "auto", "car-care-roadside": "auto",
              "education-community": "education", "tutoring-online-courses": "education", "government-utilities": "public", "legal-services": "legal", "lending-collections": "collections", "billing-payments": "finance",
              "crypto-pawn-rent-to-own": "finance", "customer-service": "support", "it-saas-support": "devops", "ivr-phone-menus": "support", "website-hosting-internet": "devops", "dating-social-apps": "support", "apps-and-devices": "devops"}


def profile_for(pack_slug):
    return PROFILE_OF.get(pack_slug, "generic")


def registry(profile):
    """slot -> {'intent', 'example'} for an industry profile. The English examples are what the phrase bot starts from in every other language."""
    word, fams, extra = PROFILES.get(profile, PROFILES["generic"])
    out = {k: {"intent": v[0], "example": v[1]} for k, v in COMMON.items()}
    for fam in fams:
        for k, v in (APPT if fam == "appt" else ORDER).items():
            out[k] = {"intent": v[0], "example": v[1].replace("{a}", word)}
    for k, v in extra.items():
        out[k] = {"intent": v[0], "example": v[1]}
    for r in REQUIRED.get("*", []) + REQUIRED.get(profile, []):
        if r["slot"] in EXTRA_REQUIRED_LINES and r["slot"] not in out:
            out[r["slot"]] = {"intent": EXTRA_REQUIRED_LINES[r["slot"]][0], "example": EXTRA_REQUIRED_LINES[r["slot"]][1]}
    for k in out:
        out[k]["required"] = any(r["slot"] == k for r in REQUIRED.get("*", []) + REQUIRED.get(profile, []))
    return out


def required_lines(profile, applies, extra=()):
    """Slot names that must be said/texted in this situation ('call_out', 'menu' or 'sms') for an industry profile."""
    return [r["slot"] for r in REQUIRED.get("*", []) + REQUIRED.get(profile, []) + list(extra) if applies in r["applies"]]


def pack_slug(pack_id):
    """'en-restaurants-food-af_heart' -> ('en', 'restaurants-food')"""
    m = re.match(r"^([a-z]{2})-(.+?)-[a-z]{2}_[a-z0-9]+$", pack_id)
    return (m.group(1), m.group(2)) if m else ("en", pack_id)


# patterns that find an existing English pack phrase for a slot (used only when the pack has no workflow line for it); conservative on purpose
MATCH = {
    "thanks_review": [r"^thank you for (choosing|visiting|dining|shopping)"], "payment_received": [r"payment (has been|was) (received|processed)"], "order_cancelled": [r"^your order has been cancel+ed"],
    "closed_now": [r"we are (currently )?closed"], "sorry_mixup": [r"sorry about the mix-?up"], "apology_delay": [r"sorry for the delay"],
}


def fill(pack, profile, strict_languages=("en",)):
    """Returns (slot_map, gaps). slot_map: slot -> phrase id already in the pack. gaps: [{'slot','intent','example'}] the pack cannot say yet."""
    reg, found, gaps = registry(profile), {}, []
    for slot, info in reg.items():
        if slot in pack.slots:
            found[slot] = pack.slots[slot]; continue
        hit = None
        if pack.language in strict_languages:
            for rx in MATCH.get(slot, []):
                for it in pack.items:
                    if re.search(rx, it["text"], re.I):
                        hit = it["id"]; break
                if hit:
                    break
        if hit:
            found[slot] = hit
        else:
            gaps.append({"slot": slot, **info})
    return found, gaps


def needed_by(workflows):
    """The slot names a workflow file actually uses (so we only request what will be played)."""
    names = set()
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("audio", "play", "prompt") and isinstance(v, (str, list)):
                    names.update(x for x in ([v] if isinstance(v, str) else v) if isinstance(x, str) and not x.isdigit())
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
        elif isinstance(o, str):
            names.update(re.findall(r"\{\{\s*(?:slot|slotvar):([\w]+)\s*\}\}", o))
    walk(workflows)
    return names


def request_file(pack, profile, gaps, path):
    """Writes the queue file the phrase bot reads: what is missing, for which industry and language, with the intent and an English example."""
    doc = {"kind": "workflow_line_request", "pack": pack.meta.get("pack"), "industry_profile": profile, "language": pack.language, "voice": pack.meta.get("voice"), "slots": gaps}
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return doc
