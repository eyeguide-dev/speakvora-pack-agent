"""Industry kits: a complete set of ready-made workflows for each kind of business, written in plain words.

A kit is what that kind of business really does with customers: confirm and remind bookings, say something is ready, follow up after a missed visit, answer after hours, hand a hard question to a person.
Every kit workflow
  - has a plain title and a one-line description ("Reminds customers before their visit"),
  - sends only a sentence from the pack (a slot), so the same workflow runs in any language once the pack has the line,
  - ships switched OFF and waits for the owner to open it, read the wording and approve it (nothing is sent to a customer before that, and Practice mode stays the default after that),
  - goes through the same consent, STOP, quiet hours, limits and ask-before-sending checks as every other message.
Health, pharmacy, dispensary, legal, finance, collections, corrections and public-service kits are written to be safe by design: no promotion, no medical or legal advice, no personal details in a text, a person
takes anything sensitive, and the limits are said honestly. None of this is a claim of HIPAA, TCPA or any other certification or legal compliance; the owner stays responsible for their own rules and agreements.
"""
import re

# profiles where a message must never promote anything and never carry personal details
REGULATED = ("clinic", "pharmacy", "dispensary", "legal", "finance", "collections", "corrections", "public", "education")
# the only profiles that may use "Announce a sale" (see sales.py): shops and other businesses that sell things to the public
SALE_PROFILES = ("retail", "food", "beauty", "laundry", "auto")

# words a regulated kit line (or an owner's edit of it) must not contain: promotion
PROMO_WORDS = ("sale", "sales", "% off", "percent off", "discount", "coupon", "promo", "special offer", "limited time offer", "buy one", "deal", "deals", "free gift", "bonus", "save money", "act now")
# words a health, pharmacy or dispensary line must not contain: details about a person's health or treatment
HEALTH_DETAIL_WORDS = ("diagnos", "positive", "negative", "abnormal", "your results show", "prescribed", "dosage", "dose of", "you have been prescribed", "your condition", "your medication is", "your test shows", "cancer", "hiv", "pregnan", "std ")
# an edit of a line in these kits is refused when it makes a promise that only a person may make
PROMISE_WORDS = ("guarantee", "we guarantee", "you will win", "you will recover", "cure", "safe to take", "no risk", "we will win", "you should take", "you should stop taking")

# kit workflows that hand a sensitive or risky text to a person: once you approve one, it is checked before the general keyword answers
SAFETY_FIRST = ("health_questions_to_a_person", "medicine_questions_to_a_pharmacist", "product_questions_to_staff", "questions_about_a_case_to_a_person", "suspected_fraud_to_a_person", "disputes_to_a_person",
                "case_questions_to_a_person", "case_and_benefit_questions_to_a_person", "grades_and_records_to_staff", "emergency_to_a_person", "roadside_to_a_person", "billing_and_account_to_a_person", "security_to_a_person",
                "damage_and_lost_item_claims_to_a_person")

# the extra events kits listen for, with plain names (merged into the workflow builder's event list)
EVENTS = {
    "call.missed": "Someone calls and nobody answers", "forms.due": "A customer still has forms to complete", "appointment.prep": "A booking needs a reminder of what to bring", "results.ready": "Something is ready to collect or discuss",
    "recall.due": "A customer is due for their next regular visit", "referral.received": "A referral arrives", "refill.ready": "A refill is ready", "refill.due": "A refill is coming due", "order.problem": "A problem with an order",
    "pickup.deadline": "A ready order is waiting too long", "id.check": "A pickup needs an ID check", "intake.received": "A new enquiry or intake arrives", "documents.needed": "More documents are needed",
    "case.update": "There is an update on a matter", "deadline.approaching": "A deadline is coming up", "consultation.confirmed": "A consultation is confirmed", "application.received": "An application arrives",
    "application.update": "An application has an update", "outage.notice": "A service outage starts or ends", "payment.plan_agreed": "A payment plan is agreed", "payment.hardship": "A customer says they are struggling to pay",
    "statement.ready": "A statement or invoice is ready", "booking.created": "A stay is booked", "guest.checkin_open": "Check-in opens for a guest", "guest.checked_in": "A guest has checked in", "room.ready": "A room is ready",
    "guest.checkout_due": "Checkout is today", "guest.checked_out": "A guest has checked out", "booking.arrival_soon": "A guest arrives soon", "waitlist.added": "A customer joins the waitlist", "waitlist.table_ready": "A waitlist table opens up",
    "pickup.ready": "An order is ready to collect", "stock.back": "An item is back in stock", "return.received": "A return arrives", "refund.issued": "A refund is issued", "order.shipped": "An order has shipped",
    "item.ready": "An item is cleaned or finished and ready", "membership.renewing": "A membership renews soon", "aftercare.due": "Aftercare advice is due", "estimate.ready": "An estimate is ready", "estimate.approved": "An estimate is approved",
    "vehicle.ready": "A vehicle is ready", "service.due": "A vehicle is due for service", "enrolment.opened": "Enrolment opens", "class.cancelled": "A class is cancelled", "fee.due": "A fee is coming due",
    "student.absent": "A student is absent", "visit.scheduled": "A visit is scheduled", "visit.cancelled": "A visit is cancelled", "ticket.waiting": "A customer is waiting for an answer", "survey.due": "It is time to ask how we did",
    "visit.rules": "A visitor needs the visiting rules",
}

