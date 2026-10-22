"""Jira and Confluence Cloud, with the customer's own Atlassian account (site address, email, API token). The agent turns a bug report into a Jira Bug (or adds evidence to the matching one) and keeps a known-issues page in Confluence.
What it never does: invent a cause or a fix. It records what was reported, in the reporter's words, with card numbers, passwords, keys and other secrets removed, and marks everything it does not know as unknown."""
import base64, hashlib, html, re, time
from urllib.parse import quote

from .. import web as http

STOP = set("the a an and or but is are was were be been it its this that to of in on at for with my me i we you our your not no cant cannot can wont dont doesnt didnt after when then so just very really please help up down out again still keeps keep tried try".split())


# ---- privacy and wording (no network) -----------------------------------------------------------------------------------------------------------------------------------------------------------
_PAT = [
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[card number removed]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[ID number removed]"),
    (re.compile(r"(?i)\b(?:password|passcode|passwd|pwd|pin|secret|token|api[ _-]?key)\s*(?:is|:|=)\s*\S+"), "[secret removed]"),
    (re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{8,}\b"), "[key removed]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{8,}\b"), "[key removed]"),
    (re.compile(r"\bAKIA[0-9A-Z]{12,}\b"), "[key removed]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\b"), "[token removed]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"), "[token removed]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email removed]"),
    (re.compile(r"(?<![\w])\+?\d[\d\s().-]{8,}\d(?![\w])"), "[phone removed]"),
]


def redact(text):
    """Removes what must never reach a ticket: card numbers, ID numbers, passwords, keys, tokens, email addresses and phone numbers."""
    t = str(text or "")
    for rx, rep in _PAT:
        t = rx.sub(rep, t)
    return t


def clean(text, limit=1500):
    return re.sub(r"\s+", " ", redact(text)).strip()[:limit]


def words(text):
    """The telling words of a report, cut to their first five letters so press, pressing and pressed count as one."""
    t = re.sub(r"\[[^\]]*removed\]", " ", str(text or "").lower())            # the privacy placeholders are not part of the problem
    return sorted({w[:5] for w in re.findall(r"[a-z]+", t) if len(w) > 2 and w not in STOP})[:14]


def similar(a, b):
    """0 to 1: how much two reports are about the same thing."""
    a, b = set(a), set(b)
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter >= 3 and inter / min(len(a), len(b)) >= 0.75:           # a short report that is mostly contained in a longer one about the same thing
        return 1.0
    return inter / len(a | b)


def fingerprint(text):
    """A short code for a report's telling words. It is put on the ticket as a label, so a later report finds the ticket even if this agent lost its memory."""
    ws = words(redact(text))
    return "sv-" + hashlib.sha256(" ".join(ws).encode()).hexdigest()[:10] if ws else ""


def summary_of(text, limit=110):
    t = clean(text, 400)
    first = re.split(r"(?<=[.!?])\s", t, maxsplit=1)[0] or t
    return first[:limit].rstrip(" .,;:") or "Customer reported a problem"


def adf(blocks):
    """Atlassian Document Format from a list of ('p', text) / ('h', text) / ('li', [text, ...])."""
    out = []
    for kind, v in blocks:
        if kind == "h":
            out.append({"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": str(v)[:200]}]})
        elif kind == "li":
            out.append({"type": "bulletList", "content": [{"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": str(x)[:500]}]}]} for x in v]})
        else:
            out.append({"type": "paragraph", "content": [{"type": "text", "text": str(v)[:3000]}]})
    return {"type": "doc", "version": 1, "content": out}


def bug_description(text, source="", app_version="", reported_at="", count=1, extra=None):
    """What goes in the ticket. Everything the reporter did not say is marked Unknown, and the cause is stated as not determined."""
    rows = [("h", "Reported problem (reporter's words, private details removed)"), ("p", clean(text, 2500) or "Unknown"),
            ("h", "Details"), ("li", [f"Reported through: {source or 'Unknown'}", f"Reported at: {reported_at or time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}",
                                      f"App version: {app_version or 'Unknown'}", f"Reports so far: {count}"]),
            ("h", "Not known yet"), ("li", ["Steps to reproduce: Unknown", "Expected behavior: Unknown", "Root cause: not determined", "Fix: none confirmed"])]
    for k, v in (extra or {}).items():
        rows.append(("p", f"{k}: {clean(v, 300)}"))
    rows.append(("p", "Created by the Speakvora agent from a customer or system report. Treat it as a report, not a diagnosis."))
    return adf(rows)


