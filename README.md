# speakvora-pack-agent

A small agent that turns an offline voice pack into automated work: confirm bookings, remind people from your calendar, tell customers an order is ready, answer texts, calls and email, wake your on-call engineer when a pipeline fails, and tell your team in Slack or Teams.

It runs on **your own server**, next to your app, with **your own accounts**. Standard-library Python only. No hosted service, no per-message fee from us, nothing to install in your chat or calendar.

> Speakvora sells offline voice packs (audio you ship once). Every pack includes this agent. The agent is free software (MIT); the pack audio is licensed separately. You can use the agent with any set of audio files laid out like a pack.

## Try it in two minutes, no accounts

```bash
git clone https://github.com/eyeguide-dev/speakvora-pack-agent && cd speakvora-pack-agent
python3 examples/restaurant/demo.py
```
It runs a restaurant's day against fake Twilio, Slack and Google servers on your machine and prints what the agent did, and what it refused to do (no consent, opted out).

## Use it with a pack

```bash
pip install speakvora-pack-agent        # or use the copy inside every Speakvora pack
cd your-unzipped-pack
speakvora-pack-agent init --pack .      # writes agent.json + workflows.json for the pack's industry
speakvora-pack-agent check              # what is connected, which spoken lines are missing
speakvora-pack-agent source add github  # ready webhook mappings: github, gitlab, pagerduty, stripe, shopify, calendly, generic-pos
speakvora-pack-agent run                # DRY RUN: records what it would do, sends nothing
speakvora-pack-agent run --live         # when the log looks right
```

## What it connects to
Texts, calls and WhatsApp through Twilio, or any provider's web API (`sms_provider`, `call_provider`); Slack and Microsoft Teams; Google Calendar and Microsoft 365 (ICS link or OAuth); SMTP and IMAP email; any system that sends a webhook (a short mapping, no code); any REST API (`http` action). See [docs/connect-anything.md](docs/connect-anything.md) and [docs/integrate-existing-numbers.md](docs/integrate-existing-numbers.md).

## Safety is on by default
Dry-run first. Customer messages need consent. STOP is always honoured. Quiet hours and limits (`strict`, `standard`, `open`). Notices your industry must say are added automatically (automated-call line, opt-out footer, emergency and privacy for health, facility notices, debt-collector notice, confidentiality). Signed requests only. A kill switch (create a file named `STOP` in `agent-state/`). See [docs/safety.md](docs/safety.md) and [docs/limits-and-control.md](docs/limits-and-control.md).

## Honest limits
Keyword and menu based, not a chatbot. You run it (Python 3.9+). US texting needs carrier registration in your provider account; inbound phone menus need Twilio. Tested against simulated services, so start in dry-run with your own accounts. Legal notice wording is a starting point for your counsel, not legal advice. Not for medical advice, emergencies or patient information. Not an inmate calling platform.

## License
MIT for the software. Logos or brand names mentioned belong to their owners; no endorsement implied. Pack audio is separate.
