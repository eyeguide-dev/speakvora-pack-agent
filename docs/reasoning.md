# Reasoning with your own AI key (optional)

The agent follows rules you configure. That is why it works offline and costs nothing per turn. Some requests are not rules: "review these conversations, decide which customers need a refund and explain why". For those you can add a **reasoning step** to a workflow and plug in **your own AI key**. You pay your AI provider for the tokens; Speakvora charges nothing and sees nothing.

Only the questions you route to it are sent. Everything else stays rules, offline and free.

## The safety model: the AI proposes, a person approves
1. The workflow gives the model a task and some input (and a list of contacts by id and name).
2. The model answers with a short explanation and **proposals** (send this text to this contact, post this to this channel...). It cannot run anything.
3. The proposals appear in the dashboard under **Needs you**, with the reasoning and exactly what was sent to the model. A person approves the ones they want (or rejects all).
4. Approved proposals run as normal journaled sends: consent, STOP, quiet hours, limits and the kill switch are checked again. Approving twice sends nothing twice.
A workflow can list low-risk actions under `auto_allow` (for example a Slack post to your own team) so they run without a click. Customer texts and emails should stay on approval.

## What the model sees, and what it cannot do
* Only the task, the `inputs` you template in and the contact ids and names. Emails, phone numbers and card-like numbers in that text are replaced with `[email]`, `[phone]` and `[number]` first (`reasoner.redact` to change). The model never sees a contact's phone number or email.
* It can only propose actions you list in `allow`: `sms`, `email`, `slack`, `teams`, `http`, `calendar_create`. Customers are named by contact id from YOUR list, Slack channels must be in `channels`, and `http` URLs must be in `hosts`. Anything else it proposes is dropped and shown as "not allowed here".
* Customer messages use the consent you put on each contact (`sms_consent`). No consent, no send.
* An answer in the wrong shape, an unreachable model or a missing key produces a failed job and no action. If the connection is down the question waits in the queue and is asked when it returns (and expires after an hour).
* In dry run the model is not called at all; the log shows how many characters would have been sent.

## Set it up
In `agent.json`:
```json
"reasoner": {
  "provider": "openai",                       // or "anthropic"
  "base_url": "https://api.openai.com/v1",    // any OpenAI-compatible endpoint; omit for Anthropic's default
  "api_key": "env:AI_API_KEY",                // never write a key in the file
  "model": "the-model-name-you-choose",
  "max_per_hour": 20, "max_tokens": 900, "max_input_chars": 12000
}
```
* **OpenAI-compatible** covers OpenAI, Azure OpenAI, Groq, Together, OpenRouter, DeepInfra, vLLM and local servers. For a fully offline setup point `base_url` at a local server such as Ollama (`http://localhost:11434/v1`): nothing leaves your machine.
* **Anthropic** uses the Messages API (`"provider": "anthropic"`).
* `max_per_hour` protects your bill: past it, the job is blocked, not sent.

A workflow step (see `examples/refund-review/`):
```json
{"action": "reason", "task": "Decide which customers should get a refund and explain why.",
 "inputs": "{{conversations}}", "contacts": "{{customers}}",
 "allow": ["sms", "slack"], "channels": ["#support"], "notify": "#support"}
```
`{{conversations}}` on its own passes the real list or record from the event (or from an `http` GET you saved with `save_as`). `notify` posts a short note to your team when there is something to approve.

## From Slack
A workflow triggered by a slash command can contain a reasoning step. Slack gets an answer within its three seconds ("On it..."), the model works in the background and the proposal waits in the dashboard. Set `"ack"` on the workflow to change the first message.

## Commands
```
python -m speakvora_pack_agent proposals list
python -m speakvora_pack_agent proposals approve <job id> [--only 0,2]
python -m speakvora_pack_agent proposals reject <job id> [--only 1]
```

## Honest limits
* A model can be wrong. Read the reasoning and what was sent before you approve; keep customer-facing actions on approval.
* Using a hosted model sends the (redacted) inputs you chose to that provider: check its terms. A local model keeps everything on your machine.
* Not for medical, legal or financial advice, emergencies or patient information.
* The agent does not give the model tools to look things up on its own: you decide what data goes in, through the workflow.
