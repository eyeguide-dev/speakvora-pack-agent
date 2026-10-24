"""Announce a sale: only shops, a draft from a page change, nothing sent without approval, only people on the consent list, STOP, sending hours, limits, a test to the owner and a rehearsal in Practice mode."""
import json, os, re, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_pack_agent import Rig, NOON
from test_kits import rig_for
from speakvora_pack_agent import config, recipes, sales, wfedit
from speakvora_pack_agent.engine import Agent

PAGE1 = "<html><body><h1>Maple Street Shoes</h1><p>New boots arrive in November.</p><p>Shop our full range of boots and sandals.</p></body></html>"
PAGE2 = "<html><body><h1>Maple Street Shoes</h1><p>New boots arrive in November.</p><p>Fall Sale: 25% off all boots until Sunday.</p></body></html>"


def shop(profile="retail", dry=False, **kw):
    r = rig_for(profile, dry=dry, **kw); a = r.agent
    a.cfg["business"] = "Maple Street Shoes"
    return r, a


def fill_consent(a, n=3, prefix="646555020"):
    for i in range(n):
        sales.add_consent(a, f"{prefix}{i}", "counter sign-up sheet", int(a.now()) - 86400, f"P{i}")


def make_draft(a, text=None):
    f = {"v": PAGE1}
    sales.set_sources(a, ["https://mapleshoes.example/sale"])
    sales.watch(a, fetch=lambda u: (PAGE1, "text/html")); f["v"] = PAGE2
    res = sales.watch(a, fetch=lambda u: (PAGE2, "text/html"))
    return res["draft"]


class Who(unittest.TestCase):
    def test_only_shops_get_it(self):
        for p in ("clinic", "pharmacy", "dispensary", "legal", "finance", "public", "education", "corrections", "collections", "lodging", "trades", "support"):
            r = rig_for(p); a = r.agent
            self.assertFalse(sales.view(a)["available"], p)
            with self.assertRaises(sales.SaleError): sales.add_consent(a, "6465550200", "web form", None)
            with self.assertRaises(sales.SaleError): sales.set_sources(a, ["https://example.com/sale"])
            self.assertEqual(sales.watch(a)["status"], "not_available"); self.assertEqual(sales.inbound(a, "+16465550200", "deals"), "")
            self.assertFalse(any(w.get("sale") for w in a.workflows)); r.close()
        for p in ("retail", "food", "beauty", "laundry", "auto"):
            r = rig_for(p); self.assertTrue(sales.view(r.agent)["available"], p); r.close()

    def test_the_sale_workflow_is_off_until_pages_are_listed(self):
        r, a = shop(); self.assertNotIn("announce_a_sale", [w["name"] for w in a.workflows])
        with self.assertRaises(sales.SaleError): sales.enable(a, True)
        sales.set_sources(a, ["https://mapleshoes.example/sale"]); v = sales.enable(a, True); self.assertTrue(v["on"]); self.assertIn("announce_a_sale", [w["name"] for w in a.workflows])
        self.assertFalse(sales.enable(a, False)["on"]); r.close()


class Consent(unittest.TestCase):
    def test_a_person_needs_a_source_and_a_real_time(self):
        r, a = shop()
        with self.assertRaises(sales.SaleError): sales.add_consent(a, "6465550200", "", None)
        with self.assertRaises(sales.SaleError): sales.add_consent(a, "12", "web form", None)
        with self.assertRaises(sales.SaleError): sales.add_consent(a, "6465550200", "web form", int(a.now()) + 10 * 86400)
        sales.add_consent(a, "6465550200", "web form on our site", None, "Ann"); self.assertEqual(sales.view(a)["consent_count"], 1)
        c = sales.view(a)["consent"][0]; self.assertEqual(c["source"], "web form on our site"); self.assertTrue(c["at"]); r.close()

    def test_csv_import_refuses_rows_without_a_source_or_date(self):
        r, a = shop()
        out = sales.import_csv(a, "phone,source,date,name\n6465550201,sign-up sheet,2026-09-01,Ann\n6465550202,,2026-09-01,Bob\n6465550203,web form,,Cy\n6465550204,web form,2026-09-02,Di\n")
        self.assertEqual(out["added"], 2); self.assertEqual(out["refused_count"], 2); r.close()

    def test_stop_removes_a_person_for_good_and_only_deals_brings_them_back(self):
        r, a = shop(); fill_consent(a, 2); who = "+16465550200"
        self.assertIn("unsubscribed", a.handle_sms({"From": who, "Body": "STOP"}))
        self.assertEqual(sales.view(a)["consent_count"], 1)
        with self.assertRaises(sales.SaleError): sales.add_consent(a, who, "web form", None)
        a.handle_sms({"From": who, "Body": "START"}); self.assertEqual(sales.view(a)["consent_count"], 1)          # START alone does not restore sale texts
        out = a.handle_sms({"From": who, "Body": "DEALS"}); self.assertIn("signed up", out); self.assertEqual(sales.view(a)["consent_count"], 2)
        c = next(x for x in sales.view(a)["consent"] if x["full"] == who); self.assertIn("texted DEALS", c["source"]); r.close()


