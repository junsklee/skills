# CUBRID Test-Case Creation Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two Claude Code skills (`create-cubrid-sql-testcase`, `create-cubrid-shell-testcase`) that draft CUBRID CTP test cases from a CBRD JIRA issue, gate them through the reviewer suite, and finish as fork branch + PR after explicit confirmation.

**Architecture:** Two per-category orchestrator skills sharing a non-skill common dir (`cubrid-testcase-creation-common/`: two stdlib REST scripts + shared protocol/verify references). Drafting doctrine is per-skill; tw-kang assets are vendored with provenance; the mined test-creation KB routes feature-specific feedback into the drafter; the existing reviewer suite is the mandatory self-review gate. Two-phase flow (draft→verify handoff→answer intake→PR) that collapses to one phase when `CUBRID_TC_ALLOW_LOCAL_CTP=1`.

**Tech Stack:** Python 3.6.8 stdlib (urllib/json/argparse/unittest), GitHub REST v3 (git data + contents APIs), `cubrid-jira` CLI, Claude Code skill format.

**Spec:** `docs/superpowers/specs/2026-07-14-create-cubrid-testcase-suite-design.md` (same branch — read before starting).

## Execution model (parallel waves)

- Wave 1: Tasks 1–5 in PARALLEL (file-disjoint). Wave 2: Tasks 6–7 in PARALLEL (need wave-1 interfaces). Wave 3: Task 8 (controller), then Task 9's two calibration runs in PARALLEL.
- **Implementers MUST NOT run any git command.** Each task writes its files only; the controller stages and commits that task's exact file set after its review passes (single suite prefix `create-cubrid-testcase:`). This is the deliberate deviation from standard per-task commit steps, to make parallel dispatch safe.

## Global Constraints

- Worktree: `~/worktrees/skills-create-cubrid-testcase`, branch `feat/create-cubrid-testcase-skills`. All new files under it.
- Python 3.6.8 (`/usr/bin/python3`): f-strings OK; NO dataclasses, NO walrus, NO `subprocess.run(capture_output=)`, NO third-party packages.
- No `gh`/`jq`. GitHub = REST with `GITHUB_TOKEN` via `bash -lc 'export GITHUB_TOKEN; …'`.
- `push_package.py` is DRY-RUN by default; only `--yes` writes to GitHub. Nothing is pushed and no PR opened during this plan — all integration checks are read-only or dry-run.
- On this host NEVER execute CTP/csql/cubrid; `CUBRID_TC_ALLOW_LOCAL_CTP` must never be set here. `.answer` content is never authored by hand.
- SKILL.md files under 200 lines, English; review/PR-facing text Korean with English identifiers.
- Commits: English, prefix `create-cubrid-testcase:`, NO Co-Authored-By.
- Vendor source: `/tmp/claude-1004/-home-qahome/a5dd2d1f-8b15-4f87-94ff-d5d277f9fd04/scratchpad/twkang-skills` (git pull first; record `git rev-parse --short HEAD` in provenance headers).
- Reviewer suite (gate doctrine): `~/.claude/skills/review-cubrid-testcase-pr/references/` + `~/pr-review-mining/reviewer_rubric/`. KB: `~/pr-review-mining/test_creation_kb` (`CUBRID_TESTCREATE_KB_DIR`).
- Calibration fixtures (read-only): SQL → CBRD-25709 / merged PR CUBRID/cubrid-testcases#2988; shell → CBRD-26563 / merged PR CUBRID/cubrid-testcases-private-ex#3626. Golden context: `~/pr-review-mining/review_runs/`.

---

### Task 1: Common scripts (`ghlib.py`, `fetch_context.py`, `push_package.py`) — TDD

**Files:**
- Create: `cubrid-testcase-creation-common/scripts/ghlib.py`
- Create: `cubrid-testcase-creation-common/scripts/fetch_context.py`
- Create: `cubrid-testcase-creation-common/scripts/push_package.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_fetch_context.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_push_package.py`

**Interfaces:**
- Consumes: nothing.
- Produces (used by Tasks 6, 7, 9):
  - `fetch_context.py engine-pr <pr-ref> --out FILE` → markdown (title/state/description/changed files).
  - `fetch_context.py tree <owner/repo> --grep TOKEN [--prefix P] [--ref develop]` → matching blob paths, one per line.
  - `fetch_context.py get <owner/repo> PATH... --out DIR [--ref develop]` → downloads files preserving repo paths (containment enforced).
  - `push_package.py status --upstream O/R --fork-owner U --branch BR [--base-ref develop]` → JSON `{branch_exists, base_sha, branch_sha, empty_answers, pr}`.
  - `push_package.py push --upstream O/R --fork-owner U --branch BR --package-dir DIR --message MSG [--base-ref develop] [--update] [--yes]` → dry-run plan or single commit on fork branch (git data API).
  - `push_package.py pr --upstream O/R --fork-owner U --branch BR --title T --body-file F [--base-ref develop] [--yes]` → dry-run payload+curl or opened PR.
  - Pure helpers: `branch_name(key)->'cbrd_NNNNN_tc'`, `collect_package(dir)->[(repo_path,abs_path)]`, `answers_empty({path:size})->[paths]`, `build_pr_payload(title,body,fork_owner,branch,base_ref)->dict`, `parse_pr_ref(ref)->(owner,repo,int)`, `filter_tree(paths,contains,prefix)->[paths]`, `safe_dest(base,name)->path`.

- [ ] **Step 1: Create dirs and write the failing tests**

```bash
cd ~/worktrees/skills-create-cubrid-testcase
mkdir -p cubrid-testcase-creation-common/scripts/tests cubrid-testcase-creation-common/references
```

Create `cubrid-testcase-creation-common/scripts/tests/test_fetch_context.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fetch_context import filter_tree, parse_pr_ref, safe_dest


class TestParsePrRef(unittest.TestCase):
    def test_full_url(self):
        self.assertEqual(parse_pr_ref("https://github.com/CUBRID/cubrid/pull/7213"),
                         ("CUBRID", "cubrid", 7213))

    def test_short_form(self):
        self.assertEqual(parse_pr_ref("CUBRID/cubrid-testcases#2988"),
                         ("CUBRID", "cubrid-testcases", 2988))

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_pr_ref("http://jira.cubrid.org/browse/CBRD-25709")


class TestFilterTree(unittest.TestCase):
    PATHS = ["sql/_13_issues/_26_2h/cases/cbrd_25709.sql",
             "sql/_13_issues/_26_2h/answers/cbrd_25709.answer",
             "shell/_06_issues/_26_1h/cbrd_26563/cases/cbrd_26563.sh",
             "sql/_36_guava/cbrd_26486/cases/01_uuid_basic.sql"]

    def test_substring_case_insensitive(self):
        self.assertEqual(len(filter_tree(self.PATHS, "CBRD_25709")), 2)

    def test_prefix_scope(self):
        got = filter_tree(self.PATHS, "cbrd", prefix="shell/")
        self.assertEqual(got, ["shell/_06_issues/_26_1h/cbrd_26563/cases/cbrd_26563.sh"])

    def test_no_match(self):
        self.assertEqual(filter_tree(self.PATHS, "cbrd_99999"), [])


class TestSafeDest(unittest.TestCase):
    def setUp(self):
        self.base = os.path.abspath("/data/ctx")

    def test_normal(self):
        self.assertEqual(safe_dest(self.base, "sql/cases/a.sql"),
                         os.path.join(self.base, "sql", "cases", "a.sql"))

    def test_traversal_contained(self):
        self.assertTrue(safe_dest(self.base, "../../etc/passwd")
                        .startswith(self.base + os.sep))

    def test_absolute_contained(self):
        self.assertTrue(safe_dest(self.base, "/etc/passwd")
                        .startswith(self.base + os.sep))


if __name__ == "__main__":
    unittest.main()
```

Create `cubrid-testcase-creation-common/scripts/tests/test_push_package.py`:

```python
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from push_package import answers_empty, branch_name, build_pr_payload, collect_package


class TestBranchName(unittest.TestCase):
    def test_jira_key(self):
        self.assertEqual(branch_name("CBRD-25709"), "cbrd_25709_tc")

    def test_lower_underscore(self):
        self.assertEqual(branch_name("cbrd_26563"), "cbrd_26563_tc")

    def test_embedded(self):
        self.assertEqual(branch_name("[CBRD-26572] uuid tests"), "cbrd_26572_tc")

    def test_rejects_no_key(self):
        with self.assertRaises(ValueError):
            branch_name("no key here")


class TestCollectPackage(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "sql", "_13_issues", "_26_2h", "cases"))
        os.makedirs(os.path.join(self.d, "sql", "_13_issues", "_26_2h", "answers"))
        with open(os.path.join(self.d, "sql/_13_issues/_26_2h/cases/cbrd_1.sql"), "w") as fh:
            fh.write("select 1;")
        open(os.path.join(self.d, "sql/_13_issues/_26_2h/answers/cbrd_1.answer"), "w").close()
        with open(os.path.join(self.d, ".hidden"), "w") as fh:
            fh.write("x")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_walk_skips_dotfiles_and_uses_repo_paths(self):
        got = collect_package(self.d)
        paths = [p for p, _ in got]
        self.assertEqual(paths, ["sql/_13_issues/_26_2h/answers/cbrd_1.answer",
                                 "sql/_13_issues/_26_2h/cases/cbrd_1.sql"])
        for _, ap in got:
            self.assertTrue(os.path.isabs(ap))


class TestAnswersEmpty(unittest.TestCase):
    def test_flags_only_empty_answer_files(self):
        sizes = {"a/cases/x.sql": 10, "a/answers/x.answer": 0,
                 "a/answers/y.answer": 5, "a/answers/x.answer_cci": 0,
                 "a/cases/empty.queryPlan": 0}
        self.assertEqual(answers_empty(sizes),
                         ["a/answers/x.answer", "a/answers/x.answer_cci"])


class TestBuildPrPayload(unittest.TestCase):
    def test_shape(self):
        p = build_pr_payload("[CBRD-1] t", "본문", "junsklee", "cbrd_1_tc", "develop")
        self.assertEqual(p, {"title": "[CBRD-1] t", "body": "본문",
                             "head": "junsklee:cbrd_1_tc", "base": "develop"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/worktrees/skills-create-cubrid-testcase/cubrid-testcase-creation-common/scripts
python3 -m unittest discover -s tests -v
```
Expected: ImportError/ModuleNotFoundError for `fetch_context` and `push_package`.

- [ ] **Step 3: Write `ghlib.py`**

```python
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
```

- [ ] **Step 4: Write `fetch_context.py`**

