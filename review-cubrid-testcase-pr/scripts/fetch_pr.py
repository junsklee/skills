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


def gh_request(path, token, accept="application/vnd.github+json", raw=False):
    url = path if path.startswith("http") else API + path
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": accept,
        "User-Agent": "review-cubrid-testcase-pr",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    return data if raw else json.loads(data.decode("utf-8"))


def gh_paginate(path, token, max_pages=10):
    out = []
    sep = "&" if "?" in path else "?"
    for page in range(1, max_pages + 1):
        chunk = gh_request(path + sep + "per_page=100&page=" + str(page), token)
        out.extend(chunk)
        if len(chunk) < 100:
            break
    return out


def fetch_file(owner, repo, path, ref, token):
    quoted = urllib.parse.quote(path)
    return gh_request(
        "/repos/%s/%s/contents/%s?ref=%s" % (owner, repo, quoted, ref),
        token, accept="application/vnd.github.raw", raw=True)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr", help="PR URL or OWNER/REPO#N")
    ap.add_argument("--out", required=True, help="output bundle directory")
    ap.add_argument("--max-file-bytes", type=int, default=200000)
    ap.add_argument("--max-total-bytes", type=int, default=2000000)
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set; run via: bash -lc 'export GITHUB_TOKEN; ...'")

    owner, repo, number = parse_pr_url(args.pr)
    base = "/repos/%s/%s" % (owner, repo)

    pr = gh_request("%s/pulls/%d" % (base, number), token)
    diff = gh_request("%s/pulls/%d" % (base, number), token,
                      accept="application/vnd.github.diff", raw=True)
    files = gh_paginate("%s/pulls/%d/files" % (base, number), token)
    commits = gh_paginate("%s/pulls/%d/commits" % (base, number), token)
    reviews = gh_paginate("%s/pulls/%d/reviews" % (base, number), token)
    review_comments = gh_paginate("%s/pulls/%d/comments" % (base, number), token)
    issue_comments = gh_paginate("%s/issues/%d/comments" % (base, number), token)
    head_sha = pr["head"]["sha"]
    try:
        checks = gh_request("%s/commits/%s/check-runs" % (base, head_sha), token)
    except urllib.error.HTTPError:
        checks = {}
    try:
        status = gh_request("%s/commits/%s/status" % (base, head_sha), token)
    except urllib.error.HTTPError:
        status = {}

    paths = [f["filename"] for f in files]
    jira_key = extract_jira_key(pr.get("title"), pr.get("body"), paths)
    categories = detect_categories(paths)

    files_dir = os.path.abspath(os.path.join(args.out, "files"))
    os.makedirs(files_dir, exist_ok=True)
    truncated = []
    total = 0
    for f in files:
        name = f["filename"]
        if f.get("status") == "removed":
            continue
        # repo paths are relative; refuse anything that would escape files_dir
        dest = os.path.normpath(os.path.join(files_dir, name))
        if not dest.startswith(files_dir + os.sep):
            dest = os.path.join(files_dir, name.replace("..", "__"))
        if total >= args.max_total_bytes:
            truncated.append({"path": name, "reason": "total-cap"})
            continue
        try:
            blob = fetch_file(owner, repo, name, head_sha, token)
        except urllib.error.HTTPError as e:
            truncated.append({"path": name, "reason": "fetch-error-%d" % e.code})
            continue
        if len(blob) > args.max_file_bytes:
            blob = blob[:args.max_file_bytes]
            truncated.append({"path": name, "reason": "file-cap"})
        total += len(blob)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(blob)

    bundle = {
        "pr": {
            "owner": owner, "repo": repo, "number": number,
            "title": pr.get("title"), "body": pr.get("body"),
            "state": pr.get("state"), "draft": pr.get("draft"),
            "base": pr["base"]["ref"], "head_sha": head_sha,
            "user": pr["user"]["login"], "html_url": pr.get("html_url"),
        },
        "commits": [{"sha": c["sha"], "message": c["commit"]["message"]}
                    for c in commits],
        "changed_files": [{"path": f["filename"], "status": f["status"],
                           "additions": f["additions"], "deletions": f["deletions"],
                           "patch": f.get("patch")} for f in files],
        "jira_key": jira_key,
        "categories": categories,
        "existing_reviews": [{"user": r["user"]["login"], "state": r["state"],
                              "body": r.get("body")} for r in reviews],
        "existing_review_comments": [{"user": c["user"]["login"],
                                      "path": c.get("path"),
                                      "line": c.get("line") or c.get("original_line"),
                                      "body": c.get("body")}
                                     for c in review_comments],
        "existing_issue_comments": [{"user": c["user"]["login"], "body": c.get("body")}
                                    for c in issue_comments],
        "ci": {"check_runs": [{"name": c.get("name"), "conclusion": c.get("conclusion")}
                              for c in (checks.get("check_runs") or [])],
               "combined_status": status.get("state")},
        "truncated": truncated,
    }
    with open(os.path.join(args.out, "pr.diff"), "wb") as fh:
        fh.write(diff)
    with open(os.path.join(args.out, "bundle.json"), "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, ensure_ascii=False)
    print("bundle: %s | files: %d | truncated: %d | jira: %s | categories: %s"
          % (args.out, len(files), len(truncated), jira_key,
             ",".join(sorted(categories))))


if __name__ == "__main__":
    main()
