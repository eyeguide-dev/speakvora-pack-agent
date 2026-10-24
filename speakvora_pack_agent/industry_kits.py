"""One kit per BUNDLE (industry slug), on top of the profile kit in kits.py.

A bundle's slug (restaurants-food, healthcare, pharmacy, jail-corrections-bail...) is how we know which workflows ship with it. The profile kit holds what every business of that family needs
(for example every shop); this file holds what THAT business type needs on top (a bar, a car-care shop, a telehealth practice, a utility, a marketplace seller...), plus a spoken welcome for its phone line.

Item: (name, title, what, trigger, slot, intent, text, team) exactly as in kits.KITS. Each slug-only slot is language-neutral and is written natively in every language by the phrase pipeline.
Health, legal, money, public, school and prison bundles are written safe by design: no promotion, no advice, no personal details, a person for anything sensitive, honest limits (see kits.REGULATED).
"""

# slug -> profile (kept equal to slots.PROFILE_OF by a test, plus the bundles that use the generic profile)
SLUG_PROFILE = {
    "jail-corrections-bail": "corrections", "restaurants-food": "food", "bars-food-trucks": "food", "healthcare": "clinic", "telehealth": "clinic", "pharmacy": "pharmacy", "dispensary": "dispensary",
    "hotels-travel": "lodging", "airport-parking-taxi": "lodging", "retail-shopping": "retail", "furniture-home-goods": "retail", "fashion-gifts-hobby-stores": "retail", "amazon-marketplace-sellers": "retail",
    "dropshipping-ecommerce": "retail", "returns-refunds": "retail", "beauty-fitness": "beauty", "studios-print-coworking": "beauty", "laundry-dry-cleaning": "laundry", "home-services": "trades",
    "trades-outdoor-services": "trades", "automotive": "auto", "car-care-roadside": "auto", "education-community": "education", "tutoring-online-courses": "education", "government-utilities": "public",
    "legal-services": "legal", "lending-collections": "collections", "billing-payments": "finance", "crypto-pawn-rent-to-own": "finance", "customer-service": "support", "ivr-phone-menus": "support",
    "dating-social-apps": "support", "it-saas-support": "devops", "website-hosting-internet": "devops", "apps-and-devices": "devops", "everyday": "generic", "guidance-wayfinding": "generic",
    "kiosks-self-service": "generic", "warehouse-voice": "generic",
}

EV = {}      # event -> plain name, merged into the workflow builder's list by kits.py


def _e(event, plain):
    EV[event] = plain
    return event


def _i(name, title, what, trig, slot, intent, text, team=""):
    t = ("event", _e(trig[1], trig[2])) if trig[0] == "event" else trig
    return (name, title, what, t, slot, intent, text, team)


def _p(*words):
    return ("sms", list(words))


# the welcome a caller hears first (the pack's own voice), then the menu. Said only when the pack has the line.
WELCOME = {
    "healthcare": "Thank you for calling. I can give you our hours and address, help with appointment questions, or connect you to a team member. If this is an emergency, hang up and call nine one one.",
    "telehealth": "Thank you for calling. I can help with video visit questions, our hours, or connect you to a team member. If this is an emergency, hang up and call nine one one.",
    "pharmacy": "Thank you for calling the pharmacy. I can share our hours and address, or connect you to the pharmacy counter. If this is an emergency, hang up and call nine one one.",
    "dispensary": "Thank you for calling. I can share our hours, address and pickup details, or connect you to a team member.",
    "restaurants-food": "Thank you for calling. I can share our hours and address, help with a reservation or an order, or connect you to the host.",
    "bars-food-trucks": "Thanks for calling. I can tell you where we are today, when we are open, or connect you to a team member.",
    "hotels-travel": "Thank you for calling. I can help with check-in and checkout details, directions, or connect you to the front desk.",
    "airport-parking-taxi": "Thank you for calling. I can help with pickup and parking questions, directions, or connect you to a team member.",
    "retail-shopping": "Thank you for calling. I can share our hours and address, help with an order or a return, or connect you to a team member.",
    "furniture-home-goods": "Thank you for calling. I can help with delivery and pickup questions, our hours, or connect you to a team member.",
    "fashion-gifts-hobby-stores": "Thank you for calling. I can share our hours and address, help with an order or a gift question, or connect you to a team member.",
    "amazon-marketplace-sellers": "Thank you for calling. I can help with an order question or a return, or connect you to a team member.",
    "dropshipping-ecommerce": "Thank you for calling. I can help with where your order is, a return, or connect you to a team member.",
    "returns-refunds": "Thank you for calling. I can explain how returns and refunds work, check on one with your order number, or connect you to a team member.",
    "beauty-fitness": "Thank you for calling. I can help with booking, class times and membership questions, or connect you to a team member.",
    "studios-print-coworking": "Thank you for calling. I can help with bookings, our hours, or connect you to a team member.",
    "laundry-dry-cleaning": "Thank you for calling. I can tell you when your order will be ready, share our hours, or connect you to a team member.",
    "home-services": "Thank you for calling. I can help with booking a visit, check on an arrival window, or connect you to the office.",
    "trades-outdoor-services": "Thank you for calling. I can help with booking a job, check on a visit, or connect you to the office.",
    "automotive": "Thank you for calling. I can help with service appointments, check on your vehicle, or connect you to the service desk.",
    "car-care-roadside": "Thank you for calling. I can help with appointments and quotes, or connect you to a team member. If anyone is in danger, hang up and call nine one one.",
    "education-community": "Thank you for calling. I can share class times, our hours and enrolment details, or connect you to the office.",
    "tutoring-online-courses": "Thank you for calling. I can help with session times, enrolment questions, or connect you to a team member.",
    "government-utilities": "Thank you for calling. I can share office hours, help with service updates and appointments, or connect you to a staff member. If this is an emergency, hang up and call nine one one.",
    "legal-services": "Thank you for calling. I can share our hours, help schedule a consultation, or connect you to a team member. I cannot give legal advice.",
    "lending-collections": "Thank you for calling. This is an automated assistant. I can share our hours, help with payment options, or connect you to a team member.",
    "billing-payments": "Thank you for calling. I can share our hours, point you to your secure account, or connect you to a team member. Please never say your card number or password on this call.",
    "crypto-pawn-rent-to-own": "Thank you for calling. I can share our hours and address, help with payment questions, or connect you to a team member.",
    "customer-service": "Thank you for calling. I can help with order and account questions, or connect you to a team member.",
    "ivr-phone-menus": "Thank you for calling. You can speak or use your keypad. I can share our hours, help with common questions, or connect you to a team member.",
    "dating-social-apps": "Thank you for calling support. I can help with account and safety questions, or connect you to a team member. If you are in danger, hang up and call nine one one.",
    "it-saas-support": "Thank you for calling support. I can check the service status, take your details for a ticket, or connect you to a team member.",
    "website-hosting-internet": "Thank you for calling. I can check the service status, take your details for a ticket, or connect you to a team member.",
    "apps-and-devices": "Thank you for calling support. I can help with setup questions, check the service status, or connect you to a team member.",
    "everyday": "Thank you for calling. I can share our hours and address, take a message, or connect you to a team member.",
    "guidance-wayfinding": "Welcome. I can help you find your way, share opening times, or connect you to a team member.",
    "kiosks-self-service": "Thank you for calling. I can help with a problem at one of our kiosks, share our hours, or connect you to a team member.",
    "warehouse-voice": "Thank you for calling the warehouse desk. I can share receiving hours and dock details, or connect you to a team member.",
    "jail-corrections-bail": "Thank you for calling. This is an automated assistant. I can share visiting information and office hours, or connect you to a staff member.",
}

