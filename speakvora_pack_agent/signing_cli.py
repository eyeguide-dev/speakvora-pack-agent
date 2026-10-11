import json, urllib.request

from .connectors import signing


def send(cfg, path, url=""):
    body = open(path, "rb").read()
    url = url or f"http://{cfg['listen']['host']}:{cfg['listen']['port']}/event"
    req = urllib.request.Request(url, data=body, method="POST", headers={**signing.sign(cfg["events"]["secret"], body), "content-type": "application/json"})
    print(urllib.request.urlopen(req, timeout=15).read().decode())
    return 0