# slot -> (what the line is for, the plain sentence); the same slots are asked for in every language by the phrase pipeline
S_COMMON = {
    "missed_call_reply": ("Text back someone whose call was missed.", "Sorry we missed your call. A team member will get back to you as soon as we can. You can also reply to this message."),
    "after_hours_reply": ("Answer a text that arrives when the business is closed.", "Thanks for your message. We are closed right now and will reply when we open."),
    "appointment_reminder_morning": ("Reminder on the morning of the booking.", "Good morning. This is a friendly reminder that your {a} is today."),
    "appointment_reminder_early": ("Reminder two days before.", "This is an early reminder about your {a} with us. Reply if you need to change it."),
    "survey_ask": ("Ask how the visit went, without a promotion.", "Thank you for coming. We would like to hear how it went. Reply with a few words or ask for a person to call you."),
}
# the lines Announce a sale needs (sales.py). The sale text itself is the owner's own approved words; these are the fixed lines around it.
S_SALE = {
    "sale_optin_invite": ("Invite a customer to opt in to sale texts, with the STOP promise.", "Reply DEALS to get text messages about our sales. You can reply STOP at any time to stop them."),
    "sale_optin_confirm": ("Confirm a customer opted in to sale texts.", "You are signed up for text messages about our sales. Message and data rates may apply. Reply STOP at any time to stop."),
    "sale_stop_footer": ("Footer on every sale text: how to stop.", "Reply STOP to opt out."),
    "sale_already_optin": ("Reply when someone who already opted in asks to join again.", "You are already signed up for our sale texts. Reply STOP at any time to stop."),
}
EMERGENCY_AFTER_HOURS = "Thanks for your message. We are closed right now and will reply when we open. If this is an emergency, call nine one one."

# ---- the kits ------------------------------------------------------------------------------------------------------------------------------------------------
# item: (name, title, what, trigger, slot, intent, text, team)    trigger: ("event", name) | ("sms", [keywords]) | ("after_hours",) | ("reminder",) | ("missed_call",)
# team: a notice to your own staff (Slack or Teams) sent with the text, or "" for none. {a} in a text is the word for a booking in this kind of business.

