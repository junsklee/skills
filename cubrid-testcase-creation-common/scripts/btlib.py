#!/usr/bin/env python3
"""Builder-Tester report-server HTTP primitives + config (Python 3.6, stdlib)."""
import json
import os
import urllib.error
import urllib.request

DEFAULT_URL = "http://192.168.2.154:8091"
DEFAULT_WORKER_IPS = "192.168.2.154:8090"


class BuilderTesterError(Exception):
    """The Builder-Tester service is unreachable or returned an error."""


def builder_url():
    return os.environ.get("BUILDER_TESTER_URL", DEFAULT_URL).rstrip("/")


def worker_ips():
    raw = os.environ.get("BUILDER_TESTER_WORKER_IPS", DEFAULT_WORKER_IPS)
    return [w.strip() for w in raw.split(",") if w.strip()]


def bt_request(path, method="GET", data=None, timeout=60):
    url = path if path.startswith("http") else builder_url() + path
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "verify-testcase",
    })
    req.get_method = lambda: method
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise BuilderTesterError("HTTP %d from %s: %s"
                                 % (e.code, url, e.read().decode("utf-8", "replace")))
    except urllib.error.URLError as e:
        raise BuilderTesterError("cannot reach %s: %s" % (url, e))


def bt_get_text(path, timeout=60):
    url = path if path.startswith("http") else builder_url() + path
    req = urllib.request.Request(url, headers={"User-Agent": "verify-testcase"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise BuilderTesterError("HTTP %d from %s" % (e.code, url))
    except urllib.error.URLError as e:
        raise BuilderTesterError("cannot reach %s: %s" % (url, e))