SLUG_KITS = {
    "healthcare": [
        _i("new_patient_welcome", "Welcomes new patients", "texts a short welcome and what to do before a first visit, with no health detail", ("event", "patient.new", "A new patient registers"), "new_patient_welcome", "Welcome a new patient.",
           "Welcome, we are glad you chose us. Please arrive a little early for your first visit so we can finish your forms."),
        _i("insurance_card_update", "Asks patients to bring updated insurance details", "texts a reminder to bring a new insurance card to the next visit", ("event", "insurance.update_due", "Insurance details need updating"), "insurance_update_due", "Ask for updated insurance details.",
           "Please bring your updated insurance card to your next visit."),
        _i("visit_summary_ready", "Tells patients a visit summary is ready", "texts only that a summary is waiting in the patient portal", ("event", "summary.ready", "A visit summary is ready"), "summary_ready", "A visit summary is ready.",
           "Your visit summary is ready in your patient portal."),
        _i("earlier_time_opened", "Offers an earlier time that opened up", "texts that an earlier time is free and to reply to take it", ("event", "slot.opened", "An earlier time opens up"), "earlier_time_opened", "An earlier appointment opened up.",
           "An earlier appointment time has opened up. Reply if you would like it."),
        _i("billing_questions_to_the_office", "Passes billing questions to your billing office", "tells the person the billing office will contact them and never to text card numbers", _p("bill", "statement", "copay", "invoice", "insurance claim"),
           "billing_to_office", "A billing question is passed to the billing office.", "Our billing office will contact you. Please do not send card numbers or personal details by text.", "Billing question by text from {{sms.from}}. Nothing was answered."),
        _i("crisis_to_a_person", "Passes a person in crisis to help straight away", "answers a worried message with crisis and emergency numbers and tells your team to call at once", _p("crisis", "suicide", "suicidal", "hurt myself", "kill myself", "end my life"),
           "crisis_line", "A person may be in crisis.", "If you are in crisis, call or text nine eight eight in the United States, or call nine one one now. A team member is being told right away.", "URGENT: a crisis message from {{sms.from}}. Please call them now."),
    ],
    "telehealth": [
        _i("video_visit_link", "Sends the video visit link", "texts that the video link is ready and to join a few minutes early", ("event", "video.link_ready", "A video visit link is ready"), "video_link_ready", "A video visit link is ready.",
           "Your video visit link is ready. Please join a few minutes early."),
        _i("video_visit_tech_help", "Helps people who cannot join the video visit", "tells people a team member will help and never walks through anything medical", _p("link", "video", "camera", "cannot join", "can't join", "audio"),
           "video_help", "Help someone who cannot join a video visit.", "If you cannot join, please call us and a team member will help you get connected.", "Video visit trouble from {{sms.from}}: {{sms.body}}"),
        _i("visit_starting_soon", "Tells patients their visit is about to begin", "texts that the provider is about to join", ("event", "video.starting", "A video visit is about to start"), "video_starting", "A video visit is starting.",
           "Your video visit is about to begin. Please make sure you are in a quiet place with a good connection."),
        _i("crisis_to_a_person", "Passes a person in crisis to help straight away", "answers a worried message with crisis and emergency numbers and tells your team to call at once", _p("crisis", "suicide", "suicidal", "hurt myself", "kill myself", "end my life"),
           "crisis_line", "A person may be in crisis.", "If you are in crisis, call or text nine eight eight in the United States, or call nine one one now. A team member is being told right away.", "URGENT: a crisis message from {{sms.from}}. Please call them now."),
    ],
    "pharmacy": [
        _i("delivery_on_the_way", "Tells customers their delivery is on the way", "texts that a delivery is coming, naming nothing in it", ("event", "pharmacy.delivery", "A pharmacy delivery goes out"), "pharmacy_delivery", "A delivery is on its way.",
           "Your delivery from the pharmacy is on its way. Someone needs to be there to receive it."),
        _i("transfer_received", "Confirms a transfer request arrived", "texts that a transfer request arrived and the pharmacy will call, with no detail", ("event", "transfer.received", "A prescription transfer request arrives"), "transfer_received", "Confirm a transfer request arrived.",
           "We have received your transfer request and the pharmacy will contact you."),
        _i("consultation_offered", "Offers a call with the pharmacist", "texts that the pharmacist is available to talk and how to ask", ("event", "pharmacist.offer", "A pharmacist chat is offered"), "pharmacist_available", "Offer a talk with the pharmacist.",
           "Our pharmacist is happy to talk with you. Please call the pharmacy counter when it suits you."),
        _i("out_of_stock_call", "Tells customers an item needs a call", "texts that something needs a call from the pharmacy, naming nothing", ("event", "order.on_hold", "An order is on hold"), "order_on_hold", "An order needs a call.",
           "Your order needs a quick call from the pharmacy. Please call us when you can."),
    ],
    "dispensary": [
        _i("order_confirmed_adults", "Confirms an order for pickup", "texts that an order is placed, naming no products", ("event", "pickup.confirmed", "A pickup order is confirmed"), "pickup_confirmed", "Confirm a pickup order.",
           "Your order is confirmed for pickup. Please bring a valid government photo ID."),
        _i("id_not_accepted", "Explains what happens when ID cannot be accepted", "texts that staff may not hand over an order without a valid ID and offers a call", ("event", "id.rejected", "An ID cannot be accepted"), "id_not_accepted", "Explain an ID problem.",
           "We could not hand over the order today without a valid government photo ID. Please call us and a team member will help."),
        _i("store_hours_changed", "Tells customers hours changed", "texts a plain notice of changed hours to people who agreed to messages, with no offers", ("event", "hours.changed", "Your opening hours change"), "hours_changed", "Opening hours have changed.",
           "Our opening hours have changed. Please see our website or call us for the new times."),
    ],
    "restaurants-food": [
        _i("large_party_enquiry", "Passes large group requests to the manager", "tells the person the manager will confirm a large party", _p("large party", "big group", "party of ten", "private room", "banquet"),
           "large_party_to_manager", "A large booking is passed to the manager.", "Thank you. For a large group our manager will contact you to confirm the details.", "Large party enquiry from {{sms.from}}: {{sms.body}}"),
        _i("catering_enquiry", "Handles catering questions", "tells the person the catering team will reply and gathers nothing sensitive", _p("catering", "cater", "event order"),
           "catering_to_team", "A catering question is passed to the team.", "Thank you for asking about catering. Our team will reply with details as soon as we can.", "Catering enquiry from {{sms.from}}: {{sms.body}}"),
        _i("pickup_order_running_late", "Tells guests a pickup order is running late", "texts a sorry and a new estimate from your kitchen", ("event", "order.running_late", "A pickup order runs late"), "order_late_sorry", "A pickup order is late.",
           "Sorry, your order is taking a little longer than planned. We will let you know the moment it is ready."),
        _i("lost_item", "Handles lost property questions", "tells the guest the host will check and call back", _p("left my", "lost my", "forgot my", "lost and found"),
           "lost_item_to_host", "A lost item question is passed to the host.", "Sorry about that. We will check for it and a team member will get back to you.", "Lost item enquiry from {{sms.from}}: {{sms.body}}"),
        _i("reservation_deposit_reminder", "Reminds guests about a booking deposit", "texts that a booking needs its deposit, with no amount", ("event", "deposit.due", "A booking deposit is due"), "deposit_due", "A booking deposit is due.",
           "Your reservation needs its deposit to be held. Please complete it using the link we sent."),
    ],
    "bars-food-trucks": [
        _i("truck_location_today", "Tells people where the truck is today", "texts today's location to people who asked", ("event", "truck.location", "The truck moves to a new spot"), "truck_location", "Today's truck location.",
           "We are open today. Our location and hours are on our page."),
        _i("sold_out", "Says an item has sold out", "texts that something sold out so people can choose again", ("event", "item.sold_out", "An item sells out"), "item_sold_out", "An item sold out.",
           "Sorry, that item has sold out today. Reply if you would like something else."),
        _i("event_booking_enquiry", "Handles private event and truck hire questions", "tells people the team will reply about hire dates", _p("book the truck", "private event", "hire", "wedding", "corporate"),
           "event_hire_to_team", "A hire question is passed to the team.", "Thank you for your interest. Our team will reply about dates and details soon.", "Event hire enquiry from {{sms.from}}: {{sms.body}}"),
        _i("age_check_reminder", "Reminds guests an ID check applies", "texts that photo ID may be asked for when ordering drinks", ("event", "id.check", "A pickup needs an ID check"), "age_id_reminder", "Remind guests an ID check applies.",
           "Please bring a valid photo ID. We may ask to see it before serving drinks."),
    ],
    "hotels-travel": [
        _i("pre_arrival_questions", "Answers parking and arrival questions before check-in", "replies with the details you wrote for arrival", _p("parking", "early check-in", "arrive", "arrival", "late arrival"),
           "arrival_questions", "Answer arrival questions.", "Thank you for asking. Our front desk will confirm the details for your arrival and reply soon.", "Arrival question from {{sms.from}}: {{sms.body}}"),
        _i("housekeeping_request", "Passes housekeeping requests to staff", "tells the guest housekeeping has their request", _p("housekeeping", "clean", "towels", "linen", "toiletries"),
           "housekeeping_noted", "A housekeeping request was noted.", "Thank you, housekeeping has your request and will take care of it as soon as they can.", "Housekeeping request from {{sms.from}}: {{sms.body}}"),
        _i("noise_or_problem_in_room", "Passes room problems to the front desk right away", "tells the guest the desk is on it and tells your team", _p("noise", "broken", "not working", "no hot water", "air conditioning", "wifi"),
           "room_problem_to_desk", "A room problem is passed to the front desk.", "We are sorry about that. The front desk has been told and will help you right away.", "ROOM PROBLEM from {{sms.from}}: {{sms.body}}"),
        _i("late_checkout_request", "Handles late checkout requests", "tells the guest the desk will reply, with no promise", _p("late checkout", "check out late"),
           "late_checkout_noted", "A late checkout request was noted.", "Thank you for asking. The front desk will reply about late checkout as soon as they can.", "Late checkout request from {{sms.from}}"),
        _i("booking_changed_by_property", "Tells guests their booking changed", "texts that a booking was changed and to contact the desk", ("event", "booking.changed", "A stay is changed"), "stay_changed", "A stay was changed.",
           "Your stay has been updated. Please contact the front desk if you have questions."),
    ],
    "airport-parking-taxi": [
        _i("driver_on_the_way", "Tells riders the driver is on the way", "texts that the driver is coming", ("event", "driver.on_the_way", "A driver is on the way"), "driver_on_the_way", "A driver is on the way.", "Your driver is on the way and will arrive shortly."),
        _i("driver_arrived", "Tells riders the driver has arrived", "texts that the driver is outside", ("event", "driver.arrived", "A driver has arrived"), "driver_arrived", "A driver has arrived.", "Your driver has arrived and is waiting for you."),
        _i("shuttle_pickup_instructions", "Sends shuttle pickup instructions", "texts where to wait for the shuttle", ("event", "shuttle.ready", "A shuttle is ready"), "shuttle_pickup_info", "Shuttle pickup instructions.", "Your shuttle is ready. Please wait at the pickup point and a driver will meet you."),
        _i("flight_delay_noted", "Confirms a flight delay was noted", "texts that the pickup time was moved", ("event", "flight.delayed", "A flight is delayed"), "flight_delay_noted", "A flight delay was noted.", "We have noted your delay and will adjust your pickup. Reply if your plans change again."),
        _i("lost_item_in_vehicle", "Handles lost items left in a vehicle", "tells the person the team will check", _p("left in", "lost my", "forgot my", "left my"), "lost_item_to_team", "A lost item is passed to the team.", "Sorry about that. We will check the vehicle and a team member will get back to you.", "Lost item enquiry from {{sms.from}}: {{sms.body}}"),
    ],
    "retail-shopping": [
        _i("gift_card_balance_to_a_person", "Passes gift card questions to staff", "never discusses card numbers by text", _p("gift card", "gift certificate", "store credit"), "gift_card_to_staff", "A gift card question is passed to staff.",
           "For your safety please do not send card numbers by text. A team member will help you with your gift card.", "Gift card question from {{sms.from}}. Nothing was answered."),
        _i("item_on_hold_ready", "Tells customers a held item is ready", "texts that an item set aside is ready", ("event", "hold.ready", "A held item is ready"), "hold_ready", "A held item is ready.", "The item we set aside for you is ready. We will hold it for a short time."),
        _i("loyalty_points_note", "Answers loyalty questions", "tells people where to see their points", _p("points", "rewards", "loyalty"), "loyalty_answer", "Answer a loyalty question.", "You can see your points and rewards in your account or at the counter."),
        _i("price_match_question", "Passes price questions to the team", "never promises a price match: says the team will reply", _p("price match", "cheaper", "price adjust"), "price_question_to_team", "A price question is passed to the team.", "Thank you for asking. A team member will reply about prices and what we can do.", "Price question from {{sms.from}}: {{sms.body}}"),
    ],
    "furniture-home-goods": [
        _i("delivery_window", "Tells customers their delivery window", "texts the day and window of a delivery", ("event", "delivery.scheduled", "A delivery is scheduled"), "delivery_window", "A delivery window.", "Your delivery is scheduled. We will message you when the team is on the way."),
        _i("delivery_team_on_the_way", "Tells customers the delivery team is on the way", "texts when the truck leaves", ("event", "delivery.on_the_way", "The delivery team is on the way"), "delivery_team_coming", "The delivery team is coming.", "Our delivery team is on the way. Please make sure someone is there to receive your order."),
        _i("damaged_on_arrival", "Handles damage reports kindly", "says sorry and that a person will arrange a fix", _p("damaged", "broken", "scratched", "dent", "missing part"), "damage_to_team", "A damage report is passed to the team.", "We are very sorry about that. A team member will contact you to put it right.", "Damage report from {{sms.from}}: {{sms.body}}"),
        _i("assembly_booking", "Confirms an assembly booking", "texts the assembly visit was booked", ("event", "assembly.scheduled", "An assembly visit is scheduled"), "assembly_booked", "An assembly visit is booked.", "Your assembly visit is booked. We will send a reminder before it."),
        _i("showroom_appointment_help", "Helps book a showroom visit", "tells people how to ask for a showroom time", _p("showroom", "see in store", "visit the store"), "showroom_help", "Explain how to book a showroom visit.", "To book a showroom visit, please reply with a day and time and the team will confirm."),
    ],
    "fashion-gifts-hobby-stores": [
        _i("gift_wrapping_request", "Handles gift wrap and message requests", "tells the customer the request was noted", _p("gift wrap", "gift message", "wrap it"), "gift_wrap_noted", "A gift wrap request was noted.", "Thank you, we have noted your gift request and will take care of it."),
        _i("size_exchange_help", "Helps with size exchanges", "explains how to ask for another size", _p("wrong size", "too small", "too big", "exchange"), "exchange_help", "Explain how to exchange an item.", "To exchange an item, please reply with your order number and the size you would like and the team will help."),
        _i("pre_order_arrived", "Tells customers a pre-order arrived", "texts that a pre-order is in", ("event", "preorder.arrived", "A pre-order arrives"), "preorder_arrived", "A pre-order arrived.", "Good news, the item you pre-ordered has arrived."),
        _i("workshop_or_class_reminder", "Reminds customers about a workshop", "texts a short reminder of a class they booked", ("event", "workshop.reminder", "A workshop is coming up"), "workshop_reminder", "A workshop reminder.", "A friendly reminder that your workshop is coming up soon. We look forward to seeing you."),
    ],
    "amazon-marketplace-sellers": [
        _i("order_question_to_the_platform", "Points marketplace buyers to the right place", "tells buyers to message through the marketplace, and not to share card details", _p("amazon", "marketplace", "ebay", "etsy", "my order"), "marketplace_redirect", "Point a buyer to the marketplace messages.",
           "For the fastest help with a marketplace order, please use the messages in your order page. Please never share card details by text."),
        _i("shipping_label_created", "Tells buyers a label was made", "texts that the order is being packed", ("event", "label.created", "A shipping label is made"), "label_created", "A shipping label was made.", "Your order has been packed and a shipping label was created. We will share tracking soon."),
        _i("tracking_shared", "Sends tracking when it is ready", "texts that tracking is ready", ("event", "tracking.ready", "Tracking is ready"), "tracking_ready", "Tracking is ready.", "Your tracking details are ready. You can follow your order using the link in your messages."),
    ],
    "dropshipping-ecommerce": [
        _i("supplier_delay_notice", "Tells customers about a supplier delay", "texts a sorry and a plain new estimate", ("event", "supplier.delay", "A supplier delay happens"), "supplier_delay", "A supplier delay.", "Sorry, your order is delayed at our supplier. We will update you as soon as we have a new date."),
        _i("order_shipped_from_supplier", "Tells customers it left the warehouse", "texts that the order left the warehouse", ("event", "supplier.shipped", "A supplier ships an order"), "supplier_shipped", "A supplier shipped an order.", "Your order has left our warehouse partner and is on its way."),
        _i("abandoned_cart_gentle", "Reminds shoppers about a cart, only if they agreed", "texts one gentle reminder, never repeated, only to people who agreed to messages", ("event", "cart.abandoned", "A cart is left behind"), "cart_reminder", "A gentle cart reminder.", "You left something in your cart. It is still there if you would like to finish your order."),
        _i("where_is_my_order", "Answers where is my order", "asks for the order number and a person checks", _p("where is my order", "tracking", "has it shipped"), "order_status_ask", "Ask for the order number.", "Please reply with your order number and we will check on it for you."),
    ],
    "returns-refunds": [
        _i("return_label_sent", "Sends return instructions", "texts that a return label was sent", ("event", "return.label_sent", "A return label is sent"), "return_label_sent", "A return label was sent.", "We have sent your return label. Please pack the item and follow the instructions."),
        _i("return_in_transit", "Tells customers the return is on its way", "texts that the return was received by the carrier", ("event", "return.in_transit", "A return is on its way back"), "return_in_transit", "A return is on its way.", "Your return is on its way back to us. We will tell you when it arrives."),
        _i("refund_timing_question", "Explains refund timing without promises", "tells people how long refunds can take and where to look", _p("refund", "money back", "when will i get"), "refund_timing", "Explain refund timing.", "Refunds can take a few days to appear after we process them. A team member can check on yours."),
        _i("return_window_ending", "Tells customers a return window is closing", "texts a plain notice that the return period is ending", ("event", "return.window_ending", "A return window is ending"), "return_window_ending", "A return window is ending.", "A reminder that the time to return your item is ending soon."),
    ],
    "beauty-fitness": [
        _i("class_waitlist_spot", "Tells members a class spot opened", "texts that a spot opened and to reply to claim it", ("event", "class.spot_opened", "A class spot opens up"), "class_spot_open", "A class spot opened.", "A spot has opened in the class you wanted. Reply soon if you would like it."),
        _i("class_cancelled", "Tells members a class is cancelled", "texts that a class was cancelled", ("event", "class.cancelled", "A class is cancelled"), "class_cancelled_member", "A class was cancelled.", "Sorry, your class has been cancelled. We will help you pick another time."),
        _i("membership_freeze_help", "Explains how to pause a membership", "tells members how to ask and passes it to staff", _p("freeze", "pause my membership", "cancel membership"), "membership_change_help", "Explain how to change a membership.", "To change your membership, a team member will contact you. Please do not send payment details by text.", "Membership change request from {{sms.from}}: {{sms.body}}"),
        _i("first_visit_tips", "Welcomes first-time visitors", "texts what to bring on a first visit", ("event", "visit.first", "A first visit is booked"), "first_visit_welcome", "Welcome a first-time customer.", "We are looking forward to your first visit. Please arrive a few minutes early."),
        _i("injury_or_reaction_to_a_person", "Passes injuries and reactions to a person", "never gives advice: tells the person to seek medical help and alerts your team", _p("injured", "injury", "reaction", "allergic", "burn"), "reaction_to_person", "An injury or reaction is passed to a person.",
           "We are sorry to hear that. If you need medical help, call nine one one. A team member is being told and will contact you.", "URGENT: reaction or injury message from {{sms.from}}: {{sms.body}}"),
    ],
    "studios-print-coworking": [
        _i("proof_ready", "Tells customers a print proof is ready", "texts that a proof is ready to approve", ("event", "proof.ready", "A print proof is ready"), "proof_ready", "A proof is ready.", "Your proof is ready. Please reply to approve it or tell us what to change."),
        _i("print_job_ready", "Tells customers a print job is ready", "texts that a job is ready to collect", ("event", "job.ready", "A job is ready"), "print_job_ready", "A print job is ready.", "Your print job is ready for pickup."),
        _i("desk_booking_confirmed", "Confirms a desk or room booking", "texts the booking and access instructions", ("event", "desk.booked", "A desk or room is booked"), "desk_booked", "A desk or room is booked.", "Your desk booking is confirmed. We will send access details before you arrive."),
        _i("meeting_room_ending", "Warns a room booking is ending", "texts a gentle ending notice", ("event", "room.ending", "A room booking is ending"), "room_ending", "A room booking is ending.", "A friendly note that your room booking ends soon."),
        _i("artwork_problem", "Asks for better artwork", "texts that the file needs a fix", ("event", "artwork.problem", "A print file has a problem"), "artwork_problem", "A print file needs a fix.", "We need a better version of your file to print it well. Please send a new one."),
    ],
    "laundry-dry-cleaning": [
        _i("pickup_and_delivery_window", "Tells customers their pickup or drop-off window", "texts the window for a collection or delivery", ("event", "route.scheduled", "A pickup or delivery is scheduled"), "route_window", "A pickup or delivery window.", "Your pickup or delivery is scheduled. We will message you when the driver is on the way."),
        _i("stain_note", "Confirms a stain note was passed on", "tells customers the note was passed to the team, with no promise", _p("stain", "spot", "special care"), "stain_noted", "A stain note was passed on.", "Thank you, we have noted your request. We will do our best, and cannot always promise a stain will come out."),
        _i("alteration_ready", "Tells customers alterations are ready", "texts that alterations are done", ("event", "alteration.ready", "An alteration is ready"), "alteration_ready", "An alteration is ready.", "Your alteration is finished and ready for pickup."),
        _i("subscription_pickup_reminder", "Reminds subscribers of their pickup", "texts the night before a regular pickup", ("event", "pickup.tomorrow", "A regular pickup is tomorrow"), "pickup_tomorrow", "A regular pickup is tomorrow.", "A reminder that your regular pickup is tomorrow. Please leave your items ready."),
    ],
    "home-services": [
        _i("quote_expires", "Reminds customers a quote is ending", "texts that a quote is about to end", ("event", "quote.expiring", "A quote is about to expire"), "quote_expiring", "A quote is ending soon.", "Your quote is ending soon. Reply if you would like to go ahead or have a question."),
        _i("access_instructions", "Asks for access details before a visit", "asks how to get in, never for codes by text", ("event", "access.needed", "Access details are needed for a visit"), "access_needed", "Ask about access.", "Please let us know how our technician can get in. Do not send door codes by text, a team member will call."),
        _i("invoice_ready", "Tells customers an invoice is ready", "texts that the invoice is ready, with no amount", ("event", "invoice.ready", "An invoice is ready"), "invoice_ready", "An invoice is ready.", "Your invoice is ready. We have sent it to your email."),
        _i("warranty_question_to_the_office", "Passes warranty questions to the office", "never promises coverage by text", _p("warranty", "guarantee", "redo", "not fixed"), "warranty_to_office", "A warranty question is passed to the office.", "We are sorry it is not right. The office will contact you to look into it.", "Warranty or redo request from {{sms.from}}: {{sms.body}}"),
        _i("maintenance_plan_due", "Reminds customers a service check is due", "texts that a yearly check is due", ("event", "maintenance.due", "A maintenance visit is due"), "maintenance_due", "A maintenance visit is due.", "It is time for your regular maintenance visit. Reply to book a time."),
    ],
    "trades-outdoor-services": [
        _i("weather_reschedule", "Tells customers a job moved because of weather", "texts that weather moved the job and a new time will follow", ("event", "weather.reschedule", "Weather moves a job"), "weather_reschedule", "Weather moved a job.", "Because of the weather we need to move your visit. We will contact you with a new time."),
        _i("crew_on_the_way", "Tells customers the crew is on the way", "texts that the crew left", ("event", "crew.on_the_way", "The crew is on the way"), "crew_on_the_way", "The crew is on the way.", "Our crew is on the way to you now."),
        _i("seasonal_service_due", "Reminds customers a seasonal service is due", "texts that a seasonal job is due", ("event", "season.due", "A seasonal service is due"), "seasonal_due", "A seasonal service is due.", "It is time for your seasonal service. Reply to book a time."),
        _i("site_photos_request", "Asks for photos for a quote", "asks the customer to send photos by reply", _p("quote", "estimate", "how much"), "photos_for_quote", "Ask for photos for a quote.", "To prepare a quote, please reply with a few photos and the address. A team member will follow up."),
        _i("gate_or_pet_note", "Confirms a gate or pet note", "tells the customer the note was passed to the crew", _p("gate", "dog", "pet", "locked"), "gate_note", "A gate or pet note was passed on.", "Thank you, we have passed that note to the crew."),
    ],
    "automotive": [
        _i("inspection_results_ready", "Tells customers an inspection is done", "texts that an inspection report is ready, with no findings", ("event", "inspection.ready", "An inspection is done"), "inspection_ready", "An inspection is done.", "Your inspection is finished. Please call us or reply and the service desk will go over it with you."),
        _i("parts_arrived", "Tells customers a part arrived", "texts that a part arrived and work will continue", ("event", "parts.arrived", "A part arrives"), "parts_arrived", "A part arrived.", "The part for your vehicle has arrived and we will continue the work."),
        _i("extra_work_approval", "Asks permission before extra work", "asks for approval by reply and never starts without it", ("event", "extra_work.found", "Extra work is found"), "extra_work_approval", "Ask approval for extra work.", "We found something that needs your approval before we go ahead. Please reply or call us."),
        _i("recall_notice", "Tells customers about a recall notice", "texts that a notice exists and to call the service desk", ("event", "recall.notice", "A recall notice applies"), "recall_notice", "A recall notice applies.", "A notice applies to your vehicle. Please call the service desk to book a free check."),
        _i("test_drive_booking", "Confirms a test drive", "texts the test drive booking", ("event", "testdrive.booked", "A test drive is booked"), "testdrive_booked", "A test drive is booked.", "Your test drive is booked. Please bring your driving licence."),
    ],
    "car-care-roadside": [
        _i("wash_ready", "Tells customers their car is ready", "texts when a detail or wash is done", ("event", "wash.ready", "A wash or detail is done"), "wash_ready", "A wash is ready.", "Your vehicle is clean and ready for pickup."),
        _i("tow_requested_to_a_person", "Passes towing requests to dispatch", "never promises a time: says dispatch will call and to call emergency services if unsafe", _p("tow", "towing", "stuck", "flat tyre", "flat tire", "jump start", "battery dead"),
           "tow_to_dispatch", "A towing request is passed to dispatch.", "We have your request and dispatch will call you. If you are in danger or on a busy road, call nine one one first.", "ROADSIDE request from {{sms.from}}: {{sms.body}}"),
        _i("membership_renewal_roadside", "Reminds members their plan renews", "texts that a plan is renewing", ("event", "membership.renewing", "A membership renews soon"), "plan_renewing", "A plan renews soon.", "Your plan renews soon. Reply if you would like to make a change."),
        _i("quote_request_vehicle_details", "Asks for vehicle details for a quote", "asks for the vehicle and the problem by reply", _p("quote", "how much", "price for"), "quote_vehicle_details", "Ask for vehicle details for a quote.", "To give you a quote, please reply with the make, model and year of your vehicle and what you need."),
    ],
    "education-community": [
        _i("event_reminder", "Reminds families about an event", "texts a short event reminder", ("event", "event.reminder", "A community event is coming up"), "event_reminder", "An event reminder.", "A friendly reminder that our event is coming up soon. We hope to see you there."),
        _i("closure_or_delay", "Tells families about a closure or late start", "texts a short closure notice", ("event", "closure.notice", "A closure or delay is announced"), "closure_notice", "A closure or delay notice.", "We are closed or starting late today. Please check our website or call for the latest update."),
        _i("volunteer_signup_thanks", "Thanks people who sign up to help", "texts a thank you and what happens next", ("event", "volunteer.signup", "Someone signs up to volunteer"), "volunteer_thanks", "Thank a new volunteer.", "Thank you for signing up to help. A team member will contact you with the details."),
        _i("registration_received", "Confirms a registration arrived", "texts that a registration arrived", ("event", "registration.received", "A registration arrives"), "registration_received", "A registration arrived.", "We have received your registration. We will contact you if we need anything else."),
        _i("pickup_change_to_the_office", "Passes pickup changes to the office", "never accepts changes of who collects a child by text: says call the office", _p("pick up", "pickup", "collect my", "someone else"), "pickup_change_to_office", "A pickup change is passed to the office.",
           "For a child's safety we cannot change who collects them by text. Please call the office.", "Pickup change request by text from {{sms.from}}. Nothing was changed. Please call them."),
    ],
    "tutoring-online-courses": [
        _i("session_link", "Sends the online session link", "texts the link before a session", ("event", "session.link", "A session link is ready"), "session_link", "A session link is ready.", "Your session link is ready. Please join a few minutes early."),
        _i("tutor_changed", "Tells families a tutor changed", "texts that the tutor changed", ("event", "tutor.changed", "A tutor changes"), "tutor_changed", "A tutor changed.", "Your tutor for the next session has changed. Please contact us if you have questions."),
        _i("session_cancelled", "Tells families a session was cancelled", "texts that a session is cancelled", ("event", "session.cancelled", "A session is cancelled"), "session_cancelled", "A session was cancelled.", "Your session has been cancelled. We will help you find another time."),
        _i("course_access_help", "Helps with course login trouble", "tells people to use the reset link and never to share passwords", _p("login", "log in", "password", "cannot access"), "course_access_help", "Help with course access.", "Please use the reset link on the sign-in page. Never share your password by text. A team member can also help."),
        _i("homework_reminder", "Reminds students about work due", "texts a reminder, with no grades", ("event", "work.due", "Work is due"), "work_due", "Work is due.", "A friendly reminder that your work is due soon."),
    ],
    "government-utilities": [
        _i("service_restored", "Tells people a service is back", "texts that a service was restored", ("event", "service.restored", "A service is restored"), "service_restored", "A service is restored.", "Good news, the service is back. Please contact us if you still have a problem."),
        _i("outage_cause_not_guessed", "Answers outage questions honestly", "says a team is working on it and gives no time it cannot guarantee", _p("outage", "no power", "no water", "no service", "is it down"), "outage_answer", "Answer an outage question.",
           "We know about the problem and our team is working on it. We will share an update as soon as we can."),
        _i("permit_update", "Tells people a permit has an update", "texts only that there is an update in the secure account", ("event", "permit.update", "A permit has an update"), "permit_update", "A permit has an update.", "There is an update on your permit. Please sign in to your account to see it."),
        _i("bill_ready_to_view", "Tells customers a bill is ready", "texts that a bill is ready in the account, with no amount", ("event", "bill.ready", "A bill is ready"), "bill_ready", "A bill is ready.", "Your bill is ready. Please sign in to your account to see it."),
        _i("gas_or_hazard_to_emergency", "Sends hazards to emergency numbers first", "tells people to call emergency services for gas, wires or flooding", _p("gas leak", "smell gas", "downed line", "wires down", "flooding"), "hazard_emergency", "A hazard is reported.",
           "If there is danger, leave the area and call nine one one now. We are telling our team.", "HAZARD report from {{sms.from}}: {{sms.body}}"),
    ],
    "legal-services": [
        _i("conflict_check_pending", "Tells enquirers a check is under way", "texts that the firm is checking it can help, giving no advice", ("event", "conflict.check", "A conflict check is under way"), "conflict_check", "A conflict check is under way.", "We are checking whether our firm can help with your enquiry. We will contact you soon."),
        _i("engagement_letter_ready", "Tells clients a document is ready to sign", "texts that a document is waiting in the secure channel", ("event", "engagement.ready", "An engagement letter is ready"), "engagement_ready", "A document is ready to sign.", "A document is ready for you in our secure channel. Please review and sign it there."),
        _i("court_date_reminder", "Reminds clients about a date, without detail", "texts that a date is coming and to call the office", ("event", "court.reminder", "A court date is coming up"), "court_date_reminder", "A date is coming up.", "A date on your matter is coming up. Please contact our office to go over it."),
        _i("invoice_ready_legal", "Tells clients an invoice is ready", "texts that an invoice is ready, with no amount", ("event", "invoice.ready", "An invoice is ready"), "invoice_ready_legal", "An invoice is ready.", "Your invoice is ready in our secure channel."),
    ],
    "lending-collections": [
        _i("payment_arrangement_reminder", "Reminds customers of an agreed arrangement", "texts a plain reminder with the required notice and no amount", ("event", "arrangement.reminder", "A payment arrangement is due"), "arrangement_reminder", "An arrangement reminder.", "A reminder that a payment under your arrangement is coming up."),
        _i("cease_contact_request", "Honours a request to stop contact", "records STOP and says contact will stop where the law requires, and a person will confirm in writing", _p("stop contacting", "do not contact", "cease"), "stop_contact_ack", "A request to stop contact.",
           "We have noted your request. A team member will confirm it in writing.", "Request to stop contact from {{sms.from}}. Please follow your policy."),
        _i("verification_request", "Offers written verification", "tells the person they can ask for details in writing", _p("validate", "prove", "verification", "who are you"), "verification_offer", "Offer written verification.", "You can ask us to confirm the details in writing. A team member will contact you."),
        _i("loan_payment_received", "Confirms a payment arrived", "texts that a payment arrived, with no amount", ("event", "payment.received", "A payment comes in"), "payment_received", "A payment arrived.", "Your payment has been received. Thank you."),
    ],
    "billing-payments": [
        _i("subscription_renewing", "Tells customers a plan renews soon", "texts that a plan renews, with no amount", ("event", "subscription.renewing", "A subscription renews soon"), "subscription_renewing", "A subscription renews soon.", "Your plan renews soon. You can change or cancel it in your account."),
        _i("card_expiring", "Tells customers a saved card is expiring", "texts that a card needs updating in the secure account, never by text", ("event", "card.expiring", "A saved card is expiring"), "card_expiring", "A card is expiring.", "A payment method on your account is expiring. Please update it in your secure account, never by text."),
        _i("refund_processed", "Confirms a refund", "texts that a refund was processed, with no amount", ("event", "payment.refunded", "A payment is refunded"), "refund_processed_fin", "A refund was processed.", "Your refund has been processed. It can take a few days to appear."),
        _i("invoice_overdue_gentle", "Sends one gentle overdue notice", "texts a gentle note, with no amount and no threats", ("event", "invoice.overdue", "An invoice is overdue"), "invoice_overdue", "An invoice is overdue.", "An invoice on your account is past due. Please sign in to your account or contact us if you need help."),
        _i("scam_warning", "Warns people about scams", "says the business never asks for passwords or card numbers by text", _p("scam", "suspicious", "phishing", "is this real"), "scam_warning", "Warn about scams.", "We never ask for your password, PIN or full card number by text or phone. If a message worries you, contact us using the number on our website."),
    ],
    "crypto-pawn-rent-to-own": [
        _i("loan_due_date", "Reminds customers an item or loan date is coming", "texts that a date is near, with no amount", ("event", "due.soon", "A due date is near"), "due_date_near", "A due date is near.", "A date on your agreement is coming up. Please contact us or visit if you have questions."),
        _i("item_available_for_pickup", "Tells customers an item can be collected", "texts that an item is ready to collect", ("event", "item.ready", "An item is cleaned or finished and ready"), "pawn_item_ready", "An item is ready to collect.", "Your item is ready to collect. Please bring a valid photo ID."),
        _i("price_questions_to_staff", "Passes value and price questions to staff", "never quotes value by text", _p("worth", "value", "how much will you give", "offer"), "value_to_staff", "A value question is passed to staff.", "We cannot give a value by text. Please bring the item in and a team member will help.", "Value question by text from {{sms.from}}. Nothing was answered."),
        _i("crypto_scam_warning", "Warns people about wallet and key scams", "says never to share keys or recovery phrases", _p("seed phrase", "private key", "recovery phrase", "wallet"), "key_scam_warning", "Warn about keys and recovery phrases.", "Never share your private keys or recovery phrase with anyone, including us. A team member will contact you."),
    ],
    "customer-service": [
        _i("case_closed", "Tells customers a case was closed", "texts that a case is closed and how to reopen it", ("event", "case.closed", "A case is closed"), "case_closed", "A case was closed.", "Your case has been closed. Reply if you still need help and we will reopen it."),
        _i("refund_or_credit_issued", "Tells customers a credit or refund was issued", "texts that it was issued, with no amount", ("event", "credit.issued", "A credit is issued"), "credit_issued", "A credit was issued.", "A credit or refund has been added to your account."),
        _i("callback_missed", "Apologises for a missed callback", "texts that the team tried and will try again", ("event", "callback.missed", "A callback was missed"), "callback_missed", "A callback was missed.", "Sorry we missed you. We will try again, or you can reply with a better time."),
        _i("vip_or_urgent_to_a_person", "Sends urgent complaints to a person at once", "tells the customer a person will call and alerts your team", _p("urgent", "very upset", "legal action", "cancel everything"), "urgent_to_person", "An urgent complaint is passed to a person.", "We are sorry and we understand this is urgent. A team member will contact you right away.", "URGENT customer message from {{sms.from}}: {{sms.body}}"),
    ],
    "ivr-phone-menus": [
        _i("callback_instead_of_waiting", "Offers a callback instead of waiting", "texts that a callback is booked", ("event", "callback.offered", "A callback is offered"), "callback_booked_ivr", "A callback is booked.", "We have booked a callback for you so you do not have to wait. Thank you for your patience."),
        _i("business_hours_menu_text", "Texts the menu options", "texts the options a caller can choose", _p("menu", "options", "what can you do"), "menu_by_text", "Text the menu options.", "You can call us and say or press your choice: hours, a booking, a status check, or a person."),
        _i("after_hours_message_taken", "Confirms a voicemail was taken", "texts that a message was recorded", ("event", "voicemail.left", "A voicemail is left"), "voicemail_taken", "A voicemail was taken.", "We have your message and will call you back as soon as we can."),
        _i("wrong_number_polite", "Handles wrong numbers politely", "answers kindly", _p("wrong number"), "wrong_number", "Answer a wrong number.", "Sorry about that. You have reached a business line. No further messages will be sent unless you ask."),
    ],
    "dating-social-apps": [
        _i("safety_report_to_a_person", "Passes safety reports to a person at once", "never judges a report by text: says a team member will contact them and gives emergency advice", _p("harass", "threat", "unsafe", "scared", "stalk", "abuse", "report a user"),
           "safety_report_to_person", "A safety report is passed to a person.", "We are sorry and we take this seriously. A team member will contact you. If you are in danger, call nine one one.", "SAFETY REPORT from {{sms.from}}: {{sms.body}}"),
        _i("account_recovery_help", "Helps with account recovery safely", "points to the secure recovery page and never takes passwords", _p("locked out", "hacked", "cannot log in", "forgot password"), "account_recovery", "Help with account recovery.", "Please use the recovery option on the sign-in page. Never share your password or codes by text."),
        _i("subscription_help", "Helps with subscription questions", "points to the account page", _p("subscription", "cancel", "billing"), "subscription_help_app", "Help with a subscription.", "You can manage your plan in your account settings. A team member can also help."),
        _i("profile_removed_notice", "Tells a person a profile action happened", "texts that an action was taken on their account and how to appeal", ("event", "profile.action", "A profile action is taken"), "profile_action", "A profile action was taken.", "An action was taken on your account. You can ask for a review and a team member will look at it."),
    ],
    "it-saas-support": [
        _i("ticket_needs_info", "Asks the customer for more information", "texts that more information is needed", ("event", "ticket.needs_info", "A ticket needs more information"), "ticket_needs_info", "A ticket needs more information.", "We need a little more information to help you. Please reply to your ticket."),
        _i("status_page_update", "Tells customers about a status update", "texts a plain status update", ("event", "status.update", "A status update is posted"), "status_update_posted", "A status update was posted.", "We posted an update about the service. Please check our status page."),
        _i("scheduled_maintenance_window", "Warns about a maintenance window", "texts a maintenance window notice", ("event", "maintenance.scheduled", "Maintenance is scheduled"), "maintenance_window", "Maintenance is scheduled.", "We have planned maintenance coming up. Some features may be briefly unavailable."),
        _i("sla_breach_alert_team", "Alerts your team when a ticket waits too long", "tells your team a ticket is late", ("event", "sla.at_risk", "A ticket is at risk of waiting too long"), "", "A ticket is at risk.", "A ticket for {{customer.name}} is waiting too long. Please pick it up.", ""),
        _i("password_and_key_warning", "Warns customers never to send secrets", "tells customers not to send passwords or keys", _p("password", "api key", "token", "secret"), "secrets_warning", "Warn about sending secrets.", "Please never send passwords, keys or tokens by text. A team member will help you safely."),
    ],
    "website-hosting-internet": [
        _i("site_down_ack", "Acknowledges a site-down report", "texts that the report is received and the status page link", _p("site is down", "website down", "cannot reach", "not loading"), "site_down_ack", "A site-down report was received.", "We have your report and our team is checking. We will share an update as soon as we can."),
        _i("renewal_reminder_domain", "Reminds customers a domain or plan renews", "texts that a renewal is near", ("event", "renewal.upcoming", "A renewal is coming up"), "renewal_upcoming", "A renewal is coming up.", "A renewal on your account is coming up. You can manage it in your account."),
        _i("certificate_expiring", "Warns customers a certificate is expiring", "texts that a certificate needs renewing", ("event", "certificate.expiring", "A certificate is expiring"), "certificate_expiring", "A certificate is expiring.", "A security certificate on your account is expiring soon. Please renew it in your account."),
        _i("install_visit_booked", "Confirms an installation visit", "texts the visit booking", ("event", "install.scheduled", "An installation is scheduled"), "install_scheduled", "An installation is scheduled.", "Your installation visit is booked. A technician will arrive in the time window we gave you."),
    ],
    "apps-and-devices": [
        _i("device_setup_help", "Offers setup help", "points to the setup guide and a person", _p("setup", "set up", "install", "pair"), "setup_help", "Offer setup help.", "Please follow the setup guide in the app. A team member can also help if you reply."),
        _i("update_available", "Tells customers an update is available", "texts that an update is out", ("event", "update.available", "An update is available"), "update_available", "An update is available.", "A new update is available for your device. Please install it from the app."),
        _i("warranty_or_replacement_to_a_person", "Passes replacement requests to a person", "never promises a replacement by text", _p("replace", "replacement", "warranty", "broken", "faulty"), "replacement_to_person", "A replacement request is passed to a person.", "We are sorry it is not working. A team member will contact you about next steps.", "Replacement request from {{sms.from}}: {{sms.body}}"),
        _i("factory_reset_warning", "Warns before a reset", "tells people a reset can erase their data", _p("factory reset", "reset my device", "wipe"), "reset_warning", "Warn before a reset.", "A reset can erase your data. Please back up first, or reply and a team member will go through it with you."),
    ],
    "everyday": [
        _i("message_taken", "Confirms a message was taken", "texts that the message was passed on", _p("message", "tell him", "tell her", "call me back"), "message_taken", "A message was taken.", "Thank you, we have your message and will pass it on."),
        _i("directions_by_text", "Texts directions on request", "sends your address and how to find you", _p("directions", "how do i get", "where are you"), "directions_text", "Send directions.", "Here is how to find us. Reply if you need anything else."),
        _i("callback_promised", "Confirms a callback", "texts that someone will call back", ("event", "callback.promised", "A callback is promised"), "callback_promised", "A callback is promised.", "A team member will call you back as soon as they can."),
    ],
    "guidance-wayfinding": [
        _i("find_a_place", "Helps people find a place", "tells people how to ask for directions inside", _p("where is", "find the", "which way", "restroom", "toilet", "exit"), "wayfinding_help", "Help someone find a place.", "Please tell us where you want to go and we will help you find the way."),
        _i("accessible_route_request", "Answers accessible route questions", "passes accessibility questions to a person", _p("wheelchair", "accessible", "lift", "elevator", "ramp", "step free"), "accessible_route_help", "Help with an accessible route.", "A team member will help you with the best accessible route. Please wait a moment.", "Accessible route request from {{sms.from}}: {{sms.body}}"),
        _i("opening_times_today", "Tells people when it opens", "replies with opening times", _p("open", "closing time", "what time"), "opening_times_reply", "Say opening times.", "Please see our opening times below."),
    ],
    "kiosks-self-service": [
        _i("kiosk_out_of_order", "Tells customers a kiosk is out of order", "texts that a kiosk is broken and where to go", ("event", "kiosk.down", "A kiosk is out of order"), "kiosk_out_of_order", "A kiosk is out of order.", "Sorry, that kiosk is out of order. Please see a team member and they will help you."),
        _i("kiosk_problem_report", "Takes a problem report", "tells the person the team was told", _p("kiosk", "machine", "not working", "ate my", "stuck"), "kiosk_report", "A kiosk problem was reported.", "Thank you for telling us. We have passed this to our team and they will look into it.", "Kiosk problem from {{sms.from}}: {{sms.body}}"),
        _i("refund_from_machine", "Handles a payment problem at a kiosk", "never promises a refund by text", _p("refund", "charged twice", "took my money"), "kiosk_refund_to_person", "A kiosk payment problem is passed to a person.", "We are sorry. A team member will check what happened and contact you.", "Kiosk payment problem from {{sms.from}}: {{sms.body}}"),
        _i("receipt_by_text", "Sends a receipt by text on request", "texts that the receipt was sent", ("event", "receipt.ready", "A receipt is ready"), "receipt_ready", "A receipt is ready.", "Your receipt is ready. Thank you."),
    ],
    "warehouse-voice": [
        _i("dock_appointment_confirmed", "Confirms a dock appointment", "texts the receiving window", ("event", "dock.booked", "A dock appointment is booked"), "dock_booked", "A dock appointment is booked.", "Your dock appointment is confirmed. Please arrive in your time window."),
        _i("driver_check_in", "Tells drivers where to check in", "texts check-in instructions", ("event", "driver.arriving", "A driver is arriving"), "driver_check_in", "Tell drivers where to check in.", "Please check in at the gate office when you arrive. Have your paperwork ready."),
        _i("shipment_received", "Tells shippers a shipment was received", "texts that a delivery was received", ("event", "shipment.received", "A shipment is received"), "shipment_received", "A shipment was received.", "We have received your shipment. We will contact you if there is a problem."),
        _i("pick_shortage_alert_team", "Alerts your team about a shortage", "tells your team a pick is short", ("event", "pick.short", "A pick is short"), "", "A pick is short.", "Pick shortage: {{title}}. Please check stock.", ""),
        _i("safety_incident_to_a_person", "Sends a safety incident to a person", "tells people to call emergency services and alerts your team", _p("injury", "accident", "spill", "fire", "forklift"), "warehouse_safety", "A safety incident is reported.", "If anyone is hurt, call nine one one now. Our safety lead is being told.", "SAFETY incident from {{sms.from}}: {{sms.body}}"),
    ],
    "jail-corrections-bail": [
        _i("visit_hours_reply", "Answers visiting hours questions", "replies with the visiting information you wrote", _p("visiting hours", "visit hours", "when can i visit"), "visiting_hours_reply", "Answer visiting hours.", "Please see the visiting hours below. They can change, so check before you travel."),
        _i("deposit_confirmed", "Confirms a deposit to an account", "texts that a deposit was recorded, with no amounts", ("event", "deposit.recorded", "A deposit is recorded"), "deposit_recorded", "A deposit was recorded.", "A deposit has been recorded. Thank you."),
        _i("property_pickup_notice", "Tells families about property pickup", "texts how to arrange a property pickup", ("event", "property.pickup", "Property is ready for pickup"), "property_pickup", "Property is ready for pickup.", "Property is ready to be collected. Please contact the office for the process."),
        _i("legal_advice_refusal", "Refuses legal advice politely", "says staff cannot give legal advice", _p("lawyer", "attorney", "my rights", "should i plead"), "no_legal_advice", "A request for legal advice.", "We cannot give legal advice. Please contact a lawyer or the public defender's office."),
    ],
}