KITS = {
    "clinic": [
        ("forms_reminder", "Reminds patients to fill in their forms", "texts patients before a visit that forms are waiting, without naming any health detail", ("event", "forms.due"), "forms_reminder", "Remind to complete forms.",
         "Please complete your forms before your visit so we can see you on time.", ""),
        ("what_to_bring", "Reminds patients what to bring", "texts patients to bring a photo ID and their insurance card", ("event", "appointment.prep"), "bring_id_insurance", "Remind to bring ID and insurance card.",
         "Please bring a photo ID and your insurance card to your visit.", ""),
        ("something_is_ready", "Tells patients to contact you when something is ready", "texts only that there is news to collect or discuss, never what it is, and points to your portal or phone", ("event", "results.ready"), "results_ready", "Tell someone results are ready without details.",
         "Your results are ready. Please contact us or check your patient portal.", "Patient {{customer.name}} was told by text that something is ready. No details were sent."),
        ("checkup_due", "Reminds patients their regular visit is due", "texts that a routine visit is due, such as a yearly check or a dental cleaning, and how to book it", ("event", "recall.due"), "recall_due", "A routine visit is due.",
         "It is time for your next regular visit. Reply or call us to book a time.", ""),
        ("referral_received", "Tells patients you received their referral", "texts that a referral arrived and that someone will call, naming no one and nothing", ("event", "referral.received"), "referral_received", "Confirm a referral arrived.",
         "We have received your referral and a team member will contact you to arrange the next step.", "Referral received for {{customer.name}}."),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after hours, says whom to call in an emergency, and tells your team", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", EMERGENCY_AFTER_HOURS, "After-hours text from {{sms.from}} was answered."),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call with a plain sorry and says a person will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.",
         "Sorry we missed your call. A team member will get back to you as soon as we can. You can also reply to this message.", "Missed call from {{customer.phone}}."),
        ("health_questions_to_a_person", "Passes health questions straight to a person", "never answers a health, medicine or results question: tells the person a team member will call and tells your staff", ("sms", ["symptom", "symptoms", "pain", "bleeding", "medication", "medicine", "results", "diagnosis"]),
         "health_question_to_person", "A health question is passed to a person.", "This is something only our clinical team can answer. A team member will contact you. If it is an emergency, call nine one one.", "Health question by text from {{sms.from}}. Please call them. Nothing was answered."),
    ],
    "pharmacy": [
        ("refill_ready", "Tells customers their refill is ready", "texts that a refill is ready for pickup, without naming any medicine", ("event", "refill.ready"), "refill_ready", "A refill is ready.", "Your refill is ready for pickup at the pharmacy counter.", ""),
        ("refill_coming_up", "Reminds customers a refill is coming up", "texts that it is nearly time to refill, without naming any medicine", ("event", "refill.due"), "refill_reminder", "Reminder to refill.", "It is almost time to refill your prescription.", ""),
        ("pickup_deadline", "Reminds customers to pick up soon", "texts that an order has been waiting, so it is not returned to stock", ("event", "pickup.deadline"), "pickup_deadline", "Pickup deadline.", "Please pick up your order soon. We can only hold it for a limited time.", ""),
        ("insurance_needs_attention", "Asks customers to call about insurance", "texts that something needs checking with their insurance and to call the pharmacy, with no detail", ("event", "order.problem"), "insurance_issue", "Insurance needs attention.", "We need to check something with your insurance. Please call the pharmacy.", "Insurance question for {{customer.name}}. Please call them."),
        ("medicine_questions_to_a_pharmacist", "Passes medicine questions to the pharmacist", "never answers a question about doses, interactions or side effects: says a pharmacist will call", ("sms", ["dose", "dosage", "interaction", "side", "effects", "reaction", "pregnant", "substitute"]),
         "pharmacist_will_call", "A medicine question is passed to the pharmacist.", "A pharmacist needs to answer that. We have passed your question on and someone will call you. If it is an emergency, call nine one one.", "Medicine question by text from {{sms.from}}. Nothing was answered. Please call them."),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after hours and says whom to call in an emergency", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", EMERGENCY_AFTER_HOURS, ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says a person will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.",
         "Sorry we missed your call. A team member will get back to you as soon as we can. You can also reply to this message.", "Missed call from {{customer.phone}}."),
    ],
    "dispensary": [
        ("order_ready_for_pickup", "Tells customers their order is ready", "texts that an order is ready, naming no products", ("event", "pickup.ready"), "order_ready", "Tell the customer an order is ready for pickup.", "Good news, your order is ready for pickup.", ""),
        ("bring_id", "Reminds customers to bring valid ID", "texts that a valid government photo ID is needed to collect", ("event", "id.check"), "pickup_id_reminder", "Remind the customer to bring valid photo ID to collect.",
         "Please bring a valid government photo ID. We can only hand your order to the person who is allowed to collect it.", ""),
        ("pickup_deadline", "Reminds customers to pick up soon", "texts that an order has been waiting a while", ("event", "pickup.deadline"), "pickup_deadline", "Pickup deadline.", "Please pick up your order soon. We can only hold it for a limited time.", ""),
        ("product_questions_to_staff", "Passes product and health questions to staff", "never gives dosing, strength, health or treatment information: says a team member will help in store", ("sms", ["dose", "dosage", "strength", "potency", "treat", "treats", "condition", "pregnant", "medical", "reaction"]),
         "staff_will_help", "A product or health question is passed to staff.", "We cannot give health or dosing advice by text. A team member can help you in store or by phone. If it is an emergency, call nine one one.", "Product or health question by text from {{sms.from}}. Nothing was answered."),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after hours without any promotion", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", EMERGENCY_AFTER_HOURS, ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says a person will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.",
         "Sorry we missed your call. A team member will get back to you as soon as we can. You can also reply to this message.", "Missed call from {{customer.phone}}."),
    ],
    "legal": [
        ("intake_received", "Confirms you received an enquiry", "texts that an enquiry arrived and someone will be in touch, with no advice and no detail of the matter", ("event", "intake.received"), "intake_received", "Intake received.", "Thank you, we have received your information and will be in touch.", "New enquiry from {{customer.name}}. Please follow up."),
        ("consultation_confirmed", "Confirms a consultation", "texts the day and time of a consultation, nothing about the matter", ("event", "consultation.confirmed"), "consultation_confirmed", "Confirm a consultation.", "Your consultation is confirmed. Please bring any papers you have been asked for.", ""),
        ("documents_needed", "Asks clients for missing documents", "texts that documents are needed and to send them through your secure channel, never by text", ("event", "documents.needed"), "documents_needed", "More documents needed.",
         "We need a few more documents. Please send them through our secure channel and not by text.", ""),
        ("matter_update_waiting", "Tells clients there is news without the details", "texts only that there is an update and to contact the office, never what it says", ("event", "case.update"), "case_update", "A case update exists.", "There is an update on your matter. Please contact our office.", ""),
        ("deadline_coming_up", "Reminds clients about an important date", "texts that a date is coming up and to contact the office, naming nothing about the matter", ("event", "deadline.approaching"), "deadline_reminder", "A date is coming up.",
         "An important date is coming up on your matter. Please contact our office so we can go over it with you.", "Deadline reminder sent to {{customer.name}}."),
        ("questions_about_a_case_to_a_person", "Passes legal questions to a person", "never gives legal advice or discusses a case by text: says a team member will contact them", ("sms", ["advice", "deadline", "case", "court", "represent", "settlement", "sue", "privileged"]),
         "legal_question_to_person", "A legal question is passed to a person.", "We cannot give legal advice by text. A member of our team will contact you. This message is not legal advice.", "Legal question by text from {{sms.from}}. Nothing was answered. Please call them."),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after hours, without advice", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", "Thanks for your message. We are closed right now and will reply when we open. This message is not legal advice.", ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says a person will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.",
         "Sorry we missed your call. A team member will get back to you as soon as we can. You can also reply to this message.", "Missed call from {{customer.phone}}."),
    ],
    "finance": [
        ("payment_coming_due", "Reminds customers a payment is due soon", "texts that a payment is due soon, with no amount or account number", ("event", "payment.due"), "payment_due", "Payment due soon.", "A payment is due soon on your account.", ""),
        ("payment_did_not_go_through", "Tells customers a payment did not go through", "texts that a payment failed and to update details in their secure account, never by text", ("event", "payment.failed"), "payment_failed", "Payment failed.",
         "Your payment could not be processed. Please update your payment details in your secure account.", ""),
        ("payment_received", "Confirms a payment arrived", "texts that a payment arrived, with no amount", ("event", "payment.received"), "payment_received", "Confirm a payment arrived.", "Your payment has been received. Thank you.", ""),
        ("statement_ready", "Tells customers a statement is ready", "texts that a statement is ready in their secure account, with no figures", ("event", "statement.ready"), "statement_ready", "A statement is ready.", "Your statement is ready. Please sign in to your secure account to see it.", ""),
        ("struggling_to_pay", "Offers help when someone is struggling to pay", "replies kindly to someone who says they cannot pay and tells your team to call", ("event", "payment.hardship"), "hardship_help", "Offer help with hardship.",
         "If you are having trouble paying, please contact us. We have options that may help.", "Customer {{customer.name}} said they are struggling to pay. Please call them."),
        ("suspected_fraud_to_a_person", "Passes fraud and account questions to a person", "never discusses balances, transfers or disputes by text: says a team member will call", ("sms", ["balance", "transfer", "wire", "fraud", "loan", "dispute", "chargeback", "locked", "unauthorized"]),
         "account_question_to_person", "An account or fraud question is passed to a person.", "For your safety we cannot discuss accounts by text. A team member will contact you. Never share your password, PIN or full card number with anyone.", "Account or fraud question by text from {{sms.from}}. Nothing was answered."),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after hours without discussing any account", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", "Thanks for your message. We are closed right now and will reply when we open. Never share your password or PIN by text.", ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says a person will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.",
         "Sorry we missed your call. A team member will get back to you as soon as we can. You can also reply to this message.", "Missed call from {{customer.phone}}."),
    ],
    "collections": [
        ("payment_plan_agreed", "Confirms a payment plan", "texts that a plan was agreed and where to find its terms, with no figures", ("event", "payment.plan_agreed"), "payment_plan_confirmed", "Confirm a payment plan.",
         "Your payment plan has been recorded. You can see the terms in your account or ask us to send them in writing.", ""),
        ("struggling_to_pay", "Offers help when someone is struggling to pay", "replies kindly and tells your team to call, with no pressure", ("event", "payment.hardship"), "hardship_help", "Offer help with hardship.",
         "If you are having trouble paying, please contact us. We have options that may help.", "Customer {{customer.name}} said they are struggling to pay. Please call them."),
        ("disputes_to_a_person", "Passes disputes and rights questions to a person", "never argues or threatens: says a team member will contact them and that they can ask for a written statement", ("sms", ["dispute", "disputed", "hardship", "garnish", "sue", "validation"]),
         "dispute_to_person", "A dispute is passed to a person.", "We have noted your request. A team member will contact you, and you can ask us to confirm the details in writing.", "Dispute or rights question by text from {{sms.from}}. Nothing was answered."),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after hours with the required notice", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", "Thanks for your message. We are closed right now and will reply when we open.", ""),
    ],
    "corrections": [
        ("visit_scheduled", "Confirms a visit", "texts that a visit is scheduled and to bring valid photo ID", ("event", "visit.scheduled"), "visit_scheduled", "Confirm a visit.", "Your visit has been scheduled. Please bring a valid photo ID.", ""),
        ("visit_cancelled", "Tells visitors a visit was cancelled", "texts that a scheduled visit was cancelled", ("event", "visit.cancelled"), "visit_cancelled", "A visit was cancelled.", "Your scheduled visit has been cancelled.", ""),
        ("case_questions_to_a_person", "Passes questions about a person's case to staff", "never discusses a person's charges, sentence or release: says staff will help", ("sms", ["inmate", "detainee", "charged", "charges", "sentence", "release"]),
         "case_question_to_staff", "A question about a person's case is passed to staff.", "We cannot discuss a person's case by text. A staff member can help you during business hours.", "Case question by text from {{sms.from}}. Nothing was answered."),
    ],
    "public": [
        ("application_received", "Confirms an application arrived", "texts that an application arrived, with no detail about it", ("event", "application.received"), "application_received", "Confirm an application arrived.", "We have received your application. We will let you know when there is an update.", ""),
        ("application_update_waiting", "Tells people there is an update", "texts only that there is an update and to check their secure account", ("event", "application.update"), "application_update", "Application update.", "There is an update on your application. Please check your account.", ""),
        ("more_documents_needed", "Asks for more documents", "texts that documents are needed and where to send them, never by text", ("event", "documents.needed"), "documents_needed", "More documents needed.",
         "We need a few more documents to continue. Please check your account.", ""),
        ("service_outage", "Tells people about a service problem", "texts that a service problem is known and that updates will follow", ("event", "outage.notice"), "outage_notice", "Service outage notice.",
         "We are aware of a service issue and are working on it. We will share an update as soon as we can.", ""),
        ("appointment_help", "Helps with changing an appointment", "tells people how to change a booking by text", ("sms", ["reschedule", "cancel appointment", "change appointment"]), "reschedule_help", "Explain how to change a booking by text.",
         "To change your {a}, please reply with a new day and time and the team will confirm.", "Booking change request from {{sms.from}}: {{sms.body}}"),
        ("case_and_benefit_questions_to_a_person", "Passes case and benefit questions to a person", "never says whether someone qualifies or what their case holds: says staff will help", ("sms", ["case", "benefits", "immigration", "appeal", "eligibility", "visa", "citizenship"]),
         "case_question_to_staff", "A question about a case or benefits is passed to staff.", "We cannot discuss a case or decide eligibility by text. A staff member can help you. Please do not send personal numbers by text.", "Case question by text from {{sms.from}}. Nothing was answered."),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after hours", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", EMERGENCY_AFTER_HOURS, ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says a person will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.",
         "Sorry we missed your call. A team member will get back to you as soon as we can. You can also reply to this message.", "Missed call from {{customer.phone}}."),
    ],
    "education": [
        ("class_cancelled", "Tells families a class is cancelled", "texts that a class is cancelled, with no student names", ("event", "class.cancelled"), "class_cancelled", "A class is cancelled.", "Today's class has been cancelled. We are sorry and will share the new date soon.", ""),
        ("enrolment_open", "Tells families enrolment is open", "texts that enrolment is open, only to people who asked to hear about it", ("event", "enrolment.opened"), "enrolment_open", "Enrolment open.", "Enrolment is now open. Reply for details.", ""),
        ("fee_coming_due", "Reminds families a fee is due", "texts that a fee is due, with no amounts or student names", ("event", "fee.due"), "payment_due", "Fee due.", "A payment is due soon. Please see your account for the details.", ""),
        ("student_absent", "Tells a parent or guardian a student is absent", "texts a short absence notice to the number on file, with no reasons or records", ("event", "student.absent"), "student_absent", "Tell a guardian a student is absent.",
         "We noticed a student in your family was not in class today. Please contact the office if you have a question.", "Absence notice sent for {{customer.name}}."),
        ("what_to_bring", "Reminds students what to bring", "texts a short reminder of what to bring", ("event", "appointment.prep"), "class_bring", "Remind what to bring to class.", "A friendly reminder to bring what you need for your class.", ""),
        ("grades_and_records_to_staff", "Passes grade and record questions to staff", "never shares grades, records or custody details by text: says the office will help", ("sms", ["grades", "gpa", "transcript", "records", "custody", "bullying", "suspended"]),
         "records_to_staff", "A question about records is passed to the office.", "We cannot share grades or records by text. The school office can help you. Please do not send personal details by text.", "Records question by text from {{sms.from}}. Nothing was answered."),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after hours", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", "Thanks for your message. The office is closed right now and will reply when it opens.", ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says a person will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.",
         "Sorry we missed your call. A team member will get back to you as soon as we can. You can also reply to this message.", "Missed call from {{customer.phone}}."),
    ],
    "food": [
        ("added_to_waitlist", "Tells guests they are on the waitlist", "texts guests that they are on the list and when a table opens", ("event", "waitlist.added"), "waitlist_added", "Added to a waitlist.", "You are on our waitlist. We will message you as soon as a table opens up.", ""),
        ("table_is_ready", "Tells guests their table is ready", "texts guests when their table opens up", ("event", "waitlist.table_ready"), "table_ready", "Table is ready.", "Your table is ready. Please check in with the host.", "Table ready for {{customer.name}}."),
        ("hold_a_late_table", "Tells guests you will hold the table", "answers a guest who is running late", ("sms", ["running late", "be late", "on my way", "late"]), "hold_table", "Reassure a late guest.", "No problem, we will hold your table for a few extra minutes.", "{{sms.from}} is running late: {{sms.body}}"),
        ("note_an_allergy", "Confirms you wrote down an allergy", "texts that the allergy note was passed to the kitchen and asks them to tell the staff when they arrive; never promises it is safe", ("sms", ["allergy", "allergic", "gluten", "nut"]),
         "allergy_noted", "Confirm an allergy note.", "We have noted your allergy information for the kitchen. Please also tell your server when you arrive so the team can talk it through with you.", "ALLERGY NOTE from {{sms.from}}: {{sms.body}}. Please pass to the kitchen."),
        ("note_a_special_occasion", "Confirms a special occasion", "texts that a birthday or anniversary note was added", ("sms", ["birthday", "anniversary", "celebrating", "occasion"]), "occasion_noted", "Confirm a special occasion note.", "We have noted your special occasion and will do our best to make it memorable.", "Occasion note from {{sms.from}}: {{sms.body}}"),
        ("book_a_table_by_text", "Helps guests book a table by text", "explains what to send to book a table", ("sms", ["book", "reserve", "reservation", "table"]), "reservation_help", "Explain how to book by text.",
         "To make or change a reservation, please reply with your name, party size and preferred time, and the team will confirm.", "Booking request by text from {{sms.from}}: {{sms.body}}"),
        ("ask_how_it_went", "Asks guests how their visit went", "texts a short thank you and asks for feedback, with no offer in the message", ("event", "survey.due"), "survey_ask", "Ask how the visit went.", S_COMMON["survey_ask"][1], ""),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after closing and points to your hours", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", S_COMMON["after_hours_reply"][1], ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says someone will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.", S_COMMON["missed_call_reply"][1], "Missed call from {{customer.phone}}."),
    ],
    "lodging": [
        ("booking_confirmed", "Confirms a stay", "texts that a stay is booked, with no payment or passport detail", ("event", "booking.created"), "stay_confirmed", "Confirm a stay.", "Your stay is confirmed. We look forward to welcoming you.", ""),
        ("arrival_details", "Sends arrival details before check-in", "texts a short reminder of how to arrive and check in", ("event", "booking.arrival_soon"), "arrival_details", "Tell a guest how to arrive.", "We look forward to seeing you soon. When you arrive, please come to the front desk to check in.", ""),
        ("check_in_open", "Tells guests check-in is open", "texts that they can check in now", ("event", "guest.checkin_open"), "checkin_open", "Check-in opens.", "Check-in is now open. Please come to the front desk when you arrive.", ""),
        ("room_ready", "Tells guests their room is ready", "texts when a room is ready and to collect the key", ("event", "room.ready"), "room_ready", "Room is ready.", "Your room is ready. Please stop by the front desk for your key.", "Room ready for {{customer.name}}."),
        ("checkout_reminder", "Reminds guests about checkout", "texts a friendly checkout reminder on the morning of departure", ("event", "guest.checkout_due"), "checkout_reminder", "Checkout reminder.", "A friendly reminder that checkout is this morning. Thank you for staying with us.", ""),
        ("thanks_after_stay", "Thanks guests after they leave", "texts a thank you and asks how the stay went", ("event", "guest.checked_out"), "thanks_review", "Thank the customer after a visit and ask for a review.", "Thank you for choosing us. If you were happy with your visit, a quick review means a lot to our team.", ""),
        ("front_desk_requests", "Passes guest requests to the front desk", "tells guests the front desk has their request", ("sms", ["towel", "towels", "housekeeping", "late checkout", "early check-in", "extra", "pillow"]), "request_received", "Confirm a request reached the front desk.", "Thank you, we have passed your request to the front desk.", "Guest request from {{sms.from}}: {{sms.body}}"),
        ("after_hours", "Answers texts when the desk is closed", "replies to texts when the front desk is closed", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", "Thanks for your message. The front desk is closed right now and will reply when it opens. If this is an emergency, call nine one one.", ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says someone will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.", S_COMMON["missed_call_reply"][1], "Missed call from {{customer.phone}}."),
    ],
    "retail": [
        ("order_shipped", "Tells customers their order has shipped", "texts that an order shipped", ("event", "order.shipped"), "order_shipped", "Tell the customer an order shipped.", "Your order has shipped and is on its way to you.", ""),
        ("ready_for_pickup", "Tells customers their order is ready to collect", "texts when an order is ready to collect in store", ("event", "pickup.ready"), "pickup_ready", "An order is ready to collect.", "Good news, your order is ready to collect in store.", ""),
        ("back_in_stock", "Tells customers an item is back in stock", "texts only people who asked to be told, about the item they asked for", ("event", "stock.back"), "back_in_stock", "Item back in stock.", "Good news, the item you asked about is back in stock.", ""),
        ("return_received", "Confirms a return arrived", "texts that a return arrived and is being checked", ("event", "return.received"), "return_received", "Return received.", "We have received your return and it is being processed.", ""),
        ("refund_issued", "Tells customers their refund was issued", "texts that a refund was issued and may take a few days", ("event", "refund.issued"), "refund_issued", "Refund issued.", "Your refund has been issued. It can take a few days to appear.", ""),
        ("order_problem", "Apologises for an order problem", "texts a sorry for a problem and says the team is fixing it", ("event", "order.problem"), "sorry_mixup", "Apologise for a mix-up and say it is being fixed.", "We are sorry about the mix-up and the team is fixing it right away.", "Order problem for {{customer.name}}. Please follow up."),
        ("ask_how_we_did", "Asks customers how it went", "texts a thank you and asks for feedback after an order, with no offer in it", ("event", "survey.due"), "survey_ask", "Ask how the order went.", S_COMMON["survey_ask"][1], ""),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after closing", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", S_COMMON["after_hours_reply"][1], ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says someone will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.", S_COMMON["missed_call_reply"][1], "Missed call from {{customer.phone}}."),
    ],
    "beauty": [
        ("aftercare", "Sends aftercare tips after a visit", "texts a short aftercare reminder after a service", ("event", "aftercare.due"), "aftercare_tip", "Aftercare reminder.", "Thank you for visiting. Please follow the aftercare tips we discussed.", ""),
        ("membership_renewing", "Reminds members their membership renews soon", "texts members who agreed to messages that their membership renews soon", ("event", "membership.renewing"), "membership_renewal", "Membership renewal.", "Your membership renews soon. Reply if you would like to make a change.", ""),
        ("rebook_nudge", "Reminds customers it is time to rebook", "texts that it is time for their next visit", ("event", "recall.due"), "rebook_due", "It is time to rebook.", "It is about time for your next visit. Reply to book a time that suits you.", ""),
        ("running_late", "Reassures customers who are running late", "answers a customer who texts that they are late", ("sms", ["running late", "be late", "on my way", "late"]), "running_late_ok", "Reassure someone who is running late.", "No problem, we will hold your {a} for a few extra minutes.", "{{sms.from}} is running late: {{sms.body}}"),
        ("ask_how_it_went", "Asks customers how their visit went", "texts a short thank you and asks for feedback, with no offer in the message", ("event", "survey.due"), "survey_ask", "Ask how the visit went.", S_COMMON["survey_ask"][1], ""),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after closing", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", S_COMMON["after_hours_reply"][1], ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says someone will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.", S_COMMON["missed_call_reply"][1], "Missed call from {{customer.phone}}."),
    ],
    "laundry": [
        ("items_ready", "Tells customers their items are ready", "texts when cleaning is finished and the items are ready to collect", ("event", "item.ready"), "garment_ready", "Garments are ready.", "Your items are cleaned and ready for pickup.", ""),
        ("pickup_reminder", "Reminds customers to collect their items", "texts a reminder when items have been waiting", ("event", "pickup.deadline"), "pickup_deadline", "Pickup deadline.", "Please pick up your order soon. We can only hold it for a limited time.", ""),
        ("problem_with_an_item", "Apologises for a problem with an item", "texts a sorry and says a person will call to put it right", ("event", "order.problem"), "sorry_mixup", "Apologise for a mix-up and say it is being fixed.", "We are sorry about the mix-up and the team is fixing it right away.", "Problem with an item for {{customer.name}}. Please call them."),
        ("damage_and_lost_item_claims_to_a_person", "Passes damage and lost-item claims to a person", "never decides a claim by text: says the manager will call", ("sms", ["damaged", "ruined", "lost", "missing", "claim"]), "claim_to_person", "A claim is passed to a person.", "We are sorry about that. A manager will contact you to look into it.", "Claim by text from {{sms.from}}: {{sms.body}}"),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after closing", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", S_COMMON["after_hours_reply"][1], ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says someone will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.", S_COMMON["missed_call_reply"][1], "Missed call from {{customer.phone}}."),
    ],
    "trades": [
        ("estimate_ready", "Tells customers their estimate is ready", "texts that an estimate is ready and how to approve it", ("event", "estimate.ready"), "estimate_ready", "Estimate is ready.", "Your estimate is ready. Reply to approve it or ask a question.", ""),
        ("estimate_approved", "Confirms an approved estimate", "texts that the approval was received and the work will be scheduled", ("event", "estimate.approved"), "estimate_approved", "Confirm an estimate was approved.", "Thank you, we have your approval and will schedule the work.", "Estimate approved by {{customer.name}}. Please schedule the job."),
        ("emergency_to_a_person", "Passes emergencies and safety problems to a person", "never gives repair advice for a safety problem: tells them to call emergency services and alerts the office", ("sms", ["gas", "sparks", "sparking", "flooding", "flooded", "smoke"]),
         "safety_to_person", "A safety problem is passed to a person.", "If anyone is in danger, leave the building and call nine one one. Do not touch anything. We are alerting our office right now.", "SAFETY TEXT from {{sms.from}}: {{sms.body}}. Please call them now."),
        ("after_hours", "Answers texts when the office is closed", "replies to texts sent after hours", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", "Thanks for your message. The office is closed right now and will reply when it opens. If anyone is in danger, call nine one one.", ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says someone will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.", S_COMMON["missed_call_reply"][1], "Missed call from {{customer.phone}}."),
    ],
    "auto": [
        ("estimate_ready", "Tells customers their repair estimate is ready", "texts that an estimate is ready and how to approve it", ("event", "estimate.ready"), "estimate_ready", "Estimate is ready.", "Your repair estimate is ready. Reply to approve it or ask a question.", ""),
        ("service_is_due", "Reminds customers a service is due", "texts that a vehicle is due for service", ("event", "service.due"), "service_due", "Service reminder.", "Your vehicle is due for service. Reply to book a time.", ""),
        ("vehicle_is_ready", "Tells customers their vehicle is ready", "texts when the work is done and the vehicle is ready", ("event", "vehicle.ready"), "vehicle_ready", "Vehicle is ready.", "Your vehicle is ready for pickup.", ""),
        ("roadside_to_a_person", "Passes roadside and accident calls to a person", "never dispatches or advises on an accident: says to call emergency services and alerts the shop", ("sms", ["accident", "crash", "stranded", "broke down", "breakdown", "tow"]),
         "roadside_to_person", "A roadside problem is passed to a person.", "If anyone is hurt or you are in danger, call nine one one now. We are alerting our team, but we cannot send help by text.", "ROADSIDE TEXT from {{sms.from}}: {{sms.body}}. Please call them now."),
        ("after_hours", "Answers texts when the shop is closed", "replies to texts sent after closing", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", S_COMMON["after_hours_reply"][1], ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says someone will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.", S_COMMON["missed_call_reply"][1], "Missed call from {{customer.phone}}."),
    ],
    "support": [
        ("waiting_for_an_answer", "Apologises when a customer waits too long", "texts a sorry and says a person is on it", ("event", "ticket.waiting"), "apology_delay", "Apologise for a delay and promise an update.", "Sorry for the delay. We will update you as soon as we can.", "{{customer.name}} has been waiting. Please reply."),
        ("ask_how_we_did", "Asks customers how the help went", "texts a short thank you and asks if the problem was solved", ("event", "survey.due"), "survey_ask", "Ask how the help went.", S_COMMON["survey_ask"][1], ""),
        ("billing_and_account_to_a_person", "Passes account and security questions to a person", "never asks for or accepts passwords or codes by text", ("sms", ["breach", "hacked", "compromised", "security", "admin", "delete"]), "security_to_person", "A security question is passed to a person.",
         "For your security, a team member will contact you. Please never send a password or code by text.", "Security question by text from {{sms.from}}. Nothing was answered."),
        ("after_hours", "Answers texts when support is closed", "replies to texts sent after hours", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", S_COMMON["after_hours_reply"][1], ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says someone will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.", S_COMMON["missed_call_reply"][1], "Missed call from {{customer.phone}}."),
    ],
    "devops": [
        ("status_update", "Sends a status update when asked", "replies with the status line when a customer texts status or outage", ("sms", ["status", "outage", "down", "is it down"]), "status_update", "Service status update.", "Here is an update on the service status.", ""),
        ("planned_maintenance", "Warns customers about planned maintenance", "texts that maintenance is about to begin", ("event", "outage.notice"), "maintenance_notice", "Planned maintenance notice.", "Planned maintenance is about to begin.", ""),
        ("security_to_a_person", "Passes security reports to a person", "never accepts a password or key by text", ("sms", ["breach", "hacked", "compromised", "security", "incident"]), "security_to_person", "A security report is passed to a person.",
         "For your security, a team member will contact you. Please never send a password or key by text.", "Security report by text from {{sms.from}}. Nothing was answered."),
        ("after_hours", "Answers texts when support is closed", "replies to texts sent after hours", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", S_COMMON["after_hours_reply"][1], ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says someone will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.", S_COMMON["missed_call_reply"][1], "Missed call from {{customer.phone}}."),
    ],
    "generic": [
        ("ask_how_it_went", "Asks customers how it went", "texts a short thank you and asks for feedback, with no offer in the message", ("event", "survey.due"), "survey_ask", "Ask how the visit went.", S_COMMON["survey_ask"][1], ""),
        ("after_hours", "Answers texts when you are closed", "replies to texts sent after closing", ("after_hours",), "after_hours_reply", "Answer a text that arrives when the business is closed.", S_COMMON["after_hours_reply"][1], ""),
        ("missed_call_text", "Texts people back after a missed call", "replies to a missed call and says someone will respond", ("missed_call",), "missed_call_reply", "Text back someone whose call was missed.", S_COMMON["missed_call_reply"][1], "Missed call from {{customer.phone}}."),
    ],
}

