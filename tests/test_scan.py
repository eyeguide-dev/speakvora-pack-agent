import json, os, time, unittest
from test_pack_agent import Rig
from speakvora_pack_agent import scan as SC, dashboard as DB, reasoner as R, knowledge as KN, brain

HOME = ('<html><head><title>Bella Trattoria</title></head><body><h1>Bella Trattoria</h1><p>Family Italian kitchen at 12 Main Street. Open Tuesday to Sunday 5 to 10 PM. Dogs welcome on the patio.</p>'
        '<a href="/menu">Menu</a><a href="/about">About</a><a href="/blog/x">Blog</a><a href="https://other.example/y">Other</a><a href="/photo.jpg">pic</a></body></html>')
MENU = '<html><head><title>Menu</title></head><body><h2>Pasta</h2><p>Spaghetti carbonara 18. Penne arrabbiata 16. Gnocchi 19.</p><h2>Desserts</h2><p>Tiramisu 9</p></body></html>'
ABOUT = '<html><head><title>About</title></head><body><p>We hold a reservation for fifteen minutes. We do not take bookings for parties over eight.</p></body></html>'
PAGES = {"https://bella.example/": HOME, "https://bella.example/menu": MENU, "https://bella.example/about": ABOUT, "https://bella.example/blog/x": "<html><body><p>" + "blog " * 40 + "</p></body></html>"}
AI = {"business": {"name": "Bella Trattoria", "address": "12 Main Street", "hours": "Tuesday to Sunday, 5 to 10 PM"}, "summary": "A family Italian kitchen. Dogs are welcome on the patio.", "tone": "warm",
      "categories": [{"name": "Pasta", "items": [{"name": "Spaghetti carbonara", "price": "18"}, {"name": "Penne arrabbiata", "price": "16"}]}, {"name": "Desserts", "items": [{"name": "Tiramisu", "price": "9"}]}],
      "policies": ["We hold a reservation for fifteen minutes."], "faqs": [{"q": "Are dogs allowed?", "a": "Yes, on the patio."}], "unknowns": []}


def fetch(url, **k):
    if url.endswith("/robots.txt") or url.endswith("sitemap.xml") or url.endswith("sitemap_index.xml"):
        raise OSError("none")
    if url in PAGES:
        return PAGES[url].encode(), "text/html"
    raise OSError("404")


def rig(**kw):
    return Rig(extra={"reasoner": {"provider": "anthropic", "api_key": "k", "model": "m"}, "business": "Bella Trattoria", "facts": {"address": "12 Main Street"}, **kw})


