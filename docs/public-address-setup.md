# Getting a permanent public address for your agent

Order tracking links, phone calls that play your recordings and replies to inbound texts all need a web address that reaches the agent from the internet. **A tracking link a customer receives starts with this address, so it must never change.** A free "quick tunnel" address changes every time it restarts and its old links stop working: use it for testing only.

The dashboard never opens through this address (it refuses requests that arrive through a tunnel), so exposing the agent does not expose your dashboard.

## Option A (recommended): your own domain with a Cloudflare named tunnel (free)
You need a domain you own (for example `bellandbasil.com`) with its DNS on Cloudflare (a free Cloudflare account; Cloudflare tells you the two name servers to set at your domain registrar).

1. Install `cloudflared` on the computer that runs the agent (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
2. Log in and pick your domain:
   `cloudflared tunnel login`
3. Create the tunnel:
   `cloudflared tunnel create speakvora-agent`
   It prints an id and writes a credentials file in your `.cloudflared` folder.
4. Create `~/.cloudflared/config.yml` (use your id, your user name and your domain):
   ```
   tunnel: YOUR-TUNNEL-ID
   credentials-file: /Users/YOU/.cloudflared/YOUR-TUNNEL-ID.json
   ingress:
     - hostname: orders.bellandbasil.com
       service: http://127.0.0.1:8787
     - service: http_status:404
   ```
5. Point the name at the tunnel:
   `cloudflared tunnel route dns speakvora-agent orders.bellandbasil.com`
6. Run it now: `cloudflared tunnel run speakvora-agent`. To start it automatically whenever the computer starts: `sudo cloudflared service install` (macOS and Linux; on Windows run `cloudflared service install` in an administrator terminal).
7. Open the dashboard, **Connect, Your business**, type `https://orders.bellandbasil.com` as the public address, Save, then press **Test**. It must say it reaches this agent.
8. Check from another device: `https://orders.bellandbasil.com/health` should show a short status.

## Option B: Tailscale Funnel
Install Tailscale, turn on Funnel for your machine, and run `tailscale funnel 8787`. It gives a stable `https://your-machine.your-tailnet.ts.net` address. Use that as the public address.

## Option C: a small always-on server
Run the agent on a small cloud server (any $5 a month virtual machine) behind a web server such as Caddy that handles the certificate and proxies your domain to port 8787.

## Rules that keep links alive
- **Never change the address** after you have sent links. If you must, keep the old name pointing at the same tunnel too. The Orders tab flags links made with an older address.
- **The computer running the agent must stay on and awake**, because it serves the order pages. For a restaurant, use a small always-on machine rather than a laptop that sleeps.
- Set the same address as your Twilio webhooks if you use inbound texts or calls: `https://orders.bellandbasil.com/twilio/sms` and `/twilio/call`.
- **Back up the `agent-state` folder** (it holds `orders.db`, every link you have sent). Copy it to another disk or cloud folder regularly; restoring it on a new machine restores every link, as long as the address points at the new machine.

## What to fill in first (Connect, Your business)
Business name, website, customer service phone (becomes the Call button on every order page), other service numbers, opening hours, address and the public address. When order links are switched on, going live is blocked until these are filled in and the public address test has passed.