# the smart reminder: how long before a booking a customer is reminded, and the sentence each choice uses
REMINDER_CHOICES = {   # key -> (words the owner sees, minutes before the start (0 = the morning of), the slot that is said)
    "two_days": ("Two days before", 2880, "appointment_reminder_early"),
    "day_before": ("The day before", 1440, "appointment_reminder"),
    "morning_of": ("The morning of the booking", 0, "appointment_reminder_morning"),
    "four_hours": ("Four hours before", 240, "appointment_reminder_today"),
    "two_hours": ("Two hours before", 120, "appointment_reminder_today"),
    "one_hour": ("One hour before", 60, "appointment_reminder_today"),
}
REMINDER_DEFAULT = ["day_before", "two_hours"]
MORNING_AT = "08:00"
# profiles whose customers book a time (they get the smart reminder); the reminder names the booking in their own words (an appointment, a reservation, a visit...)
REMINDER_PROFILES = ("food", "clinic", "lodging", "beauty", "laundry", "retail", "trades", "auto", "education", "public", "legal", "finance", "support", "corrections", "collections", "devops", "generic")

REMINDER_WORDS = {"two_days": "early", "day_before": "a day before", "morning_of": "in the morning", "four_hours": "four hours before", "two_hours": "two hours before", "one_hour": "an hour before"}


