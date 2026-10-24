"""Industry kits, plain names, the smart reminder, editing and approving a workflow, answering while closed, and the safe-by-design rules for health, legal, finance and public businesses."""
import datetime as dt, json, os, re, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_pack_agent import Rig, NOON, CUST, TOKEN
from speakvora_pack_agent import config, dashboard, kits, recipes, slots as SL, wfedit
from speakvora_pack_agent.engine import Agent

REG = ("clinic", "pharmacy", "dispensary", "legal", "finance", "collections", "corrections", "public", "education")


def rig_for(profile, **kw):
    r = Rig(extra={"industry_profile": profile, "mode": "open", "facts": {"hours": "Mon to Fri, 9 to 5", "address": "12 Main St", "review_url": "https://example.com/r", "oncall_phone": "+16465550123"}}, **kw)
    json.dump(recipes.workflows_for(profile), open(os.path.join(r.tmp, "workflows.json"), "w"))
    r.agent = Agent(config.load(os.path.join(r.tmp, "agent.json")), now=lambda: r.now[0])
    return r


def plain_ok(t):
    return bool(t) and "_" not in t and not re.search(r"\b(sms|api|webhook|json|slot|event)\b", t, re.I) and t[0].isupper()


class KitContent(unittest.TestCase):
    def test_every_profile_has_a_kit_with_plain_names(self):
        for p in SL.PROFILES:
            ws = recipes.workflows_for(p)["workflows"]
            self.assertGreaterEqual(len([w for w in ws if w.get("kit")]), 3, p)
            names = [w["name"] for w in ws]
            self.assertEqual(len(names), len(set(names)), p)
            for w in ws:
                self.assertTrue(plain_ok(w.get("title", "")), (p, w["name"], w.get("title")))
                self.assertTrue(w.get("what"), (p, w["name"]))
                if w.get("kit"):
                    self.assertFalse(w["enabled"]); self.assertFalse(w["approved"])

    def test_no_two_workflows_answer_the_same_event(self):
        for p in SL.PROFILES:
            evs = [w["on"]["event"] for w in recipes.workflows_for(p)["workflows"] if "event" in (w.get("on") or {})]
            self.assertEqual(len(evs), len(set(evs)), (p, [e for e in evs if evs.count(e) > 1]))

    def test_every_kit_line_is_a_real_registered_slot_without_digits(self):
        for p in SL.PROFILES:
            reg = SL.registry(p)
            for w in recipes.workflows_for(p)["workflows"]:
                if not w.get("kit"):
                    continue
                for slot in SL.needed_by(w):
                    self.assertIn(slot, reg, (p, w["name"], slot))
                    ex = reg[slot]["example"]
                    self.assertFalse(re.search(r"\d", ex), (p, slot, ex))
                    self.assertTrue(ex.endswith((".", "?", "!")) and len(ex.split()) >= 4, (p, slot, ex))

    def test_regulated_kits_never_promote_and_health_kits_never_name_health_details(self):
        for p in REG:
            for slot, v in kits.slot_table(p).items():
                self.assertEqual(kits.violations(p, v[1].replace("{a}", "booking")), [], (p, slot))
            for w in recipes.workflows_for(p)["workflows"]:
                self.assertFalse(w.get("sale"), p)
                for step in w.get("do", []):
                    if step.get("action") in ("sms", "reply", "email"):
                        self.assertEqual(kits.violations(p, re.sub(r"\{\{[^}]*\}\}", "", step.get("text", ""))), [], (p, w["name"]))

    def test_health_and_legal_questions_always_go_to_a_person(self):
        want = {"clinic": "health_questions_to_a_person", "pharmacy": "medicine_questions_to_a_pharmacist", "dispensary": "product_questions_to_staff", "legal": "questions_about_a_case_to_a_person",
                "finance": "suspected_fraud_to_a_person", "public": "case_and_benefit_questions_to_a_person", "corrections": "case_questions_to_a_person", "collections": "disputes_to_a_person"}
        for p, name in want.items():
            w = next(x for x in recipes.workflows_for(p)["workflows"] if x["name"] == name)
            self.assertTrue(any(s["action"] == "notify" for s in w["do"]), name)
            txt = SL.registry(p)[SL.needed_by(w).copy().pop()]["example"].lower()
            self.assertTrue("team" in txt or "pharmacist" in txt or "staff" in txt, (p, txt))

    def test_no_certification_claims_in_any_kit_text(self):
        for p in SL.PROFILES:
            blob = json.dumps(kits.slot_table(p)).lower() + json.dumps(recipes.workflows_for(p)).lower()
            for bad in ("hipaa compliant", "hipaa-compliant", "certified", "tcpa compliant", "legally compliant"):
                self.assertNotIn(bad, blob, p)

    def test_sale_workflow_exists_only_for_shops(self):
        for p in SL.PROFILES:
            has = any(w.get("sale") for w in recipes.workflows_for(p)["workflows"])
            self.assertEqual(has, p in ("retail", "food", "beauty", "laundry", "auto"), p)
        for p in REG + ("lodging", "trades", "support", "devops", "generic"):
            self.assertFalse(kits.sale_allowed(p), p)

    def test_plain_titles_for_the_event_automations_too(self):
        from speakvora_pack_agent import eventflows
        for ev, spec in eventflows.SPECS.items():
            self.assertTrue(plain_ok(spec[0]), spec[0])


