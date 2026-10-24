# Your industry's ready-made workflows

Every bundle comes with a complete set of workflows for its kind of business, in plain words. Open **Your agent**, then the list of ready-made automations. It shows ten at a time; scroll inside the panel for the rest. Filter by **Needs your OK**, **On** and **Off**.

## What you get

| Kind of business | A few of the ready-made workflows (the full list is in your dashboard) |
|---|---|
| Clinics and healthcare (including dental and mental health) | Reminds patients before their visit · Reminds patients to fill in their forms · Reminds patients what to bring · Tells patients to contact you when something is ready · Reminds patients their regular visit is due · Tells patients you received their referral · Passes health questions straight to a person |
| Pharmacy | Tells customers their refill is ready · Reminds customers a refill is coming up · Reminds customers to pick up soon · Asks customers to call about insurance · Passes medicine questions to the pharmacist |
| Dispensary | Tells customers their order is ready · Reminds customers to bring valid ID · Passes product and health questions to staff |
| Law firms | Confirms you received an enquiry · Confirms a consultation · Asks clients for missing documents · Tells clients there is news without the details · Reminds clients about an important date |
| Finance and billing | Reminds customers a payment is due soon · Tells customers a payment did not go through · Confirms a payment arrived · Tells customers a statement is ready · Offers help when someone is struggling to pay |
| Lending and collections | The required notice on every message · Confirms a payment plan · Offers help when someone is struggling to pay · Passes disputes to a person |
| Prisons and jails | Confirms a visit · Tells visitors a visit was cancelled · Sends the visiting rules · Passes questions about a person's case to staff |
| Government, utilities, insurance | Confirms an application arrived · Tells people there is an update · Asks for more documents · Tells people about a service problem |
| Schools and courses | Tells families a class is cancelled · Tells families enrolment is open · Reminds families a fee is due · Tells a guardian a student is absent |
| Restaurants and food | Tells guests they are on the waitlist · Tells guests their table is ready · Tells guests you will hold the table · Confirms you wrote down an allergy · Asks guests how their visit went |
| Hotels and travel | Confirms a stay · Sends arrival details · Tells guests their room is ready · Reminds guests about checkout · Passes guest requests to the front desk |
| Retail and online shops | Tells customers their order has shipped · Tells customers an item is back in stock · Confirms a return arrived · Tells customers their refund was issued · **Announces your sales** (see below) |
| Salons, spas, fitness | Sends aftercare tips · Reminds members their membership renews soon · Reminds customers it is time to rebook · Reassures customers who are running late |
| Laundry and dry cleaning | Tells customers their items are ready · Reminds customers to collect their items · Passes damage and lost-item claims to a person |
| Home services | Tells customers their estimate is ready · Confirms an approved estimate · Passes emergencies and safety problems to a person |
| Car repair and roadside | Tells customers their repair estimate is ready · Reminds customers a service is due · Passes roadside and accident calls to a person |
| Customer service and software support | Apologises when a customer waits too long · Passes account and security questions to a person · Sends a status update when asked |

Every industry also has **Reminds customers before their booking** (the smart reminder), **Answers texts when you are closed** and **Texts people back after a missed call**.

## Nothing is sent until you approve it
A kit workflow starts **off** and says **Needs your OK**.
1. Press it. It opens in plain words: what it does, what starts it, what it says, and which apps it needs.
2. Change the wording if you like (the box shows the sentence a customer would read) and, where it makes sense, **when it runs**: the words that start a text answer, the time of day, how long before a booking.
3. Press **Approve and turn on**. You can turn it off again with the switch, or press **Use the recorded wording** to go back to the original.

Your changes are saved in your own agent folder (`agent-state/workflow_edits.json`), so a bundle update never overwrites them. Approving does not skip anything else: every message still goes through consent, STOP, quiet hours, limits, "ask before sending" and Practice mode.

## Safe by design for health, legal, money, public and school businesses
In clinics, pharmacies, dispensaries, law firms, finance, collections, prisons, public services and schools the ready-made wording:
* never promotes anything (no sales, discounts, offers or deals) and never sends a promotional blast;
* never gives a diagnosis, medical advice, a dose, legal advice or a decision about someone's case, and never says what a result is: it says there is something to collect or discuss and points to your portal or phone;
* never puts a name of a medicine, a condition, an account number or a balance in a text;
* passes anything sensitive to a person quickly, and says that you are not a replacement for emergency services (it names the emergency number where it matters);
* is honest about its limits.

When you edit the wording in one of these businesses, a promotion or a health detail is refused with a plain reason. This is not a claim of HIPAA, TCPA, GDPR or any other compliance or certification. Texts and calls may still contain what you type, and you are responsible for your own rules and agreements (see `health-industries.md`).

## The smart reminder
**Reminds customers before their booking** sends a reminder at the times you choose from your Google or Outlook calendar. Open it and tick any of:

| Choice | When | What it says |
|---|---|---|
| Two days before | 48 hours before the start | an early reminder, and how to change it |
| The day before | 24 hours before | a friendly reminder about the booking |
| The morning of the booking | at the time you set (06:00 to 11:00, default 08:00) | "Good morning, a reminder that your booking is today" |
| Four hours, two hours or one hour before | that long before | "Just a reminder that your booking is coming up soon today" |

The agent picks the right line for each time, in your pack's language and voice. Default: the day before and two hours before. It reminds each booking once per time, never after a booking has started, skips the morning line when a booking starts too early for it, and only looks at calendar entries whose title contains the word you set (Appointment, or Reservation for restaurants). Customer details (phone, "SMS OK: yes") come from the calendar entry as before.

## While you are closed
Open **Answers texts when you are closed**, tick your open days and set opening and closing times. Outside them, a text that nothing else answers gets your "we are closed" reply. Until you set your times it stays quiet: unknown is never treated as closed.

## Announce a sale
Only for businesses that sell to the public (shops, restaurants, salons, laundries, car businesses). See `announce-a-sale.md`.