class Drafts(unittest.TestCase):
    def test_a_new_sale_becomes_a_draft_and_nothing_is_sent(self):
        r, a = shop(); fill_consent(a); sales.set_sources(a, ["https://mapleshoes.example/sale"])
        self.assertEqual(sales.watch(a, fetch=lambda u: (PAGE1, "text/html"))["status"], "nothing_new")                         # the first look only learns what is there
        self.assertEqual(sales.watch(a, fetch=lambda u: (PAGE1, "text/html"))["status"], "nothing_new")
        res = sales.watch(a, fetch=lambda u: (PAGE2, "text/html")); self.assertEqual(res["status"], "draft")
        x = next(d for d in sales.view(a)["drafts"] if d["id"] == res["draft"])
        self.assertIn("25% off", x["text"]); self.assertIn("https://mapleshoes.example/sale", x["text"])
        self.assertEqual(r.mock.calls("Messages.json"), []); a.tick(); self.assertEqual(r.mock.calls("Messages.json"), []); r.close()

    def test_the_same_sale_is_not_drafted_twice(self):
        r, a = shop(); sales.set_sources(a, ["https://mapleshoes.example/sale"])
        sales.watch(a, fetch=lambda u: (PAGE1, "text/html")); self.assertEqual(sales.watch(a, fetch=lambda u: (PAGE2, "text/html"))["status"], "draft")
        self.assertEqual(sales.watch(a, fetch=lambda u: (PAGE2, "text/html"))["status"], "nothing_new"); r.close()

    def test_a_broken_page_is_reported_and_drafts_nothing(self):
        r, a = shop(); sales.set_sources(a, ["https://mapleshoes.example/sale"])
        def boom(u): raise OSError("down")
        res = sales.watch(a, fetch=boom); self.assertEqual(res["status"], "errors"); self.assertEqual(sales.view(a)["drafts"], []); r.close()

    def test_a_product_list_with_prices_drafts_only_real_prices(self):
        r, a = shop(); sales.set_sources(a, [], "https://mapleshoes.example/feed.json")
        feed1 = json.dumps([{"name": "Trail boot", "price": 120}]); feed2 = json.dumps([{"name": "Trail boot", "price": 120, "sale_price": 90}, {"name": "Sandal", "price": 40}])
        sales.watch(a, fetch=lambda u: (feed1, "application/json")); res = sales.watch(a, fetch=lambda u: (feed2, "application/json")); self.assertEqual(res["status"], "draft")
        t = sales.view(a)["drafts"][0]["text"]; self.assertIn("Trail boot now $90, was $120", t); self.assertNotIn("Sandal", t); r.close()

    def test_addresses_must_be_public_websites(self):
        r, a = shop()
        for bad in ("http://localhost/x", "http://192.168.1.5/x", "file:///etc/passwd", "ftp://x.test/a", "http://printer.local/a"):
            with self.assertRaises(sales.SaleError): sales.set_sources(a, [bad])
        with self.assertRaises(sales.SaleError): sales.set_sources(a, ["https://a.example/%d" % i for i in range(9)]); r.close()

    def test_text_rules(self):
        r, a = shop(); fill_consent(a); did = make_draft(a)
        with self.assertRaises(sales.SaleError): sales.edit_draft(a, did, "x" * 400)
        with self.assertRaises(sales.SaleError): sales.edit_draft(a, did, "Call about card 4111 1111 1111 1111")
        with self.assertRaises(sales.SaleError): sales.edit_draft(a, did, "Hello {{customer.name}}")
        sales.edit_draft(a, did, "Fall sale this weekend: 25% off boots."); self.assertIn("25% off boots", sales.view(a)["drafts"][0]["text"]); r.close()


