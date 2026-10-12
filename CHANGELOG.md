# Changelog

## 0.3.0
Job journal. Every send (text, call, Slack or Teams post, email, calendar entry, webhook, API write) is written down before it is sent and tracked through pending, sending, queued, sent, delivered or undelivered (from Twilio's status callback), needs_review, failed, blocked, expired and cancelled. A crash while sending is never sent again by itself (needs_review); jobs written but not started are queued; events accepted from your app are written down before the answer and resumed after a restart without repeating finished actions. A timeout or server error is now needs_review instead of a plain error. New `jobs list|cancel|retry|mark-sent` commands, job counts in `/health`, Twilio idempotency header and a configurable idempotency header for your own providers (best effort). See docs/jobs-and-recovery.md. Replaces the 0.2.0 outbox list (converted automatically).
Local dashboard at /dashboard on the running agent: counts, jobs that need you (cancel, retry, mark arrived or send again after a review), recent activity, bundle coverage, pause-all button and a form to request more lines. See docs/dashboard.md.

## 0.2.0
Offline queue: when the network is down, texts, calls, Slack and Teams posts, email, calendar entries and webhooks wait in an outbox on disk and are sent in order when the connection returns. Only requests that provably never left the machine are queued (a timeout or server error is never retried, so nothing is sent twice); safety checks (consent, STOP, quiet hours, limits, kill switch) run again at send time; old actions expire (`queue.max_age_minutes`). New `queue list|flush|drop` command, `queued` in `/health` and `check`. See docs/offline-and-queue.md.

## 0.1.0
First public release: workflows from events, calendars (Google, Microsoft 365), texts and calls (Twilio or any provider API), WhatsApp, Slack, Teams, SMTP and IMAP email, webhook mappings (GitHub, GitLab, PagerDuty, Stripe, Shopify, Calendly, generic), the `http` action, required industry notices, consent, STOP, quiet hours, limits modes, kill switch, dry-run by default, and the `slots` command that asks for missing spoken lines.
