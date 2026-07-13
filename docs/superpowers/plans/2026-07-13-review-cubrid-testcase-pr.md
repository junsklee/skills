# review-cubrid-testcase-pr Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `review-cubrid-testcase-pr` skill: a thin orchestrator that fetches a CUBRID test-case PR + JIRA context, delegates review to a subagent armed with category doctrine, renders a Korean review locally, and posts it to the PR only after explicit user confirmation.

**Architecture:** One skill directory in `~/skills` (worktree checkout of branch `feat/review-cubrid-testcase-pr`). Two stdlib-only Python scripts do all GitHub REST traffic (`fetch_pr.py` read, `post_review.py` write with dry-run default). Four reference files carry the review doctrine; SKILL.md orchestrates: fetch → enrich → route by category → spawn reviewer subagent (fan-out >4 test-case dirs) → confirm → post.

**Tech Stack:** Python 3.6.8 stdlib only (urllib, json, argparse, unittest), GitHub REST API v3, `cubrid-jira` CLI (optional enrichment), Claude Code skill format (`SKILL.md` + `scripts/` + `references/`).

**Spec:** `docs/superpowers/specs/2026-07-13-review-cubrid-testcase-pr-design.md` (same branch — read it before starting).

## Global Constraints

- All work happens in the worktree `~/worktrees/skills-review-cubrid-testcase-pr` on branch `feat/review-cubrid-testcase-pr` (already created; `git worktree list` confirms). Never switch `~/skills` itself off `feat/cubrid-jira-ops`.
- Python code MUST run on Python 3.6.8 (`/usr/bin/python3`): f-strings OK; NO dataclasses, NO walrus, NO `subprocess.run(capture_output=)`, NO third-party packages.
- No `gh`, no `jq` on this host. GitHub access = REST API with `GITHUB_TOKEN`, loaded via `bash -lc 'export GITHUB_TOKEN; …'` (the token is set unexported in `~/.bash_profile`).
- `post_review.py` is dry-run by default; only `--yes` sends anything to GitHub. Nothing is posted to any PR during this plan — all integration tests are read-only or dry-run.
- NEVER execute test cases, CTP, or `run_cubrid_install` on this host (production QAHome CUBRID at `~/CUBRID`, `qaresu` DB).
- `SKILL.md` under 200 lines, written in English. Review *output* is Korean with English identifiers/paths/commands.
- Commit messages: English, prefixed `review-cubrid-testcase-pr:`, NO `Co-Authored-By` lines.
- Integration fixtures (read-only, already merged): SQL → `https://github.com/CUBRID/cubrid-testcases/pull/2956` (expect `jira_key=CBRD-26906`, category `sql`, files include `cbrd_26906.sql/.answer/.queryPlan`); shell → `https://github.com/CUBRID/cubrid-testcases-private-ex/pull/3621` (expect `jira_key=CBRD-26862`, category `shell`).

---

### Task 1: `fetch_pr.py` pure helpers (parse / JIRA-key / category) — TDD

**Files:**
- Create: `review-cubrid-testcase-pr/scripts/fetch_pr.py` (helpers only in this task)
- Test: `review-cubrid-testcase-pr/scripts/tests/test_fetch_pr.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces (used by Tasks 2, 3, 8):
  - `parse_pr_url(url: str) -> (owner: str, repo: str, number: int)` — accepts `https://github.com/OWNER/REPO/pull/N[...]` and `OWNER/REPO#N`; raises `ValueError` otherwise.
  - `extract_jira_key(title, body, paths) -> str | None` — returns e.g. `"CBRD-26906"`; priority: body line 1 → body line 2 → anywhere in body → title → `cbrd_xxxxx` in changed paths.
  - `detect_categories(paths: list) -> dict` — keys only when non-empty: `"sql"` (covers `sql/` + `medium/`), `"shell"`, `"excluded_list"` (`shell/config/*excluded_list*`), `"other"`; values are the matching path lists.

- [ ] **Step 1: Create the working directories**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr
mkdir -p review-cubrid-testcase-pr/scripts/tests review-cubrid-testcase-pr/references
```

- [ ] **Step 2: Write the failing tests**

Create `review-cubrid-testcase-pr/scripts/tests/test_fetch_pr.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fetch_pr import parse_pr_url, extract_jira_key, detect_categories


class TestParsePrUrl(unittest.TestCase):
    def test_full_url(self):
        self.assertEqual(
            parse_pr_url("https://github.com/CUBRID/cubrid-testcases/pull/2956"),
            ("CUBRID", "cubrid-testcases", 2956))

    def test_full_url_with_trailing_segment(self):
        self.assertEqual(
            parse_pr_url("https://github.com/CUBRID/cubrid-testcases-private-ex/pull/3621/files"),
            ("CUBRID", "cubrid-testcases-private-ex", 3621))

    def test_short_form(self):
        self.assertEqual(parse_pr_url("CUBRID/cubrid-testcases#2956"),
                         ("CUBRID", "cubrid-testcases", 2956))

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_pr_url("http://jira.cubrid.org/browse/CBRD-26563")


