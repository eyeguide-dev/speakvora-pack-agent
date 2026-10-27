"""Microsoft Teams: post to a channel through its incoming-webhook / Workflows URL (Teams > channel > Workflows > "Post to a channel when a webhook request is received"). Text only."""
from .. import web as http


class Teams:
    def __init__(self, cfg):
        self.url = cfg.get("webhook_url", "")
        self.configured = bool(self.url)
        self.outgoing_secret = str(cfg.get("outgoing_secret", "") or "")       # the security token Teams shows when you create an Outgoing Webhook (see teams_in.py)
        self.allow = [str(x).strip().lower() for x in (cfg.get("allow") or []) if str(x).strip()]      # display names or emails that may talk to the bug desk; empty = anyone in that channel

    def post(self, text, title=None, key=None):
        if key and self.outgoing_secret:                                       # two-way is on: tell people how to answer
            if key not in text:
                text += f"\n\nTicket: {key}"
            text += f"\n\nTo update it, @mention the bot, for example: {key} fixed: what you did"
        body = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
            "body": ([{"type": "TextBlock", "text": title, "weight": "Bolder"}] if title else []) + [{"type": "TextBlock", "text": text, "wrap": True}]}}]}
        return http.request("POST", self.url, body=body)[1]
