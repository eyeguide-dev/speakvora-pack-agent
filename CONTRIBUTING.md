# Contributing

Thanks for helping. The agent is standard-library Python only; please keep it that way.

* Run the tests: `python -m unittest discover -s tests` (about 30 seconds; they use fake Twilio, Slack, Google and Microsoft servers on localhost).
* Add a test for every change. Safety rules (consent, STOP, required notices, limits, signatures) must stay covered.
* New webhook presets go in `speakvora_pack_agent/data/sources/` with a test that checks the signature and the mapping.
* Keep messages plain and honest; do not add marketing text to default workflows.
