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


def _workflows_for(profile):
    reg = SL.registry(profile)
    if profile == "food":
        return json.load(open(os.path.join(HERE, "data", "food.workflows.json"), encoding="utf-8"))
    has = lambda s: s in reg  # noqa: E731
    w = []
    if has("order_ready"):
        w += [{"name": "order_ready", "on": {"event": "order.ready"}, "do": [_sms(None, "{{business}}: order {{order.number}} is ready. {{slot:order_ready}}" + (" {{slot:pickup_instructions}}" if has("pickup_instructions") else "")),
                                                                         {"action": "notify", "text": "Order {{order.number}} is ready. Text to {{customer.name}}: {{last.sms}}."}]},
              {"name": "order_received", "on": {"event": "order.received"}, "do": [_sms(None, "{{business}}: {{slot:order_received}}")]},
              {"name": "order_delayed", "on": {"event": "order.delayed"}, "do": [_sms(None, "{{business}}: {{slot:order_delayed}}"), {"action": "notify", "text": "Order {{order.number}} delayed. Text to customer: {{last.sms}}."}]}]
        if has("order_cancelled"):
            w.append({"name": "order_cancelled", "on": {"event": "order.cancelled"}, "do": [_sms(None, "{{business}}: {{slot:order_cancelled}}")]})
        if has("order_ready_delivery"):
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
    w += [{"name": "thanks_review", "on": {"event": "visit.completed"}, "do": [_sms(None, "{{business}}: {{slot:thanks_review}} {{fact:review_url}}")]},
          {"name": "sms_hours", "on": {"sms": {"topic": "hours"}}, "do": [{"action": "reply", "text": "{{slot:hours_intro}} {{fact:hours}}"}]},
          {"name": "sms_directions", "on": {"sms": {"topic": "directions"}}, "do": [{"action": "reply", "text": "{{slot:directions_intro}} {{fact:address}}"}]},
          {"name": "sms_status", "on": {"sms": {"topic": "status"}}, "do": [{"action": "reply", "text": "{{slot:status_help}}"}, {"action": "notify", "text": "Status question by text from {{sms.from}}: {{sms.body}}"}]},
          {"name": "sms_person", "on": {"sms": {"topic": "person"}}, "do": [
              {"action": "reply", "text": "{{slot:handoff_received}}"}, {"action": "notify", "text": "Someone needs a person: {{sms.from}} says \"{{sms.body}}\""}]},
          {"name": "phone_menu", "on": {"call": {"menu": {"prompt": "menu_prompt", "fallback_say": "Press 1 for opening hours, 2 to book, 3 to check on something, or 0 for a person.", "options": {
              "1": [{"action": "play", "audio": ["hours_intro"]}, {"action": "reply", "text": "{{fact:hours}}"}],
              "2": [{"action": "notify", "text": "Caller {{call.from}} wants to book or change a booking."}, {"action": "reply", "text": "Thanks, the team will call you back."}],
              "3": [{"action": "play", "audio": ["status_help"]}, {"action": "notify", "text": "Caller {{call.from}} asked for a status update."}],
              "0": [{"action": "play", "audio": ["handoff_person"]}, {"action": "notify", "text": "Caller {{call.from}} wants a person."}]}}}}, "do": []},
          {"name": "daily_briefing", "on": {"schedule": {"at": "09:30"}}, "do": [{"action": "notify", "text": "Today:\n{{today_text}}"}]},
          {"name": "slack_say", "on": {"slack_command": "/say"}, "do": [_sms("{{command.arg2}}", "{{business}}: {{slotvar:command.arg1}}"), {"action": "reply", "text": "Texted {{command.arg2}}: {{slotvar:command.arg1}}"}]}]
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
            "slack": {"bot_token": "env:SLACK_BOT_TOKEN", "signing_secret": "env:SLACK_SIGNING_SECRET", "channel": "#general"},
            "google_calendar": {"mode": "ics", "ics_url": "env:CALENDAR_ICS_URL"}, "teams": {}, "microsoft_calendar": {}, "inbox": {}, "sources": []}
