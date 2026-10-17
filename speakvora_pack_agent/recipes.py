"""Ready-made workflows for every industry profile, built from the slots that profile has. `init` writes these next to the pack so an unzipped bundle runs after you fill in your hours and connect your services."""
import json, os

from . import slots as SL

HERE = os.path.dirname(os.path.abspath(__file__))


def _sms(to, text):
    return {"action": "sms", "to": "{{customer.phone}}" if to is None else to, "text": text}


def workflows_for(profile, lang="en"):
    return localize(_workflows_for(profile), lang)


def localize(doc, lang):
    """Non-English packs: the few English glue words inside message texts become the pack language's own (staff Slack/Teams alerts stay English)."""
    from . import i18n
    if i18n.lang_of(lang) == "en":
        return doc
    swaps = [("order {{order.number}} is ready. ", "{{t:order}} {{order.number}}: "), ("(about {{order.extra_minutes}} more minutes)", "({{order.extra_minutes}} {{t:min}})"), (", party of {{party}}.", " · {{party}}."), (" Reply C to cancel or just come by.", ""),
             ("(This reply was sent by an automated assistant.)", "{{t:auto_footer}}"), ("(This reply was sent by an automated assistant. Reply to reach a person.)", "{{t:auto_footer}}")]
    import json as _j
    txt = _j.dumps(doc, ensure_ascii=False)
    for a, b in swaps:
        txt = txt.replace(_j.dumps(a, ensure_ascii=False)[1:-1], _j.dumps(b, ensure_ascii=False)[1:-1])
    return _j.loads(txt)


TRACK_PROFILES = ('food', 'retail', 'laundry', 'pharmacy', 'dispensary')                                       # businesses whose customers watch an order move through steps
LOOKUP_PROFILES = ('clinic', 'pharmacy', 'dispensary')
PERSON_WORDS = {   # words that mean the caller needs a person, not the assistant: health, dose, condition, results, medicines
    'clinic': ['symptom', 'symptoms', 'results', 'result', 'medication', 'medicine', 'prescription', 'pain', 'doctor', 'nurse', 'treatment', 'diagnosis', 'pregnant', 'bleeding'],
    'pharmacy': ['dose', 'dosage', 'interaction', 'interactions', 'side', 'effects', 'reaction', 'pregnant', 'substitute', 'generic', 'pharmacist', 'symptom', 'symptoms'],
    'dispensary': ['dose', 'dosage', 'strength', 'potency', 'treat', 'treats', 'condition', 'pregnant', 'medical', 'certification', 'caregiver', 'reaction', 'pharmacist']}                                               # private status comes only from the business's own connected records system


