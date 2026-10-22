"""Ready-made automations for every event your app can send, so no event in the list does nothing.
Each is a plain workflow ("when this happens, do this") in your own agent folder, switched on like any other and following the same safety rules as the rest: consent, STOP, quiet hours, limits and practice mode.
A customer text goes to {{customer.phone}} only when the app sent a phone number and consent. A team notice goes to Slack or Teams. Your own workflows for an event take priority: when you made one for an event, the ready-made one for that event stays quiet.
Safety and emergency events (a facility lockdown) are never automated here: they are listed as "coming soon" until they can be tied to a verified life-safety system."""
import json, os

SOON = {"facility.lockdown": "Safety and emergency events are never automated by this agent. This one needs a verified life-safety system, so it is coming later."}

# event: (title, what it does, kind, text). kind: c = text the customer, t = tell your team (Slack or Teams), b = tell your team and text the customer (the second text)
SPECS = {
    "order.received": ("Confirm a new order", "texts the customer that the order arrived", "c", "{{business}}: we received your order {{order.number}}. We will text you as it moves along."),
    "order.preparing": ("Say an order is being prepared", "texts the customer", "c", "{{business}}: we are preparing order {{order.number}}."),
    "order.ready": ("Say an order is ready", "texts the customer", "c", "{{business}}: order {{order.number}} is ready."),
    "order.delayed": ("Apologise for a late order", "texts the customer", "c", "{{business}}: order {{order.number}} is running late. We are sorry and will update you soon."),
    "order.picked_up": ("Thank them after pickup", "texts the customer", "c", "{{business}}: order {{order.number}} was picked up. Thank you!"),
    "order.out_for_delivery": ("Say an order is on its way", "texts the customer", "c", "{{business}}: order {{order.number}} is out for delivery."),
    "order.delivered": ("Confirm a delivery", "texts the customer", "c", "{{business}}: order {{order.number}} was delivered. Thank you!"),
    "order.cancelled": ("Confirm a cancelled order", "texts the customer", "c", "{{business}}: order {{order.number}} was cancelled. Reply to this text if that is a mistake."),
    "table.ready": ("Say a table is ready", "texts the guest", "c", "{{business}}: your table is ready. Please come to the host stand."),
    "reservation.created": ("Confirm a reservation", "texts the guest", "c", "{{business}}: your reservation is confirmed. Reply to this text if you need to change it."),
    "reservation.no_show": ("Follow up on a missed reservation", "texts the guest", "c", "{{business}}: we missed you today. Reply to this text and we will help you rebook."),
    "visit.completed": ("Thank customers after a visit", "texts the customer", "c", "Thanks for visiting {{business}}, {{customer.name}}! We hope to see you again soon."),
    "visit.next_due": ("Remind customers their next visit is due", "texts the customer", "c", "{{business}}: it is time for your next visit. Reply to this text to book."),
    "appointment.created": ("Confirm a new appointment", "texts the customer", "c", "{{business}}: your appointment is confirmed. Reply to this text if you need to change it."),
    "appointment.changed": ("Confirm a changed appointment", "texts the customer", "c", "{{business}}: your appointment was changed. Reply to this text if that does not work for you."),
    "appointment.cancelled": ("Confirm a cancelled appointment", "texts the customer", "c", "{{business}}: your appointment was cancelled. Reply to this text when you want to rebook."),
    "appointment.no_show": ("Follow up on a missed appointment", "texts the customer", "c", "{{business}}: we missed you at your appointment. Reply to this text and we will help you rebook."),
    "appointment.ready": ("Say an appointment is ready", "texts the customer", "c", "{{business}}: we are ready for you now."),
    "payment.failed": ("Tell customers a payment failed", "texts the customer (never asks for card details)", "c", "{{business}}: your payment did not go through. Please update your payment method, or reply to this text and we will help."),
    "payment.received": ("Confirm a payment", "texts the customer", "c", "{{business}}: we received your payment. Thank you!"),
    "payment.refunded": ("Confirm a refund", "texts the customer", "c", "{{business}}: your refund was issued. It can take a few days to show on your statement."),
    "payment.due": ("Remind customers a payment is coming due", "texts the customer", "c", "{{business}}: a payment is coming due. Reply to this text if you have a question."),
    "account.funded": ("Confirm money added to an account", "texts the customer", "c", "{{business}}: funds were added to your account. Thank you!"),
    "account.low_balance": ("Warn when an account balance is low", "texts the customer", "c", "{{business}}: your account balance is running low. Reply to this text if you would like to add funds."),
    "job.scheduled": ("Confirm a scheduled job", "texts the customer", "c", "{{business}}: your visit is scheduled. Reply to this text if you need to change it."),
    "job.on_the_way": ("Say a technician is on the way", "texts the customer", "c", "{{business}}: our technician is on the way."),
    "job.in_progress": ("Say a job is under way", "texts the customer", "c", "{{business}}: we have started your job."),
    "job.completed": ("Thank customers when a job is done", "texts the customer", "c", "{{business}}: your job is finished. Thank you! Reply to this text if anything is not right."),
    "job.followup_due": ("Follow up after a job", "texts the customer", "c", "{{business}}: how did everything go with your job? Reply to this text and tell us."),
    "quote.followup_due": ("Follow up on a quote", "texts the customer", "c", "{{business}}: do you have any questions about your quote? Reply to this text and we will help."),
    "callback.scheduled": ("Confirm a scheduled callback", "texts the customer", "c", "{{business}}: we will call you back as planned. Reply to this text if the time no longer works."),
    "repair.received": ("Confirm an item arrived for repair", "texts the customer", "c", "{{business}}: we received your item for repair. We will text you as it moves along."),
    "repair.in_progress": ("Say a repair is under way", "texts the customer", "c", "{{business}}: we have started your repair."),
    "repair.ready": ("Say a repair is ready", "texts the customer", "c", "{{business}}: your repair is ready for pickup."),
    "repair.picked_up": ("Thank them after a repair pickup", "texts the customer", "c", "{{business}}: thank you for picking up your repair. Reply to this text if anything is not right."),
    "ticket.created": ("Confirm a new support ticket", "texts the customer", "c", "{{business}}: we received your request. We will keep you updated."),
    "ticket.in_progress": ("Say a ticket is being worked on", "texts the customer", "c", "{{business}}: we are working on your request."),
    "ticket.updated": ("Tell customers a ticket was updated", "texts the customer", "c", "{{business}}: there is an update on your request. Reply to this text to see it or ask a question."),
    "ticket.resolved": ("Say a ticket is resolved", "texts the customer", "c", "{{business}}: your request is resolved. Reply to this text if you need anything else."),
    "customer.escalated": ("Alert your team when a customer asks for a manager", "tells your team and texts the customer", "b", "A customer asked for a manager: {{customer.name}} {{customer.phone}}. Please call them back.|{{business}}: a manager will contact you as soon as possible."),
    "pipeline.failed": ("Alert your team when a build fails", "tells your team", "t", "Build FAILED: {{repo}} {{branch}} {{author}} {{url}}"),
    "pipeline.succeeded": ("Tell your team when a build passes", "tells your team", "t", "Build passed: {{repo}} {{branch}} {{url}}"),
    "deploy.succeeded": ("Tell your team about a deployment", "tells your team", "t", "Deployed: {{repo}} {{branch}} {{url}}"),
    "deploy.failed": ("Alert your team when a deployment fails", "tells your team", "t", "Deploy FAILED: {{repo}} {{branch}} {{url}}"),
    "incident.triggered": ("Alert your team about an incident", "tells your team", "t", "INCIDENT: {{incident.title}} {{url}}"),
    "incident.resolved": ("Tell your team an incident is resolved", "tells your team", "t", "Incident resolved: {{incident.title}} {{url}}"),
    "release.published": ("Tell your team about a release", "tells your team", "t", "Release published: {{repo}} {{release.name}} {{url}}"),
    "pull_request.ready": ("Tell your team a pull request is ready", "tells your team", "t", "Pull request ready for review: {{repo}} {{pull_request.title}} {{url}}"),
    "issue.opened": ("Tell your team about a new issue", "tells your team", "t", "New issue: {{repo}} {{issue.title}} {{url}}"),
    "security.alert": ("Alert your team about a security alert", "tells your team", "t", "SECURITY ALERT: {{repo}} {{alert.title}} {{url}}"),
}


