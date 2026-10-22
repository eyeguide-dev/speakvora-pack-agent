"""A permanent address for your agent, so Twilio, WhatsApp, Telegram and your own apps always reach it and you never type 127.0.0.1:8787 again.
Cloudflare Tunnel (free) is the main way: you paste one token and name an address on your own domain, and this agent runs the tunnel for you (the free `cloudflared` helper) and uses that address everywhere.
Tailscale Funnel (free, no domain needed) gives a fixed name.ts.net address. A person who already has a server can use their own reverse proxy and just type the address.
Safety: the dashboard never opens through the public webhook address. If you want it on the internet too, it uses a SECOND address that must sit behind Cloudflare Access (an email login), and it still needs your access token."""
import base64, hashlib, json, os, platform, re, shutil, stat, subprocess, sys, tarfile, tempfile, threading, time

from . import web

HOST_RX = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
RELEASES = "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"


class AddressError(ValueError):
    pass


def settings(agent):
    return agent.cfg.get("address") or {}


def clean_host(v, label="Address"):
    h = re.sub(r"^https?://", "", str(v or "").strip().lower()).strip("/ ")
    if not h:
        return ""
    if not HOST_RX.match(h):
        raise AddressError(f"{label} must be a web name like hooks.yourbusiness.com (no https://, no slashes).")
    return h


def parse_token(tok):
    """A Cloudflare tunnel token is a long base64 text that holds the account, tunnel id and secret. Returns the cleaned token or raises with a plain reason."""
    t = re.sub(r"\s+", "", str(tok or ""))
    m = re.search(r"eyJ[A-Za-z0-9_\-+/=]{30,}", t)                    # also finds the token inside a pasted command ("cloudflared tunnel run --token eyJ...")
    if m:
        t = m.group(0)
    try:
        d = json.loads(base64.b64decode(t + "=" * (-len(t) % 4), altchars=b"-_" if ("-" in t or "_" in t) else None))
    except Exception:  # noqa: BLE001
        raise AddressError("That does not look like a Cloudflare tunnel token. It is one very long piece of text that starts with eyJ. In Cloudflare, open your tunnel and copy only the token.")
    if not (isinstance(d, dict) and d.get("a") and d.get("t") and d.get("s")):
        raise AddressError("That token is incomplete. Copy the whole token from the tunnel's page in Cloudflare.")
    return t


def find_cloudflared(agent=None):
    env = os.environ.get("CLOUDFLARED_BIN")
    if env and os.path.exists(env):
        return env
    w = shutil.which("cloudflared")
    if w:
        return w
    if agent is not None:
        p = os.path.join(agent.state.dir, "bin", "cloudflared" + (".exe" if sys.platform == "win32" else ""))
        if os.path.exists(p):
            return p
    return ""


def install_commands():
    """What to type to install the free helper, for the computer this agent runs on."""
    if sys.platform == "darwin":
        return {"os": "Mac", "commands": ["brew install cloudflared"], "note": "Needs Homebrew (brew.sh). Or press Install for me."}
    if sys.platform == "win32":
        return {"os": "Windows", "commands": ["winget install --id Cloudflare.cloudflared"], "note": "Run it in PowerShell. Or press Install for me."}
    return {"os": "Linux", "commands": ["curl -L --output cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x cloudflared && sudo mv cloudflared /usr/local/bin/"], "note": "Or press Install for me."}


def _asset_name():
    m = platform.machine().lower(); arm = m in ("arm64", "aarch64")
    if sys.platform == "darwin":
        return "cloudflared-darwin-arm64.tgz" if arm else "cloudflared-darwin-amd64.tgz"
    if sys.platform == "win32":
        return "cloudflared-windows-amd64.exe" if not arm else "cloudflared-windows-arm64.exe"
    return "cloudflared-linux-arm64" if arm else "cloudflared-linux-amd64"