class Steps(unittest.TestCase):
    def setUp(self):
        self.old = (SC._get, R._chat, SC.web_search); SC._get = lambda url, data=None, **k: fetch(url)
        self.addCleanup(lambda: (setattr(SC, "_get", self.old[0]), setattr(R, "_chat", self.old[1]), setattr(SC, "web_search", self.old[2])))

    def test_it_lists_what_it_already_knows_without_any_network(self):
        r = rig(); self.addCleanup(r.close)
        SC._get = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network yet"))
        labels = [x["label"] for x in SC.view(r.agent)["known"]]; self.assertIn("Business name", labels); self.assertIn("Address", labels)

    def test_it_finds_the_website_ranks_own_sites_first_and_hides_nothing(self):
        r = rig(); self.addCleanup(r.close)
        SC.web_search = lambda q: [{"url": "https://www.yelp.com/biz/bella", "title": "Bella - Yelp", "snippet": ""}, {"url": "https://bella.example/menu", "title": "Bella Trattoria", "snippet": "Italian"}, {"url": "https://bella.example/about", "title": "About", "snippet": ""}]
        d = SC.search(r.agent); c = d["candidates"]
        self.assertEqual(c[0]["url"], "https://bella.example/"); self.assertFalse(c[0]["listing"]); self.assertTrue(c[-1]["listing"]); self.assertEqual(len([x for x in c if x["host"] == "bella.example"]), 1)

    def test_a_search_that_fails_says_so_and_lets_the_owner_type_the_address(self):
        r = rig(); self.addCleanup(r.close)
        def boom(q): raise OSError("offline")
        SC.web_search = boom; d = SC.search(r.agent); self.assertIn("type your website", d["error"])
        self.assertEqual(SC.set_site(r.agent, "bella.example")["site"], "https://bella.example")
        with self.assertRaises(ValueError): SC.set_site(r.agent, "not a site")

    def test_the_crawl_stays_on_the_site_skips_images_and_obeys_robots(self):
        r = rig(); self.addCleanup(r.close)
        pages = SC.crawl(r.agent, "https://bella.example/", 10, fetch=fetch, delay=0); urls = [p["url"] for p in pages]
        self.assertIn("https://bella.example/menu", urls); self.assertNotIn("https://other.example/y", urls); self.assertFalse([u for u in urls if u.endswith(".jpg")])
        import urllib.robotparser
        orig = SC._robots; SC._robots = lambda base: (lambda rp: (rp.parse(["User-agent: *", "Disallow: /menu"]), rp)[1])(urllib.robotparser.RobotFileParser()); self.addCleanup(lambda: setattr(SC, "_robots", orig))
        self.assertNotIn("https://bella.example/menu", [p["url"] for p in SC.crawl(r.agent, "https://bella.example/", 10, fetch=fetch, delay=0)])

    def test_nothing_is_changed_until_the_owner_approves_then_only_what_they_ticked(self):
        r = rig(); self.addCleanup(r.close); a = r.agent
        R._chat = lambda cfg, system, user, mt=None: (json.dumps(AI), {})
        SC.set_site(a, "https://bella.example/"); SC._run(a, "https://bella.example/", 10, fetch, 0)
        d = SC.load(a); self.assertEqual(d["step"], "review"); self.assertEqual(brain.load(a)["status"], "none"); self.assertEqual([s for s in KN._idx(a)["sources"]], [])
        keys = {s["key"]: s for s in d["fact_suggestions"]}; self.assertIn("hours", keys); self.assertFalse(keys["address"]["differs"])
        SC.apply(a, facts=["hours"], profile=True, menu=True)
        self.assertEqual(brain.load(a)["status"], "approved"); self.assertIn("Spaghetti carbonara", KN.text_all(a)); self.assertIn("5 to 10", str(a.cfg["facts"]["hours"]))
        self.assertEqual(SC.load(a)["step"], "approved")

    def test_private_details_are_removed_before_anything_goes_to_the_ai(self):
        r = rig(); self.addCleanup(r.close); a = r.agent; seen = []
        R._chat = lambda cfg, system, user, mt=None: (seen.append(user) or json.dumps(AI), {})
        SC.extract(a, [{"url": "https://bella.example/c", "title": "c", "text": "Call us on 646-555-0101 or email ann@bella.example. Tiramisu 9."}])
        self.assertFalse([u for u in seen if "ann@bella.example" in u or "646-555-0101" in u])

    def test_phrase_ideas_wait_for_the_owner_and_never_include_links_or_emails(self):
        r = rig(); self.addCleanup(r.close); a = r.agent
        R._chat = lambda cfg, system, user, mt=None: (json.dumps(AI if "organise" in system else {"lines": ["Welcome to Bella Trattoria, how can I help you today?", "Email us at ann@bella.example anytime.", "Dogs are welcome on our heated patio."]}), {})
        SC.set_site(a, "https://bella.example/"); SC._run(a, "https://bella.example/", 10, fetch, 0); SC.apply(a, facts=[], profile=True, menu=True)
        d = SC.suggest_phrases(a); self.assertEqual(d["phrases"], ["Welcome to Bella Trattoria, how can I help you today?", "Dogs are welcome on our heated patio."])

    def test_thinking_ahead_prepares_ideas_from_what_is_known_without_recording_and_rejects_invented_prices(self):
        r = rig(); self.addCleanup(r.close); a = r.agent
        a.cfg["facts"] = {"hours": "Open 11am to 10pm every day", "info": "Lunch is 20 dollars. Dinner is 35 dollars."}
        R._chat = lambda cfg, system, user, mt=None: (json.dumps({"questions": ["What time do you open?"], "lines": ["We are open 11am to 10pm every day of the week.", "Our pasta special is only 9.99 dollars today.", "Dinner is 20 dollars per person here.", "One moment while I check that for you."]}), {})
        d = SC.anticipate(a)
        self.assertEqual(d["phrases"], ["We are open 11am to 10pm every day of the week.", "One moment while I check that for you."])
        self.assertTrue(d["auto_ready"]); self.assertEqual(d["anticipated"]["questions"], ["What time do you open?"]); self.assertFalse(d.get("voiced"))


