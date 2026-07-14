#!/usr/bin/env python3
"""Shared GitHub REST helpers for the test-case creation suite (Python 3.6, stdlib)."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


def token():
    t = os.environ.get("GITHUB_TOKEN")
    if not t:
        sys.exit("GITHUB_TOKEN is not set; run via: bash -lc 'export GITHUB_TOKEN; ...'")
    return t


def gh_request(path, tok, accept="application/vnd.github+json", raw=False,
               method=None, data=None):
    url = path if path.startswith("http") else API + path
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": "Bearer " + tok,
        "Accept": accept,
        "User-Agent": "create-cubrid-testcase",
        "Content-Type": "application/json",
    })
    if method:
        req.get_method = lambda: method
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read()
    return payload if raw else json.loads(payload.decode("utf-8"))


def gh_paginate(path, tok, max_pages=10):
    out = []
    sep = "&" if "?" in path else "?"
    for page in range(1, max_pages + 1):
        chunk = gh_request(path + sep + "per_page=100&page=" + str(page), tok)
        out.extend(chunk)
        if len(chunk) < 100:
            break
    return out


def parse_repo(ref):
    """'OWNER/REPO' -> (owner, repo); ValueError otherwise."""
    parts = ref.strip().split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("expected OWNER/REPO, got: " + ref)
    return parts[0], parts[1]