def _workflows_for(profile):
    reg = SL.registry(profile)
    if profile == "food":
        return json.load(open(os.path.join(HERE, "data", "food.workflows.json"), encoding="utf-8"))
    has = lambda s: s in reg  # noqa: E731
    w = []
    if has("order_ready"):
        if profile in TRACK_PROFILES:                                                  # one text with a tracking link; the page then shows each step (pizza-tracker style); a text per step is opt-in (tracking.text_each_step)
            tr = lambda st, **k: {"action": "track", "status": st, **k}              # noqa: E731
            w += [{"name": "order_received", "on": {"event": "order.received"}, "do": [tr("received"), _sms(None, "{{business}}: {{slot:order_received}} {{track.line}}")]},
                  {"name": "order_preparing", "on": {"event": "order.preparing"}, "do": [tr("preparing"), dict(_sms(None, "{{business}}: {{slot:order_preparing}} {{track.line}}"), each_step=True)]},
                  {"name": "order_ready", "on": {"event": "order.ready"}, "do": [tr("ready"), dict(_sms(None, "{{business}}: order {{order.number}} is ready. {{slot:order_ready}}" + (" {{slot:pickup_instructions}}" if has("pickup_instructions") else "") + (" {{slot:pickup_id_reminder}}" if has("pickup_id_reminder") else "")), **({} if profile in ("pharmacy", "dispensary") else {"each_step": True})),
                                                                              {"action": "notify", "text": "Order {{order.number}} is ready (status page updated)."}]},
                  {"name": "order_picked_up", "on": {"event": "order.picked_up"}, "do": [tr("picked_up"), dict(_sms(None, "{{business}}: {{slot:order_picked_up}}"), **({} if profile in ("pharmacy", "dispensary") else {"each_step": True}))]},
                  {"name": "order_delayed", "on": {"event": "order.delayed"}, "do": [tr("preparing", delayed=True), _sms(None, "{{business}}: {{slot:order_delayed}} {{track.line}}"), {"action": "notify", "text": "Order {{order.number}} delayed. Text to customer: {{last.sms}}."}]}]
            if has("order_ready_delivery"):
                w += [{"name": "order_out_for_delivery", "on": {"event": "order.out_for_delivery"}, "do": [tr("out_for_delivery", delivery=True), dict(_sms(None, "{{business}}: {{slot:order_ready_delivery}} {{track.line}}"), each_step=True)]},
                      {"name": "order_delivered", "on": {"event": "order.delivered"}, "do": [tr("delivered", delivery=True), dict(_sms(None, "{{business}}: {{slot:order_delivered}}"), each_step=True)]}]
        else:                                                                           # pharmacy and others: a plain text at each main step, never naming what was ordered
            w += [{"name": "order_received", "on": {"event": "order.received"}, "do": [_sms(None, "{{business}}: {{slot:order_received}}")]},
                  {"name": "order_ready", "on": {"event": "order.ready"}, "do": [_sms(None, "{{business}}: order {{order.number}} is ready. {{slot:order_ready}}" + (" {{slot:pickup_instructions}}" if has("pickup_instructions") else "")),
                                                                              {"action": "notify", "text": "Order {{order.number}} is ready. Text to {{customer.name}}: {{last.sms}}."}]},
                  {"name": "order_picked_up", "on": {"event": "order.picked_up"}, "do": [_sms(None, "{{business}}: {{slot:order_picked_up}}")]},
                  {"name": "order_delayed", "on": {"event": "order.delayed"}, "do": [_sms(None, "{{business}}: {{slot:order_delayed}}"), {"action": "notify", "text": "Order {{order.number}} delayed. Text to customer: {{last.sms}}."}]}]
        if has("order_cancelled"):
            w.append({"name": "order_cancelled", "on": {"event": "order.cancelled"}, "do": ([{"action": "track", "status": "cancelled"}] if profile in TRACK_PROFILES else []) + [_sms(None, "{{business}}: {{slot:order_cancelled}}")]})
        if has("order_ready_delivery") and profile not in TRACK_PROFILES:
            w.append({"name": "order_out_for_delivery", "on": {"event": "order.out_for_delivery"}, "do": [_sms(None, "{{business}}: {{slot:order_ready_delivery}}")]})
    if has("appointment_confirmed"):
        w += [{"name": "appointment_created", "on": {"event": "appointment.created"}, "do": [
                  _sms(None, "{{business}}: {{slot:appointment_confirmed}} {{start_text}}."),
                  {"action": "calendar_create", "title": "Appointment: {{customer.name}}", "start": "{{start_epoch}}", "minutes": "{{minutes}}", "description": "Name: {{customer.name}}\nPhone: {{customer.phone}}\nSMS OK: {{customer.sms_consent}}"},
                  {"action": "notify", "text": "New booking: {{customer.name}}, {{start_text}}. Text: {{last.sms}}."}]},
              {"name": "appointment_changed", "on": {"event": "appointment.changed"}, "do": [_sms(None, "{{business}}: {{slot:appointment_changed}} {{start_text}}.")]},
              {"name": "appointment_cancelled", "on": {"event": "appointment.cancelled"}, "do": [_sms(None, "{{business}}: {{slot:appointment_cancelled}}")]},
              {"name": "appointment_reminder_24h", "on": {"calendar": {"starts_in_minutes": 1440, "window_minutes": 30, "title_contains": "Appointment"}}, "do": [_sms(None, "{{business}}: {{slot:appointment_reminder}} {{start_local}}.")]},
              {"name": "appointment_reminder_2h", "on": {"calendar": {"starts_in_minutes": 120, "window_minutes": 15, "title_contains": "Appointment"}}, "do": [_sms(None, "{{business}}: {{slot:appointment_reminder_today}} {{start_local}}.")]},
              {"name": "no_show_followup", "on": {"event": "appointment.no_show"}, "do": [_sms(None, "{{business}}: {{slot:no_show_followup}}")]},
              {"name": "sms_reschedule", "on": {"sms": {"topic": "reschedule"}}, "do": [
                  {"action": "reply", "text": "{{slot:reschedule_help}}"}, {"action": "notify", "text": "Booking request by text from {{sms.from}}: {{sms.body}}"}]},
              {"name": "ready_for_you", "on": {"event": "appointment.ready"}, "do": [_sms(None, "{{business}}: {{slot:ready_for_you}}")]}]
    if has("quote_followup"):                                                       # service business: follow-ups your own system triggers when they are due, each also creates a task for the team
        w += [{"name": "quote_followup", "on": {"event": "quote.followup_due"}, "do": [_sms(None, "{{business}}: {{slot:quote_followup}}"), {"action": "notify", "text": "Follow-up task: call {{customer.name}} about their quote. Text sent: {{last.sms}}."}]},
              {"name": "job_followup", "on": {"event": "job.followup_due"}, "do": [_sms(None, "{{business}}: {{slot:job_followup}}"), {"action": "notify", "text": "Follow-up task: check the finished work with {{customer.name}}."}]},
              {"name": "next_visit_due", "on": {"event": "visit.next_due"}, "do": [_sms(None, "{{business}}: {{slot:next_visit_due}}")]}]
    if profile == "trades" and has("on_the_way"):                                  # a visit or job the customer can follow: booked, on the way, in progress, done
        jt = lambda st, **k: {"action": "track", "status": st, "flow": "job", **k}   # noqa: E731
        w += [{"name": "job_scheduled", "on": {"event": "job.scheduled"}, "do": [jt("scheduled"), _sms(None, "{{business}}: {{slot:appointment_confirmed}} {{start_text}} {{track.line}}")]},
              {"name": "job_on_the_way", "on": {"event": "job.on_the_way"}, "do": [jt("on_the_way"), dict(_sms(None, "{{business}}: {{slot:on_the_way}} {{track.line}}"), each_step=True)]},
              {"name": "job_in_progress", "on": {"event": "job.in_progress"}, "do": [jt("in_progress")]},
              {"name": "job_completed", "on": {"event": "job.completed"}, "do": [jt("completed"), dict(_sms(None, "{{business}}: {{slot:job_followup}}"), each_step=True)]}]
    if profile == "auto" and has("repair_received"):                               # a repair order the customer can follow
        rt = lambda st, **k: {"action": "track", "status": st, "flow": "repair", **k}   # noqa: E731
        w += [{"name": "repair_received", "on": {"event": "repair.received"}, "do": [rt("received"), _sms(None, "{{business}}: {{slot:repair_received}} {{track.line}}")]},
              {"name": "repair_in_progress", "on": {"event": "repair.in_progress"}, "do": [rt("in_progress")]},
              {"name": "repair_ready", "on": {"event": "repair.ready"}, "do": [rt("ready"), dict(_sms(None, "{{business}}: {{slot:vehicle_ready}}"), each_step=True)]},
              {"name": "repair_picked_up", "on": {"event": "repair.picked_up"}, "do": [rt("picked_up")]}]
    if profile == "support" and has("ticket_created"):                             # a support request the customer can follow
        kt = lambda st, **k: {"action": "track", "status": st, "flow": "ticket", **k}   # noqa: E731
        w += [{"name": "ticket_created", "on": {"event": "ticket.created"}, "do": [kt("received"), _sms(None, "{{business}}: {{slot:ticket_created}} {{track.line}}")]},
              {"name": "ticket_in_progress", "on": {"event": "ticket.in_progress"}, "do": [kt("in_progress")]},
              {"name": "ticket_resolved", "on": {"event": "ticket.resolved"}, "do": [kt("resolved"), dict(_sms(None, "{{business}}: {{slot:ticket_update}}"), each_step=True)]}]
    if profile in PERSON_WORDS:                                                      # health: questions about symptoms, doses, conditions or results are never answered by text; a person is told
        w += [{"name": "sms_clinical", "on": {"sms": {"keywords": PERSON_WORDS[profile]}}, "do": [{"action": "reply", "text": "{{slot:handoff_received}}"}, {"action": "notify", "text": "A customer asked a health or product question by text ({{sms.from}}). Please call them."}]}]
        w += [{"name": "sms_info", "on": {"sms": {"keywords": ["parking", "visiting", "visitor", "visitors", "departments", "department", "billing", "directory"]}}, "do": [{"action": "reply", "text": "{{fact:info}}"}]}]
    if profile == "pharmacy" and has("refill_help"):
        w += [{"name": "sms_refill", "on": {"sms": {"keywords": ["refill", "refills", "renew"]}}, "do": [{"action": "reply", "text": "{{slot:refill_help}}"}, {"action": "notify", "text": "Refill question by text from {{sms.from}}. No details were taken."}]}]
    w += [{"name": "thanks_review", "on": {"event": "visit.completed"}, "do": [_sms(None, "{{business}}: {{slot:thanks_review}} {{fact:review_url}}")]},
          {"name": "sms_hours", "on": {"sms": {"topic": "hours"}}, "do": [{"action": "reply", "text": "{{slot:hours_intro}} {{fact:hours}}"}]},
          {"name": "sms_directions", "on": {"sms": {"topic": "directions"}}, "do": [{"action": "reply", "text": "{{slot:directions_intro}} {{fact:address}}"}]},
          {"name": "sms_status", "on": {"sms": {"topic": "status"}}, "do": ([{"action": "lookup", "connection": "records", "deliver": "reply", "fallback_slot": "handoff_received"}] if profile in LOOKUP_PROFILES else [{"action": "reply", "text": "{{slot:status_help}}"}]) + [{"action": "notify", "text": "Status question by text from {{sms.from}}"}]},
          {"name": "sms_person", "on": {"sms": {"topic": "person"}}, "do": [
              {"action": "reply", "text": "{{slot:handoff_received}}"}, {"action": "notify", "text": "Someone needs a person: {{sms.from}} says \"{{sms.body}}\""}]},
          {"name": "phone_menu", "on": {"call": {"menu": {**({"person_words": PERSON_WORDS[profile]} if profile in PERSON_WORDS else {}), "prompt": "menu_prompt", "fallback_say": "Press 1 for opening hours, 2 to book, 3 to check on something, or 0 for a person.", "options": {
              "1": [{"action": "play", "audio": ["hours_intro"]}, {"action": "reply", "text": "{{fact:hours}}"}],
              "2": [{"action": "notify", "text": "Caller {{call.from}} wants to book or change a booking."}, {"action": "reply", "text": "Thanks, the team will call you back."}],
              "3": ([{"action": "lookup", "connection": "records", "deliver": "sms", "fallback_slot": "handoff_received"}] if profile in LOOKUP_PROFILES else [{"action": "play", "audio": ["status_help"]}]) + [{"action": "notify", "text": "Caller {{call.from}} asked for a status update."}],
              "0": [{"action": "play", "audio": ["handoff_person"]}, {"action": "notify", "text": "Caller {{call.from}} wants a person."}, {"action": "transfer", "to": "{{fact:oncall_phone}}"}]}}}}, "do": []},
          {"name": "daily_briefing", "on": {"schedule": {"at": "09:30"}}, "do": [{"action": "notify", "text": "Today:\n{{today_text}}"}]},
          {"name": "slack_say", "on": {"slack_command": "/say"}, "do": [_sms("{{command.arg2}}", "{{business}}: {{slotvar:command.arg1}}"), {"action": "reply", "text": "Text to {{command.arg2}} ({{last.sms}}): {{slotvar:command.arg1}}"}]}]
    if profile == "devops":
        oncall = lambda slot, kind="sms": {"action": kind, "to": "{{fact:oncall_phone}}", "urgent": True, **({"text": "{{business}}: {{slot:" + slot + "}} {{repo}} {{branch}} {{url}}"} if kind == "sms" else {"play": [slot]})}  # noqa: E731
        w += [{"name": "pipeline_failed", "on": {"event": "pipeline.failed"}, "do": [{"action": "notify", "text": "Pipeline FAILED: {{repo}} {{branch}} by {{author}} {{url}}"}, oncall("pipeline_failed")]},
              {"name": "pipeline_succeeded", "on": {"event": "pipeline.succeeded"}, "do": [{"action": "notify", "text": "Pipeline passed: {{repo}} {{branch}} {{url}}"}]},
              {"name": "deploy_succeeded", "on": {"event": "deploy.succeeded"}, "do": [{"action": "notify", "text": "Deployed: {{repo}} {{branch}} {{url}}"}]},
              {"name": "deploy_failed", "on": {"event": "deploy.failed"}, "do": [{"action": "notify", "text": "Deploy FAILED: {{repo}} {{branch}} {{url}}"}, oncall("deploy_failed"), oncall("oncall_alert", "call")]},
              {"name": "incident_opened", "on": {"event": "incident.triggered"}, "do": [{"action": "notify", "text": "INCIDENT: {{incident.title}} {{url}}"}, oncall("incident_opened"), oncall("oncall_alert", "call")]},
              {"name": "incident_resolved", "on": {"event": "incident.resolved"}, "do": [{"action": "notify", "text": "Incident resolved: {{incident.title}}"}, oncall("incident_resolved")]},
              {"name": "security_alert", "on": {"event": "security.alert"}, "do": [{"action": "notify", "text": "Security alert on {{repo}}: {{url}}"}, oncall("security_alert")]},
              {"name": "pull_request_ready", "on": {"event": "pull_request.ready"}, "do": [{"action": "notify", "text": "Review requested: {{repo}} {{title}} by {{author}} {{url}}"}]},
              {"name": "release_published", "on": {"event": "release.published"}, "do": [{"action": "notify", "text": "Release published: {{repo}} {{title}} {{url}}"}]},
              {"name": "issue_opened", "on": {"event": "issue.opened"}, "do": [{"action": "notify", "text": "New issue in {{repo}}: {{title}} {{url}}"}]}]
    if profile == "corrections":
        w += [{"name": "account_funded", "on": {"event": "account.funded"}, "do": [_sms(None, "{{business}}: {{slot:account_funded}}")]},
              {"name": "account_low_balance", "on": {"event": "account.low_balance"}, "do": [_sms(None, "{{business}}: {{slot:account_low_balance}}")]},
              {"name": "visit_rules", "on": {"sms": {"topic": "rules"}}, "do": [{"action": "reply", "text": "{{slot:visit_rules_reminder}} {{fact:visit_rules}}"}]},
              {"name": "bail_info", "on": {"sms": {"topic": "bail"}}, "do": [{"action": "reply", "text": "{{slot:bail_info_help}} {{fact:bail_contact}}"}]},
              {"name": "lockdown", "on": {"event": "facility.lockdown"}, "do": [_sms(None, "{{business}}: {{slot:lockdown_notice}}")]}]
    if profile == "collections":
        w += [{"name": "payment_due_notice", "on": {"event": "payment.due"}, "do": [_sms(None, "{{business}}: {{slot:payment_due}}")]},
              {"name": "payment_failed_notice", "on": {"event": "payment.failed"}, "do": [_sms(None, "{{business}}: {{slot:payment_failed}}")]},
              {"name": "sms_hardship", "on": {"sms": {"topic": "hardship"}}, "do": [
                  {"action": "reply", "text": "{{slot:hardship_help}} {{slot:payment_plan_offer}}"}, {"action": "notify", "text": "Payment help requested by text from {{sms.from}}: {{sms.body}}"}]}]
    w += [{"name": "email_hours", "on": {"email": {"topic": "hours"}}, "do": [
              {"action": "email", "to": "{{email.from}}", "subject": "Re: {{email.subject}}", "text": "{{business}}: {{slot:hours_intro}} {{fact:hours}}\n\n(This reply was sent by an automated assistant. Reply to reach a person.)"}]},
          {"name": "email_person", "on": {"email": {"topic": "person", "keywords": ["complaint", "urgent", "refund"]}}, "do": [
              {"action": "notify", "text": "Customer email needs a person: {{email.from}}: {{email.subject}}"},
              {"action": "email", "to": "{{email.from}}", "subject": "Re: {{email.subject}}", "text": "{{business}}: {{slot:handoff_received}}"}]}]
    if profile == "support":
        w += [{"name": "email_ticket", "on": {"email": {}}, "do": [
                  {"action": "http", "method": "POST", "url": "https://YOUR-HELPDESK-HOST/api/tickets", "headers": {"Authorization": "Bearer YOUR-HELPDESK-TOKEN"}, "json": {"from": "{{email.from}}", "subject": "{{email.subject}}", "body": "{{email.body}}"}, "save_as": "ticket"},
                  {"action": "email", "to": "{{email.from}}", "subject": "Re: {{email.subject}}", "text": "{{business}}: {{slot:ticket_created}} Ticket {{http.ticket.id}}.\n\n(This reply was sent by an automated assistant.)"},
                  {"action": "notify", "text": "New ticket {{http.ticket.id}} from {{email.from}}: {{email.subject}}"}]},
              {"name": "ticket_update", "on": {"event": "ticket.updated"}, "do": [_sms(None, "{{business}}: {{slot:ticket_update}} {{ticket.summary}}"), {"action": "email", "to": "{{customer.email}}", "subject": "Update on your request", "text": "{{business}}: {{slot:ticket_update}}\n{{ticket.summary}}"}]},
              {"name": "customer_escalated", "on": {"event": "customer.escalated"}, "do": [_sms(None, "{{business}}: {{slot:handoff_received}}"), {"action": "notify", "text": "ESCALATION: {{customer.name}} {{customer.phone}}: {{reason}}"}]},
              {"name": "callback_scheduled", "on": {"event": "callback.scheduled"}, "do": [_sms(None, "{{business}}: {{slot:callback_scheduled}} {{start_text}}.")]}]
    return {"workflows": w}