class Wording(unittest.TestCase):
    def test_recording_text_never_says_the_free_allowance_pays_for_new_lines(self):
        from speakvora_pack_agent import ui
        self.assertNotIn("free allowance first", ui.JS); self.assertIn("do not renew", ui.JS)
        guide = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "speakvora_pack_agent", "data", "guides", "ai.md"), encoding="utf-8").read()
        self.assertNotIn("free allowance first", guide); self.assertIn("do not renew", guide)


class Confirming(unittest.TestCase):
    def test_the_owner_checks_what_the_ai_says_and_a_wrong_answer_is_fixed_in_their_words(self):
        r = rig(); self.addCleanup(r.close); a = r.agent
        old = (SC._get, R._chat); self.addCleanup(lambda: (setattr(SC, "_get", old[0]), setattr(R, "_chat", old[1])))
        SC._get = lambda url, data=None, **k: fetch(url); R._chat = lambda cfg, system, user, mt=None: (json.dumps(AI), {})
        SC.set_site(a, "https://bella.example/"); SC._run(a, "https://bella.example/", 10, fetch, 0); SC.apply(a, facts=[], profile=True, menu=True)
        d = SC.make_checks(a); qs = [c["q"] for c in d["checks"]]
        self.assertIn("What are your hours?", qs); self.assertTrue([q for q in qs if q.startswith("How much is the")]); self.assertIn("Are dogs allowed?", qs)
        R._chat = lambda cfg, system, user, mt=None: (json.dumps({"say": "We are open every day until midnight.", "action": "continue", "do": []}), {})
        d = SC.check_ask(a, 0); self.assertEqual(d["checks"][0]["status"], "asked"); self.assertIn("midnight", d["checks"][0]["answer"])
        with self.assertRaises(ValueError): SC.check_mark(a, 0, False, "")
        d = SC.check_mark(a, 0, False, "We are open Tuesday to Sunday, 5 to 10 PM."); self.assertEqual(d["checks"][0]["status"], "fixed")
        self.assertEqual(KN.qa_match(a, "What are your hours?")[0], "We are open Tuesday to Sunday, 5 to 10 PM.")
        self.assertEqual(SC.check_mark(a, 1, True)["checks"][1]["status"], "right")


