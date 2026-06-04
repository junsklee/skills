#!/usr/bin/env python3
"""Re-apply the local 'authenticate the read path' patch to cubrid-jira.

Why: cubrid-jira's `search` uses an UNauthenticated GET (cubrid_jira/http.py
`fetch_issue`), assuming anonymous browse is enabled. The jira.cubrid.org
instance requires auth even for reads, so `search` returns HTTP 401 without
this patch. We chose a LOCAL patch (no upstream PR), so `uv tool upgrade
cubrid-jira` will overwrite it — re-run this script afterward.

Usage (run with the tool's own interpreter, where cubrid_jira is importable):
    ~/.local/share/uv/tools/cubrid-jira/bin/python3 \\
        ~/skills/cubrid-jira-ops/references/apply-read-auth-patch.py
    # add --check to only report status (exit 0 patched, 1 not patched)

Idempotent: safe to run repeatedly; a no-op if already patched.
"""
from __future__ import annotations

import sys

OLD = '''def fetch_issue(key: str) -> dict:
    """Unauthenticated GET for an issue's full JSON.

    Kept separate from :class:`JiraClient` because the read-only fetch flow
    must not require credentials — the public CUBRID JIRA happily serves
    issue JSON without auth.
    """
    url = f"{REST_API}/{key}?expand=renderedFields"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:'''

NEW = '''def _optional_credentials() -> "tuple[str, str] | None":
    """Best-effort credential lookup for read requests.

    LOCAL PATCH: this JIRA instance requires auth even for reads, so the read
    path must send Basic auth when credentials are available. Unlike
    ``auth.resolve_credentials`` this never exits — it returns ``None`` so
    anonymous reads still work wherever the server allows them.
    """
    import netrc as _netrc
    import os

    user = os.environ.get("CUBRID_JIRA_USER")
    pw = os.environ.get("CUBRID_JIRA_PASSWORD")
    if user and pw:
        return user, pw
    try:
        auth = _netrc.netrc().authenticators("jira.cubrid.org")
    except Exception:
        return None
    if auth and auth[0] and auth[2]:
        return auth[0], auth[2]
    return None


def fetch_issue(key: str) -> dict:
    """GET an issue's full JSON.

    Sends Basic auth when credentials are resolvable (env or ``~/.netrc``),
    falling back to an anonymous request where the server allows it. (LOCAL
    PATCH — upstream sends no auth on reads.)
    """
    url = f"{REST_API}/{key}?expand=renderedFields"
    headers = {"Accept": "application/json"}
    creds = _optional_credentials()
    if creds:
        headers["Authorization"] = basic_auth_header(*creds)
    req = urllib.request.Request(url, headers=headers)
    try:'''

MARKER = "_optional_credentials"


def locate() -> str:
    try:
        import cubrid_jira.http as h
    except ImportError:
        sys.exit("Error: cubrid_jira not importable. Run with the tool's "
                 "interpreter:\n"
                 "  ~/.local/share/uv/tools/cubrid-jira/bin/python3 "
                 "~/skills/cubrid-jira-ops/references/apply-read-auth-patch.py")
    return h.__file__


def main() -> None:
    check_only = "--check" in sys.argv[1:]
    path = locate()
    text = open(path, encoding="utf-8").read()

    if MARKER in text:
        print(f"Already patched: {path}")
        sys.exit(0)
    if check_only:
        print(f"NOT patched: {path}")
        sys.exit(1)
    if OLD not in text:
        sys.exit(f"Error: anchor not found in {path}. cubrid-jira's source "
                 "changed; update OLD/NEW in this script to match.")

    open(path, "w", encoding="utf-8").write(text.replace(OLD, NEW, 1))
    print(f"Patched: {path}")


if __name__ == "__main__":
    main()