class KitsRun(unittest.TestCase):
    def test_a_kit_workflow_does_nothing_until_it_is_approved(self):
        r = rig_for("clinic"); a = r.agent
        self.assertNotIn("something_is_ready", [w["name"] for w in a.workflows])
        r.event("results.ready", customer=CUST); self.assertEqual(r.mock.calls("Messages.json"), [])
        d = wfedit.save(a, "something_is_ready", approve=True)
        self.assertEqual(d["state"], "on"); self.assertIn("something_is_ready", [w["name"] for w in a.workflows])
        r.event("results.ready", customer=CUST)
        sent = r.mock.calls("Messages.json"); self.assertEqual(len(sent), 1)
        body = sent[0]["form"]["Body"]; self.assertIn("results are ready", body.lower()); self.assertNotRegex(body.lower(), r"diagnos|positive|negative")
        r.close()

    def test_turning_on_without_approval_is_refused(self):
        from speakvora_pack_agent import connect
        r = rig_for("clinic")
        with self.assertRaises(connect.SetupError): connect.set_workflow(r.agent, "something_is_ready", True)
        with self.assertRaises(wfedit.EditError): wfedit.save(r.agent, "something_is_ready", enable=True)
        r.close()

    def test_editing_the_words_is_checked_for_the_industry(self):
        r = rig_for("clinic"); a = r.agent
        d = wfedit.detail(a, "something_is_ready"); self.assertEqual(len(d["texts"]), 2)
        with self.assertRaises(wfedit.EditError): wfedit.save(a, "something_is_ready", texts={"0": "Big sale this week, 20% off checkups!"})
        with self.assertRaises(wfedit.EditError): wfedit.save(a, "something_is_ready", texts={"0": "Your test shows a negative result."})
        with self.assertRaises(wfedit.EditError): wfedit.save(a, "something_is_ready", texts={"0": "{{os.system}} hello"})
        d = wfedit.save(a, "something_is_ready", texts={"0": "{{business}}: There is news waiting for you. Please call us."}, approve=True)
        self.assertTrue(d["texts"][0]["changed"])
        r.event("results.ready", customer=CUST); self.assertIn("news waiting", r.mock.calls("Messages.json")[0]["form"]["Body"])
        d = wfedit.reset(a, "something_is_ready"); self.assertFalse(d["texts"][0]["changed"])
        r.close()

    def test_a_shop_may_edit_freely_but_never_a_secret(self):
        r = rig_for("retail"); a = r.agent
        wfedit.save(a, "order_shipped", texts={"0": "{{business}}: Your parcel is on its way, thanks for the sale!"}, approve=True)
        with self.assertRaises(wfedit.EditError): wfedit.save(a, "order_shipped", texts={"0": "Your card 4111 1111 1111 1111 shipped"})
        r.close()

    def test_keywords_and_daily_time_can_be_changed(self):
        r = rig_for("clinic"); a = r.agent
        wfedit.save(a, "health_questions_to_a_person", keywords="chest, rash", approve=True)
        out = a.handle_sms({"From": "+16465550101", "Body": "I have a rash"}); self.assertIn("clinical team", out)
        wfedit.save(a, "daily_briefing", daily_at="07:15"); self.assertEqual(next(w for w in a.workflows if w["name"] == "daily_briefing")["on"]["schedule"]["at"], "07:15")
        with self.assertRaises(wfedit.EditError): wfedit.save(a, "daily_briefing", daily_at="25:00")
        with self.assertRaises(wfedit.EditError): wfedit.save(a, "daily_briefing", keywords="x")
        r.close()

    def test_health_question_by_text_is_never_answered_only_passed_on(self):
        r = rig_for("clinic"); a = r.agent; wfedit.save(a, "health_questions_to_a_person", approve=True)
        out = a.handle_sms({"From": "+16465550101", "Body": "what does this medication do"})
        self.assertIn("clinical team", out); self.assertNotRegex(out.lower(), r"take|dose|mg"); self.assertTrue(r.mock.calls("chat.postMessage")); r.close()


