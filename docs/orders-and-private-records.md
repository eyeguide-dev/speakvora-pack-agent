# Order tracking links, pharmacy texts, and private records from your own system

## Which industries get a tracking link
Any business where the customer waits on something and the page can show a step without showing private details:

| Industry | What the customer follows | Events your system sends |
|---|---|---|
| Restaurants, bars, food trucks, catering | Order: received, preparing, ready, collected (or on the way, delivered) | `order.received`, `order.preparing`, `order.ready`, `order.picked_up`, `order.out_for_delivery`, `order.delivered` |
| Retail, e-commerce, furniture, fashion, gifts, marketplace sellers, returns | Order: confirmed, packed, ready or on the way, collected or delivered | same `order.*` events |
| Laundry and dry cleaning | Items: received, cleaning, ready, collected (or delivered) | same `order.*` events |
| Pharmacy and dispensary | Order: received, preparing, ready, collected (never what is in it) | same `order.*` events |
| Home services and trades | Visit: received, scheduled, on the way, in progress, completed | `job.scheduled`, `job.on_the_way`, `job.in_progress`, `job.completed` |
| Auto repair and car care | Repair: checked in, in progress, ready, collected | `repair.received`, `repair.in_progress`, `repair.ready`, `repair.picked_up` |
| Customer service and IT or SaaS support | Request: received, in progress, resolved | `ticket.created`, `ticket.in_progress`, `ticket.resolved` |

Not offered as a public link: clinics and hospitals, legal, banking and lending, collections, corrections, public services and similar, because the status itself is private. For those, a person's status comes only from your own connected records system after they are verified (see below), never from a link.

## Order tracking (restaurants, laundry, retail and similar)
When your system sends `order.received`, the customer gets **one text** with a private link, like the ones pizza chains send. The page behind the link shows the order moving through its steps and updates by itself:
- pickup: received, preparing, ready for pickup, picked up
- delivery: received, preparing, on its way, delivered (send `"delivery": true` in the order, or `order.out_for_delivery`)

Your system just keeps telling the agent where the order is: `order.preparing`, `order.ready`, `order.picked_up`, `order.out_for_delivery`, `order.delivered`, `order.delayed`, `order.cancelled`. Each event updates the page; no more texts go out unless you set `"tracking": {"text_each_step": true}` in `agent.json`.
The page carries the Speakvora logo, your business name (with an initials badge), the order number, a headline for the step (for example "In the kitchen."), a step bar worded for your industry (a restaurant says Preparing, a laundry says Cleaning, a store says Packed), your own estimate if you send one, the time of the latest update, and buttons to **call** or **text** your business so a customer with a question reaches someone from the page. It shows no customer name or number and nothing about what was ordered. The code in the link is long and random, the page tells search engines to ignore it, and the link stops working three days after the order is finished. The agent serves the page at `public_base_url/track/<code>`, so the address in `public_base_url` must be reachable by your customers' phones.

### Estimate and contact buttons
Send `"order": {"number": "1042", "eta": "6:15 - 6:25 PM"}` (or `"eta"` on any order event) to show the estimate card, "provided by the restaurant"; send an empty `eta` to clear it. The **Call** button uses `facts.phone` (or `tracking.contact_phone`) in `agent.json`: set it to the number customers should ring. The **Text** button opens a text to your agent's sending number with the order number filled in, and your agent passes it to your team like any other message.

### Speakvora hosts the pages: nothing to set up
The first time a business opens its dashboard, the **Set up your order pages** card asks once for its business name, website, customer service phone (the Call button), other service numbers, opening hours, address and Speakvora API key (speakvora.com, your account, Voice API, Create a key). One button, **Create my order pages**, saves them and creates the hosted pages. Going live is blocked until that is done. After that, every customer link looks like `https://speakvora.com/o/<random code>`: it works even when the business's computer is off, never changes, and needs no domain, tunnel or public address.

What goes to Speakvora for a page: the order number, its step and times, your estimate text, and your business details (name, phone, website, hours). **Never** the customer's name, number or message, or what was ordered. If the internet is down when an order changes, the link is still created and the page catches up as soon as the agent is back online. Change a business detail in the dashboard and every page updates.

Every link is also saved on the business's own computer the moment it is made (`agent-state/orders.db`) and listed in the dashboard's **Orders** tab (search by order number, copy or open the link, see the step history, export to a spreadsheet). Links never expire. The list holds the order number, steps and times only.
Advanced: set `"tracking": {"mode": "self"}` and a `public_base_url` to serve the pages from your own agent instead.

## Pharmacy and dispensary
Customers get a plain text when an order is **placed** (with the tracking link), **ready for pickup** and **picked up**, and the same page shows the steps. The texts and the page never say what is in the order. A customer who texts or calls can reach staff (press 0 or say "person").

## Health and other private details: only from your own connected system
The agent never writes or guesses private details. It can pass on an answer **word for word from your records system**, only when all of these hold:
1. The **Call handling controls** card in Settings shows private records approved: a named reviewer, how your system verifies people, your privacy notice, jurisdiction profile, transfer roster, `phi_enabled` for health businesses, and your go-live approval.
2. Your system answers the agent's request with `{"found": true, "verified": true, "message": "...", "allowed_phones": ["+1..."]}`. `verified` means YOUR system checked who is asking (caller ID alone never counts). `allowed_phones` lists the patient's number and any caregiver or representative your system authorised.
3. The asking number is on that list.
Otherwise the person hears that staff will help them. On a text, the answer goes straight back as the reply. On a phone call nothing private is spoken: the details are texted to the number on file, and the agent erases that text from its own records as soon as it is sent. Only the outcome (answered, or not authorised) is logged.

Connect it in **Connect, Your apps**: add a connection with the id `records`, the address of your lookup endpoint and its key. The agent POSTs `{"phone": "...", "text": "<what they typed>", "channel": "text"|"call"}` and nothing else.

## Hospitals and clinics
General administrative questions (hours, departments, directions, scheduling procedure) are answered from approved facts. Patient-specific status uses the same connected-system lookup above. Clinical questions, symptoms and results go to staff.

## Industry call-handling controls (draft catalog)
The agent ships a catalog of 1,140 draft rules for 23 industries, 49 policy settings and source references (`data/call_controls.json`, from your Speakvora Industry Call Handling Controls workbook). **Every rule is a draft until you review it.** The dashboard (Settings, Call handling controls) lists the rules for your industry and marks the ones the agent already enforces in code: caller ID is never identity; passwords and card numbers are refused; the call starts by saying it is automated; emergencies get "call 911" and stop the menu (when speech input is on); a person is always one request away; webhooks go only to hosts you wrote; private lookups are logged by outcome only. This is not legal advice or a compliance certificate.

## Feeding the tracker from your system (the API)
Your ordering or kitchen system sends each change to the agent as a signed event, the same way every other event arrives (see `docs/integrate-in-10-minutes.md` for the signature). One example, a kitchen marking an order ready:
```
curl -X POST https://YOUR-AGENT-ADDRESS/event -H "content-type: application/json" -H "x-sv-timestamp: <unix seconds>" -H "x-sv-signature: <HMAC of timestamp and body with your events secret>" \
  -d '{"event":"order.ready","id":"evt-1042-ready","customer":{"name":"Ann","phone":"+15551234567","sms_consent":true},"order":{"number":"1042"}}'
```
The first event for an order (`order.received`) texts the customer the link once; every later event only moves the page along. Send the same `order.number` each time. Use a different `id` per event so a repeat is ignored.
