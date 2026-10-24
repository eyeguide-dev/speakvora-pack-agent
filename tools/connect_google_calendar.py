#!/usr/bin/env python3
"""Connect Google Calendar so the agent can add its own bookings (read and change mode).

Run it from your agent folder after you create a Desktop OAuth client (see docs/google-calendar.md):

    python3 connect_google_calendar.py --agent-dir ~/speakvora-agents/my-agent --email you@gmail.com

It asks for the client ID and client secret (the secret is typed hidden), opens Google's consent page,
catches the answer on this computer only (127.0.0.1, a free port, nothing goes to Speakvora), swaps it for a
refresh token and saves all three in agent-state/secrets.json (mode 600). Then it points agent.json at them.
Nothing is printed that could be reused by someone else. It never changes or deletes any event of yours.
"""
import argparse, getpass, http.server, json, os, secrets, socket, sys, urllib.parse, urllib.request, webbrowser

SCOPE = "https://www.googleapis.com/auth/calendar.events"


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-dir", required=True, help="folder that holds agent.json")
    ap.add_argument("--email", default="", help="the Google account that owns the calendar (hint only)")
    ap.add_argument("--calendar-id", default="primary", help="calendar ID from the calendar's settings; use a separate calendar for bookings if you can")
    a = ap.parse_args()
    cfg_path = os.path.join(os.path.expanduser(a.agent_dir), "agent.json")
    cfg = json.load(open(cfg_path))
    state_dir = os.path.normpath(os.path.join(os.path.dirname(cfg_path), cfg.get("state_dir", "agent-state")))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from speakvora_pack_agent import secrets_store as SS

    client_id = input("OAuth client ID: ").strip()
    client_secret = getpass.getpass("OAuth client secret (hidden): ").strip()
    port = free_port(); redirect = f"http://127.0.0.1:{port}/"; state = secrets.token_urlsafe(12); got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state or "code" not in q:
                self.send_response(400); self.end_headers(); self.wfile.write(b"Not the answer I was waiting for."); return
            got["code"] = q["code"][0]
            self.send_response(200); self.send_header("content-type", "text/html"); self.end_headers()
            self.wfile.write(b"<h2>Calendar connected. You can close this tab.</h2>")

        def log_message(self, *x):
            pass

    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state, **({"login_hint": a.email} if a.email else {})})
    print("Opening Google's consent page. If it does not open, paste this address into your browser:\n" + url)
    webbrowser.open(url)
    http.server.HTTPServer(("127.0.0.1", port), H).handle_request()
    if "code" not in got:
        sys.exit("No answer received.")
    body = urllib.parse.urlencode({"code": got["code"], "client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
    tok = json.load(urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=body), timeout=30))
    if not tok.get("refresh_token"):
        sys.exit("Google did not return a refresh token. Remove the app at myaccount.google.com/permissions and run this again.")
    SS.set_value(state_dir, "GOOGLE_CLIENT_ID", client_id)
    SS.set_value(state_dir, "GOOGLE_CLIENT_SECRET", client_secret)
    SS.set_value(state_dir, "GOOGLE_REFRESH_TOKEN", tok["refresh_token"])
    cfg["google_calendar"] = {"mode": "oauth", "client_id": "env:GOOGLE_CLIENT_ID", "client_secret": "env:GOOGLE_CLIENT_SECRET",
                              "refresh_token": "env:GOOGLE_REFRESH_TOKEN", "calendar_id": a.calendar_id, "allow_create": True}
    json.dump(cfg, open(cfg_path, "w"), indent=2)
    print("Saved. Restart the agent, then in the dashboard open Connect, Google Calendar and press Save and test.")


if __name__ == "__main__":
    main()
