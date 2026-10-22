import json, time, unittest
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


class Asking(unittest.TestCase):
    def call(self, a, path, body=None):
        h = {"x-dashboard-token": DB.token(a)}; code, raw, _c, _h = DB.handle(a, "POST" if body is not None else "GET", path, h, json.dumps(body or {}).encode()); return code, json.loads(raw)

    def test_every_step_that_reads_the_web_or_spends_something_asks_first(self):
        r = rig(); self.addCleanup(r.close); a = r.agent
        for path in ("/dash/api/scan/search", "/dash/api/scan/read", "/dash/api/scan/phrases", "/dash/api/scan/phrases/add"):
            code, out = self.call(a, path, {}); self.assertEqual(code, 400, path); self.assertIn("until you say OK", out["message"])
        self.assertEqual(self.call(a, "/dash/api/scan")[0], 200)


if __name__ == "__main__":
    unittest.main()