def agent_config(business="YOUR-BUSINESS-NAME"):
    return {"business": business, "dry_run": True, "pack": "./pack", "workflows": "./workflows.json", "timezone": "America/New_York", "listen": {"host": "127.0.0.1", "port": 8787},
            "public_base_url": "https://YOUR-PUBLIC-ADDRESS-FOR-THIS-AGENT", "events": {"secret": "env:SV_EVENT_SECRET"},
            "facts": {"hours": "YOUR-OPENING-HOURS", "address": "YOUR-ADDRESS", "review_url": "YOUR-REVIEW-LINK", "oncall_phone": "YOUR-ONCALL-PHONE"},
            "mode": "standard", "compliance": {"sms_footer": "first", "recording": False, "extra_required": []},
            "recipients": {"allow": []},
            "consent": {"field": "customer.sms_consent", "required": True},
            "twilio": {"account_sid": "env:TWILIO_ACCOUNT_SID", "auth_token": "env:TWILIO_AUTH_TOKEN", "from_number": "env:TWILIO_FROM"},
            "slack": {"bot_token": "env:SLACK_BOT_TOKEN", "signing_secret": "env:SLACK_SIGNING_SECRET", "channel": "#general", "channels": {}},
            "google_calendar": {"mode": "ics", "ics_url": "env:CALENDAR_ICS_URL"}, "teams": {}, "microsoft_calendar": {}, "inbox": {}, "sources": []}