class Sending(unittest.TestCase):
    def test_approve_sends_only_to_people_on_the_list_and_never_after_stop(self):
        r, a = shop(); fill_consent(a, 4); a.state.opt_out("+16465550202"); did = make_draft(a)
        pv = sales.preview(a, did); self.assertEqual(pv["will_send_to"], 3); self.assertEqual(pv["left_out"]["replied_stop"], 1); self.assertIn("Reply STOP", pv["message"]); self.assertTrue(pv["message"].startswith("Maple Street Shoes:"))
        out = sales.approve(a, did); self.assertEqual(out["status"], "sent")
        sent = r.mock.calls("Messages.json"); self.assertEqual(sorted(s["form"]["To"] for s in sent), ["+16465550200", "+16465550201", "+16465550203"])
        self.assertTrue(all("Reply STOP to opt out" in s["form"]["Body"] and "25% off" in s["form"]["Body"] for s in sent))
        self.assertEqual(sales.view(a)["drafts"][0]["status"], "sent"); r.close()

    def test_practice_mode_rehearses_and_sends_nothing(self):
        r, a = shop(dry=True); fill_consent(a, 3); did = make_draft(a); out = sales.approve(a, did)
        self.assertEqual(out["status"], "practiced"); self.assertEqual(r.mock.calls("Messages.json"), [])
        self.assertTrue(any(x.get("status") == "dry_run" for x in r.log())); d = sales.view(a)["drafts"][0]; self.assertEqual(d["status"], "draft"); self.assertTrue(d["practiced"])
        self.assertEqual(sales.view(a)["history"][0]["practice"], True); r.close()

    def test_an_empty_consent_list_cannot_be_approved(self):
        r, a = shop(); did = make_draft(a)
        with self.assertRaises(sales.SaleError): sales.approve(a, did)
        self.assertEqual(r.mock.calls("Messages.json"), []); r.close()

    def test_a_declined_or_unapproved_draft_is_never_sent(self):
        r, a = shop(); fill_consent(a); did = make_draft(a); a.tick(); a.tick(); self.assertEqual(r.mock.calls("Messages.json"), [])
        sales.decline(a, did)
        with self.assertRaises(sales.SaleError): sales.approve(a, did)
        self.assertEqual(r.mock.calls("Messages.json"), []); r.close()

    def test_outside_sending_hours_it_waits_and_sends_in_the_morning(self):
        r, a = shop(); fill_consent(a, 2); did = make_draft(a); r.now[0] = NOON + 9 * 3600 + 1800          # 21:30 in New York
        out = sales.approve(a, did); self.assertEqual(out["status"], "waiting"); a.tick(); self.assertEqual(r.mock.calls("Messages.json"), [])
        r.now[0] = NOON + 22 * 3600                                                                          # 10:00 next morning
        a.tick(); self.assertEqual(len(r.mock.calls("Messages.json")), 2); self.assertEqual(sales.view(a)["history"][0]["status"], "sent"); r.close()

    def test_batches_and_the_hourly_limit(self):
        r = Rig(extra={"industry_profile": "retail", "limits": {"per_hour": 3, "per_recipient_per_day": 5}, "quiet_hours": {"start": "00:00", "end": "00:00", "applies_to": []}})           # the team notice about the draft counts as one of the three
        json.dump(recipes.workflows_for("retail"), open(os.path.join(r.tmp, "workflows.json"), "w")); a = Agent(config.load(os.path.join(r.tmp, "agent.json")), now=lambda: r.now[0]); r.agent = a; a.cfg["business"] = "Maple Street Shoes"
        fill_consent(a, 5); did = make_draft(a); sales.approve(a, did)
        self.assertEqual(len(r.mock.calls("Messages.json")), 2); self.assertEqual(sales.view(a)["sending"][0]["pending"], 3)           # the hourly limit holds the rest, nobody is skipped
        r.now[0] += 3700; a.tick(); self.assertEqual(len(r.mock.calls("Messages.json")), 5); self.assertEqual(sales.view(a)["history"][0]["status"], "sent")
        self.assertEqual(sorted(s["form"]["To"] for s in r.mock.calls("Messages.json")), ["+1646555020%d" % i for i in range(5)]); r.close()          # everyone got exactly one, nobody was skipped by the limit

    def test_most_sale_texts_per_person_per_month(self):
        r, a = shop(); fill_consent(a, 2); sales.set_sources(a, ["https://mapleshoes.example/sale"], settings={"max_per_month": 1})
        did = make_draft(a); sales.approve(a, did); self.assertEqual(len(r.mock.calls("Messages.json")), 2)
        d2 = sales.watch(a, fetch=lambda u: (PAGE2 + "<p>Weekend Clearance: sandals half price.</p>", "text/html"))["draft"]
        self.assertEqual(sales.preview(a, d2)["will_send_to"], 0); self.assertEqual(sales.preview(a, d2)["left_out"]["sent_too_many_this_month"], 2); r.close()

    def test_a_changed_text_after_approval_stops_the_run(self):
        r, a = shop(); fill_consent(a, 2); did = make_draft(a); r.now[0] = NOON + 9 * 3600 + 1800
        sales.approve(a, did); d = sales.load(a); d["drafts"][did]["text"] = "Everything free for everyone"; sales._save(a, d)
        r.now[0] = NOON + 22 * 3600; a.tick(); self.assertEqual(r.mock.calls("Messages.json"), []); self.assertEqual(sales.view(a)["drafts"][0]["status"], "draft"); r.close()

    def test_someone_who_says_stop_after_approval_is_not_texted(self):
        r, a = shop(); fill_consent(a, 3); did = make_draft(a); r.now[0] = NOON + 9 * 3600 + 1800
        sales.approve(a, did); a.handle_sms({"From": "+16465550201", "Body": "STOP"}); r.now[0] = NOON + 22 * 3600; a.tick()
        self.assertEqual(sorted(s["form"]["To"] for s in r.mock.calls("Messages.json")), ["+16465550200", "+16465550202"]); r.close()

    def test_a_test_needs_the_owners_own_number(self):
        r, a = shop(); fill_consent(a, 2); did = make_draft(a); a.cfg["facts"]["oncall_phone"] = ""
        with self.assertRaises(sales.SaleError): sales.test_send(a, did)
        self.assertEqual(r.mock.calls("Messages.json"), []); r.close()

    def test_owner_test_with_a_number(self):
        r, a = shop(); fill_consent(a, 2); did = make_draft(a); sales.set_sources(a, ["https://mapleshoes.example/sale"], settings={"owner_phone": "+16465559999"})
        t = sales.test_send(a, did); self.assertEqual(t["status"], "sent")
        sent = r.mock.calls("Messages.json"); self.assertEqual([s["form"]["To"] for s in sent], ["+16465559999"]); self.assertTrue(sent[0]["form"]["Body"].startswith("[TEST]"))
        for _ in range(4): sales.test_send(a, did)
        with self.assertRaises(sales.SaleError): sales.test_send(a, did); r.close()

    def test_workflow_runs_the_watch_on_its_schedule(self):
        r, a = shop(); sales.set_sources(a, ["https://mapleshoes.example/sale"]); sales.enable(a, True)
        pages = {"v": PAGE1}; orig = sales._fetch; sales._fetch = lambda u: (pages["v"], "text/html")
        try:
            a.tick(); pages["v"] = PAGE2; r.now[0] += 86400; a.tick()
        finally:
            sales._fetch = orig
        self.assertEqual(len(sales.view(a)["drafts"]), 1); self.assertEqual(r.mock.calls("Messages.json"), []); r.close()


class Honest(unittest.TestCase):
    def test_the_consent_note_is_honest_and_makes_no_legal_claims(self):
        n = sales.CONSENT_NOTE.lower()
        self.assertIn("not legal advice", n); self.assertIn("prior written agreement", n)
        for bad in ("compliant", "guarantee", "certified", "fully legal"):
            self.assertNotIn(bad, n)


if __name__ == "__main__":
    unittest.main()