class EveryDay(unittest.TestCase):
    def setUp(self):
        self.old = (SC._get, R._chat); SC._get = lambda url, data=None, **k: fetch(url)
        self.addCleanup(lambda: (setattr(SC, "_get", self.old[0]), setattr(R, "_chat", self.old[1])))

    def approved(self, **kw):
        r = rig(**kw); self.addCleanup(r.close); a = r.agent
        R._chat = lambda cfg, system, user, mt=None: (json.dumps(AI), {})
        SC.set_site(a, "https://bella.example/"); SC._run(a, "https://bella.example/", 10, fetch, 0); SC.apply(a, facts=[], profile=True, menu=True, daily=True)
        return a

    def test_the_diff_finds_price_new_removed_and_hours_changes(self):
        new = json.loads(json.dumps(AI)); new["categories"][0]["items"][0]["price"] = "20"; new["categories"][0]["items"].append({"name": "Lasagna", "price": "21"}); new["categories"][0]["items"].pop(1); new["business"]["hours"] = "Monday to Sunday, 5 to 11 PM"
        kinds = {(c["kind"], c.get("item")) for c in SC.diff(AI, new)}
        self.assertEqual(kinds, {("price", "Spaghetti carbonara"), ("new", "Lasagna"), ("removed", "Penne arrabbiata"), ("hours", None)}); self.assertEqual(SC.diff(AI, AI), [])

    def test_it_checks_once_a_day_only_if_switched_on_and_changes_wait_for_the_owner(self):
        a = self.approved(); changed = json.loads(json.dumps(AI)); changed["categories"][0]["items"][0]["price"] = "20"
        d = SC.load(a); d["daily"]["last"] = time.time() - 90000; SC.save(a, d)
        R._chat = lambda cfg, system, user, mt=None: (json.dumps(changed), {})
        SC.daily_run(a, fetch); d = SC.load(a)
        self.assertEqual(d["updates"]["changes"][0]["kind"], "price"); self.assertIn("18", KN.text_all(a)); self.assertNotIn("carbonara, 20", KN.text_all(a))          # found, but nothing changed yet
        d = SC.load(a); d["daily"]["last"] = time.time(); SC.save(a, d); self.assertFalse(SC.daily_tick(a))                      # just checked: not again today
        SC.set_daily(a, False); d = SC.load(a); d["daily"]["last"] = 0; SC.save(a, d); self.assertFalse(SC.daily_tick(a))             # switched off: never

    def test_saying_yes_updates_the_price_list_and_lists_the_old_price_lines_to_remove(self):
        a = self.approved(); changed = json.loads(json.dumps(AI)); changed["categories"][0]["items"][0]["price"] = "20"
        d = SC.load(a); d["voiced"] = [{"text": "Our spaghetti carbonara is 18 dollars.", "at": 1}, {"text": "Dogs are welcome on the patio.", "at": 1}]; SC.save(a, d)
        from speakvora_pack_agent import learned
        ld = learned.load(a); ld["items"].append({"id": "learned:abc", "text": "Our spaghetti carbonara is 18 dollars.", "file": "/nonexistent", "added": 1, "auto": False, "source": "typed"}); learned.save(a, ld)
        d = SC.load(a); d["updates"] = {"found": 1, "changes": SC.diff(AI, changed), "extracted": changed, "text": "", "fact_suggestions": []}; SC.save(a, d)
        R._chat = lambda cfg, system, user, mt=None: (json.dumps({"lines": ["Our spaghetti carbonara is 20 dollars."]}), {})
        d = SC.apply_updates(a); self.assertIn("carbonara, 20", KN.text_all(a)); self.assertEqual([x["text"] for x in d["stale"]], ["Our spaghetti carbonara is 18 dollars."]); self.assertIsNone(d["updates"])
        d = SC.remove_stale(a, ["learned:abc"]); self.assertEqual(d["stale"], []); self.assertFalse([i for i in learned.load(a)["items"] if i["id"] == "learned:abc"])

    def test_phrases_are_made_from_the_businesss_own_products_and_an_invented_price_is_dropped(self):
        a = self.approved()
        R._chat = lambda cfg, system, user, mt=None: (json.dumps({"lines": ["Our spaghetti carbonara is 18 dollars and made fresh.", "Our tiramisu is 99 dollars tonight only.", "We are open Tuesday to Sunday from 5 to 10 PM."]}), {})
        d = SC.suggest_phrases(a); self.assertEqual(d["phrases"], ["Our spaghetti carbonara is 18 dollars and made fresh.", "We are open Tuesday to Sunday from 5 to 10 PM."]); self.assertGreater(d["phrase_cost_usd"], 0)


class Asking(unittest.TestCase):
    def call(self, a, path, body=None):
        h = {"x-dashboard-token": DB.token(a)}; code, raw, _c, _h = DB.handle(a, "POST" if body is not None else "GET", path, h, json.dumps(body or {}).encode()); return code, json.loads(raw)

    def test_every_step_that_reads_the_web_or_spends_something_asks_first(self):
        r = rig(); self.addCleanup(r.close); a = r.agent
        for path in ("/dash/api/scan/search", "/dash/api/scan/read", "/dash/api/scan/phrases", "/dash/api/scan/phrases/add", "/dash/api/scan/check/ask"):
            code, out = self.call(a, path, {}); self.assertEqual(code, 400, path); self.assertIn("until you say OK", out["message"])
        self.assertEqual(self.call(a, "/dash/api/scan")[0], 200)


if __name__ == "__main__":
    unittest.main()
