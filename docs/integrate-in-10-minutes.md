# Add the agent to your business in 10 minutes

Works in all 12 pack languages (en es fr pt it de fi hi ja zh ar ko). The agent speaks and writes in the language of your pack.

1. **Unzip your pack** and install: `pip install speakvora-pack-agent` (or use `deploy/Dockerfile`). Python 3.9+; install `ffmpeg` if you want phone calls to play the pack's audio.
2. **Create the config:** `speakvora-pack-agent init --pack ./pack` writes `agent.json` and `workflows.json` for your industry. It starts in dry-run mode: nothing is sent anywhere.
3. **See what is missing:** `speakvora-pack-agent doctor` lists what to fix, one line each.
4. **Run it:** `speakvora-pack-agent run`. Then `speakvora-pack-agent doctor` again to test the public address (use a tunnel such as cloudflared while testing).
5. **Connect your app:** `speakvora-pack-agent events --lang python` (or node, php, ruby, go, curl) prints a signed, copy-paste example for every event your workflows react to. Texts, calls and calendar events need no code at all; point Twilio, Slack or Teams at the addresses doctor prints.
6. **Go live:** set `"dry_run": false` once the dry-run log looks right.

Your own phone, Slack, calendar, email and tools stay yours: you connect your accounts and you are billed by those providers. Webhooks from GitHub, GitLab, PagerDuty, Stripe, Shopify and Calendly map in with `speakvora-pack-agent source list`.

## Limits

Default mode is `standard`: sensible per-person and hourly limits and quiet hours. Want none? `speakvora-pack-agent init --mode open` (or set `"mode": "open"`) removes the per-person limits, hourly cap and quiet hours. Always on in every mode: STOP/opt-out handling, required notices (automated-call and recording notices, opt-out footer, emergency and privacy lines) and the kill switch (`touch state/PAUSE`). Those protect your customers and you.

## Deploy

`deploy/Dockerfile`, `deploy/docker-compose.yml`, `deploy/speakvora-pack-agent.service` (systemd). Keep secrets in an `.env` file, never in the repository.