def reminder_title(profile):
    return {"clinic": "Reminds patients before their visit", "legal": "Reminds clients before their consultation", "food": "Reminds guests before their reservation", "lodging": "Reminds guests before they arrive",
            "education": "Reminds students and families before a class", "corrections": "Reminds visitors before a visit", "trades": "Reminds customers before the technician comes"}.get(profile, "Reminds customers before their booking")


def sale_allowed(profile):
    """Only shops and other businesses that sell to the public may use Announce a sale. Never a regulated one."""
    return profile in SALE_PROFILES and profile not in REGULATED


def slot_table(profile):
    """slot -> (intent, English example) for everything this kit says. {a} stays in the text: slots.registry swaps in the booking word."""
    from . import industry_kits as IK
    out = {it[4]: (it[5], it[6]) for it in KITS.get(profile, []) if it[4]}
    for slug in slugs_of(profile):                                       # every bundle of this family: its own workflows' lines and its phone welcome
        for it in IK.SLUG_KITS.get(slug, []):
            if it[4]:
                out.setdefault(it[4], (it[5], it[6]))
        if slug in IK.WELCOME:
            out["call_welcome_" + _slug_us(slug)] = ("The first thing a caller hears at this business, before the menu.", IK.WELCOME[slug])
    out.update(IK.CALL_COMMON)
    if profile in REMINDER_PROFILES:
        for k in ("appointment_reminder_morning", "appointment_reminder_early"):
            out[k] = S_COMMON[k]
    if profile in SALE_PROFILES:
        out.update(S_SALE)
    return out