# extra phone call-answering lines every business can use in a custom phone menu, a Slack /say, or the live AI (profile level, all industries)
CALL_COMMON = {
    "call_how_can_i_help": ("Ask a caller what they need.", "How can I help you today?"),
    "call_one_moment": ("Tell a caller to wait while something is checked.", "One moment please while I check that for you."),
    "call_take_message": ("Offer to take a message.", "I can take a message and make sure the right person gets it."),
    "call_message_taken": ("Confirm a message was taken.", "Thank you, I have your message and a team member will get back to you."),
    "call_callback_offer": ("Offer a callback.", "I can ask a team member to call you back. Would you like that?"),
    "call_repeat_please": ("Ask a caller to repeat.", "Could you please say that again a little more slowly?"),
    "call_confirm_number": ("Ask for a callback number.", "What is the best number for us to call you back on?"),
    "call_transfer_now": ("Tell a caller they are being connected.", "Please hold while I connect you to a team member."),
    "call_closed_message": ("Said when a call arrives while closed.", "Thank you for calling. We are closed right now. Please leave a message or call again when we open."),
    "call_busy_wait": ("Said when all staff are busy.", "All of our team are busy right now. Thank you for waiting, someone will be with you shortly."),
    "call_spelled_name": ("Ask a caller to spell their name.", "Could you please spell your name for me?"),
    "call_directions_offer": ("Offer directions by text.", "I can text you our address and directions. Would you like that?"),
}