class SmartReminder(unittest.TestCase):
    def rem(self, a):
        return [o for o in a.tick() if o["workflow"] == "smart_reminder"]

    def evs(self, r, start, title="Appointment: Ann"):
        r.agent._events = lambda a, b: [{"id": "ev1", "title": title, "start": start, "end": start + 3600, "description": "Phone: 646-555-0101\nSMS OK: yes"}]

    def test_the_day_before_uses_the_day_before_line(self):
        r = rig_for("beauty"); a = r.agent; wfedit.save(a, "smart_reminder", approve=True, reminder={"before": ["day_before"], "morning_at": "08:00"})
        self.evs(r, NOON + 86400 - 600); out = [o for o in a.tick() if o["workflow"] == "smart_reminder"]; self.assertEqual([o["reminder"] for o in out], ["day_before"])
        body = r.mock.calls("Messages.json")[0]["form"]["Body"]; self.assertIn("friendly reminder", body); self.assertNotIn("today", body)
        self.assertEqual([o for o in a.tick() if o["workflow"] == "smart_reminder"], []); r.close()                                                   # once only

    def test_two_hours_before_uses_the_coming_up_line(self):
        r = rig_for("beauty"); a = r.agent; wfedit.save(a, "smart_reminder", approve=True, reminder={"before": ["two_hours"], "morning_at": "08:00"})
        self.evs(r, NOON + 7200 - 300); a.tick(); self.assertIn("coming up soon today", r.mock.calls("Messages.json")[0]["form"]["Body"]); r.close()

    def test_the_morning_of_reminder_and_its_edge(self):
        morning = dt.datetime(2026, 10, 12, 12, 30, tzinfo=dt.timezone.utc).timestamp()             # 08:30 in New York
        r = rig_for("beauty", now=morning); a = r.agent; wfedit.save(a, "smart_reminder", approve=True, reminder={"before": ["morning_of"], "morning_at": "08:00"})
        self.evs(r, morning + 3 * 3600); a.tick(); self.assertIn("Good morning", r.mock.calls("Messages.json")[0]["form"]["Body"]); r.close()
        r = rig_for("beauty", now=morning); a = r.agent; wfedit.save(a, "smart_reminder", approve=True, reminder={"before": ["morning_of"], "morning_at": "08:00"})
        self.evs(r, morning - 1800); self.assertEqual(self.rem(a), []); r.close()                       # it already started: never reminded after the start
        r = rig_for("beauty", now=morning); a = r.agent; wfedit.save(a, "smart_reminder", approve=True, reminder={"before": ["morning_of"], "morning_at": "08:00"})
        self.evs(r, morning + 600); self.assertEqual(self.rem(a), []); r.close()                        # too close to the start for a morning line

    def test_other_calendar_entries_are_not_reminded_and_unapproved_never_runs(self):
        r = rig_for("beauty"); a = r.agent; self.evs(r, NOON + 86400 - 600, "Closed for stock take"); self.assertEqual(self.rem(a), [])
        wfedit.save(a, "smart_reminder", approve=True); self.assertEqual(self.rem(a), []); self.assertEqual(r.mock.calls("Messages.json"), []); r.close()

    def test_reminder_choices_are_validated(self):
        r = rig_for("beauty")
        with self.assertRaises(wfedit.EditError): wfedit.save(r.agent, "smart_reminder", reminder={"before": []})
        with self.assertRaises(wfedit.EditError): wfedit.save(r.agent, "smart_reminder", reminder={"before": ["day_before"], "morning_at": "23:00"})
        d = wfedit.detail(r.agent, "smart_reminder"); self.assertEqual(d["timing"]["kind"], "reminder"); self.assertEqual([c["key"] for c in d["timing"]["choices"] if c["on"]], kits.REMINDER_DEFAULT); r.close()

    def test_the_right_wording_is_used_per_industry_booking_word(self):
        self.assertIn("reservation", SL.registry("food")["appointment_reminder_morning"]["example"])
        self.assertIn("visit", SL.registry("trades")["appointment_reminder_early"]["example"])


