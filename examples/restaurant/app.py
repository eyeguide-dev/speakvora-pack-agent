"""A tiny stand-in restaurant app (orders, a kitchen screen, reservations) used to show the pack agent. Its only link to the agent is agent_hook.notify(...)."""
import json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

try:
    from agent_hook import notify
except ImportError:                                  # the app works without the agent
    def notify(*a, **k):
        pass

ORDERS, RESERVATIONS = {}, {}


def page(title, body):
    return f"<!doctype html><meta charset=utf-8><title>{title}</title><body style='font:16px system-ui;max-width:640px;margin:30px auto'><h1>Bella Trattoria</h1>{body}".encode()


class App(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="text/html"):
        if isinstance(body, (dict, list)):
            body, ctype = json.dumps(body).encode(), "application/json"
        self.send_response(code); self.send_header("content-type", ctype); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def form(self):
        raw = self.rfile.read(int(self.headers.get("content-length") or 0)).decode()
        return json.loads(raw) if raw.startswith("{") else {k: v[0] for k, v in parse_qs(raw).items()}

    def do_GET(self):
        if self.path == "/kitchen":
            rows = "".join(f"<li>#{n} {o['name']} {o['status']} <form method=post action=/orders/{n}/ready style=display:inline><button>Ready</button></form> <form method=post action=/orders/{n}/delayed style=display:inline><button>Delayed 10 min</button></form> <form method=post action=/orders/{n}/done style=display:inline><button>Picked up</button></form></li>" for n, o in ORDERS.items())
            return self.send(200, page("Kitchen", f"<h2>Kitchen</h2><ul>{rows}</ul>"))
        if self.path == "/host":
            rows = "".join(f"<li>{r['name']} party of {r['party']} {r['when']} {r['status']} <form method=post action=/reservations/{n}/table style=display:inline><button>Table ready</button></form> <form method=post action=/reservations/{n}/noshow style=display:inline><button>No-show</button></form></li>" for n, r in RESERVATIONS.items())
            return self.send(200, page("Host", f"<h2>Host stand</h2><ul>{rows}</ul>"))
        self.send(200, page("Order", "<h2>Order for pickup</h2><form method=post action=/orders>Name <input name=name><br>Phone <input name=phone><br><label><input type=checkbox name=sms_consent value=1> Text me updates about my order (msg &amp; data rates may apply, reply STOP to opt out)</label><br>Item <input name=item value=Margherita><br><button>Order</button></form><p><a href=/kitchen>Kitchen</a> · <a href=/host>Host</a></p>"))

    def do_POST(self):
        f, p = self.form(), self.path.strip("/").split("/")
        cust = lambda d: {"name": d.get("name", ""), "phone": d.get("phone", ""), "sms_consent": str(d.get("sms_consent", "")).lower() in ("1", "true", "yes", "on")}  # noqa: E731
        if p == ["orders"]:
            n = len(ORDERS) + 41; ORDERS[n] = {"name": f.get("name", ""), "phone": f.get("phone", ""), "consent": cust(f)["sms_consent"], "item": f.get("item", ""), "status": "received"}
            return self.send(201, {"order": n})
        if p[0] == "orders" and len(p) == 3 and int(p[1]) in ORDERS:
            o, n = ORDERS[int(p[1])], int(p[1]); c = {"name": o["name"], "phone": o["phone"], "sms_consent": o["consent"]}
            o["status"] = {"ready": "ready", "delayed": "delayed", "done": "picked up"}[p[2]]
            notify({"ready": "order.ready", "delayed": "order.delayed", "done": "visit.completed"}[p[2]], customer=c, order={"number": n, "extra_minutes": 10})
            return self.send(200, {"order": n, "status": o["status"]})
        if p == ["reservations"]:
            n = len(RESERVATIONS) + 1; start = int(f.get("start_epoch") or time.time() + 86400)
            RESERVATIONS[n] = {"name": f.get("name", ""), "phone": f.get("phone", ""), "consent": cust(f)["sms_consent"], "party": f.get("party", "2"), "when": time.strftime("%a %b %d %I:%M %p", time.localtime(start)), "status": "booked"}
            notify("reservation.created", customer=cust(f), party=f.get("party", "2"), start_epoch=start, start_text=RESERVATIONS[n]["when"])
            return self.send(201, {"reservation": n})
        if p[0] == "reservations" and len(p) == 3 and int(p[1]) in RESERVATIONS:
            r = RESERVATIONS[int(p[1])]; c = {"name": r["name"], "phone": r["phone"], "sms_consent": r["consent"]}
            r["status"] = "seated-soon" if p[2] == "table" else "no-show"
            notify("table.ready" if p[2] == "table" else "reservation.no_show", customer=c, party=r["party"])
            return self.send(200, {"status": r["status"]})
        self.send(404, {"error": "not_found"})


def serve(port=8080, host="127.0.0.1"):
    return ThreadingHTTPServer((host, port), App)


if __name__ == "__main__":
    print("Bella Trattoria demo app on http://127.0.0.1:8080"); serve().serve_forever()