def name_for(event):
    return "auto_" + event.replace(".", "_")


def workflow(event):
    title, what, kind, text = SPECS[event]
    if kind == "c":
        do = [{"action": "sms", "to": "{{customer.phone}}", "text": text}]
    elif kind == "t":
        do = [{"action": "notify", "text": text}]
    else:
        team, cust = text.split("|", 1)
        do = [{"action": "notify", "text": team}, {"action": "sms", "to": "{{customer.phone}}", "text": cust}]
    return {"name": name_for(event), "title": title, "what": what, "general": True, "on": {"event": event}, "do": do}


def covered(doc):
    return {(w.get("on") or {}).get("event") for w in doc.get("workflows", []) if (w.get("on") or {}).get("event")}


def ensure(agent):
    """Adds the ready-made automation for every event that has none yet (once; your switches are kept). Returns how many were added."""
    path = (agent.cfg or {}).get("workflows")
    if not path or not os.path.exists(path):
        return 0
    try:
        doc = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    have = covered(doc); names = {w.get("name") for w in doc.get("workflows", [])}
    add = [workflow(e) for e in SPECS if e not in have and name_for(e) not in names]
    if not add:
        return 0
    doc.setdefault("workflows", []).extend(add)
    try:
        open(path + ".bak", "w", encoding="utf-8").write(open(path, encoding="utf-8").read())
        tmp = path + ".tmp"; json.dump(doc, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, path)
    except OSError:
        return 0
    return len(add)