def install_cloudflared(agent, request=web.request, download=None):
    """Downloads the official cloudflared from Cloudflare's own GitHub release into this agent's folder. It is only kept when the file matches the SHA-256 that GitHub publishes for that release file; with no checksum to compare, nothing is installed."""
    name = _asset_name()
    st, rel = request("GET", RELEASES, {"accept": "application/vnd.github+json"}, timeout=20)
    if st != 200 or not isinstance(rel, dict):
        raise AddressError("Could not read Cloudflare's release list. Check the internet connection, or install it yourself with the command shown.")
    asset = next((a for a in rel.get("assets", []) if a.get("name") == name), None)
    digest = str((asset or {}).get("digest") or "")
    if not asset or not digest.startswith("sha256:"):
        raise AddressError("Cloudflare's release does not list a checksum for your computer, so it is not installed automatically. Install it with the command shown instead.")
    data = (download or _download)(asset["browser_download_url"])
    if hashlib.sha256(data).hexdigest() != digest[7:]:
        raise AddressError("The download did not match Cloudflare's checksum, so it was thrown away. Try again, or install it with the command shown.")
    d = os.path.join(agent.state.dir, "bin"); os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, "cloudflared" + (".exe" if sys.platform == "win32" else ""))
    if name.endswith(".tgz"):
        with tempfile.TemporaryDirectory() as tmp:
            tp = os.path.join(tmp, "c.tgz"); open(tp, "wb").write(data)
            with tarfile.open(tp) as t:
                m = next((x for x in t.getmembers() if os.path.basename(x.name) == "cloudflared" and x.isfile()), None)
                if not m:
                    raise AddressError("The download did not contain the helper.")
                open(dest, "wb").write(t.extractfile(m).read())
    else:
        open(dest, "wb").write(data)
    os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR | stat.S_IXGRP)
    return dest


def _download(url):
    import urllib.request
    with urllib.request.urlopen(urllib.request.Request(url, headers={"user-agent": "SpeakvoraAgent"}), timeout=120) as r:
        return r.read()