def _slug_us(slug):
    return slug.replace("-", "_")


def slugs_of(profile):
    from . import industry_kits as IK
    return [s for s, p in IK.SLUG_PROFILE.items() if p == profile]


def _sms(slot):
    return {"action": "sms", "to": "{{customer.phone}}", "text": "{{business}}: {{slot:" + slot + "}}"}


def workflow_for(item, profile):
    name, title, what, trig, slot, _intent, _text, team = item
    do = []
    if not slot:                                                        # a notice for your team only: the customer gets nothing
        w = {"on": {"event": trig[1]}}
        do = [{"action": "notify", "text": _text}]
        return {"name": name, "title": title, "what": what, "kit": True, "enabled": False, "approved": False, **w, "do": do}
    if trig[0] == "sms":
        w = {"on": {"sms": {"keywords": list(trig[1])}}}
        do = [{"action": "reply", "text": "{{slot:" + slot + "}}"}]
    elif trig[0] == "after_hours":
        w = {"on": {"sms": {"when_closed": True}}}
        do = [{"action": "reply", "text": "{{slot:" + slot + "}}"}]
    elif trig[0] == "missed_call":
        w = {"on": {"event": "call.missed"}}
        do = [_sms(slot)]
    else:
        w = {"on": {"event": trig[1]}}
        do = [_sms(slot)]
    if team:
        do.append({"action": "notify", "text": team})
    out = {"name": name, "title": title, "what": what, "kit": True, "enabled": False, "approved": False, **w, "do": do}
    if name in SAFETY_FIRST or (trig[0] == "sms" and ("to_a_person" in name or "emergency" in name or name.startswith("crisis"))):
        out["priority"] = True                                          # once approved, this careful answer is looked at before the general keyword answers
    return out


