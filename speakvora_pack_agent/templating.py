"""Plain {{path.to.value}} substitution. No code, no expressions: a payload can never run anything."""
import re

_RX = re.compile(r"\{\{\s*([\w.:\-]+)\s*\}\}")


def lookup(ctx, path):
    cur = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def render(text, ctx, pack=None):
    """{{customer.name}} from the context, {{slot:order_ready}} the spoken text of a pack slot, {{fact:hours}} a fact from agent.json."""
    def sub(m):
        key = m.group(1)
        if key.startswith("slot:") and pack:
            try:
                return pack.text(key[5:])
            except Exception:  # noqa: BLE001
                return ""
        if key.startswith("slotvar:") and pack:                       # the slot NAME comes from the context, e.g. a Slack command argument
            try:
                return pack.text(str(lookup(ctx, key[8:]) or ""))
            except Exception:  # noqa: BLE001
                return ""
        if key.startswith("t:"):                                      # a short glue word in the pack's language (see i18n.GLUE)
            from . import i18n
            try:
                return i18n.glue(key[2:], ctx.get("lang", "en"))
            except KeyError:
                return ""
        if key.startswith("fact:"):
            v = (ctx.get("facts") or {}).get(key[5:])
            return "" if v is None else str(v)
        v = lookup(ctx, key)
        return "" if v is None else str(v)
    return _RX.sub(sub, str(text))


def render_obj(o, ctx, pack=None):
    if isinstance(o, str):
        return render(o, ctx, pack)
    if isinstance(o, dict):
        return {k: render_obj(v, ctx, pack) for k, v in o.items()}
    if isinstance(o, list):
        return [render_obj(v, ctx, pack) for v in o]
    return o