```python
#!/usr/bin/env python3
"""Read-only context fetcher for test-case creation (Python 3.6, stdlib).

Subcommands:
  engine-pr <pr-ref> --out FILE                    # PR title/description/files -> markdown
  tree <owner/repo> --grep TOKEN [--prefix P] [--ref develop]   # matching blob paths
  get <owner/repo> PATH... --out DIR [--ref develop]            # download files (contained)
"""
import argparse
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ghlib import gh_paginate, gh_request, parse_repo, token

_PR_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")
_SHORT_RE = re.compile(r"^([^/\s#]+)/([^/\s#]+)#(\d+)$")


def parse_pr_ref(ref):
    m = _PR_RE.search(ref) or _SHORT_RE.match(ref.strip())
    if not m:
        raise ValueError("unrecognized PR reference: " + ref)
    return m.group(1), m.group(2), int(m.group(3))


def filter_tree(paths, contains, prefix=None):
    """Case-insensitive substring match over repo paths, optional prefix scope."""
    needle = contains.lower()
    out = []
    for p in paths:
        if prefix and not p.startswith(prefix):
            continue
        if needle in p.lower():
            out.append(p)
    return out


def safe_dest(base_dir, name):
    """Resolve a repo-relative path under base_dir, never outside it."""
    clean = name.lstrip("/\\")
    dest = os.path.normpath(os.path.join(base_dir, clean))
    if not dest.startswith(base_dir + os.sep):
        dest = os.path.join(base_dir, clean.replace("..", "__"))
    return dest


def cmd_engine_pr(args):
    tok = token()
    owner, repo, num = parse_pr_ref(args.ref)
    base = "/repos/%s/%s" % (owner, repo)
    pr = gh_request("%s/pulls/%d" % (base, num), tok)
    files = gh_paginate("%s/pulls/%d/files" % (base, num), tok)
    lines = ["# Engine PR %s/%s#%d" % (owner, repo, num), "",
             "Title: %s" % pr.get("title"),
             "State: %s merged: %s" % (pr.get("state"), pr.get("merged_at")), "",
             "## Description", pr.get("body") or "(none)", "", "## Changed files"]
    lines += ["- %s (+%d/-%d)" % (f["filename"], f["additions"], f["deletions"])
              for f in files]
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("engine-pr written: %s (%d files)" % (args.out, len(files)))


def cmd_tree(args):
    tok = token()
    owner, repo = parse_repo(args.repo)
    ref = gh_request("/repos/%s/%s/git/ref/heads/%s" % (owner, repo, args.ref), tok)
    tree = gh_request("/repos/%s/%s/git/trees/%s?recursive=1"
                      % (owner, repo, ref["object"]["sha"]), tok)
    if tree.get("truncated"):
        sys.stderr.write("warning: tree listing truncated by GitHub; results may be partial\n")
    paths = [e["path"] for e in tree.get("tree", []) if e.get("type") == "blob"]
    for p in filter_tree(paths, args.grep, args.prefix):
        print(p)


def cmd_get(args):
    tok = token()
    owner, repo = parse_repo(args.repo)
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    failed = 0
    for path in args.paths:
        try:
            blob = gh_request("/repos/%s/%s/contents/%s?ref=%s"
                              % (owner, repo, urllib.parse.quote(path), args.ref),
                              tok, accept="application/vnd.github.raw", raw=True)
        except Exception as e:
            sys.stderr.write("fetch failed for %s: %s\n" % (path, e))
            failed += 1
            continue
        dest = safe_dest(out_dir, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(blob)
        print("fetched %s (%d bytes)" % (path, len(blob)))
    if failed:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p1 = sub.add_parser("engine-pr")
    p1.add_argument("ref")
    p1.add_argument("--out", required=True)
    p2 = sub.add_parser("tree")
    p2.add_argument("repo")
    p2.add_argument("--grep", required=True)
    p2.add_argument("--prefix", default=None)
    p2.add_argument("--ref", default="develop")
    p3 = sub.add_parser("get")
    p3.add_argument("repo")
    p3.add_argument("paths", nargs="+")
    p3.add_argument("--out", required=True)
    p3.add_argument("--ref", default="develop")
    args = ap.parse_args()
    if args.cmd == "engine-pr":
        cmd_engine_pr(args)
    elif args.cmd == "tree":
        cmd_tree(args)
    elif args.cmd == "get":
        cmd_get(args)
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Write `push_package.py`**

```python
#!/usr/bin/env python3
"""Create/refresh a test-case branch on the fork and open the PR (Python 3.6, stdlib).

DRY-RUN BY DEFAULT — without --yes nothing is written to GitHub.

Subcommands:
  status --upstream O/R --fork-owner U --branch BR [--base-ref develop]
  push   --upstream O/R --fork-owner U --branch BR --package-dir DIR --message MSG
         [--base-ref develop] [--update] [--yes]
  pr     --upstream O/R --fork-owner U --branch BR --title T --body-file F
         [--base-ref develop] [--yes]
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ghlib import API, gh_request, parse_repo, token


def branch_name(key):
    """'CBRD-12345' / 'cbrd_12345' / text containing either -> 'cbrd_12345_tc'."""
    m = re.search(r"(?i)cbrd[-_](\d+)", key)
    if not m:
        raise ValueError("no CBRD key in: " + key)
    return "cbrd_%s_tc" % m.group(1)


def collect_package(package_dir):
    """Walk a staging dir -> sorted [(repo_path, abs_path)]. Skips dot-entries."""
    out = []
    base = os.path.abspath(package_dir)
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith("."):
                continue
            ap = os.path.join(root, f)
            out.append((os.path.relpath(ap, base).replace(os.sep, "/"), ap))
    return sorted(out)


def answers_empty(sizes):
    """{repo_path: byte_size} -> sorted list of empty .answer/.answer_cci paths."""
    return sorted(p for p, s in sizes.items()
                  if s == 0 and (p.endswith(".answer") or p.endswith(".answer_cci")))


def build_pr_payload(title, body, fork_owner, branch, base_ref):
    return {"title": title, "body": body,
            "head": "%s:%s" % (fork_owner, branch), "base": base_ref}


def get_branch_sha(owner, repo, branch, tok):
    try:
        ref = gh_request("/repos/%s/%s/git/ref/heads/%s" % (owner, repo, branch), tok)
        return ref["object"]["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def curl_fallback(payload_path, endpoint):
    return ("curl -sS -X POST -H \"Authorization: Bearer $GITHUB_TOKEN\" "
            "-H \"Accept: application/vnd.github+json\" -d @%s %s%s"
            % (payload_path, API, endpoint))


def cmd_status(args):
    tok = token()
    uo, ur = parse_repo(args.upstream)
    base_sha = get_branch_sha(uo, ur, args.base_ref, tok)
    branch_sha = get_branch_sha(args.fork_owner, ur, args.branch, tok)
    empty = []
    if branch_sha:
        tree = gh_request("/repos/%s/%s/git/trees/%s?recursive=1"
                          % (args.fork_owner, ur, branch_sha), tok)
        sizes = dict((e["path"], e.get("size", 0)) for e in tree.get("tree", [])
                     if e.get("type") == "blob")
        empty = answers_empty(sizes)
    prs = gh_request("/repos/%s/%s/pulls?head=%s:%s&state=open"
                     % (uo, ur, args.fork_owner, args.branch), tok)
    print(json.dumps({"branch_exists": bool(branch_sha), "base_sha": base_sha,
                      "branch_sha": branch_sha, "empty_answers": empty,
                      "pr": prs[0]["number"] if prs else None}, indent=2))


def cmd_push(args):
    tok = token()
    uo, ur = parse_repo(args.upstream)
    files = collect_package(args.package_dir)
    if not files:
        sys.exit("package dir is empty: " + args.package_dir)
    base_sha = get_branch_sha(uo, ur, args.base_ref, tok)
    if not base_sha:
        sys.exit("cannot resolve upstream %s head" % args.base_ref)
    branch_sha = get_branch_sha(args.fork_owner, ur, args.branch, tok)
    if branch_sha and not args.update:
        sys.exit("branch %s already exists on %s/%s; pass --update to add a commit"
                 % (args.branch, args.fork_owner, ur))
    if not args.yes:
        print("[dry-run] would %s branch %s on %s/%s (base %s @ %s)"
              % ("update" if branch_sha else "create", args.branch,
                 args.fork_owner, ur, args.base_ref, base_sha[:9]))
        for rp, ap in files:
            print("[dry-run]   + %s (%d bytes)" % (rp, os.path.getsize(ap)))
        print("[dry-run] commit message: %s" % args.message)
        return
    if not branch_sha:
        gh_request("/repos/%s/%s/git/refs" % (args.fork_owner, ur), tok,
                   data={"ref": "refs/heads/" + args.branch, "sha": base_sha})
        head = base_sha
    else:
        head = branch_sha
    head_commit = gh_request("/repos/%s/%s/git/commits/%s"
                             % (args.fork_owner, ur, head), tok)
    entries = []
    for rp, ap in files:
        with open(ap, "rb") as fh:
            content = fh.read()
        blob = gh_request("/repos/%s/%s/git/blobs" % (args.fork_owner, ur), tok,
                          data={"content": base64.b64encode(content).decode("ascii"),
                                "encoding": "base64"})
        entries.append({"path": rp, "mode": "100644", "type": "blob",
                        "sha": blob["sha"]})
    tree = gh_request("/repos/%s/%s/git/trees" % (args.fork_owner, ur), tok,
                      data={"base_tree": head_commit["tree"]["sha"], "tree": entries})
    commit = gh_request("/repos/%s/%s/git/commits" % (args.fork_owner, ur), tok,
                        data={"message": args.message, "tree": tree["sha"],
                              "parents": [head]})
    gh_request("/repos/%s/%s/git/refs/heads/%s" % (args.fork_owner, ur, args.branch),
               tok, method="PATCH", data={"sha": commit["sha"]})
    print("pushed %d file(s) to %s/%s@%s (commit %s)"
          % (len(files), args.fork_owner, ur, args.branch, commit["sha"][:9]))


def cmd_pr(args):
    tok = token()
    uo, ur = parse_repo(args.upstream)
    with open(args.body_file, encoding="utf-8") as fh:
        body = fh.read().strip()
    if not body:
        sys.exit("PR body is empty; refusing")
    payload = build_pr_payload(args.title, body, args.fork_owner, args.branch,
                               args.base_ref)
    payload_path = args.body_file + ".payload.json"
    with open(payload_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    endpoint = "/repos/%s/%s/pulls" % (uo, ur)
    if not args.yes:
        print("[dry-run] would POST %s%s" % (API, endpoint))
        print("[dry-run] head=%s base=%s title=%s"
              % (payload["head"], payload["base"], args.title))
        print("[dry-run] payload saved to %s" % payload_path)
        print("[dry-run] manual send: " + curl_fallback(payload_path, endpoint))
        return
    try:
        out = gh_request(endpoint, tok, data=payload)
        print("PR created: %s" % out.get("html_url"))
    except urllib.error.HTTPError as e:
        sys.stderr.write("POST failed: HTTP %d\n%s\n"
                         % (e.code, e.read().decode("utf-8", "replace")))
        sys.stderr.write("payload preserved at %s\nmanual send: %s\n"
                         % (payload_path, curl_fallback(payload_path, endpoint)))
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write("POST failed: %s\npayload preserved at %s\nmanual send: %s\n"
                         % (e, payload_path, curl_fallback(payload_path, endpoint)))
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    for name in ("status", "push", "pr"):
        p = sub.add_parser(name)
        p.add_argument("--upstream", required=True)
        p.add_argument("--fork-owner", required=True)
        p.add_argument("--branch", required=True)
        p.add_argument("--base-ref", default="develop")
        if name == "push":
            p.add_argument("--package-dir", required=True)
            p.add_argument("--message", required=True)
            p.add_argument("--update", action="store_true")
            p.add_argument("--yes", action="store_true")
        if name == "pr":
            p.add_argument("--title", required=True)
            p.add_argument("--body-file", required=True)
            p.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    if args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "push":
        cmd_push(args)
    elif args.cmd == "pr":
        cmd_pr(args)
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd ~/worktrees/skills-create-cubrid-testcase/cubrid-testcase-creation-common/scripts
python3 -m unittest discover -s tests -v
```
Expected: OK, 14 tests.

- [ ] **Step 7: Read-only integration checks**

```bash
cd ~/worktrees/skills-create-cubrid-testcase/cubrid-testcase-creation-common/scripts
bash -lc 'export GITHUB_TOKEN; python3 fetch_context.py engine-pr CUBRID/cubrid#7213 --out /tmp/ep.md' && head -3 /tmp/ep.md
bash -lc 'export GITHUB_TOKEN; python3 fetch_context.py tree CUBRID/cubrid-testcases --grep cbrd_25709 --prefix sql/' 
bash -lc 'export GITHUB_TOKEN; python3 push_package.py status --upstream CUBRID/cubrid-testcases --fork-owner junsklee --branch cbrd_99999_tc'
```
Expected: engine-pr writes markdown with `Title:` line; tree prints `sql/_13_issues/_26_2h/cases/cbrd_25709.sql` and its `.answer`; status prints JSON with `"branch_exists": false, "pr": null`.

Also verify push dry-run stays read-only:
```bash
mkdir -p /tmp/pkgtest/sql/cases && echo 'select 1;' > /tmp/pkgtest/sql/cases/t.sql
bash -lc 'export GITHUB_TOKEN; python3 push_package.py push --upstream CUBRID/cubrid-testcases --fork-owner junsklee --branch cbrd_99999_tc --package-dir /tmp/pkgtest --message test'
```
Expected: `[dry-run] would create branch …` lines only; then re-run `status` → still `"branch_exists": false`.

- [ ] **Step 8: Report DONE (controller commits)** — do not run git.

---

### Task 2: Vendor tw-kang assets into both skills

**Files:**
- Create: `create-cubrid-shell-testcase/references/init_sh_helpers.md`, `references/crash_cas_patterns.md`, `references/directory_guide.md`
- Create: `create-cubrid-shell-testcase/examples/{basic_entry.sh,config_change.sh,utility_test.sh,output_comparison.sh,cci_crash_repro.sh,cci_crash_repro.c}`
- Create: `create-cubrid-sql-testcase/examples/{bug_fix_error_cases.sql,bug_fix_select.sql,feature_query_plan.sql}`

**Interfaces:** Consumes: the tw-kang clone (Global Constraints). Produces: vendored files that Tasks 4, 5, 6, 7 reference by the paths above.

- [ ] **Step 1: Refresh clone, capture commit, copy with provenance headers**

```bash
SRC=/tmp/claude-1004/-home-qahome/a5dd2d1f-8b15-4f87-94ff-d5d277f9fd04/scratchpad/twkang-skills
cd $SRC && git pull -q; SHA=$(git rev-parse --short HEAD); echo "vendoring from $SHA"
W=~/worktrees/skills-create-cubrid-testcase
mkdir -p $W/create-cubrid-shell-testcase/references $W/create-cubrid-shell-testcase/examples \
         $W/create-cubrid-sql-testcase/examples
for f in init_sh_helpers crash_cas_patterns directory_guide; do
  { echo "<!-- Vendored from tw-kang/skills@develop ($SHA), cubrid-shell-tc-create/references/$f.md. Refresh from upstream; do not fork content silently. -->"; \
    cat $SRC/cubrid-shell-tc-create/references/$f.md; } > $W/create-cubrid-shell-testcase/references/$f.md
done
for f in basic_entry.sh config_change.sh utility_test.sh output_comparison.sh cci_crash_repro.sh; do
  { echo "# Vendored from tw-kang/skills@develop ($SHA), cubrid-shell-tc-create/examples/$f"; \
    cat $SRC/cubrid-shell-tc-create/examples/$f; } > $W/create-cubrid-shell-testcase/examples/$f
done
{ echo "/* Vendored from tw-kang/skills@develop ($SHA), cubrid-shell-tc-create/examples/cci_crash_repro.c */"; \
  cat $SRC/cubrid-shell-tc-create/examples/cci_crash_repro.c; } > $W/create-cubrid-shell-testcase/examples/cci_crash_repro.c
for f in bug_fix_error_cases.sql bug_fix_select.sql feature_query_plan.sql; do
  { echo "-- Vendored from tw-kang/skills@develop ($SHA), cubrid-sql-tc-create/examples/$f"; \
    cat $SRC/cubrid-sql-tc-create/examples/$f; } > $W/create-cubrid-sql-testcase/examples/$f
done
```

Caution: `basic_entry.sh` begins with `#!/bin/bash` — the provenance line lands ABOVE the shebang, which breaks direct execution. These examples are reference material (never executed), but to keep them clean insert the provenance line AFTER the shebang when the first line starts with `#!`:

```bash
cd $W/create-cubrid-shell-testcase/examples
for f in *.sh; do
  if [ "$(sed -n '2p' $f | grep -c '^#!')" = "1" ]; then
    sed -i '1{h;d};2{G}' $f   # swap line1 (provenance) and line2 (shebang)
  fi
done
head -2 $W/create-cubrid-shell-testcase/examples/basic_entry.sh
```
Expected: line 1 = `#!/bin/bash` (or the file's original first line), line 2 = provenance comment. Verify every vendored file: `grep -L "Vendored from tw-kang" $W/create-cubrid-shell-testcase/references/*.md $W/create-cubrid-shell-testcase/examples/* $W/create-cubrid-sql-testcase/examples/*` prints nothing.

- [ ] **Step 2: Verify content integrity (no truncation)**

```bash
for pair in "cubrid-shell-tc-create/references/init_sh_helpers.md create-cubrid-shell-testcase/references/init_sh_helpers.md" \
            "cubrid-sql-tc-create/examples/feature_query_plan.sql create-cubrid-sql-testcase/examples/feature_query_plan.sql"; do
  set -- $pair; a=$SRC/$1; b=$W/$2
  echo "$1: src=$(wc -l < $a) vendored=$(wc -l < $b)"   # vendored = src + 1 (provenance line)
done
```

- [ ] **Step 3: Report DONE (controller commits)** — do not run git.

---

### Task 3: Common references (`two-phase-protocol.md`, `verify-procedure.md`)

**Files:**
- Create: `cubrid-testcase-creation-common/references/two-phase-protocol.md`
- Create: `cubrid-testcase-creation-common/references/verify-procedure.md`

**Interfaces:** Consumes: tw-kang verify SKILL.mds (read from the clone at `$SRC/cubrid-sql-tc-verify/SKILL.md` and `$SRC/cubrid-shell-tc-verify/SKILL.md` for distillation; cite their commit). Produces: the two files Tasks 6/7 reference verbatim by path.

- [ ] **Step 1: Write `two-phase-protocol.md`** with exactly this content:

````markdown
# Two-phase creation protocol (shared contract)

Both creation skills follow this protocol. State lives in GitHub, not on
disk: the fork branch `cbrd_NNNNN_tc` is the single source of truth.

## Phase detection

Run `push_package.py status --upstream <repo> --fork-owner junsklee
--branch cbrd_NNNNN_tc`:

| branch_exists | empty_answers | pr | Phase |
|---|---|---|---|
| false | — | — | Phase 1 (fresh draft) |
| true | non-empty | null | Phase 2 (answers pending) |
| true | empty list | null | Phase 2, step 3 (ready for PR) |
| true | — | number | DONE — point the user at the PR; stop |

If the branch exists but the user asked for a fresh draft, offer:
resume (phase 2) / overwrite (`push --update`, only with explicit consent) /
abort. NEVER force-push or overwrite silently.

## Execution policy (host-conditional)

`CUBRID_TC_ALLOW_LOCAL_CTP=1` in the environment enables local answer
generation via `verify-procedure.md`. Flag absent → static-only: seeded
empty answers + printed verify handoff. On the QAHome development host the
flag must never be set (production CUBRID lives there); the deployment
machine sets it deliberately.

## Confirmation gates (both are hard gates)

1. **Push gate** — nothing is pushed to the fork until the user explicitly
   approves the rendered package in this conversation.
2. **PR gate** — no PR is opened until the user explicitly approves the
   rendered Korean PR body. `push_package.py` is dry-run by default; `--yes`
   only after the corresponding gate.

## Verify handoff (printed at end of phase 1 when answers are empty)

```
검증 필요 — 테스트 장비에서:
1. (없다면) CTP 설치 및 빌드 설치 — verify-procedure.md 참고
2. cubrid-sql-tc-verify 또는 cubrid-shell-tc-verify 스킬로
   <branch의 testcase 경로> 를 실행해 .answer 생성/검증
3. 생성된 .answer(.result) 파일을 가지고 동일 스킬을 다시 호출하면
   Phase 2(답지 검증 → 커밋 → PR)로 이어집니다.
```

## PR conventions (phase 2, step 3)

- Title: `[CBRD-NNNNN] <English description>`.
- Body: Korean; line 1 exactly `Refer to: http://jira.cubrid.org/browse/CBRD-NNNNN`;
  then scenario/coverage summary and the verification evidence the user
  supplied (build id, pass output).
- Base `develop`, head `junsklee:cbrd_NNNNN_tc`, upstream CUBRID repo.
````

- [ ] **Step 2: Write `verify-procedure.md`** with exactly this content (distilled from tw-kang `cubrid-sql-tc-verify` and `cubrid-shell-tc-verify`; keep the provenance line, substituting the actual commit):

````markdown
<!-- Distilled from tw-kang/skills@develop (<COMMIT>) cubrid-sql-tc-verify/SKILL.md + cubrid-shell-tc-verify/SKILL.md. -->
# Verify procedure — answer generation and pass/fail on a CTP host

Dual use: (a) the runbook the skills execute locally when
`CUBRID_TC_ALLOW_LOCAL_CTP=1`; (b) the handoff instructions printed for a
test machine otherwise. NEVER run any of this on the QAHome development
host.

## Preconditions

- CTP at `$CTP_HOME` (env → `~/CTP` → `~/cubrid-testtools/CTP`). Sanity:
  `ls $CTP_HOME/bin/ctp.sh` (sql) / `ls $CTP_HOME/shell/init_path/init.sh` (shell).
  Missing → `git clone https://github.com/CUBRID/cubrid-testtools.git && cp -rf cubrid-testtools/CTP ~/`.
- A CUBRID build URL for the binary under test.
- Work from a scratch dir: `work=$(mktemp -d)`.

## Install the build (both categories)

```bash
sh "$CTP_HOME/common/script/run_cubrid_install" <build_url> 2>&1 | tee "$work/install.log"
grep '\[ERROR\]' "$work/install.log"        # any hit -> stop, show lines
source ~/.cubrid.sh && cubrid_rel            # must print a version
```
`run_cubrid_install` can return 0 on failure and wipes `$HOME/CUBRID` first —
trust the binary, not the exit code.

## SQL cases

1. Locale lib (DB startup fails without it) and a real JDK (CTP compiles
   Java SP classes; `which java` may be a JRE):
   ```bash
   export JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java))))
   [ -x "$JAVA_HOME/bin/javac" ] || JAVA_HOME=$(dirname "$JAVA_HOME")
   [ ! -f $CUBRID/lib/libcubrid_all_locales.so ] && sh $CUBRID/bin/make_locale.sh -t 64bit
   ```
2. Category → conf → run command: `sql` → `sql.conf` → `run`; path contains
   `/medium/` → `medium_dev.conf` → `run`; `sql_by_cci` → `sql_by_cci.conf`
   → `run_cci`.
3. Structure: the `.sql` must sit in `cases/` with a sibling `answers/`.
   **Seed an empty `answers/<name>.answer` first** — interactive `run`
   silently SKIPS a case with no answer file (`Total:1 / Success:0 / Fail:0`).
4. Execute (DB setup takes 1–3 min):
   ```bash
   printf "%s %s\nquit\n" "run" "$SQL_FILE" | \
     timeout 600 "$CTP_HOME/bin/ctp.sh" sql -c "$CTP_HOME/conf/sql.conf" --interactive 2>&1 | tee "$work/run.log"
   ```
5. Verdict: `RESULT_DIR=$(grep "^Result Root Dir" "$work/run.log" | head -1 | awk -F': ' '{print $2}' | tr -d ' ')`;
   `cat "$RESULT_DIR/main.info"` — `Fail: 0` = PASS.
6. **Answer generation loop**: first run diffs against the empty answer
   (Fail:1) and writes real output to `$RESULT_DIR/.../<name>.result`.
   Promote it: copy over `answers/<name>.answer`, re-run, expect `Success:1`.
   Read the final `.answer` and confirm it matches intent (row counts,
   `Error:-NNN` codes, `===` statement separators).

## Shell cases

1. Locate `{name}/cases/{name}.sh`; read it first (platform guards, services).
2. Execute from the `cases/` dir with a timeout:
   ```bash
   export init_path="$CTP_HOME/shell/init_path"
   cd <case dir> && timeout 300 sh <name>.sh 2>&1 | tee "$work/run.log"; echo "exit=$?"
   ```
3. Verdict: `cat <case dir>/<name>.result` — `OK` = pass, `NOK` = fail
   (exit 124 = timeout = fail). On NOK: check `$work/run.log`,
   `$CUBRID/log/server/*.err`, core files.
4. Afterwards check leftovers (`cubrid server status`, `ps -ef | grep cub_`)
   and clean up.

## Classify a failure before touching the answer

- **answer-fix**: format/identifier-only diff (hash suffixes, XASL ids,
  plan text, byte counters) — regenerate the baseline.
- **bug-report**: crash/core, wrong result, lock change — file it with
  evidence; do NOT bake it into the `.answer`.

## Pitfalls

- "No Results!!" → wrong `.sql` path / not in a `cases/` dir.
- "Failed to connect to database server" → missing locale lib, port
  conflict, or disk full. "Cannot connect to a broker" → broker down/port
  33120 busy.
- "socket path is too long (>108)" → CUBRID installed too deep; use a short
  path like `~/CUBRID`.
- `javac not found` → JAVA_HOME points at a JRE (fix per SQL step 1).
- Answer file missing → the case is skipped, not run (SQL step 3).
````

Replace `<COMMIT>` with the actual short SHA from `git -C $SRC rev-parse --short HEAD`.

- [ ] **Step 3: Sanity check**

```bash
cd ~/worktrees/skills-create-cubrid-testcase/cubrid-testcase-creation-common/references
grep -c "CUBRID_TC_ALLOW_LOCAL_CTP" two-phase-protocol.md   # expect 1
grep -c "Seed an empty" verify-procedure.md                  # expect 1
grep -c "Vendored\|Distilled" verify-procedure.md            # expect 1
```

- [ ] **Step 4: Report DONE (controller commits)** — do not run git.

---

### Task 4: `create-cubrid-sql-testcase/references/sql-authoring.md`

**Files:**
- Create: `create-cubrid-sql-testcase/references/sql-authoring.md`

**Interfaces:** Consumes: nothing. Produces: drafting doctrine injected into the SQL drafter subagent (Task 6 references this path).

- [ ] **Step 1: Write the file** with exactly this content:

````markdown
# SQL test-case authoring doctrine (drafter-facing)

You are DRAFTING a new CTP SQL test case. Follow every rule here; the
self-review gate checks them with the reviewer doctrine afterwards.

## Package shape

- `cases/<name>.sql` + seeded EMPTY `answers/<name>.answer` sharing the
  basename. NEVER write answer content by hand — CTP generates it.
- Optimizer/plan test → also an EMPTY `cases/<name>.queryPlan` sidecar
  (case-sensitive extension).
- Bug fix: `sql/_13_issues/_{yy}_{1|2}h/cases/…`; release-targeted issue:
  `sql/_{no}_{release_code}/cbrd_XXXXX/cases/…` — match where sibling
  issues of the same release actually landed (release targeting beats JIRA
  creation date). Multiple files per issue share ONE `cases/`+`answers/`
  pair with suffixes (`cbrd_XXXXX_select.sql`) — never one subdir per file.
- Supplementing existing tests for the same CBRD → keep their naming scheme.

## File structure

- Header block first:
  `/** This test case verifies CBRD-XXXXX: <title> */` plus a numbered
  `Coverage:` list that matches what the file actually tests.
- `evaluate 'Case N: description';` before each scenario, numbered
  sequentially, captions truthful. 3–10 scenarios per file is the norm.
- Setup at top, cleanup at bottom. `DROP TABLE IF EXISTS t;` before every
  `CREATE TABLE` (drop children before parents when FKs exist).
- **The suite shares ONE database.** Undo everything at the end: drop every
  table/view/serial/trigger/procedure, `deallocate prepare` every
  `prepare`, `drop variable` every session variable, restore every
  `SET SYSTEM PARAMETERS` to its original value.
- Comments always on their OWN line above a statement — a trailing
  same-line comment can break the CTP runner.

## Determinism by construction

- Every SELECT that can return >1 row gets a full, discriminating
  `ORDER BY` (add tie-breakers until total). Single-row/scalar/aggregate
  SELECTs get NO ORDER BY.
- Never let volatile values reach the answer: no bare
  timestamps/OIDs/UUID raw values/Java object hashes — assert derived
  values instead (`count(*)`, `bit_length(...)`, `typeof(...)`, substrings).
- Simple, distinct data values (`1,2,3` / `'a','b'`) so answer diffs read
  cleanly; explicit column lists on INSERT when it aids readability.
- Plan tests: pin the plan — hints (`NO_ELIMINATE_JOIN`, `ORDERED`,
  `MATERIALIZE`, `/*+ recompile */`) where needed; `UPDATE STATISTICS ON
  <tables>` scoped to the tables under test, never `all classes`.

## Error cases

- Assert the `-NNN` code alone (the corpus norm). `--+ server-message
  on`/`off` (always paired) ONLY for PL/CSQL `DBMS_OUTPUT` or when the
  exact message text is the point.
- Mark intentional error cases in the caption ("expects Error:-NNN").
- An unexpected error/result may be a product bug: do not design the case
  to bake it in — flag it for a CBRD issue instead.

## Faithfulness and minimality

- Reproduce the EXACT issue conditions from JIRA/engine PR: same syntax
  form, same predicate/expression shape, required `SET SYSTEM PARAMETERS`.
  A look-alike scenario that misses the code path is worthless.
- Only what exercises the target issue — no unrelated setup, hints, or
  padding cases. Cover: main success path, main failure/exclusion path,
  boundaries, empty/no-match, NULL when relevant.
- Proofread adapted/copied SQL for copy-paste artifacts: wrong
  object/user/variable names, stale JIRA numbers, unmatched parentheses,
  wrong argument counts.
- Record known gaps/limitations as `-- todo:` comments with rationale.
````

- [ ] **Step 2: Report DONE (controller commits)** — do not run git.

---

### Task 5: `create-cubrid-shell-testcase/references/shell-authoring.md`

**Files:**
- Create: `create-cubrid-shell-testcase/references/shell-authoring.md`

**Interfaces:** Consumes: nothing (companion vendored refs arrive via Task 2; reference them by filename only). Produces: drafting doctrine injected into the shell drafter subagent (Task 7 references this path).

- [ ] **Step 1: Write the file** with exactly this content:

````markdown
# Shell test-case authoring doctrine (drafter-facing)

You are DRAFTING a new CTP shell test case. Follow every rule here; the
self-review gate checks them with the reviewer doctrine afterwards.
Companion references in this directory: `init_sh_helpers.md` (full helper
list), `crash_cas_patterns.md` (crash/CAS recipes), `directory_guide.md`
(placement rules) — consult them while drafting. Style anchors live in
`../examples/`.

## Package shape

- Entry script `{test_name}/cases/{test_name}.sh` — directory name and
  script filename MUST match. Helper scripts / embedded `.c` clients live
  in the same `cases/` dir (committed next to the `.sh`).
- Bug fix bucket: `shell/_06_issues/_{yy}_{1|2}h/…` from the JIRA creation
  date; feature: `shell/_{no}_{release_code}/{feature_group}/…`. Multiple
  tests per issue: `cbrd_XXXXX_1` / `cbrd_XXXXX_{keyword}` suffixes.

## Lifecycle skeleton (every entry script)

```bash
#!/bin/bash
# CBRD-XXXXX: one-line statement of what this verifies.
# Setup -> action -> expected outcome, in 1-2 lines.
# (platform macro BEFORE init.sh when needed: WINDOWS_NOT_SUPPORTED)

. $init_path/init.sh
init test

dbname=db_xxxxx

# --- Setup ---
cubrid_createdb $dbname
cubrid server start $dbname || { write_nok "server start failed"; finish; exit 0; }

# --- Test --- (SQL inline via single-quoted heredocs; capture to logs)
csql -udba "$dbname" > result.log 2>&1 <<'EOF'
CREATE TABLE t1 (id INT PRIMARY KEY);
EOF

# --- Verify ---
if [ <condition> ]; then write_ok; else write_nok result.log; fi

# --- Cleanup (reverse order, on EVERY exit path) ---
cubrid server stop $dbname
cubrid deletedb $dbname
rm -f *.log csql.*
finish
```

- Every code path ends at exactly ONE of `write_ok`/`write_nok`, then
  reaches `finish` LAST — including early-exit error branches.
- `finish` reverts conf changes, stops services, frees broker shared
  memory; a path that skips it poisons the next test.

## Helpers over raw commands (review-blocking if violated)

`cubrid_createdb` (not `cubrid createdb`), `change_db_parameter` /
`change_broker_parameter` (not conf edits — auto-reverted by `finish`),
`xgcc` (not raw gcc), `xkill` (not kill -9/pkill), `write_ok`/`write_nok`
(not echoed PASS/FAIL), `format_csql_output`/`format_query_plan`/
`format_path_output`/`diff_ignore_lineno` before any diff. Full list:
`init_sh_helpers.md`.

## Writing rules

- SQL inline via single-quoted heredocs (`<<'EOF'`); never separate `.sql`
  files. Quote variables (`"$db"`). No hardcoded paths (`/tmp`, `/home`) —
  use `$init_path`, `$CUBRID`, cwd, `$TMPDIR`.
- Bounded loops only (poll with a counter, never `while true`); sleeps
  >10s become condition-based polling. Track every background PID
  (`cmd & pid=$!`) with a matching `wait`/`xkill`.
- Error handling on fallible steps:
  `cmd || { write_nok "reason"; <cleanup>; finish; exit 0; }`.
- Assertions specific enough not to match unrelated log lines; check exit
  codes AND observable behavior. Never destructive cleanup like
  `rm -rf $db` on paths you did not create; no global service commands
  unless the issue requires them.
- Timing: `\time -f "%e"` if you must time something (bare `time` is not
  everywhere); prefer condition polling over timing at all.

## Crash / CAS tests

Default broker is `broker1`. Single-CAS forcing, coredump baseline→delta
counting, CAS-PID stability, and the embedded CCI `.c` client pattern:
follow `crash_cas_patterns.md` exactly — pass condition combines workload
ok AND PID stable AND no new cores.

## Faithfulness and minimality

- Reproduce the exact JIRA repro (mode matters: SA vs CS, csql vs broker
  client). If the issue is csql-only, drive csql; if it needs a driver,
  embed the CCI client.
- Only what exercises the issue; no padding. Answer/inline-expected
  comparisons must normalize volatile output first (`format_*` helpers).
- Environment failures (lib/permission/locale) must not be reportable as
  product regressions — guard and classify.
````

- [ ] **Step 2: Report DONE (controller commits)** — do not run git.

---

### Task 6: `create-cubrid-sql-testcase/SKILL.md`

**Files:**
- Create: `create-cubrid-sql-testcase/SKILL.md`

**Interfaces:** Consumes: Task 1 CLI contracts; Task 3 references; Task 4 doctrine; Task 2 examples. Produces: the SQL creation skill entry point.

- [ ] **Step 1: Write the file** with exactly this content:

````markdown
---
name: create-cubrid-sql-testcase
description: Create a CUBRID CTP SQL test case (.sql + CTP-generated .answer) for a CBRD JIRA issue — draft from the issue and engine PR, route the mined test-creation KB, self-review with the reviewer doctrine, then push a fork branch and open the PR only after explicit user confirmation. Use for "sql tc 만들어줘", "SQL 테스트케이스 작성해줘", "create sql testcase for CBRD-XXXXX", "CBRD-XXXXX sql tc 생성". NOT for shell test cases (create-cubrid-shell-testcase), reviewing existing PRs (review-cubrid-testcase-pr), or plain SQL help.
---

# Create CUBRID SQL Test Case

Draft → gate → confirm → push → verify → PR, per the shared two-phase
protocol. Nothing is pushed or posted without explicit user confirmation.

## Execution policy

Local CTP/csql/cubrid execution is allowed ONLY when
`CUBRID_TC_ALLOW_LOCAL_CTP=1` is set (deployment machine). Flag absent —
including always on the QAHome development host — this skill is static-only
and uses the verify handoff. `.answer` content is NEVER written by hand.

## Path resolution

- `$SKILL` = this skill's real directory (resolve the symlink).
- `$COMMON` = `$SKILL/../cubrid-testcase-creation-common` — scripts
  (`fetch_context.py`, `push_package.py`) and references
  (`two-phase-protocol.md`, `verify-procedure.md`). Missing → STOP.
- `$REVIEWER` = `~/.claude/skills/review-cubrid-testcase-pr` (resolved).
  Its `references/` are the self-review gate. Missing → STOP (gate is core).
- `$RUBRIC` = `$CUBRID_REVIEW_RUBRIC_DIR` or `~/pr-review-mining/reviewer_rubric`;
  `$KB` = `$CUBRID_TESTCREATE_KB_DIR` or `~/pr-review-mining/test_creation_kb`.
  Either missing → note "(rubric|KB) not found — degraded" and continue.
- `$work` = fresh scratchpad dir. Upstream repo: `CUBRID/cubrid-testcases`;
  fork owner `junsklee`. All scripts run via
  `bash -lc 'export GITHUB_TOKEN; …'`.

## Phase detection (always first)

Read `$COMMON/references/two-phase-protocol.md`, then:
`python3 $COMMON/scripts/push_package.py status --upstream CUBRID/cubrid-testcases
--fork-owner junsklee --branch cbrd_NNNNN_tc` and route per its table
(fresh → Phase 1; answers pending → Phase 2; PR exists → report and stop).

## Phase 1 — draft

1. **Context.** `cubrid-jira search CBRD-NNNNN > $work/jira.md` (expected
   behavior, repro, acceptance criteria, linked engine PR). Engine PR:
   `python3 $COMMON/scripts/fetch_context.py engine-pr <ref> --out $work/engine_pr.md`.
   Category sanity: if the issue is shell-shaped (csql-only tool behavior,
   utilities, services, crash/recovery), STOP and point to
   create-cubrid-shell-testcase — never silently cross over.
2. **KB routing.** Match the feature against `$KB/INDEX.md` keywords; load
   the matching `topics/<slug>.md` + `$KB/categories/sql.md`. No match →
   category checklist only + visible note.
3. **Placement.** Existing tests for this CBRD?
   `fetch_context.py tree CUBRID/cubrid-testcases --grep cbrd_NNNNN` — hits
   → supplement mode (their naming scheme, suffixes). Fresh → propose the
   dir per `references/sql-authoring.md`, verifying release-dir placement
   against live sibling listings (`tree … --grep <release_code>` or
   `--prefix sql/_13_issues/`).
4. **Prior art.** `fetch_context.py get` 1–2 similar cases (+ this skill's
   `examples/`) as style anchors.
5. **Drafter subagent** writes the package to `$work/package/` mirroring
   repo paths, following IN ORDER: `$SKILL/references/sql-authoring.md`,
   the KB docs from step 2, prior art. Seeded EMPTY `.answer` (+ empty
   `.queryPlan` for plan tests).
6. **Self-review gate.** Reviewer subagent loads `$REVIEWER/references/`
   (review-core, sql-rules, calibration-exclusions) + `$RUBRIC` Tier 1+2
   (mined-rubric-overview, mined-general-rules, mined-sql-rules) + the KB
   topic doc, and reviews `$work/package/` as if it were a PR bundle
   (Korean output, verdict line first). `NEEDS FIX` → drafter fixes →
   re-review; max 2 loops, then surface findings to the user.
7. **Local answers (only if `CUBRID_TC_ALLOW_LOCAL_CTP=1`).** Follow
   `$COMMON/references/verify-procedure.md` (SQL section): seed → run →
   promote `.result` → re-run `Success:1`; fold real answers into the
   package; re-run the gate once.
8. **Render + push gate.** Show the package, placement rationale, coverage
   map, KB checklist satisfaction. On explicit user confirmation:
   `push_package.py push --upstream CUBRID/cubrid-testcases --fork-owner junsklee
   --branch cbrd_NNNNN_tc --package-dir $work/package --message "[CBRD-NNNNN] Add test case" --yes`
   (dry-run first, show it). Answers still empty → print the verify
   handoff from two-phase-protocol.md and STOP.

## Phase 2 — answers → PR

1. **Intake.** The user supplies `.result`/`.answer` file(s) or pasted
   content. Validate semantically BEFORE committing: each
   `evaluate 'Case N:'` produced the expected KIND of output; error cases
   show the intended `Error:-NNN`; no timestamps/OIDs/hashes/raw random
   values; row counts plausible vs setup; not encoding unfixed behavior
   (answer-fix vs bug-report per review-core.md). Suspicious → show the
   user the concern; do not commit silently.
2. **Gate re-run** over the complete package (sql + real answers).
3. **Commit + PR gate.** `push_package.py push … --update --yes` (answers
   only), then render the Korean PR body (per two-phase-protocol.md PR
   conventions: `Refer to:` line 1, coverage summary, verification
   evidence). On explicit confirmation:
   `push_package.py pr --upstream CUBRID/cubrid-testcases --fork-owner junsklee
   --branch cbrd_NNNNN_tc --title "[CBRD-NNNNN] <english>" --body-file $work/pr_body.md --yes`.

## Failure conditions

- `GITHUB_TOKEN` missing → stop. `$COMMON`/`$REVIEWER` missing → stop.
- `cubrid-jira` missing/issue restricted → proceed only with user-supplied
  scenario text + visible accuracy note.
- Push/PR HTTP failure → the script preserves the payload and prints a
  curl fallback; relay both.
- Gate still NEEDS FIX after 2 loops → show findings; user decides.
````

- [ ] **Step 2: Verify** `wc -l create-cubrid-sql-testcase/SKILL.md` < 200; `head -4` shows the frontmatter.

- [ ] **Step 3: Report DONE (controller commits)** — do not run git.

---

### Task 7: `create-cubrid-shell-testcase/SKILL.md`

**Files:**
- Create: `create-cubrid-shell-testcase/SKILL.md`

**Interfaces:** Consumes: Task 1 CLI contracts; Task 3 references; Task 5 doctrine; Task 2 vendored refs/examples. Produces: the shell creation skill entry point.

- [ ] **Step 1: Write the file** with exactly this content:

````markdown
---
name: create-cubrid-shell-testcase
description: Create a CUBRID CTP shell test case (.sh entry script, helpers, embedded CCI clients) for a CBRD JIRA issue — draft from the issue and engine PR, route the mined test-creation KB, self-review with the reviewer doctrine, then push a fork branch and open the PR only after explicit user confirmation. Use for "shell tc 만들어줘", "shell 테스트케이스 작성해줘", "create shell testcase for CBRD-XXXXX", "CBRD-XXXXX shell tc 생성". NOT for SQL test cases (create-cubrid-sql-testcase), HA/replication tests, reviewing existing PRs (review-cubrid-testcase-pr), or running tests on a build.
---

# Create CUBRID Shell Test Case

Draft → gate → confirm → push → verify → PR, per the shared two-phase
protocol. Nothing is pushed or posted without explicit user confirmation.

## Execution policy

Local CTP/csql/cubrid execution is allowed ONLY when
`CUBRID_TC_ALLOW_LOCAL_CTP=1` is set (deployment machine). Flag absent —
including always on the QAHome development host — this skill is static-only
and uses the verify handoff. Shell `.sh` drafting is static authoring;
`bash -n` syntax checking is always allowed.

## Path resolution

- `$SKILL` = this skill's real directory (resolve the symlink).
- `$COMMON` = `$SKILL/../cubrid-testcase-creation-common` — scripts
  (`fetch_context.py`, `push_package.py`) and references
  (`two-phase-protocol.md`, `verify-procedure.md`). Missing → STOP.
- `$REVIEWER` = `~/.claude/skills/review-cubrid-testcase-pr` (resolved).
  Its `references/` are the self-review gate. Missing → STOP (gate is core).
- `$RUBRIC` = `$CUBRID_REVIEW_RUBRIC_DIR` or `~/pr-review-mining/reviewer_rubric`;
  `$KB` = `$CUBRID_TESTCREATE_KB_DIR` or `~/pr-review-mining/test_creation_kb`.
  Either missing → note "(rubric|KB) not found — degraded" and continue.
- `$work` = fresh scratchpad dir. Upstream repo:
  `CUBRID/cubrid-testcases-private-ex`; fork owner `junsklee`. All scripts
  run via `bash -lc 'export GITHUB_TOKEN; …'`.

## Phase detection (always first)

Read `$COMMON/references/two-phase-protocol.md`, then:
`python3 $COMMON/scripts/push_package.py status --upstream CUBRID/cubrid-testcases-private-ex
--fork-owner junsklee --branch cbrd_NNNNN_tc` and route per its table
(fresh → Phase 1; pending → Phase 2; PR exists → report and stop).
Note: shell packages have no `.answer` files, so `empty_answers` is empty —
distinguish Phase 2 by the user bringing run results (`.result`, logs) or
asking to open the PR for an existing branch.

## Phase 1 — draft

1. **Context.** `cubrid-jira search CBRD-NNNNN > $work/jira.md`; engine PR
   via `python3 $COMMON/scripts/fetch_context.py engine-pr <ref> --out $work/engine_pr.md`.
   Category sanity: if the issue is a pure SQL semantics/answer test (no
   utilities, services, process control, or tool-specific behavior), STOP
   and point to create-cubrid-sql-testcase — never silently cross over.
2. **KB routing.** Match the feature against `$KB/INDEX.md`; load
   `topics/<slug>.md` + `$KB/categories/shell.md`. No match → category
   checklist only + visible note.
3. **Placement.** Existing tests for this CBRD?
   `fetch_context.py tree CUBRID/cubrid-testcases-private-ex --grep cbrd_NNNNN`
   — hits → supplement mode (`cbrd_NNNNN_1`/`_keyword` suffixes). Fresh →
   `shell/_06_issues/_{yy}_{1|2}h/cbrd_NNNNN/cases/` per
   `references/directory_guide.md`, verified against live sibling listings.
4. **Prior art.** `fetch_context.py get` 1–2 similar cases (+ this skill's
   `examples/`, esp. `basic_entry.sh` and `cci_crash_repro.*` for crash
   tests) as style anchors.
5. **Drafter subagent** writes `{name}/cases/{name}.sh` (+ helpers/`.c`)
   into `$work/package/` mirroring repo paths, following IN ORDER:
   `$SKILL/references/shell-authoring.md`, `init_sh_helpers.md`,
   `crash_cas_patterns.md` (crash tests), the KB docs from step 2, prior
   art. Then `bash -n` every `.sh` (syntax check only — always allowed).
6. **Self-review gate.** Reviewer subagent loads `$REVIEWER/references/`
   (review-core, shell-rules, calibration-exclusions) + `$RUBRIC` Tier 1+2
   (mined-rubric-overview, mined-general-rules, mined-shell-rules) + the
   KB topic doc, and reviews `$work/package/` as if it were a PR bundle
   (Korean output, verdict line first). `NEEDS FIX` → drafter fixes →
   re-review; max 2 loops, then surface findings to the user.
7. **Local run (only if `CUBRID_TC_ALLOW_LOCAL_CTP=1`).** Follow
   `$COMMON/references/verify-procedure.md` (shell section): run the case,
   expect `OK` in `.result`; on NOK diagnose before pushing; re-run the
   gate once if the script changed.
8. **Render + push gate.** Show the package, placement rationale, coverage
   map, KB checklist satisfaction, `bash -n` results. On explicit user
   confirmation: `push_package.py push --upstream CUBRID/cubrid-testcases-private-ex
   --fork-owner junsklee --branch cbrd_NNNNN_tc --package-dir $work/package
   --message "[CBRD-NNNNN] Add shell test case" --yes` (dry-run first, show
   it). Not yet run on a CTP host → print the verify handoff from
   two-phase-protocol.md and STOP.

## Phase 2 — run evidence → PR

1. **Intake.** The user supplies the test-machine evidence: `.result`
   content (`<name>-1 : OK`), run log excerpts, or fix requests from a NOK.
   Validate: OK verdict present; the log shows the intended scenario ran
   (not a setup/env failure masquerading as success); any script fixes from
   the NOK loop re-enter step 5–6 of Phase 1.
2. **Gate re-run** if any file changed since the last gate.
3. **Commit + PR gate.** Changed files: `push_package.py push … --update
   --yes`. Then render the Korean PR body (two-phase-protocol.md PR
   conventions, including the run evidence). On explicit confirmation:
   `push_package.py pr --upstream CUBRID/cubrid-testcases-private-ex
   --fork-owner junsklee --branch cbrd_NNNNN_tc --title "[CBRD-NNNNN] <english>"
   --body-file $work/pr_body.md --yes`.

## Failure conditions

- `GITHUB_TOKEN` missing → stop. `$COMMON`/`$REVIEWER` missing → stop.
- `cubrid-jira` missing/issue restricted → proceed only with user-supplied
  scenario text + visible accuracy note.
- Push/PR HTTP failure → payload preserved + curl fallback; relay both.
- Gate still NEEDS FIX after 2 loops → show findings; user decides.
````

- [ ] **Step 2: Verify** `wc -l create-cubrid-shell-testcase/SKILL.md` < 200; `head -4` shows the frontmatter.

- [ ] **Step 3: Report DONE (controller commits)** — do not run git.

---

### Task 8: Activation + degradation checks (controller-run)

**Files:**
- Create: symlinks `~/.claude/skills/create-cubrid-sql-testcase`, `~/.claude/skills/create-cubrid-shell-testcase`

**Interfaces:** Consumes: Tasks 1–7 complete and committed. Produces: activated skills for Task 9.

- [ ] **Step 1: Symlink both skills**

```bash
ln -sfn ~/worktrees/skills-create-cubrid-testcase/create-cubrid-sql-testcase ~/.claude/skills/create-cubrid-sql-testcase
ln -sfn ~/worktrees/skills-create-cubrid-testcase/create-cubrid-shell-testcase ~/.claude/skills/create-cubrid-shell-testcase
ls -l ~/.claude/skills/ | grep create-cubrid
```
Note: `$COMMON` resolves as `$SKILL/../cubrid-testcase-creation-common` AFTER symlink resolution — verify: `readlink -f ~/.claude/skills/create-cubrid-sql-testcase` then `ls "$(readlink -f ~/.claude/skills/create-cubrid-sql-testcase)/../cubrid-testcase-creation-common/scripts/push_package.py"`.

- [ ] **Step 2: Degradation checks (static, no subagents needed)**

- KB absent: confirm SKILL.md instructs "note + continue" — and that `$KB`=/nonexistent leaves phase-1 steps 1,3–8 runnable (doctrine review: the only KB consumer is step 2).
- Rubric absent: same — gate falls back to `$REVIEWER/references/` only.
- Reviewer refs absent: SKILL.md says STOP — confirm text present in both SKILL.mds: `grep -c "Missing → STOP" create-cubrid-*-testcase/SKILL.md` → 2 each.

- [ ] **Step 3: Commit anything uncommitted; ledger entry.**

---

### Task 9: Blind creation calibration (two parallel runs)

**Files:**
- Create: `~/pr-review-mining/review_runs/creation-acceptance/create-sql-cbrd25709.md` (report)
- Create: `~/pr-review-mining/review_runs/creation-acceptance/create-shell-cbrd26563.md` (report)
- Possibly modify: `create-cubrid-*/references/*.md` (tuning from findings)

**Interfaces:** Consumes: the activated skills. Produces: calibration evidence + tuned doctrine.

- [ ] **Step 1: SQL run.** A subagent executes `create-cubrid-sql-testcase` Phase 1 steps 1–6 for **CBRD-25709** exactly as SKILL.md specifies (drafter + gate inline), with these overrides: BLIND — must not read `CUBRID/cubrid-testcases#2988`, the merged `cbrd_25709.*` files, or `~/pr-review-mining/review_runs/pr2988*` until its draft is gated; STOP before step 8 (no push — dry-run only). THEN fetch the merged files (`fetch_context.py get CUBRID/cubrid-testcases sql/_13_issues/_26_2h/cases/cbrd_25709.sql --out …`) and compare: scenario coverage overlap, convention compliance (evaluate markers, cleanup, determinism), placement match, what the human version has that the draft lacks (misses) and vice versa. Report: flow log, the draft verbatim, gate verdicts per loop, comparison, tuning recommendations.

- [ ] **Step 2: shell run.** Same procedure with `create-cubrid-shell-testcase` for **CBRD-26563** (fixture: merged PR cubrid-testcases-private-ex#3626, file `shell/_06_issues/_26_1h/cbrd_26563/cases/cbrd_26563.sh`; blind includes `~/pr-review-mining/review_runs/pr3626*`). Extra check: draft passes `bash -n`.

- [ ] **Step 3: Acceptance criteria (evaluate honestly, each PASS/FAIL):**
  1. Draft lands in the correct directory (matches where the merged test actually lives).
  2. Draft covers the core repro scenario(s) of the JIRA issue (the merged test's main test point is present).
  3. Draft complies with category conventions (gate reached ✅ within 2 loops).
  4. No hand-written `.answer` content (SQL: seeded empty; shell: n/a).
  5. Nothing was pushed (dry-run only), nothing posted.

- [ ] **Step 4: Tune** `sql-authoring.md`/`shell-authoring.md` from misses (controller dispatches one fix subagent if needed), re-run unit tests, commit.

---

## Self-review (done at plan-writing time)

- **Spec coverage:** two skills + common dir (T1,3–7), vendoring w/ provenance (T2), KB routing + degradation (T6/T7 §2 + T8), reviewer gate w/ STOP (T6/T7 §6 + T8), two-phase + status detection (T3 protocol + T6/T7), execution-policy flag + verify-procedure dual use (T3 + T6/T7 §7), clone-free fork writes dry-run default (T1), PR conventions Korean (T3 protocol), supplement mode + sibling-verified placement (T6/T7 §3), blind calibration + degradation checks (T8–T9), unit tests (T1). No gaps found.
- **Placeholder scan:** clean — every content step carries full text; `<COMMIT>`/`$SHA` are execution-time substitutions with the exact command given.
- **Type consistency:** CLI flags in T6/T7 match T1's argparse definitions (`--upstream/--fork-owner/--branch/--package-dir/--message/--update/--yes`, `status/push/pr`, `engine-pr/tree/get`); `branch_name` output format `cbrd_NNNNN_tc` used consistently; reference filenames in SKILL.mds match T2–T5 outputs.