def smart_reminder(profile):
    """One reminder workflow whose timing the owner sets (the day before, the morning of, two hours before...). The line said is chosen by the timing: see engine.tick and reminder_plan."""
    return {"name": "smart_reminder", "title": reminder_title(profile), "what": "texts the customer before a booking at the times you choose, with a line that fits the timing", "kit": True, "enabled": False, "approved": False, "reminder": True,
            "on": {"calendar": {"smart": True, "window_minutes": 30, "title_contains": "Reservation" if profile == "food" else "Appointment"}},
            "do": [{"action": "sms", "to": "{{customer.phone}}", "text": "{{business}}: {{slotvar:reminder.slot}} {{start_local}}."}]}


def reminder_plan(setting, tz_now_local, ev_start_local, now, ev_start, window=30):
    """Which of the owner's chosen reminder times, if any, is due right now for a booking. Returns the choice key or '' (nothing due). A booking is never reminded after it has started, and the morning reminder is skipped
    when the booking starts before the morning reminder time (the earlier reminders cover it)."""
    chosen = [k for k in (setting.get("before") or REMINDER_DEFAULT) if k in REMINDER_CHOICES]
    mins = (ev_start - now) / 60
    for k in chosen:
        label, lead, _slot = REMINDER_CHOICES[k]
        if lead:
            if lead - window <= mins <= lead:
                return k
        else:
            at = str(setting.get("morning_at") or MORNING_AT)
            if ev_start_local.date() == tz_now_local.date() and tz_now_local.strftime("%H:%M") >= at and ev_start_local.strftime("%H:%M") > at and mins >= 45:
                return k
    return ""