class TestExtractJiraKey(unittest.TestCase):
    def test_refer_to_first_line(self):
        body = "Refer to: http://jira.cubrid.org/browse/CBRD-26563\n\ndetails"
        self.assertEqual(extract_jira_key("title", body, []), "CBRD-26563")

    def test_bare_angle_url_first_line(self):
        # real shape from cubrid-testcases-private-ex#3621
        body = "<http://jira.cubrid.org/browse/CBRD-26862>\n\nRevise expected count"
        self.assertEqual(extract_jira_key("title", body, []), "CBRD-26862")

    def test_second_line_fallback(self):
        body = "Some intro line\nRefer to: http://jira.cubrid.org/browse/CBRD-27001"
        self.assertEqual(extract_jira_key("title", body, []), "CBRD-27001")

    def test_title_fallback(self):
        # real shape from cubrid-testcases#2956: key only in the title
        self.assertEqual(
            extract_jira_key("[CBRD-26906] Backport from develop to 11.4", "backport #2931", []),
            "CBRD-26906")

    def test_path_fallback(self):
        paths = ["shell/_06_issues/_26_1h/cbrd_27000/cases/cbrd_27000.sh"]
        self.assertEqual(extract_jira_key("no key", "no key", paths), "CBRD-27000")

    def test_lowercase_in_body(self):
        self.assertEqual(extract_jira_key("t", "fixes cbrd-25913 regression", []),
                         "CBRD-25913")

    def test_none_when_absent(self):
        self.assertIsNone(extract_jira_key("no key", "no key", ["sql/foo/cases/a.sql"]))

    def test_none_body(self):
        self.assertEqual(extract_jira_key("[CBRD-11111] t", None, []), "CBRD-11111")