# Plain-language description of each ready-made workflow, shown in the dashboard and in the pack README.
NICE = {"job_scheduled": "books a visit and texts a link to follow it", "repair_received": "checks a vehicle in and texts a link to follow the repair", "ticket_created": "opens a request and texts a link to follow it", "quote_followup": "follows up on quotes and creates a task for your team", "job_followup": "checks in after finished work", "next_visit_due": "reminds customers their next visit is due", "order_ready": "tells customers their order is ready", "order_delayed": "apologises for delays", "table_ready": "tells guests their table is ready", "reservation_created": "confirms reservations and adds them to your calendar",
            "appointment_created": "confirms bookings and adds them to your calendar", "appointment_reminder_24h": "reminds people a day before (from Google Calendar)", "reservation_reminder_24h": "reminds guests a day before (from Google Calendar)",
            "no_show_followup": "follows up after a no-show", "thanks_review": "thanks customers and asks for a review", "sms_hours": "answers 'what are your hours?' by text", "sms_directions": "answers 'where are you?' by text",
            "sms_person": "passes 'I want a person' to your team on Slack or Teams", "phone_menu": "answers your phone with a menu (hours, booking, status, a person)", "daily_briefing": "posts today's bookings to Slack or Teams each morning",
            "slack_say": "lets staff text a customer a pack line from Slack with /say", "order_received": "confirms new orders", "order_cancelled": "confirms cancellations", "sms_reschedule": "handles 'change my booking' texts", "email_hours": "answers 'what are your hours?' emails", "email_person": "passes emails that need a person to your team",
            "email_ticket": "creates a helpdesk ticket from each customer email and confirms it", "ticket_update": "tells customers when their ticket changes", "customer_escalated": "alerts your team and reassures the customer when a case is escalated",
            "callback_scheduled": "confirms a scheduled callback", "appointment_cancelled": "confirms cancellations", "appointment_changed": "confirms changes", "order_out_for_delivery": "tells customers their delivery is on its way"}