def kit_workflows(profile, slug=None):
    """The profile's kit, then the kit of this exact bundle (its slug) on top. Without a slug only the profile kit."""
    from . import industry_kits as IK
    items = [workflow_for(it, profile) for it in KITS.get(profile, KITS["generic"])]
    have = {w["name"] for w in items}; evs = {(w.get("on") or {}).get("event") for w in items}
    for it in (IK.SLUG_KITS.get(slug, []) if slug else []):
        w = workflow_for(it, profile)
        if w["name"] in have or ((w.get("on") or {}).get("event") and (w["on"]["event"] in evs)):
            continue
        items.append(w); have.add(w["name"])
    if profile in REMINDER_PROFILES:
        items.insert(0, smart_reminder(profile))
    if sale_allowed(profile):
        from . import sales
        items.append(sales.workflow())
    return items


def all_slots(profile):
    return slot_table(profile)


def _has(word, low):
    return re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", low) is not None


def violations(profile, text):
    """Words a line must not contain in this kit: promotion in a regulated business, health detail in a health business, promises only a person may make. Used by tests and by the edit screen."""
    low = " " + str(text).lower() + " "
    bad = []
    if profile in REGULATED:
        bad += [w for w in PROMO_WORDS if _has(w, low)]
    if profile in ("clinic", "pharmacy", "dispensary"):
        bad += [w for w in HEALTH_DETAIL_WORDS if _has(w.strip(), low)]
    bad += [w for w in PROMISE_WORDS if _has(w, low)]
    return bad

from . import industry_kits as _IK  # noqa: E402
EVENTS.update(_IK.EV)
