# The local dashboard

A small page that runs inside your agent (nothing is installed, nothing leaves your machine). It shows what the agent is doing for THIS pack and lets you act on it.

Start the agent as usual (`python -m speakvora_pack_agent run`). It prints a line like

    dashboard: http://127.0.0.1:8787/dashboard#token=...

Open that address on the same machine. The part after `#` is your access token. It never goes to a server and never appears in a log. The token is kept in `agent-state/dashboard-token` (mode 600), or set your own with the environment variable `SV_DASHBOARD_TOKEN`. Every `/dash/api` call needs it; the page itself holds no data.

Two tabs. **Activity** is one list you filter: tap All, Needs you, Waiting, Sent or Delivered, pick a type (texts, calls, Slack, Teams, email, calendar, webhooks), or search a name, number, channel or workflow. **Lines** shows how complete your bundle is and lets you ask for more lines.

## What it shows
* **Mode and pause:** DRY RUN or LIVE, and a **Pause all sending** button (the same as creating the STOP file; resume removes it).
* **Counts:** waiting, need review, failed, provider accepted, delivered, expired.
* **Needs you:** every job that needs a decision, with the buttons:
  * *Cancel* a job that has not been sent;
  * *Try again* a failed or expired job (the safety checks run again);
  * *It arrived* / *It did not arrive: send again* for a job in review (a timeout or server error: it may already have gone out, so you check with the provider first).
* **Recent activity:** the last 40 sends with status, where to, and the provider's note.
* **Your bundle:** how many of the spoken lines your workflows use are in this pack, which ones are missing, and a button to request the missing ones.
* **Ask for another line:** say when a line is used and write the sentence you want. It is saved in `agent-state/slot-requests.json` and, when `SPEAKVORA_KEY` is set to an API key from your Speakvora dashboard, sent to Speakvora (the same request as `slots --send`). New lines are written, checked and voiced, then arrive in the next version of your pack. No delivery date is promised. A line request needs a clear moment and a plain sentence: no links, email addresses or long numbers.

## Safety
* The page is served with a strict content policy (no outside scripts, styles or images); POSTs from other websites are refused; the API token is compared in constant time.
* By default the agent listens on 127.0.0.1 only. If you change `listen.host` to expose it, put it behind your own HTTPS and access control: the token is the only lock.
* Job text shown is the first part of the message and the destination, never your keys.
