#!/usr/bin/env python3
"""Resolve the engine PR (CUBRID/cubrid) linked to a CBRD issue via the JIRA
dev-status pull-request panel — which `cubrid-jira search` output lacks."""
import sys, json, urllib.request, urllib.error, netrc, base64
BASE = "http://jira.cubrid.org"                 # https 302-redirects to http
ENGINE_REPO = "github.com/CUBRID/cubrid/pull/"  # the engine repo, not *-testcases*

def _auth():
    login, _, pw = netrc.netrc().authenticators("jira.cubrid.org")
    return {"Authorization": "Basic " + base64.b64encode(f"{login}:{pw}".encode()).decode()}
def _get(path):
    with urllib.request.urlopen(urllib.request.Request(BASE + path, headers=_auth()), timeout=30) as r:
        return json.load(r)
def main(key):
    iid = _get(f"/rest/api/2/issue/{key}?fields=id")["id"]
    data = _get(f"/rest/dev-status/1.0/issue/detail?issueId={iid}"
                f"&applicationType=github&dataType=pullrequest")   # applicationType MUST be lowercase
    prs = [p for d in data.get("detail", []) for p in d.get("pullRequests", [])]
    engine = [p for p in prs if ENGINE_REPO in (p.get("url") or "")]
    if not engine:
        print(f"# no CUBRID/cubrid PR linked to {key}", file=sys.stderr); return 2
    engine.sort(key=lambda p: (key.upper() not in (p.get("name") or "").upper(),  # same JIRA key = the fix
                               p.get("status") != "MERGED",
                               -int(p["url"].rstrip("/").split("/")[-1])))
    for p in engine:
        tag = "engine" if key.upper() in (p.get("name") or "").upper() else "other-repo-pr"
        print(f"{p['status']}\t{p['url']}\t[{tag}] {p['name']}")
    return 0
if __name__ == "__main__":
    try: sys.exit(main(sys.argv[1]))
    except (urllib.error.URLError, KeyError, netrc.NetrcParseError, IndexError) as e:
        print(f"# error: {e}", file=sys.stderr); sys.exit(1)