class AfterHours(unittest.TestCase):
    def test_it_stays_quiet_until_opening_times_are_set(self):
        r = rig_for("beauty"); a = r.agent; wfedit.save(a, "after_hours", approve=True)
        self.assertEqual(a.handle_sms({"From": "+16465550101", "Body": "are you around"}), ""); self.assertIn("hours", wfedit.detail(a, "after_hours")["missing"])
        wfedit.save(a, "after_hours", hours_={"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "open": "09:00", "close": "17:00"})
        self.assertEqual(a.handle_sms({"From": "+16465550101", "Body": "are you around"}), "")        # noon: open
        r.now[0] = NOON + 8 * 3600                                                                      # 20:00: closed
        self.assertIn("closed right now", a.handle_sms({"From": "+16465550101", "Body": "are you around"})); r.close()

    def test_health_after_hours_always_names_emergency_services(self):
        self.assertIn("nine one one", SL.registry("clinic")["after_hours_reply"]["example"])


class ListAndApi(unittest.TestCase):
    def test_the_list_pages_by_ten(self):
        r = rig_for("food"); a = r.agent
        p0 = wfedit.page(a, 0, 10); p1 = wfedit.page(a, 10, 10)
        self.assertEqual(len(p0["items"]), 10); self.assertGreater(p0["total"], 20); self.assertEqual(p0["items"][0]["state"], "needs_approval")
        self.assertFalse({x["name"] for x in p0["items"]} & {x["name"] for x in p1["items"]})
        self.assertTrue(all(x["state"] == "needs_approval" for x in wfedit.page(a, 0, 50, "needs_approval")["items"]))
        r.close()

    def test_dashboard_routes(self):
        r = rig_for("clinic"); a = r.agent; from speakvora_pack_agent import dashboard as D
        tok = D.token(a); H = {"x-dashboard-token": tok}
        st, body, _, _ = D.handle(a, "GET", "/dash/api/workflows/page?offset=0&limit=10", H, b""); self.assertEqual(st, 200); self.assertEqual(len(json.loads(body)["items"]), 10)
        st, body, _, _ = D.handle(a, "GET", "/dash/api/workflows/detail?name=smart_reminder", H, b""); self.assertEqual(json.loads(body)["state"], "needs_approval")
        st, body, _, _ = D.handle(a, "POST", "/dash/api/workflows/edit", H, json.dumps({"name": "forms_reminder", "approve": True, "texts": {"0": "Big sale on forms!"}}).encode()); self.assertEqual(st, 400); self.assertIn("cannot use", json.loads(body)["message"])
        st, body, _, _ = D.handle(a, "POST", "/dash/api/workflows/edit", H, json.dumps({"name": "forms_reminder", "approve": True}).encode()); self.assertEqual(st, 200); self.assertEqual(json.loads(body)["state"], "on")
        st, body, _, _ = D.handle(a, "GET", "/dash/api/sales", H, b""); self.assertFalse(json.loads(body)["available"])
        st, body, _, _ = D.handle(a, "POST", "/dash/api/sales/sources", H, json.dumps({"urls": ["https://example.com/sale"]}).encode()); self.assertEqual(st, 400); r.close()

    def test_the_ui_page_script_is_well_formed(self):
        from speakvora_pack_agent import ui
        for needle in ("pagedWorkflows", "wfEditSheet", "saleSheet", "Needs your OK", "Show 10 more", "Approve and turn on"):
            self.assertIn(needle, ui.PAGE)
        self.assertEqual(ui.PAGE.count("</script>"), 1)


if __name__ == "__main__":
    unittest.main()
