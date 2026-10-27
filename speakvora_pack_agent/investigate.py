"""Investigation context for a new bug ticket: evidence, never a diagnosis.

When the owner connected a code host (agent.json "code": {"provider": "github" | "gitlab", "repo": "owner/name" (or a GitLab project id), "token": "env:..."}) a new ticket gets a section
"Possible causes (evidence, not a diagnosis)":
  1. the files that changed between the previous deploy and the deploy the report follows (names and +/- counts only, at most 15, never file contents or diffs)
  2. the first lines of the stack trace the report carried (private details removed, at most 12 lines)
  3. up to 5 recent log lines the site sent (private details removed)
  4. up to 3 possible causes, ranked by plain word matching (no AI): changed files whose path shares words with a stack frame or with the page or action
If there is no code host, no previous deploy, or the code host does not answer, nothing is added and the ticket is created exactly as before. The token is only ever sent as a request header
to the code host; it is never written to a ticket, a message or the log.
"""
import json, re, urllib.request

from . import changes
from .connectors import atlassian as AT

MAX_FILES, MAX_STACK, MAX_LOGS, MAX_CAUSES = 15, 12, 5, 3
SENSITIVE = re.compile(r"(^|[/._-])(env|secrets?|credentials?|passwords?|passwd|id_rsa|id_dsa|id_ed25519|npmrc|netrc|htpasswd|keystore|pem|p12|pfx|kdbx)([/._-]|$)|\.env|private[_-]?key|api[_-]?key|token", re.I)
NOISE = set("index main src lib app js ts tsx jsx py rb go java mjs cjs min test tests spec node_modules anonymous async await new object module function promise native internal call apply error exception the and for with from at in is on of to com www http https file line".split())


def _get(url, headers, timeout=8):
    """One GET that returns parsed JSON. Replaced in tests. https only; the answer is read up to 3 MB."""
    if not str(url).lower().startswith("https://"):
        raise ValueError("https only")
    req = urllib.request.Request(url, headers=dict(headers or {}), method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:                 # noqa: S310 - https checked above, host chosen by the owner in agent.json
        return json.loads(r.read(3_000_000).decode("utf-8", "replace"))


def _code(agent):
    c = agent.cfg.get("code") or {}
    prov, repo, tok = str(c.get("provider") or "").lower(), str(c.get("repo") or "").strip(), str(c.get("token") or "")
    if prov not in ("github", "gitlab") or not repo or not tok or tok.startswith("env:"):          # an unset variable is "" (or still env:...): no token means no look
        return None
    return {"provider": prov, "repo": repo, "token": tok, "api": str(c.get("api_base") or "").rstrip("/"), "web": str(c.get("web_url") or "").rstrip("/")}


def error_of(ctx):
    """The error the report carried: ctx.error, or ctx.data.error (how an app event arrives)."""
    for e in (ctx.get("error"), (ctx.get("data") or {}).get("error") if isinstance(ctx.get("data"), dict) else None):
        if isinstance(e, dict):
            return e
    return {}


def sensitive(path):
    return bool(SENSITIVE.search(str(path)))


def _tokens(text):
    out = []
    for part in re.findall(r"[A-Za-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))):
        w = part.lower()
        if len(w) >= 3 and w not in NOISE and not w.isdigit() and w not in out:
            out.append(w)
    return out


def _frames(stack):
    """[(frame text, set of words from its file and function)] for the first stack lines."""
    out = []
    for ln in stack:
        words = set(_tokens(ln.replace("node_modules", " ")))
        if words:
            out.append((ln, words))
    return out


def _compare(code, base, head):
    """(files [(path, +, -)], web link, error). Names and counts only: nothing else in the answer is kept."""
    hdr = {"accept": "application/json", "user-agent": "SpeakvoraAgent"}
    if code["provider"] == "github":
        hdr.update({"authorization": "Bearer " + code["token"], "accept": "application/vnd.github+json"})
        url = f"{code['api'] or 'https://api.github.com'}/repos/{code['repo']}/compare/{base}...{head}"
        d = _get(url, hdr)
        files = [(str(f.get("filename") or ""), int(f.get("additions") or 0), int(f.get("deletions") or 0)) for f in (d.get("files") or []) if isinstance(f, dict) and f.get("filename")]
        web = str(d.get("html_url") or "") or f"{code['web'] or 'https://github.com'}/{code['repo']}/compare/{base}...{head}"
    else:
        hdr["private-token"] = code["token"]
        from urllib.parse import quote
        url = f"{code['api'] or 'https://gitlab.com/api/v4'}/projects/{quote(code['repo'], safe='')}/repository/compare?from={base}&to={head}"
        d = _get(url, hdr)
        files = []
        for f in (d.get("diffs") or []):
            if not isinstance(f, dict):
                continue
            lines = str(f.get("diff") or "").split("\n")                  # only counted here, never kept or shown
            files.append((str(f.get("new_path") or f.get("old_path") or ""), sum(1 for x in lines if x.startswith("+") and not x.startswith("+++")), sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))))
        files = [f for f in files if f[0]]
        web = str(d.get("web_url") or "") or (f"{code['web'] or 'https://gitlab.com'}/{code['repo']}/-/compare/{base}...{head}" if "/" in code["repo"] else "")
    return files, web


