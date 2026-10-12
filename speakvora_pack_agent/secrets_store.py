"""Keys typed into the dashboard are kept in agent-state/secrets.json (readable only by you, mode 600) instead of environment variables, so a person who is not a developer never has to set one. agent.json still writes
"env:NAME" for every secret; a real environment variable wins over the file. The dashboard never shows a secret again after it is saved: only the last four characters."""
import json, os


def path(state_dir):
    return os.path.join(state_dir, "secrets.json")


def read(state_dir):
    try:
        return json.load(open(path(state_dir), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write(state_dir, store):
    os.makedirs(state_dir, exist_ok=True)
    tmp = path(state_dir) + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(store, f)
    os.replace(tmp, path(state_dir))
    os.chmod(path(state_dir), 0o600)


def set_value(state_dir, name, value):
    s = read(state_dir)
    if value in (None, ""):
        s.pop(name, None)
    else:
        s[name] = value
    write(state_dir, s)


def hint(value):
    """What the page may show about a saved secret."""
    v = str(value or "")
    return "" if not v else ("..." + v[-4:] if len(v) > 8 else "saved")