class TestDetectCategories(unittest.TestCase):
    def test_sql_and_medium_grouped_as_sql(self):
        cats = detect_categories([
            "sql/_13_issues/_26_1h/cases/cbrd_26906.sql",
            "medium/_01_fixed/answers/fview1.answer"])
        self.assertEqual(sorted(cats.keys()), ["sql"])
        self.assertEqual(len(cats["sql"]), 2)

    def test_shell(self):
        cats = detect_categories(["shell/_06_issues/_26_1h/cbrd_27000/cases/cbrd_27000.sh"])
        self.assertEqual(sorted(cats.keys()), ["shell"])

    def test_excluded_list_separated_from_shell(self):
        cats = detect_categories([
            "shell/config/daily_regression_test_excluded_list_linux.conf",
            "shell/_06_issues/_26_1h/cbrd_27000/cases/cbrd_27000.sh"])
        self.assertEqual(sorted(cats.keys()), ["excluded_list", "shell"])

    def test_other(self):
        cats = detect_categories(["isolation/_01_basic/cases/x.ctl", "README.md"])
        self.assertEqual(sorted(cats.keys()), ["other"])
        self.assertEqual(len(cats["other"]), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr/scripts
python3 -m unittest discover -s tests -v
```
Expected: `ImportError: No module named 'fetch_pr'` (or `ModuleNotFoundError`).

- [ ] **Step 4: Write the helpers**

Create `review-cubrid-testcase-pr/scripts/fetch_pr.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr/scripts
python3 -m unittest discover -s tests -v
```
Expected: all tests PASS (OK, 16 tests).

- [ ] **Step 6: Commit**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr
git add review-cubrid-testcase-pr/scripts
git commit -m "review-cubrid-testcase-pr: add PR-ref/JIRA-key/category helpers"
```

---

### Task 2: `fetch_pr.py` network layer and bundle assembly

**Files:**
- Modify: `review-cubrid-testcase-pr/scripts/fetch_pr.py` (append network + main)

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces (used by Tasks 3, 8, 9):
  - CLI: `python3 fetch_pr.py <pr-ref> --out DIR [--max-file-bytes 200000] [--max-total-bytes 2000000]` → writes `DIR/bundle.json`, `DIR/pr.diff`, `DIR/files/<repo-path>`; exits non-zero without `GITHUB_TOKEN`.
  - `bundle.json` schema (top-level keys): `pr` (owner, repo, number, title, body, state, draft, base, head_sha, user, html_url), `commits` [{sha, message}], `changed_files` [{path, status, additions, deletions, patch}], `jira_key`, `categories`, `existing_reviews` [{user, state, body}], `existing_review_comments` [{user, path, line, body}], `existing_issue_comments` [{user, body}], `ci` {check_runs: [{name, conclusion}], combined_status}, `truncated` [{path, reason}].
  - `gh_request(path, token, accept=..., raw=False)` — reused by nothing else, internal.

- [ ] **Step 1: Append the network layer and main() to `fetch_pr.py`**

Append below the Task 1 code:

```python
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
```

- [ ] **Step 2: Re-run the unit tests (must still pass)**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr/scripts
python3 -m unittest discover -s tests -v
```
Expected: OK, 16 tests.

- [ ] **Step 3: Integration run — SQL fixture (read-only)**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr/scripts
bash -lc 'export GITHUB_TOKEN; python3 fetch_pr.py https://github.com/CUBRID/cubrid-testcases/pull/2956 --out /tmp/tcpr2956'
python3 - <<'PY'
import json
b = json.load(open("/tmp/tcpr2956/bundle.json"))
assert b["jira_key"] == "CBRD-26906", b["jira_key"]
assert "sql" in b["categories"], b["categories"]
paths = [f["path"] for f in b["changed_files"]]
assert any(p.endswith("cbrd_26906.sql") for p in paths), paths
assert any(p.endswith("cbrd_26906.queryPlan") for p in paths), paths
import os
assert os.path.getsize("/tmp/tcpr2956/pr.diff") > 0
print("SQL fixture OK:", paths)
PY
```
Expected: `SQL fixture OK: [...]` and the fetch line reporting `jira: CBRD-26906 | categories: sql`.

- [ ] **Step 4: Integration run — shell fixture (read-only)**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr/scripts
bash -lc 'export GITHUB_TOKEN; python3 fetch_pr.py https://github.com/CUBRID/cubrid-testcases-private-ex/pull/3621 --out /tmp/tcpr3621'
python3 - <<'PY'
import json, os
b = json.load(open("/tmp/tcpr3621/bundle.json"))
assert b["jira_key"] == "CBRD-26862", b["jira_key"]
assert "shell" in b["categories"], b["categories"]
one = b["changed_files"][0]["path"]
assert os.path.exists("/tmp/tcpr3621/files/" + one), one
print("shell fixture OK:", one)
PY
```
Expected: `shell fixture OK: shell/...sh` — proves private-repo access and head-state file download.

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr
git add review-cubrid-testcase-pr/scripts/fetch_pr.py
git commit -m "review-cubrid-testcase-pr: fetch PR bundle via GitHub REST API"
```

---

### Task 3: `post_review.py` — dry-run-default poster

**Files:**
- Create: `review-cubrid-testcase-pr/scripts/post_review.py`
- Test: `review-cubrid-testcase-pr/scripts/tests/test_post_review.py`

**Interfaces:**
- Consumes: `parse_pr_url` from `fetch_pr` (same directory).
- Produces (used by Task 8):
  - CLI: `python3 post_review.py <pr-ref> --body-file review.md [--request-changes] [--yes]`.
  - Default = dry-run: prints target URL, event, body length, saves `<body-file>.payload.json`, prints a curl fallback command; sends nothing.
  - `--yes` POSTs `/repos/{o}/{r}/pulls/{n}/reviews`; on HTTP error prints status + response + curl fallback and exits 1.
  - `build_review_payload(body_text, request_changes=False) -> dict` with keys `body`, `event` (`COMMENT` or `REQUEST_CHANGES`).

- [ ] **Step 1: Write the failing tests**

Create `review-cubrid-testcase-pr/scripts/tests/test_post_review.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from post_review import build_review_payload, curl_fallback


class TestBuildReviewPayload(unittest.TestCase):
    def test_default_is_comment(self):
        p = build_review_payload("본문 리뷰 내용")
        self.assertEqual(p, {"body": "본문 리뷰 내용", "event": "COMMENT"})

    def test_request_changes(self):
        p = build_review_payload("blocking", request_changes=True)
        self.assertEqual(p["event"], "REQUEST_CHANGES")


class TestCurlFallback(unittest.TestCase):
    def test_contains_endpoint_and_payload(self):
        cmd = curl_fallback("CUBRID", "cubrid-testcases", 2956, "/tmp/r.payload.json")
        self.assertIn("/repos/CUBRID/cubrid-testcases/pulls/2956/reviews", cmd)
        self.assertIn("@/tmp/r.payload.json", cmd)
        self.assertIn("$GITHUB_TOKEN", cmd)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr/scripts
python3 -m unittest discover -s tests -p 'test_post_review.py' -v
```
Expected: ImportError on `post_review`.

- [ ] **Step 3: Write `post_review.py`**

```python
#!/usr/bin/env python3
"""Post a review to a CUBRID test-case PR.

DRY-RUN BY DEFAULT: without --yes nothing is sent to GitHub; the payload is
saved next to the body file and an equivalent curl command is printed.

Usage:
    python3 post_review.py <pr-ref> --body-file review.md [--request-changes] [--yes]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_pr import API, parse_pr_url


def build_review_payload(body_text, request_changes=False):
    return {"body": body_text,
            "event": "REQUEST_CHANGES" if request_changes else "COMMENT"}


def curl_fallback(owner, repo, number, payload_path):
    return ("curl -sS -X POST -H \"Authorization: Bearer $GITHUB_TOKEN\" "
            "-H \"Accept: application/vnd.github+json\" "
            "-d @%s %s/repos/%s/%s/pulls/%d/reviews"
            % (payload_path, API, owner, repo, number))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr", help="PR URL or OWNER/REPO#N")
    ap.add_argument("--body-file", required=True, help="markdown file with the review body")
    ap.add_argument("--request-changes", action="store_true",
                    help="submit as REQUEST_CHANGES instead of COMMENT")
    ap.add_argument("--yes", action="store_true",
                    help="actually send the review (default: dry-run)")
    args = ap.parse_args()

    owner, repo, number = parse_pr_url(args.pr)
    with open(args.body_file, encoding="utf-8") as fh:
        body = fh.read().strip()
    if not body:
        sys.exit("review body is empty; refusing to post")

    payload = build_review_payload(body, args.request_changes)
    payload_path = args.body_file + ".payload.json"
    with open(payload_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    url = "%s/repos/%s/%s/pulls/%d/reviews" % (API, owner, repo, number)
    if not args.yes:
        print("[dry-run] would POST %s" % url)
        print("[dry-run] event=%s, body=%d chars" % (payload["event"], len(body)))
        print("[dry-run] payload saved to %s" % payload_path)
        print("[dry-run] manual send: " + curl_fallback(owner, repo, number, payload_path))
        return

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set; run via: bash -lc 'export GITHUB_TOKEN; ...'")
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "review-cubrid-testcase-pr"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        print("review posted: %s" % (out.get("html_url") or out.get("id")))
    except urllib.error.HTTPError as e:
        sys.stderr.write("POST failed: HTTP %d\n%s\n"
                         % (e.code, e.read().decode("utf-8", "replace")))
        sys.stderr.write("payload preserved at %s\nmanual send: %s\n"
                         % (payload_path, curl_fallback(owner, repo, number, payload_path)))
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all unit tests**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr/scripts
python3 -m unittest discover -s tests -v
```
Expected: OK (19 tests).

- [ ] **Step 5: Integration dry-run (sends nothing)**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr/scripts
printf '## 테스트 리뷰\n\n- dry-run 확인용\n' > /tmp/tc_review_test.md
python3 post_review.py CUBRID/cubrid-testcases#2956 --body-file /tmp/tc_review_test.md
```
Expected output contains `[dry-run] would POST https://api.github.com/repos/CUBRID/cubrid-testcases/pulls/2956/reviews`, `event=COMMENT`, and a curl command. Verify no review appeared: this ran without `--yes` and without a token export, so nothing could be sent.

- [ ] **Step 6: Commit**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr
git add review-cubrid-testcase-pr/scripts
git commit -m "review-cubrid-testcase-pr: add dry-run-default review poster"
```

---

### Task 4: `references/review-core.md` — the review doctrine

**Files:**
- Create: `review-cubrid-testcase-pr/references/review-core.md`

**Interfaces:**
- Consumes: nothing.
- Produces: doctrine text included verbatim in every reviewer-subagent prompt (Task 8 reads this path). Defines the Korean output contract used by Tasks 8–9.

- [ ] **Step 1: Write the file**

Create `review-cubrid-testcase-pr/references/review-core.md` with exactly this content:

````markdown
# CUBRID Test-Case PR Review Doctrine (core)

You are a senior CUBRID QA engineer reviewing a GitHub pull request that adds
or modifies CTP test cases. Decide whether the PR correctly validates the
linked CBRD issue, follows CTP conventions, produces deterministic and
maintainable results, and has adequate coverage. Focus on findings that affect
correctness, stability, regression detection, or maintainability — skip style
nits.

## Inputs you receive

- `bundle.json` — PR metadata, changed files (+patches), `jira_key`,
  `categories`, existing reviews/comments, CI check results, truncation notes.
- `files/` — full head-state content of every changed file. Review the FINAL
  state, not just diff fragments.
- `pr.diff` — the unified diff.
- JIRA issue text (when available) — description, acceptance criteria,
  comments, linked engine PR.
- Category rule files appended after this document.

If `truncated` in bundle.json is non-empty, state which files you could not
fully read; never pretend a truncated file was reviewed whole. If JIRA context
is missing, open the review with a note that accuracy is reduced.

## Review process

1. **Understand the intended behavior.** From JIRA + engine PR: what was
   broken or added, what changes observably after the patch, what conditions
   enable it. Do not trust test names or comments alone. If the issue wording
   conflicts with the implementation notes or the test's behavior, flag the
   ambiguity — do not silently pick a side.
2. **Review the PR as one test package.** Script/answer pairs complete and
   name-matched; paths follow repository conventions; helper files referenced
   correctly; deleted/renamed files leave no stale references; required
   variants (platform, `.answer_cci`) present when outputs differ.
3. **Setup and cleanup.** State reset before setup; every created resource
   (DB, table, user, file, process, conf change) explicitly cleaned up;
   session/system settings restored; safe even after a partial failure; no
   effect on unrelated tests or global services.
4. **Determinism.** Unordered multi-row output, catalog-order dependence,
   fixed sleeps, unbounded polling, background-process races, over-broad log
   greps, plans that depend on an uncontrolled index/access path,
   unnormalized timestamps/PIDs/paths/hashes. Require stabilization only when
   it affects answer consistency or CI reliability.
5. **Expected-output accuracy.** Values semantically correct; row counts and
   ordering right; error codes/messages right; warnings intentional;
   plan/trace markers match the purpose; negative cases do not accidentally
   use the excluded feature. A generated answer file is NOT automatically
   correct — judge it with the answer-fix vs bug-report taxonomy:
   - **answer-fix**: diff is a format/identifier change (hash suffixes, XASL
     ids, plan formatting, byte counters) — baseline regeneration, acceptable
     when JIRA describes an intentional output change.
   - **bug-report**: the answer encodes a crash, wrong result, or semantic
     regression — the answer preserves a product bug; blocking.
6. **Coverage.** Main success path; main failure/exclusion path; boundaries;
   empty/no-match; NULL behavior when relevant; regression-prone combinations
   from the acceptance criteria. Do not demand unrelated cases or redundant
   repetition of existing ones.
7. **Pre-patch/post-patch value.** Would this test fail on an unpatched build
   and pass on a patched one, for the intended reason? Claim this ONLY with
   evidence (CI logs, JIRA repro output, engine-PR linkage). Otherwise state
   that runtime verification is still required and include the exact command
   (see Verification footer). NEVER run test cases yourself.

## Severity

`NEEDS FIX` (blocking): incorrect expected result; test does not validate the
JIRA behavior; missing required negative/boundary coverage; nondeterministic
output; wrong error code; cleanup that can affect later tests; answer file
accepting a known bug; caption contradicting actual behavior; required
execution path unvalidated; test cannot distinguish patched from unpatched.

Non-blocking suggestions: wording, organization, redundant cases, formatting,
optional coverage, stability improvements unlikely to affect current CI.

## Output contract

Write the review in **Korean**. Keep file names, code identifiers, commands,
error codes, and the opening markers in English. Cite `file:line` for every
finding. Be precise and evidence-based; do not repeat the PR description; do
not restate unchanged code; do not propose large rewrites where a small
correction suffices.

Required opening line (exactly one):

```
✅ PASS — 이슈를 올바르게 검증하며 블로킹 문제가 없습니다.
```
```
❌ NEEDS FIX — <주요 블로킹 이슈 한 줄 요약>
```

Then only the relevant numbered sections:

```
1. 이슈 커버리지
2. 결정성(Determinism)
3. 기대 결과 정확성
4. Setup / Cleanup
5. 추가 커버리지 제안
```

Each finding: 파일:라인 — 무엇이 문제인지, 왜 문제인지, 요구되는 수정.

End with (NEEDS FIX only):

```
필수 조치 사항
- ...
```

## Verification footer (always include)

State what could and could not be proven statically, then give the runtime
verification command for a TEST machine (never this host):

```
검증 필요
- 패치 전 빌드에서 FAIL / 패치 후 빌드에서 PASS 여부는 정적 분석으로 확인되지 않았습니다.
- 테스트 장비에서: cubrid-shell-tc-verify (shell) 또는 cubrid-sql-tc-verify (sql)
  스킬로 <testcase path> 를 패치 전/후 빌드 URL 각각에 대해 실행해 NOK→OK 전환을 확인하세요.
```

Omit only when CI or JIRA evidence already proves both directions, and cite
that evidence instead.
````

- [ ] **Step 2: Sanity check**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr
grep -c "NEEDS FIX" references/review-core.md   # expect >= 3
grep -c "검증 필요" references/review-core.md    # expect 1
```

- [ ] **Step 3: Commit**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr
git add review-cubrid-testcase-pr/references/review-core.md
git commit -m "review-cubrid-testcase-pr: add core review doctrine"
```

---

### Task 5: `references/shell-rules.md`

**Files:**
- Create: `review-cubrid-testcase-pr/references/shell-rules.md`

**Interfaces:**
- Consumes: nothing. Produces: category rules appended to the reviewer prompt when `categories` contains `shell` or `excluded_list` (Task 8).

- [ ] **Step 1: Write the file**

Create `review-cubrid-testcase-pr/references/shell-rules.md` with exactly this content:

````markdown
# Shell test-case rules (CTP)

Checkable conventions for `shell/` test cases in cubrid-testcases-private-ex.
Violations of MUST items are `NEEDS FIX`.

## Lifecycle contract (MUST)

Entry script `{name}/cases/{name}.sh` — directory name and filename MUST match.

1. Optional platform macro (`WINDOWS_NOT_SUPPORTED` / `LINUX_NOT_SUPPORTED` /
   `AIX_NOT_SUPPORTED`) BEFORE sourcing init.sh.
2. `. $init_path/init.sh` then `init test` — first real statements.
3. Every code path ends at exactly ONE of `write_ok` / `write_nok [evidence]`.
4. `finish` is the LAST call and every exit path (including early
   `write_nok` returns) must reach it — it stops services, reverts every conf
   change, and frees broker shared memory. A path that exits without `finish`
   leaks state into the next test: blocking.
5. Cleanup before `finish` on every path: `rm -f *.log csql.* <binaries>`,
   `cubrid server stop`/`deletedb` for DBs the test created.

## Helpers over raw commands (MUST)

| Required | Instead of | Why |
|---|---|---|
| `cubrid_createdb $db` | `cubrid createdb` | charset/locale compat across versions |
| `change_db_parameter "k=v"` / `change_broker_parameter "k=v"` | editing `.conf` | auto-reverted by `finish` |
| `xgcc -o bin src.c` | raw `gcc` | auto `-I/-L $CUBRID -lcascci -lpthread`, 32/64-bit + OS detection |
| `xkill <pattern>` | `kill -9` / `pkill` | user-scoped, cross-platform |
| `write_ok` / `write_nok` | echoing PASS/FAIL | CTP result tracking |
| `format_csql_output` / `format_query_plan` / `format_path_output` / `diff_ignore_lineno` | raw `diff` | strips exec time, volatile plan text, absolute paths |

## Writing rules

- SQL inline via single-quoted heredocs (`<<'EOF'`); no separate `.sql` files.
- Variables quoted (`"$db"`); no hardcoded paths (`/tmp`, `/home`, `/opt`) —
  use `$init_path`, `$CUBRID`, cwd, `$TMPDIR`.
- Bounded loops only: poll with a counter, never `while true`; sleeps >10s
  should be condition-based polling.
- Every background PID tracked (`cmd & pid=$!`) with matching `wait`/`xkill`.
- Error handling on fallible steps (`cubrid server start`, `csql`, compiles):
  `cmd || { write_nok "reason"; <cleanup>; finish; exit 0; }`.
- Exit codes AND observable behavior both checked where appropriate;
  assertions specific enough to avoid matching unrelated log lines.
- No global service commands (`cubrid service stop` on shared instances)
  unless the issue itself requires them.

## House idioms (expected by reviewers)

- Default broker is `broker1` (not `query_editor`). Port:
  `` port=`cubrid broker status -b | grep broker1 | awk '{print $4}'` ``.
- CAS PID: `ps -f -u $USER | grep -v grep | grep broker1_cub_cas | awk '{print $2}'`.
- Crash/CAS-reuse repro: force single CAS (`MIN/MAX_NUM_APPL_SERVER=1` +
  `cubrid broker restart`), record `pid_before`.
- Coredump check = baseline → delta:
  `find "$CUBRID" ./ \( -name "core.*" -o -name "*coredump*" \) | wc -l`
  before vs after; pass = workload ok AND PID stable AND no new cores.
- Embedded CCI client: `.c` committed next to the `.sh`, compiled with `xgcc`,
  `#include "cas_cci.h"`.

## Directory conventions

- Bug fix: `shell/_06_issues/_{yy}_{1|2}h/{name}/cases/{name}.sh` where
  `{yy}{1|2}h` comes from the JIRA issue CREATION date — cross-check it.
- Feature: `shell/_{no}_{release_code}/{feature_group}/{name}/cases/{name}.sh`.
- Multiple tests per issue: `cbrd_xxxxx_1`, `cbrd_xxxxx_{keyword}` suffixes.
- Helper scripts live in the same `cases/` dir and own no lifecycle.

## Excluded-list changes

`shell/config/daily_regression_test_excluded_list_{linux,windows}.conf`:
each excluded path preceded by a `#CBRD-XXXXX (reason)` comment; the path must
exist in the tree; an exclusion without issue key + reason is NEEDS FIX.

## Failure classification vocabulary

When judging what a failing run would mean, classify as: product defect /
test defect / environment or tooling issue / flaky / inconclusive. Do not let
environment failures (lib paths, permissions, locale) masquerade as product
regressions.
````

- [ ] **Step 2: Commit**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr
git add review-cubrid-testcase-pr/references/shell-rules.md
git commit -m "review-cubrid-testcase-pr: add shell category rules"
```

---

### Task 6: `references/sql-rules.md`

**Files:**
- Create: `review-cubrid-testcase-pr/references/sql-rules.md`

**Interfaces:**
- Consumes: nothing. Produces: category rules appended to the reviewer prompt when `categories` contains `sql` (Task 8).

- [ ] **Step 1: Write the file**

Create `review-cubrid-testcase-pr/references/sql-rules.md` with exactly this content:

````markdown
# SQL test-case rules (CTP)

Checkable conventions for `sql/` and `medium/` test cases in cubrid-testcases.
Violations of MUST items are `NEEDS FIX`.

## File pairing (MUST)

- `.sql` in `cases/` and `.answer` in sibling `answers/` share the basename.
- Optimizer/plan tests add an (initially empty) `cases/{name}.queryPlan`
  sidecar — its presence makes CTP capture and diff the plan.
- `sql_by_cci` runs may need a `.answer_cci` variant when output differs; a
  PR changing a case that has an existing `.answer_cci` must update both.
- Bug fix dirs: `sql/_13_issues/_{yy}_{1|2}h/cases/…` (year/half from the
  JIRA creation date) or `sql/_{no}_{release_code}/cbrd_XXXXX/…` for a named
  release — match where sibling issues of the same release landed.
- Multiple files per issue share ONE `cases/`+`answers/` pair
  (`cbrd_27100_select.sql`, `cbrd_27100_update.sql`) — never one subdir per file.

## Structure (MUST)

- Header block first: `/** This test case verifies CBRD-XXXXX: <title> */`
  plus a numbered `Coverage:` list that matches what the file actually tests.
- `evaluate 'Case N: description'` before each scenario — the ONLY section
  marker (no `-- ===` banners); numbered sequentially; captions must describe
  the scenario truthfully.
- `DROP TABLE IF EXISTS t` before every `CREATE TABLE`; setup at top,
  cleanup at bottom.
- **The whole suite shares ONE database.** The file must undo everything:
  drop every created table/view/serial/procedure, `deallocate prepare` every
  `prepare`, restore every `SET SYSTEM PARAMETERS` to its original value.
  Leaked state breaks later tests: blocking.

## Determinism (MUST)

- Multi-row results need `ORDER BY` with a deterministic key (or become
  scalar). Single-row aggregates need NO ordering — flag superfluous ones as
  non-blocking only.
- Never bake into `.answer`: Java object hashes
  (`[Ljava.lang.Integer;@<hash>`), OIDs, timestamps, execution times,
  absolute paths, unordered set output.
- `LIMIT` without a total ordering is nondeterministic.

## Error tests

- Plain SQL error case asserts the `-NNN` code alone — the corpus norm.
- `--+ server-message on` / `off` (always PAIRED) only for PL/CSQL
  `DBMS_OUTPUT` or when the exact error MESSAGE text is the point (brittle —
  question it if used casually).
- Negative cases must not accidentally exercise the feature being excluded.

## Answer-file provenance

`.answer` files are GENERATED by CTP (seed empty answer → run → promote the
`.result`), never hand-written. Hand-written smells: missing `===…===`
statement separators, wrong affected-row-count format, error lines not in
`Error:-NNN` form. But a generated answer is not automatically correct —
check the semantics against JIRA intent (answer-fix vs bug-report taxonomy
in review-core.md).

## Optimizer tests

Require BOTH: (1) correct query result, (2) correct application/exclusion of
the optimization (plan capture via `.queryPlan`, or trace markers). Positive
and negative plan expectations must be distinguishable, result correctness
judged independently of plan correctness. Optimizer hints / forced indexes
only where needed to stabilize or validate the target access path. Never
approve a semantically wrong expected result because the plan looks right.
````

- [ ] **Step 2: Commit**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr
git add review-cubrid-testcase-pr/references/sql-rules.md
git commit -m "review-cubrid-testcase-pr: add SQL category rules"
```

---

### Task 7: `references/generic-rules.md`

**Files:**
- Create: `review-cubrid-testcase-pr/references/generic-rules.md`

**Interfaces:**
- Consumes: nothing. Produces: fallback rules appended to the reviewer prompt when `categories` contains `other` (Task 8).

- [ ] **Step 1: Write the file**

Create `review-cubrid-testcase-pr/references/generic-rules.md` with exactly this content:

````markdown
# Generic rules for categories without loaded doctrine

Used when the PR touches CTP categories other than sql/medium/shell. The
review still runs the core process (review-core.md), but the review MUST
open with an explicit flag, in Korean, e.g.:

```
⚠️ 이 PR 은 전용 리뷰 규칙이 없는 카테고리(<dirs>)를 포함합니다.
   일반 체크리스트만 적용했으므로 카테고리 관례 위반은 놓칠 수 있습니다.
```

## Category identification hints

| Tree / extension | Category | Notes |
|---|---|---|
| `.ctl` files | isolation | multi-client isolation-level scenarios |
| JUnit 4 `@Test` Java | jdbc | JUnit conventions apply |
| `.c` with CCI calls + driver script | cci | compiled client tests |
| `.sql` with `--test:` / `--check:` markers | ha_repl / cdc_repl | master/slave semantics |
| `make_ha.sh`-based `.sh` | ha_shell | HA lifecycle differs from plain shell |
| C/C++ sources under a unittest tree | unittest | engine-level unit tests |

## Generic checklist (applies to every category)

- Changed files form a complete, internally consistent package (scripts,
  inputs, answers, helpers all referenced and name-matched).
- Setup creates what it needs; cleanup removes exactly what was created and
  restores settings; safe after partial failure.
- Output is deterministic (ordering, timestamps, ids, paths normalized).
- Expected results semantically match the JIRA intent; error codes exact.
- The test can distinguish patched from unpatched behavior.
- No effect on unrelated tests or global services.

Anything category-specific that looks suspicious should be reported as a
QUESTION rather than a definitive finding, citing the lack of loaded rules.
````

- [ ] **Step 2: Commit**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr
git add review-cubrid-testcase-pr/references/generic-rules.md
git commit -m "review-cubrid-testcase-pr: add generic fallback rules"
```

---

### Task 8: `SKILL.md` orchestrator

**Files:**
- Create: `review-cubrid-testcase-pr/SKILL.md`

**Interfaces:**
- Consumes: CLI contracts from Tasks 2–3, reference files from Tasks 4–7.
- Produces: the user-invocable skill entry point.

- [ ] **Step 1: Write the file**

Create `review-cubrid-testcase-pr/SKILL.md` with exactly this content:

````markdown
---
name: review-cubrid-testcase-pr
description: Review a GitHub pull request that adds or modifies CUBRID CTP test cases (SQL or shell) against its CBRD JIRA issue, render a Korean review locally, and post it to the PR only after explicit user confirmation. Use when asked to review a test-case PR in CUBRID/cubrid-testcases, cubrid-testcases-private, or cubrid-testcases-private-ex — "review this TC PR", "TC PR 리뷰해줘", "테스트케이스 PR 검토해줘", or a testcase-repo PR URL plus the word review. NOT for creating test cases, running/verifying test cases on a build, or PRs in cubrid-testtools-internal (use create-cubrid-testtools-pr / reflect-cubrid-testtools-pr-review).
---

# Review CUBRID Test-Case PR

Fetch a test-case PR and its JIRA context, review it with category doctrine
via a subagent, render the Korean review locally, and post only after the
user explicitly confirms.

## Hard safety rule

NEVER execute test cases, CTP, or `run_cubrid_install` on this host. This
machine runs the production QAHome CUBRID (`~/CUBRID`, `qaresu` DB); CTP runs
wipe `$HOME/CUBRID` and stop CUBRID services. Review is static analysis only;
runtime proof is delegated to a test machine via the verification footer.

## Prerequisites

- `GITHUB_TOKEN` set (unexported) in `~/.bash_profile`. Wrap every script
  call in `bash -lc 'export GITHUB_TOKEN; …'`.
- `cubrid-jira` CLI — optional enrichment; skip with a visible note if absent.

Let `$SKILL` = this skill's directory and `$work` = a fresh scratchpad dir.

## Steps

### 1. Fetch the PR bundle

```bash
bash -lc "export GITHUB_TOKEN; python3 $SKILL/scripts/fetch_pr.py '<PR_URL>' --out $work/bundle"
```

Read `$work/bundle/bundle.json`. If `truncated` is non-empty, tell the user
which files were capped BEFORE reviewing. If the repo is not one of the
three testcase repos, confirm intent with the user before continuing.

### 2. JIRA context (optional enrichment)

If `jira_key` is set and `cubrid-jira` exists:
`cubrid-jira search <KEY> > $work/jira.md`. Extract: expected behavior,
acceptance criteria, repro, linked engine PR (`github.com/CUBRID/cubrid/pull/N`).
- `jira_key` null → continue; the missing `Refer to:` line is itself a finding.
- CLI missing or issue restricted → continue; the review must open with a
  "JIRA 컨텍스트 없이 리뷰됨 — 정확도 제한" note.

### 3. Engine-PR enrichment (optional)

If an engine PR is linked, fetch its title + changed-file list (REST API,
same `bash -lc` pattern) into `$work/engine_pr.md` — it tells the reviewer
what engine code changed, to judge whether the TC exercises it.

### 4. Assemble doctrine by category

From `bundle.json` `categories`:
- always include `$SKILL/references/review-core.md`
- `sql` → add `$SKILL/references/sql-rules.md`
- `shell` or `excluded_list` → add `$SKILL/references/shell-rules.md`
- `other` → add `$SKILL/references/generic-rules.md`

### 5. Spawn the reviewer subagent

Count distinct test-case directories among changed files (a test-case dir =
the parent of `cases/`, e.g. `shell/_06_issues/_26_1h/cbrd_27000`; for
`sql/.../cases/x.sql` layouts use the parent of `cases/`).

- **≤ 4 dirs** → ONE `general-purpose` subagent.
- **> 4 dirs** → one subagent per test-case dir in parallel, then synthesize:
  merge findings, drop duplicates, overall verdict = worst individual verdict.

Each subagent prompt must contain, in order: the full text of the selected
reference files; the paths `$work/bundle/bundle.json`, `$work/bundle/files/`,
`$work/bundle/pr.diff`, `$work/jira.md`, `$work/engine_pr.md` (when present);
and the instruction: *"Read the bundle, apply the doctrine, and return ONLY
the final review markdown in Korean per the Output contract — no preamble."*

Save the result to `$work/review.md`.

### 6. Render locally and confirm

Show `$work/review.md` verbatim in the session. Then ask the user explicitly
whether to post. Do NOT post without a clear yes in this conversation.

### 7. Post

```bash
bash -lc "export GITHUB_TOKEN; python3 $SKILL/scripts/post_review.py '<PR_URL>' --body-file $work/review.md --yes"
```

Default event is `COMMENT`; add `--request-changes` only when the user asks
for a blocking review. On HTTP failure the script preserves the payload and
prints a curl fallback — relay both to the user.

## Failure conditions

- `GITHUB_TOKEN` missing → stop and tell the user.
- Reviewer subagent returns empty/no verdict line → do not post; rerun or
  report.
- Re-running on the same PR posts a NEW review (v1 never edits old ones);
  the bundle includes existing reviews so the subagent avoids repeating them.
````

- [ ] **Step 2: Verify the line limit and frontmatter**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr
wc -l SKILL.md          # expect < 200
head -4 SKILL.md        # expect frontmatter with name: review-cubrid-testcase-pr
```

- [ ] **Step 3: Commit**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr
git add review-cubrid-testcase-pr/SKILL.md
git commit -m "review-cubrid-testcase-pr: add orchestrator SKILL.md"
```

---

### Task 9: Activation and calibration (local render only — nothing posted)

**Files:**
- Create: symlink `~/.claude/skills/review-cubrid-testcase-pr` → worktree skill dir
- Modify: `review-cubrid-testcase-pr/references/*.md` (tuning only if calibration finds gaps)

**Interfaces:**
- Consumes: the complete skill from Tasks 1–8.
- Produces: an activated, calibrated skill.

- [ ] **Step 1: Symlink into the skill discovery path**

```bash
ln -sfn ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr \
        ~/.claude/skills/review-cubrid-testcase-pr
ls -l ~/.claude/skills/review-cubrid-testcase-pr
```
Note: after the branch merges to main and `~/skills` picks it up, re-point the
symlink to `~/skills/review-cubrid-testcase-pr` and remove the worktree.

- [ ] **Step 2: Calibration run 1 — SQL fixture**

In a NEW Claude Code session (so the skill is discovered), run:
`/review-cubrid-testcase-pr https://github.com/CUBRID/cubrid-testcases/pull/2956`
— stop at Step 6 (render); answer "no" to posting.

Compare the rendered review against the human reviews already recorded in
`bundle.json` (`existing_reviews`, `existing_review_comments`). Note misses
(human found, agent didn't) and false blockers (agent NEEDS FIX that humans
accepted).

- [ ] **Step 3: Calibration run 2 — shell fixture**

Same procedure with
`/review-cubrid-testcase-pr https://github.com/CUBRID/cubrid-testcases-private-ex/pull/3621`.
Expect the review to exercise shell-rules (lifecycle, helpers) and to handle
a multi-test-case PR (3 changed `.sh` files, still ≤4 dirs → single pass).

- [ ] **Step 4: Tune references from calibration findings**

For each miss: add the missing checkable rule to the matching
`references/*.md`. For each false blocker: soften or scope the rule that
caused it. Keep review-core.md process stable; tune category files first.

- [ ] **Step 5: Re-run unit tests and commit tuning**

```bash
cd ~/worktrees/skills-review-cubrid-testcase-pr/review-cubrid-testcase-pr/scripts
python3 -m unittest discover -s tests -v
cd ~/worktrees/skills-review-cubrid-testcase-pr
git add review-cubrid-testcase-pr
git commit -m "review-cubrid-testcase-pr: calibration tuning from fixture PRs"
```
(Skip the commit if calibration required no changes.)

---

## Self-review (done at plan-writing time)

- **Spec coverage:** locked decisions table → Tasks: hybrid skill+subagent (T8 §5), local-then-confirm posting (T8 §6–7, T3 dry-run default), Korean output (T4 output contract), static-only + never-run-here (T4 §7, T8 safety rule), shell+SQL deep / other generic (T5, T6, T7), fan-out >4 (T8 §5), COMMENT + `--request-changes` (T3), REST-not-gh (T2), JIRA optional enrichment (T8 §2), engine-PR enrichment (T8 §3), truncation surfacing (T2, T8 §1), excluded-list rules (T5), answer-file-only PR taxonomy (T4 §5, T6 provenance), existing-review dedup (T2 bundle, T8 failure conditions), calibration plan (T9). No gaps found.
- **Placeholder scan:** no TBD/TODO/"handle appropriately"; every code/content step carries the full text.
- **Type consistency:** `parse_pr_url` tuple shape used identically in T1/T3; `bundle.json` keys in T2 match what T8 reads (`jira_key`, `categories`, `truncated`, `existing_reviews`); reference file paths in T8 §4 match T4–T7 filenames.