class Atlassian:
    def __init__(self, cfg):
        cfg = cfg or {}
        self.site = str(cfg.get("site", "")).strip().rstrip("/")
        if self.site and not self.site.startswith("http"):
            self.site = "https://" + self.site
        self.email, self.token = cfg.get("email", ""), cfg.get("api_token", "")
        self.project, self.issue_type = cfg.get("project", ""), cfg.get("issue_type") or "Bug"
        self.labels = [str(x) for x in (cfg.get("labels") or ["speakvora"])]
        self.story_link_type = cfg.get("link_type") or "Relates"
        self.space, self.page = cfg.get("space", ""), cfg.get("page_title") or "Known issues"
        self.configured = bool(self.site and self.email and self.token)
        self.jira_ready = bool(self.configured and self.project)
        self.docs_ready = bool(self.configured and self.space)

    def _h(self):
        return {"authorization": "Basic " + base64.b64encode(f"{self.email}:{self.token}".encode()).decode(), "accept": "application/json"}

    def _call(self, method, path, body=None):
        return http.request(method, self.site + path, self._h(), body=body, timeout=25)

    def link(self, key):
        return f"{self.site}/browse/{key}"

    # ---- Jira -------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    def myself(self):
        return self._call("GET", "/rest/api/3/myself")[1]

    def project_info(self):
        return self._call("GET", f"/rest/api/3/project/{quote(self.project)}")[1]

    def search(self, jql, limit=5):
        st, r = self._call("POST", "/rest/api/3/search/jql", {"jql": jql, "maxResults": limit, "fields": ["summary", "status", "labels"]})
        return (r or {}).get("issues", []) if isinstance(r, dict) else []

    def find_duplicate(self, fp, error_id=""):
        hit = self.search(f'project = "{self.project}" AND labels = "{fp}" AND statusCategory != Done ORDER BY created DESC', 1)
        if not hit and error_id:
            hit = self.search(f'project = "{self.project}" AND issuetype = "{self.issue_type}" AND statusCategory != Done AND text ~ "\\"{error_id}\\"" ORDER BY created DESC', 1)
        return hit[0]["key"] if hit else ""

    def create_bug(self, summary, description, labels):
        fields = {"project": {"key": self.project}, "summary": summary[:250], "issuetype": {"name": self.issue_type}, "description": description, "labels": labels}
        return self._call("POST", "/rest/api/3/issue", {"fields": fields})[1]["key"]

    def comment(self, key, blocks):
        return self._call("POST", f"/rest/api/3/issue/{quote(key)}/comment", {"body": adf(blocks)})[1]

    def link_issues(self, bug, story):
        return self._call("POST", "/rest/api/3/issueLink", {"type": {"name": self.story_link_type}, "inwardIssue": {"key": bug}, "outwardIssue": {"key": story}})

    # ---- Confluence ---------------------------------------------------------------------------------------------------------------------------------------------------------------
    def space_id(self):
        r = self._call("GET", f"/wiki/api/v2/spaces?keys={quote(self.space)}")[1]
        res = (r or {}).get("results") or []
        if not res:                                                      # people type the space's name (Engineering) instead of its key (ENG): find it by name too
            every = (self._call("GET", "/wiki/api/v2/spaces?limit=100")[1] or {}).get("results") or []
            res = [x for x in every if str(x.get("name", "")).lower() == self.space.lower() or str(x.get("key", "")).lower() == self.space.lower()][:1]
        if not res:
            raise http.HttpError(404, f"Confluence space {self.space} not found")
        return res[0]["id"]

    def find_page(self, sid):
        r = self._call("GET", f"/wiki/api/v2/pages?space-id={sid}&title={quote(self.page)}&body-format=storage")[1]
        res = (r or {}).get("results") or []
        return res[0] if res else None

    TABLE_HEAD = "<tr><th>Ticket</th><th>Problem</th><th>Status</th><th>Reports</th><th>First reported</th><th>Resolved</th><th>Workaround or fix (verified only)</th></tr>"

    @staticmethod
    def row(key, url, summary, status, reports, opened, resolved="", note=""):
        e = lambda s: html.escape(str(s or ""), quote=True)
        return (f'<tr><td><a href="{e(url)}">{e(key)}</a></td><td>{e(summary)}</td><td>{e(status)}</td><td>{e(reports)}</td><td>{e(opened)}</td><td>{e(resolved)}</td><td>{e(note) or "None confirmed"}</td></tr>')

    def log(self, key, summary, status, reports=1, opened="", resolved="", note=""):
        """Adds a row to the known-issues page, or changes the row of the same ticket. Creates the page the first time."""
        sid = self.space_id(); pg = self.find_page(sid); row = self.row(key, self.link(key), summary, status, reports, opened or time.strftime("%Y-%m-%d"), resolved, note)
        if not pg:
            body = ("<p>Bugs reported to the Speakvora agent and how they ended. Rows are added and changed automatically; the workaround column holds only what the team verified.</p>"
                    f"<table><tbody>{self.TABLE_HEAD}{row}</tbody></table>")
            r = self._call("POST", "/wiki/api/v2/pages", {"spaceId": sid, "status": "current", "title": self.page, "body": {"representation": "storage", "value": body}})[1]
            return {"page": r.get("id"), "created": True}
        cur = (pg.get("body") or {}).get("storage", {}).get("value", "")
        rx = re.compile(r"<tr[^>]*>(?:(?!</tr>).)*?/browse/" + re.escape(key) + r'"(?:(?!</tr>).)*</tr>', re.S)            # Confluence may rewrite attributes, so the row is found by its ticket link
        found = rx.search(cur)
        if found:
            if not note:                                      # keep what the team already wrote in the note column
                m = re.findall(r"<td>(.*?)</td>", found.group(0), re.S)
                if len(m) >= 7 and "None confirmed" not in m[6]:
                    row = row.replace("None confirmed", m[6])
            new = cur.replace(found.group(0), row)
        elif "</tbody>" in cur:
            new = cur.replace("</tbody>", row + "</tbody>", 1)
        else:
            new = cur + f"<table><tbody>{self.TABLE_HEAD}{row}</tbody></table>"
        num = int((pg.get("version") or {}).get("number", 1)) + 1
        self._call("PUT", f"/wiki/api/v2/pages/{pg['id']}", {"id": pg["id"], "status": "current", "title": self.page, "body": {"representation": "storage", "value": new}, "version": {"number": num, "message": f"{key}: {status}"}})
        return {"page": pg["id"], "created": False}