def _rank(files, frames, page_words):
    """Up to 3 changed files, best first, each with the sentence that explains the match. Plain word overlap, no AI."""
    scored = []
    for path, add, dele in files:
        pw = set(_tokens(path)); stem = set(_tokens(path.rsplit("/", 1)[-1])); best = (0, "")
        for ln, fw in frames:
            shared = pw & fw
            if shared:
                s = 2 * len(shared) + 2 * len(stem & fw)
                if s > best[0]:
                    best = (s, "Matches stack frame " + AT.clean(ln, 120))
        pshared = pw & page_words
        if pshared and best[0] < 1 + len(pshared):
            best = (1 + len(pshared), "Matches the page or action word '" + sorted(pshared)[0] + "', not a stack frame")
        if best[0]:
            scored.append((best[0], path, add, dele, best[1]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[:MAX_CAUSES]


def section(agent, ctx, hint=None, error=None):
    """The blocks to add to a new ticket ([] when there is nothing to say). Never raises."""
    try:
        code = _code(agent)
        if not code or agent.dry:
            return []
        hint = hint or {}
        head, _note = changes.pick(agent, hint=hint)
        prev = changes.previous(agent, head) if head else None
        if not head or not prev or not head.get("sha") or not prev.get("sha"):
            return []
        files, web = _compare(code, prev["sha"], head["sha"])
        if not files:
            return []
        err = error if isinstance(error, dict) else error_of(ctx)
        stack_raw = err.get("stack"); stack_lines = stack_raw if isinstance(stack_raw, list) else str(stack_raw or "").splitlines()
        stack = [AT.clean(x, 200) for x in stack_lines if str(x).strip()][:MAX_STACK]
        logs = [AT.clean(x, 200) for x in (err.get("logs") if isinstance(err.get("logs"), list) else []) if str(x).strip()][-MAX_LOGS:]
        page_words = set(_tokens(" ".join(str(err.get(k) or hint.get(k) or "") for k in ("page", "action"))))
        listed = [f"{p} (+{a} -{d})" + (" (sensitive file name)" if sensitive(p) else "") for p, a, d in files[:MAX_FILES]]
        blocks = [("h", "Possible causes (evidence, not a diagnosis)"),
                  ("p", f"Files changed between the previous deploy ({prev['sha']}) and the one before this report ({head['sha']}): {len(files)}" + (f", showing the first {MAX_FILES}" if len(files) > MAX_FILES else "") + ". Names and line counts only; no file contents were read."),
                  ("li", listed)]
        if web:
            blocks.append(("p", "Compare: " + web))
        if stack:
            blocks += [("p", "First lines of the stack trace the report carried (private details removed):"), ("li", stack)]
        if logs:
            blocks += [("p", "Recent log lines the site sent (private details removed):"), ("li", logs)]
        ranked = _rank(files, _frames(stack), page_words)
        if ranked:
            blocks += [("p", "Files that may be related, by matching words only (a lead to check, not a conclusion):"),
                       ("li", [f"{p}{' (sensitive file name)' if sensitive(p) else ''}: {why}. Evidence: {web or 'the compare link above'}" for _s, p, _a, _d, why in ranked])]
        return blocks
    except Exception as e:  # noqa: BLE001 - the ticket is created without this section; only the kind of failure is logged, never a message that could carry a token
        try:
            agent.state.log(workflow="investigate", status="skipped", reason=type(e).__name__ + (":" + str(getattr(e, "code", "")) if getattr(e, "code", None) else ""))
        except Exception:  # noqa: BLE001
            pass
        return []
