# Safety rules (always on)

* **Dry-run first.** Nothing is sent until you start with `--live` or set `"dry_run": false`.
* **Consent.** Texts, calls and emails to customers need `customer.sms_consent` true (or the person in `recipients.allow`). People who text you first can always be answered.
* **STOP.** A STOP reply opts the number out everywhere; START opts back in.
* **Quiet hours** (default 9 PM to 8 AM in your timezone) block calls and texts. **Limits:** 3 per person per day and 60 sends an hour by default.
* **Kill switch:** a file named `STOP` in `agent-state/` (or `SV_AGENT_STOP=1`) stops all sending at once.
* **Signatures.** Events, Twilio, Slack and mapped webhooks are checked; unsigned requests are refused.
* **Placeholders.** Anything still containing `YOUR-...` is never sent.
* **Your app is safe.** The agent is a separate process; it never touches your database. A failing service can not stop the others, and the app never waits for the agent.
* **Honesty.** The voices are synthetic. Tell people they are hearing an automated voice where the law or good practice requires it. Not for medical advice, emergencies or patient information.
