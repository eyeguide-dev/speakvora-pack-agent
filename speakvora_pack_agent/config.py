"""agent.json: where the pack is, which services to connect and the safety limits. Secrets are never written in the file: write "env:NAME" and put the value in an environment variable."""
import json, os

DEFAULTS = {
    "dry_run": True,                                   # nothing is sent until you turn this off on purpose
    "pack": "./pack", "workflows": "./workflows.json", "state_dir": "./agent-state",
    "listen": {"host": "127.0.0.1", "port": 8787}, "public_base_url": "",
    "timezone": "UTC", "quiet_hours": {"start": "21:00", "end": "08:00", "applies_to": ["call", "sms"]},
    "limits": {"per_recipient_per_day": 3, "per_hour": 60},
    "consent": {"field": "customer.sms_consent", "required": True},
    "events": {"secret": ""}, "facts": {},
    "mode": "standard", "compliance": {"sms_footer": "first", "extra_required": []}, "sms_provider": {}, "call_provider": {},
    "twilio": {}, "slack": {}, "google_calendar": {}, "email": {}, "webhooks": {}, "sources": [], "http": {}, "teams": {}, "microsoft_calendar": {}, "inbox": {},
}


class ConfigError(Exception):
    pass


def resolve(v, missing=None):
    """env:NAME -> the variable's value. With a `missing` list, unset variables become "" and are recorded (used by check/slots so you can inspect a pack before keys exist); without it they raise."""
    if isinstance(v, str) and v.startswith("env:"):
        name = v[4:]
        val = os.environ.get(name)
        if val is None:
            if missing is not None:
                missing.append(name); return ""
            raise ConfigError(f"Environment variable {name} is not set (agent.json asks for it).")
        return val
    if isinstance(v, dict):
        return {k: resolve(x, missing) for k, x in v.items()}
    if isinstance(v, list):
        return [resolve(x, missing) for x in v]
    return v


def merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = merge(out[k], v) if isinstance(out.get(k), dict) and isinstance(v, dict) else v
    return out


MODES = {   # how tightly the agent limits itself; you can still override any single value. Opt-outs (STOP), required notices and the kill switch are ALWAYS on in every mode.
    "strict": {"limits": {"per_recipient_per_day": 2, "per_hour": 30}, "quiet_hours": {"start": "20:00", "end": "09:00", "applies_to": ["call", "sms"]}},
    "standard": {},
    "open": {"limits": {"per_recipient_per_day": None, "per_hour": None}, "quiet_hours": {"start": "00:00", "end": "00:00", "applies_to": []}},
}


def load(path, lazy_secrets=False):
    raw = json.load(open(path, encoding="utf-8"))
    mode = raw.get("mode", "standard")
    if mode not in MODES:
        raise ConfigError(f"mode must be one of {sorted(MODES)}")
    cfg = merge(merge(DEFAULTS, MODES[mode]), raw)
    base = os.path.dirname(os.path.abspath(path))
    for k in ("pack", "workflows", "state_dir"):
        if not os.path.isabs(cfg[k]):
            cfg[k] = os.path.normpath(os.path.join(base, cfg[k]))
    missing = [] if lazy_secrets else None
    cfg = {k: (resolve(v, missing) if k not in ("pack", "workflows", "state_dir") else v) for k, v in cfg.items()}
    if lazy_secrets:
        cfg["_missing_env"] = sorted(set(missing))
    return cfg
