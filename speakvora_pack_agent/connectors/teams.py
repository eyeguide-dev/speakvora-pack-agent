"""Microsoft Teams: post to a channel through its incoming-webhook / Workflows URL (Teams > channel > Workflows > "Post to a channel when a webhook request is received"). Text only."""
from .. import web as http


class Teams:
    def __init__(self, cfg):
        self.url = cfg.get("webhook_url", "")
        self.configured = bool(self.url)

    def post(self, text, title=None):
        body = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
            "body": ([{"type": "TextBlock", "text": title, "weight": "Bolder"}] if title else []) + [{"type": "TextBlock", "text": text, "wrap": True}]}}]}
        return http.request("POST", self.url, body=body)[1]
