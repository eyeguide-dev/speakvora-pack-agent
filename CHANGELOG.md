# Changelog

## 0.2.0
Offline queue: when the network is down, texts, calls, Slack and Teams posts, email, calendar entries and webhooks wait in an outbox on disk and are sent in order when the connection returns. Only requests that provably never left the machine are queued (a timeout or server error is never retried, so nothing is sent twice); safety checks (consent, STOP, quiet hours, limits, kill switch) run again at send time; old actions expire (`queue.max_age_minutes`). New `queue list|flush|drop` command, `queued` in `/health` and `check`. See docs/offline-and-queue.md.

## 0.1.0
First public release: workflows from events, calendars (Google, Microsoft 365), texts and calls (Twilio or any provider API), WhatsApp, Slack, Teams, SMTP and IMAP email, webhook mappings (GitHub, GitLab, PagerDuty, Stripe, Shopify, Calendly, generic), the `http` action, required industry notices, consent, STOP, quiet hours, limits modes, kill switch, dry-run by default, and the `slots` command that asks for missing spoken lines.