class Tunnel:
    """Runs `cloudflared tunnel run` for you and keeps it running: restarts it if it stops, never puts the token on the command line (only in the helper's own environment), and says plainly what state it is in."""
    def __init__(self, backoff_max=60):
        self.proc = None; self.thread = None; self.state = "stopped"; self.connected = False; self.error = ""; self.token = ""; self.binary = ""; self.lines = []; self.backoff_max = backoff_max; self._stop = threading.Event()

    def start(self, binary, token):
        if self.thread and self.thread.is_alive() and (binary, token) == (self.binary, self.token):
            return
        self.stop(); self.binary, self.token = binary, token; self._stop = threading.Event(); self.state = "starting"; self.error = ""; self.connected = False
        self.thread = threading.Thread(target=self._run, daemon=True); self.thread.start()

    def stop(self):
        self._stop.set()
        p = self.proc
        if p and p.poll() is None:
            try:
                p.terminate(); p.wait(timeout=5)
            except Exception:  # noqa: BLE001
                try:
                    p.kill()
                except Exception:  # noqa: BLE001
                    pass
        self.proc = None; self.connected = False; self.state = "stopped"

    def _say(self, line):
        line = line.replace(self.token, "***") if self.token else line
        self.lines.append(line.rstrip()[:300]); del self.lines[:-30]
        low = line.lower()
        if "registered tunnel connection" in low:
            self.connected = True; self.state = "connected"; self.error = ""
        elif "unauthorized" in low or "token is not valid" in low or "failed to unmarshal" in low or "invalid tunnel secret" in low:
            self.error = "Cloudflare did not accept this token. Copy the token again from the tunnel's page."
        elif "failed to dial" in low or "no such host" in low or "connection refused" in low and "127.0.0.1" not in low and "localhost" not in low:
            self.error = "The helper cannot reach Cloudflare. Check the internet connection."

    def _run(self):
        delay = 1
        while not self._stop.is_set():
            env = dict(os.environ, TUNNEL_TOKEN=self.token)
            try:
                self.proc = subprocess.Popen([self.binary, "tunnel", "--no-autoupdate", "run"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            except OSError as e:
                self.error = f"Could not start the helper: {e}"[:200]; self.state = "error"
                if self._stop.wait(min(delay, self.backoff_max)):
                    return
                delay = min(delay * 2, self.backoff_max); continue
            self.state = "starting"
            for line in self.proc.stdout:
                self._say(line)
                if self._stop.is_set():
                    break
            rc = self.proc.wait(); self.connected = False
            if self._stop.is_set():
                return
            self.state = "restarting"
            if not self.error:
                self.error = f"The helper stopped (code {rc}); starting it again."
            if self._stop.wait(min(delay, self.backoff_max)):
                return
            delay = min(delay * 2, self.backoff_max)

    def status(self):
        return {"state": self.state, "connected": self.connected, "error": self.error, "log": list(self.lines[-6:])}


def home_id(agent):
    return hashlib.sha256(os.path.abspath(agent.state.dir).encode()).hexdigest()[:12]


def reachable(agent, host, request=web.request, access_ok=False):
    """Asks the internet whether this host really leads to THIS agent. Returns (ok, plain reason)."""
    try:
        st, r = request("GET", f"https://{host}/health", timeout=12)
    except web.NetworkDown:
        return False, f"{host} is not found on the internet yet. In Cloudflare, add it as a public hostname of your tunnel (it creates the name for you), then wait a minute."
    except web.HttpError as e:
        st, r = e.status, e.body
    except Exception as e:  # noqa: BLE001
        return False, f"Could not check {host}: {type(e).__name__}."
    if st == 200 and isinstance(r, str) and "cloudflareaccess" in r.lower():                         # a redirect ended on Cloudflare Access's login page
        st = 302
    if st == 200 and isinstance(r, dict) and r.get("home") == home_id(agent):
        return True, f"{host} reaches this agent."
    if st == 200 and isinstance(r, dict) and r.get("home"):
        return False, f"{host} reaches a DIFFERENT Speakvora agent. Point it at this computer's tunnel."
    if st in (502, 503, 504, 530, 1033):
        return False, f"{host} is set up but the tunnel is not connected to it. Check that the helper shows Connected below, and that the hostname's service is http://localhost:{agent.cfg['listen']['port']}."
    if access_ok and st in (301, 302, 307, 401, 403):
        return True, f"{host} answers with Cloudflare's login page, which is what protects the dashboard."
    if st in (301, 302, 307, 401, 403):
        return False, f"{host} answers with a login or block page. Cloudflare Access must not sit in front of the webhook address (Twilio cannot log in). Use a separate address for the dashboard."
    return False, f"{host} answered with code {st} and not this agent."


def tailscale_bin():
    return os.environ.get("TAILSCALE_BIN") or shutil.which("tailscale") or ("/Applications/Tailscale.app/Contents/MacOS/Tailscale" if os.path.exists("/Applications/Tailscale.app/Contents/MacOS/Tailscale") else "")


def tailscale_name(binary=None):
    """The fixed name.ts.net address of this computer, or '' when Tailscale is not installed, not signed in, or has no name yet."""
    b = binary or tailscale_bin()
    if not b:
        return ""
    try:
        out = subprocess.run([b, "status", "--json"], capture_output=True, text=True, timeout=15)
        d = json.loads(out.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return ""
    if d.get("BackendState") not in ("Running", None):
        return ""
    return str((d.get("Self") or {}).get("DNSName") or "").rstrip(".").lower()


def tailscale_funnel(port, binary=None):
    """Turns on Tailscale Funnel for this agent's port. Returns (ok, plain message)."""
    b = binary or tailscale_bin()
    if not b:
        return False, "Tailscale is not installed on this computer."
    try:
        out = subprocess.run([b, "funnel", "--bg", str(port)], capture_output=True, text=True, timeout=40)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"Tailscale did not answer: {type(e).__name__}."
    text = (out.stdout + out.stderr).strip()
    if out.returncode == 0:
        return True, "Funnel is on."
    if "funnel" in text.lower() and ("not enabled" in text.lower() or "acl" in text.lower() or "https" in text.lower()):
        return False, "Funnel is switched off for your Tailscale account. Open the link Tailscale printed (or Settings, Feature previews/Funnel in the Tailscale admin console), turn on HTTPS and Funnel, then press Check again."
    return False, "Tailscale said: " + text[:200]


# ---- what the dashboard shows and saves ---------------------------------------------------------------------------------------------------------------
def _real(v):
    return bool(v) and "YOUR-" not in str(v) and not str(v).startswith("env:")


def expected_base(agent):
    a = settings(agent); p = a.get("provider") or ""
    if p in ("cloudflare", "own") and a.get("hostname"):
        return "https://" + a["hostname"]
    if p == "tailscale":
        n = tailscale_name()
        return ("https://" + n) if n else ""
    return ""


def view(agent):
    a = settings(agent); p = a.get("provider") or ""; base = str(agent.cfg.get("public_base_url") or "").rstrip("/"); want = expected_base(agent)
    b = find_cloudflared(agent)
    return {"provider": p, "hostname": a.get("hostname", ""), "dashboard_hostname": a.get("dashboard_hostname", ""), "remote_dashboard": bool(a.get("remote_dashboard")), "require_access": a.get("require_access", True) is not False,
            "token_set": _real(a.get("token")), "port": agent.cfg["listen"]["port"], "helper": {"found": bool(b), "install": install_commands()}, "tunnel": agent.tunnel.status() if hasattr(agent, "tunnel") else {},
            "tailscale": {"installed": bool(tailscale_bin()), "name": tailscale_name() if p == "tailscale" else ""}, "public_base_url": base if _real(base) else "", "wanted_base_url": want, "in_use": bool(want) and base == want,
            "dashboard_url": ("https://" + a["dashboard_hostname"] + "/dashboard") if a.get("dashboard_hostname") and a.get("remote_dashboard") else ""}


def save(agent, values):
    """Saves the address settings (the token goes to this computer's secrets file, never into agent.json) and starts or stops the helper to match."""
    from . import connect as C, secrets_store as SS
    v = values or {}; raw = C._raw(agent); a = dict(raw.get("address") or {})
    if "provider" in v:
        if v["provider"] not in ("cloudflare", "tailscale", "own", ""):
            raise AddressError("Choose Cloudflare, Tailscale or My own server.")
        a["provider"] = v["provider"]
    if "hostname" in v:
        a["hostname"] = clean_host(v["hostname"], "The webhook address")
    if "dashboard_hostname" in v:
        a["dashboard_hostname"] = clean_host(v["dashboard_hostname"], "The dashboard address")
        if a["dashboard_hostname"] and a["dashboard_hostname"] == a.get("hostname"):
            raise AddressError("The dashboard needs its own address, different from the webhook address, so that Cloudflare Access can protect only the dashboard.")
    if "remote_dashboard" in v:
        a["remote_dashboard"] = bool(v["remote_dashboard"]) and str(v["remote_dashboard"]).lower() not in ("false", "0", "off", "no")
    if "require_access" in v:
        a["require_access"] = str(v["require_access"]).lower() not in ("false", "0", "off", "no")
    if a.get("remote_dashboard") and not a.get("dashboard_hostname"):
        raise AddressError("Type the dashboard address first (for example agent.yourbusiness.com), or leave the dashboard on this computer only.")
    if v.get("token"):
        SS.set_value(agent.state.dir, "TUNNEL_TOKEN", parse_token(v["token"])); a["token"] = "env:TUNNEL_TOKEN"
    if v.get("clear_token"):
        SS.set_value(agent.state.dir, "TUNNEL_TOKEN", ""); a.pop("token", None)
    raw["address"] = a; C._write_raw(agent, raw); C._reload(agent); sync(agent)
    return view(agent)


def remove(agent):
    from . import connect as C, secrets_store as SS
    raw = C._raw(agent); old = (raw.get("address") or {}).get("managed_base")
    raw.pop("address", None)
    if old and str(raw.get("public_base_url") or "").rstrip("/") == old:
        raw["public_base_url"] = "https://YOUR-PUBLIC-ADDRESS-FOR-THIS-AGENT"
    SS.set_value(agent.state.dir, "TUNNEL_TOKEN", ""); C._write_raw(agent, raw); C._reload(agent)
    if hasattr(agent, "tunnel"):
        agent.tunnel.stop()
    return view(agent)


def sync(agent):
    """Makes the running helper match the saved settings. Called when the agent starts and after every save."""
    t = getattr(agent, "tunnel", None)
    if t is None or not getattr(agent, "_serving", False):
        return
    a = settings(agent)
    if a.get("provider") == "cloudflare" and _real(a.get("token")) and a.get("hostname"):
        b = find_cloudflared(agent)
        if not b:
            t.stop(); t.state = "no_helper"; t.error = "The free Cloudflare helper (cloudflared) is not installed on this computer yet."
            return
        t.start(b, a["token"])
    else:
        t.stop()


def use_everywhere(agent, force=False):
    """Makes this the public address Twilio, Telegram, WhatsApp and your app use. Replaces a placeholder or the address this feature set earlier; a different address you typed yourself is only replaced when you confirm."""
    from . import connect as C
    want = expected_base(agent)
    if not want:
        raise AddressError("There is no address to use yet. Finish the steps first.")
    raw = C._raw(agent); cur = str(raw.get("public_base_url") or "").rstrip("/"); managed = (raw.get("address") or {}).get("managed_base")
    if _real(cur) and cur != want and cur != managed and not force:
        return {"needs_confirm": True, "current": cur, "wanted": want}
    raw["public_base_url"] = want; raw.setdefault("address", {})["managed_base"] = want
    C._write_raw(agent, raw); C._reload(agent)
    agent.audio.base = want
    return {"ok": True, "public_base_url": want}


def check(agent, request=web.request):
    """The live checklist: each line is proven or says in plain words what is missing."""
    a = settings(agent); p = a.get("provider") or ""; items = []
    add = lambda i, label, ok, detail="": items.append({"id": i, "label": label, "ok": bool(ok), "detail": detail})  # noqa: E731
    if p == "cloudflare":
        b = find_cloudflared(agent); t = agent.tunnel.status() if hasattr(agent, "tunnel") else {}
        add("helper", "The free Cloudflare helper is installed", b, "" if b else "Press Install for me, or run the command shown.")
        add("token", "Your tunnel token is saved", _real(a.get("token")), "" if _real(a.get("token")) else "Paste the token from your tunnel's page in Cloudflare.")
        add("tunnel", "The tunnel is connected to Cloudflare", t.get("connected"), "" if t.get("connected") else (t.get("error") or "Waiting for the helper to connect (it can take 10 to 20 seconds)."))
        ok, why = reachable(agent, a["hostname"], request) if a.get("hostname") else (False, "Type the webhook address, for example hooks.yourbusiness.com.")
        add("reach", "The webhook address reaches this agent", ok, "" if ok else why)
        if a.get("dashboard_hostname") and a.get("remote_dashboard"):
            ok2, why2 = reachable(agent, a["dashboard_hostname"], request, access_ok=True)
            add("dashboard", "The dashboard address answers (behind Cloudflare Access)", ok2, "" if ok2 else why2)
    elif p == "tailscale":
        n = tailscale_name(); add("installed", "Tailscale is installed and signed in", n, "" if n else "Install Tailscale (tailscale.com/download), sign in, and press Check again.")
        if n:
            ok, why = reachable(agent, n, request); add("reach", "Your fixed address reaches this agent", ok, "" if ok else (why + " Press Turn on Funnel if you have not yet."))
    elif p == "own":
        ok, why = reachable(agent, a["hostname"], request) if a.get("hostname") else (False, "Type the address your server uses for this agent.")
        add("reach", "The address reaches this agent", ok, "" if ok else why)
    else:
        add("choose", "Choose how to get a permanent address", False, "Pick Cloudflare (recommended), Tailscale, or My own server.")
    want = expected_base(agent); base = str(agent.cfg.get("public_base_url") or "").rstrip("/")
    if want:
        add("use", "Twilio, Telegram and WhatsApp use this address", base == want, "" if base == want else "Press Use this address everywhere.")
    allok = bool(items) and all(i["ok"] for i in items)
    return {"items": items, "ready": allok, "summary": "Ready: your agent has a permanent address." if allok else "Not finished: " + next((i["label"] for i in items if not i["ok"]), "")}
