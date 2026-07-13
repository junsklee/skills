#!/usr/bin/env python3
"""Fetch a CUBRID test-case PR into a local review bundle.

Stdlib-only, Python 3.6 compatible. Reads GITHUB_TOKEN from the environment
(set unexported in ~/.bash_profile -- call via: bash -lc 'export GITHUB_TOKEN; ...').

Usage:
    python3 fetch_pr.py <pr-ref> --out <dir> [--max-file-bytes N] [--max-total-bytes N]

<pr-ref> accepts https://github.com/OWNER/REPO/pull/N or OWNER/REPO#N.

Writes:
    <out>/bundle.json   # meta, jira_key, categories, existing reviews, ci, truncation notes
    <out>/pr.diff       # unified diff of the PR
    <out>/files/<path>  # full head-state content of each changed file (capped)
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"

_JIRA_RE = re.compile(r"CBRD[-_](\d+)", re.IGNORECASE)
_PATH_RE = re.compile(r"cbrd[_-](\d+)", re.IGNORECASE)
_URL_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")
_SHORT_RE = re.compile(r"^([^/\s#]+)/([^/\s#]+)#(\d+)$")


def parse_pr_url(url):
    """Accept https://github.com/OWNER/REPO/pull/N[/...] or OWNER/REPO#N."""
    m = _URL_RE.search(url)
    if not m:
        m = _SHORT_RE.match(url.strip())
    if not m:
        raise ValueError("unrecognized PR reference: " + url)
    return m.group(1), m.group(2), int(m.group(3))


def extract_jira_key(title, body, paths):
    """Resolve the CBRD issue key.

    Priority: PR body line 1, body line 2, anywhere in body, PR title,
    then cbrd_xxxxx tokens in changed paths. Returns None when absent.
    """
    body = body or ""
    lines = body.splitlines()
    candidates = [
        lines[0] if lines else "",
        lines[1] if len(lines) > 1 else "",
        body,
        title or "",
    ]
    for chunk in candidates:
        m = _JIRA_RE.search(chunk)
        if m:
            return "CBRD-" + m.group(1)
    for p in paths or []:
        m = _PATH_RE.search(p)
        if m:
            return "CBRD-" + m.group(1)
    return None


def detect_categories(paths):
    """Map changed paths to review categories.

    Keys present only when non-empty:
      sql            -- sql/ and medium/ trees (same doctrine)
      shell          -- shell/ tree except excluded lists
      excluded_list  -- shell/config/*excluded_list* regression exclusions
      other          -- everything else (generic rules + "rules not loaded" flag)
    """
    cats = {}
    for p in paths:
        if p.startswith("shell/config/") and "excluded_list" in p:
            cats.setdefault("excluded_list", []).append(p)
        elif p.startswith("sql/") or p.startswith("medium/"):
            cats.setdefault("sql", []).append(p)
        elif p.startswith("shell/"):
            cats.setdefault("shell", []).append(p)
        else:
            cats.setdefault("other", []).append(p)
    return cats
