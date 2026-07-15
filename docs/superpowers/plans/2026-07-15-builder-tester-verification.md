# Builder-Tester Verification Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the CUBRID shell test-creation suite a `verify_testcase.py` tool that submits a freshly drafted shell script to the Builder-Tester service, proving it fails on the pre-fix build and passes on the post-fix build (special cases exempted), and can derive `.answer` files from a real post-fix run — removing the human CTP handoff for shell TCs.

**Architecture:** A thin HTTP-primitives module (`btlib.py`, mirroring `ghlib.py`) plus one CLI orchestrator (`verify_testcase.py`, mirroring `push_package.py`) in the shared `cubrid-testcase-creation-common/scripts/`. All decision logic (request assembly, verdict computation, capture transform, commit-pair resolution) lives as pure module-level functions with unit tests; network I/O is isolated. The two creation/review skills call the CLI and degrade gracefully when the service is unreachable.

**Tech Stack:** Python 3.6 stdlib only (`urllib`, `json`, `base64`, `hashlib`, `argparse`, `re`, `time`, `unittest`) — no third-party packages, no `gh`/`jq`/`curl` dependency. Python 3.6 means **no f-strings, no walrus, no 3.7+ stdlib**; use `%`-formatting like the sibling scripts.

## Global Constraints

- **Python 3.6, stdlib only.** No third-party imports. Match the style of `ghlib.py` / `push_package.py` / `fetch_context.py` (module-top imports, `%`-formatting, dry-run-by-default + `--yes`, step-labeled error messages).
- **Dry-run by default; `--yes` to perform any network write** (build submission). Local file writes (deriving an answer into the case dir) are allowed without `--yes`, but the *submission that produces them* is gated.
- **Never execute tests, CTP, csql, cubrid, or `run_cubrid_install` on this host.** This tool only talks HTTP to the remote Builder-Tester; it never runs a build or test locally.
- **No secrets in requests.** `GITHUB_TOKEN` is used only for local GitHub commit-pair resolution and is never placed in a Builder-Tester payload. Never read or print credentials embedded in git remote URLs.
- **No Claude/Anthropic watermark** anywhere — not in code comments, commit messages, docs, or PR bodies. No `Co-Authored-By`, no 🤖.
- **`.answer` files are never hand-written** — only machine-derived from a real run, and always shown to the user for approval before use.
- **Config via env, with documented defaults:** `BUILDER_TESTER_URL` (default `http://192.168.2.154:8091`), `BUILDER_TESTER_WORKER_IPS` (default `192.168.2.154:8090` — the single node co-located with the report server).
- **Commit to the existing branch** `feat/builder-tester-verify` in `~/worktrees/skills-main` (branched off `feat/shell-verdict-mining`). Do not open a PR unless the user asks.

## Server contract (verified against source + live service 2026-07-15)

Gateway = report-server at `BUILDER_TESTER_URL`. Endpoints:

- `POST /api/builder/build` — body is the raw build request; returns `{"status": "accepted"|"queued"|"already_running"|"error", "taskId": "req_...", ...}`. (`queued`/`accepted`/`already_running` are emitted **only here**.)
- `GET /api/builder/status?taskId=ID` — returns **only** `{"status": "running", "progress", "progressSummary"}` while the task occupies the single build slot, or `{"status": "not_found"}` otherwise, or `{"status": "error"}` on handler failure. **CRITICAL: a *queued* task returns `not_found`** — queued requests live in `pendingRequests`, not `activeTasks`, and `/status?taskId=` only checks `activeTasks`. With `maxConcurrentBuilds=1` and multi-hour builds, a freshly submitted task commonly reads `not_found` for a long time while it waits. `not_found` therefore means "not currently building" (queued OR finished OR never existed) — **it is NOT a completion signal.**
- `GET /api/builder/status` (no `taskId`) — the all-tasks view: `{"activeTasks": [{"taskId", "progress", "progressSummary"}], "queuedRequests": N, "queuedTaskIds": ["req_...", ...]}`. This is how you tell a queued task from a finished one.
- `GET /api/reports?pageSize=N&page=P&q=QUERY` — `{"items": [...], "page", "pageSize", "totalItems", "totalPages"}`. Each item: `id` (== the taskId), `commits`, `results[]`, `verdict` (**null in practice — do not rely on it**). Each `results[]` entry: `test`, `commit` (full sha), `status` (`pass`/`fail`), `attempts`, `attemptLogMetadata[]` (`{logFileName, attempt, status}`).
- `GET /api/log/:req_id/tests/:filename` — full `sh -x`-traced stdout of one attempt (plain text).

Build request (custom-script mode) — minimal valid shape the client sends:

```json
{
  "commits": ["<pre_sha>", "<post_sha>"],
  "customShellScript": "<entry .sh content>",
  "customAttachments": [{"targetPath": "helper.c", "contentBase64": "..."}],
  "workerIps": ["192.168.2.154:8090"],
  "callbackUrl": "http://192.168.2.154:8091/callback",
  "runMode": "fixed-runs", "minRuns": 2, "maxRuns": 2,
  "buildType": "debug", "commitBuildMode": "checkout"
}
```

Facts that drive the design (verified against `Builder.java` / `BuilderTask.java`):
- `tests` is **omitted** — the Builder injects `["custom_script_test"]` itself when `customShellScript` is present (`Builder.java:780`), and `custom_script_test` runs in a temp dir (`BuilderTask.java:1783-1793`), so **`customScriptTestPath` is never sent** (the placeholder path does not consult it). Shell tests are location-independent (user-confirmed).
- `customAttachments` is only accepted alongside `customShellScript`. The server's `validateAttachmentTargetPath` (`Builder.java:991-1015`) rejects a leading `/`, NUL, **any whitespace**, the characters `' " ` $`, and any `.`/`..` path segment. The client must mirror these rules to fail fast before consuming builder capacity.
- `workerIps` is required for non-buildOnly requests.
- `commitBuildMode: "checkout"` builds each commit's actual tree independently (correct for a real pre/post pair); `baseline_cherrypick` would cherry-pick and is wrong here.
- The report `id` equals the `taskId` returned by submit.
- `compare_result_between_files <produced_log> <expected_answer> [sort]` — first arg is the produced/actual log, second is the checked-in answer (confirmed across the house corpus); an optional 3rd normalization arg (e.g. `sort`) may follow.

## File Structure

- **Create** `cubrid-testcase-creation-common/scripts/btlib.py` — Builder-Tester HTTP primitives + config. Mirrors `ghlib.py`.
- **Create** `cubrid-testcase-creation-common/scripts/verify_testcase.py` — CLI + all pure orchestration helpers. Mirrors `push_package.py`.
- **Create** `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` — unit tests for the pure helpers of both new modules.
- **Create** `cubrid-testcase-creation-common/references/builder-tester-verification.md` — reference doc the skills read.
- **Modify** `create-cubrid-shell-testcase/SKILL.md` — step 7 becomes the three-way verification ladder + the answer-derivation sub-step.
- **Modify** `cubrid-testcase-creation-common/references/two-phase-protocol.md` — add the remote-verification path.
- **Modify** `cubrid-testcase-creation-common/references/verify-procedure.md` — note the remote path as the primary verification for shell.
- **Modify** `review-cubrid-testcase-pr/SKILL.md` — add the optional, ask-first shell-PR verification step (with its own `$COMMON` path resolution).
- **Modify** `create-cubrid-sql-testcase/SKILL.md` — one-line note that Builder-Tester verification is shell-only.

Test command used throughout (run from `~/worktrees/skills-main`):

```bash
python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v
```

---

## Task 1: `btlib.py` — Builder-Tester HTTP primitives + config

**Files:**
- Create: `cubrid-testcase-creation-common/scripts/btlib.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py`

**Interfaces:**
- Produces: `builder_url() -> str`, `worker_ips() -> list[str]`, `bt_request(path, method="GET", data=None, timeout=60) -> dict`, `bt_get_text(path, timeout=60) -> str`, `class BuilderTesterError(Exception)`. Env vars `BUILDER_TESTER_URL`, `BUILDER_TESTER_WORKER_IPS`.

- [ ] **Step 1: Write the failing test**

Create `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` with this header and the first test class. **Do not add an `if __name__ == "__main__"` guard here** — later tasks append classes below, and the guard must live only at the end of the file (added by Task 6). The suite is always run via `unittest discover`.

```python
import base64
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import btlib
import verify_testcase as vt


class TestBtlibConfig(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k)
                       for k in ("BUILDER_TESTER_URL", "BUILDER_TESTER_WORKER_IPS")}
        for k in self._saved:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_builder_url_default(self):
        self.assertEqual(btlib.builder_url(), "http://192.168.2.154:8091")

    def test_builder_url_env_override_strips_trailing_slash(self):
        os.environ["BUILDER_TESTER_URL"] = "http://host:9000/"
        self.assertEqual(btlib.builder_url(), "http://host:9000")

    def test_worker_ips_default(self):
        self.assertEqual(btlib.worker_ips(), ["192.168.2.154:8090"])

    def test_worker_ips_env_override_trims_and_drops_empty(self):
        os.environ["BUILDER_TESTER_WORKER_IPS"] = " a:1 , ,b:2 ,"
        self.assertEqual(btlib.worker_ips(), ["a:1", "b:2"])

    def test_error_is_exception(self):
        self.assertTrue(issubclass(btlib.BuilderTesterError, Exception))
```

Note: the header imports `verify_testcase as vt` too, so it must exist. Create it as an empty-CLI stub in this task's Step 3 (or Task 2 creates it — either way the import must resolve before running any test). This task's Step 3 creates `btlib.py`; the `vt` import will fail until Task 2. To keep Task 1 runnable in isolation, create a one-line placeholder `verify_testcase.py` now containing only `"""placeholder — implemented in Task 2."""` and replace it fully in Task 2. (If executing strictly task-by-task with a fresh worker, this placeholder makes Task 1's tests pass; Task 2 overwrites it.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'btlib'`.

- [ ] **Step 3: Write minimal implementation**

Create the placeholder `cubrid-testcase-creation-common/scripts/verify_testcase.py`:

```python
"""placeholder — implemented in Task 2."""
```

Create `cubrid-testcase-creation-common/scripts/btlib.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS (5 tests in `TestBtlibConfig`).

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/btlib.py \
        cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: add Builder-Tester HTTP primitives (btlib)"
```

---

## Task 2: Request assembly + attachments

**Files:**
- Rewrite: `cubrid-testcase-creation-common/scripts/verify_testcase.py` (replace the placeholder)
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` (add classes)

**Interfaces:**
- Consumes: `btlib.worker_ips`, `btlib.builder_url`, `btlib.BuilderTesterError`.
- Produces: `b64_file(abs_path) -> str`; `validate_target(rel) -> None` (raises `ValueError` on any name the builder would reject); `collect_attachments(case_dir, entry_abs) -> list[dict]` (walks **`case_dir`** — the entry script's own directory — excluding the entry + dotfiles, each `{"targetPath", "contentBase64"}` sorted by targetPath); `build_request(script_text, commits, worker_ip_list, attachments=None, run_mode="fixed-runs", min_runs=2, max_runs=2, build_type="debug", callback_url=None, commit_build_mode="checkout") -> dict` (positional `worker_ip_list`); `parse_submit_response(resp) -> str` (taskId, raises `BuilderTesterError`).

**Design note (attachment walk root):** shell test packages keep every helper (`.c`/`.java`, data files, `.answer` files) **next to the entry `.sh` in the `cases/` dir**, and reference them relative to the run's cwd. `collect_attachments` therefore walks the entry's own directory (`case_dir = dirname(entry)`), never a staging root — this avoids emitting `..` targetPaths and never sweeps in a sibling `answers/` dir or a second test case. `derive-answer` (Task 6) writes derived `.answer` files into this same dir.

- [ ] **Step 1: Write the failing test**

Append to `test_builder_tester.py`:

```python
class TestValidateTarget(unittest.TestCase):
    def test_accepts_plain_relative(self):
        vt.validate_target("helper.c")
        vt.validate_target("sub/data.txt")

    def test_rejects_absolute_and_dotdot(self):
        for bad in ("/etc/passwd", "../x", "a/../b", "./x"):
            with self.assertRaises(ValueError):
                vt.validate_target(bad)

    def test_rejects_builder_forbidden_chars(self):
        for bad in ("a b.txt", 'a".txt', "a$b.txt", "a`b.txt", "a'b.txt"):
            with self.assertRaises(ValueError):
                vt.validate_target(bad)


class TestCollectAttachments(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cases = os.path.join(self.d, "shell", "_06_issues", "cbrd_1", "cases")
        os.makedirs(self.cases)
        self.entry = os.path.join(self.cases, "cbrd_1.sh")
        with open(self.entry, "w") as fh:
            fh.write("#!/bin/bash\n")
        with open(os.path.join(self.cases, "helper.c"), "w") as fh:
            fh.write("int main(){return 0;}\n")
        with open(os.path.join(self.cases, "cbrd_1.answer"), "w") as fh:
            fh.write("expected\n")
        os.makedirs(os.path.join(self.cases, "sub"))
        with open(os.path.join(self.cases, "sub", "data.txt"), "w") as fh:
            fh.write("x\n")
        with open(os.path.join(self.cases, ".hidden"), "w") as fh:
            fh.write("secret\n")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_walks_case_dir_excludes_entry_and_dotfiles(self):
        atts = vt.collect_attachments(self.cases, self.entry)
        paths = [a["targetPath"] for a in atts]
        self.assertEqual(paths, ["cbrd_1.answer", "helper.c", "sub/data.txt"])
        for a in atts:
            self.assertNotIn("..", a["targetPath"])
            self.assertTrue(a["contentBase64"])

    def test_ignores_sibling_dirs_outside_case_dir(self):
        # A sibling answers/ dir (SQL-style layout) is not walked.
        sib = os.path.join(self.d, "shell", "_06_issues", "cbrd_1", "answers")
        os.makedirs(sib)
        with open(os.path.join(sib, "x.answer"), "w") as fh:
            fh.write("y\n")
        paths = [a["targetPath"] for a in vt.collect_attachments(self.cases, self.entry)]
        self.assertNotIn("../answers/x.answer", paths)
        self.assertEqual(paths, ["cbrd_1.answer", "helper.c", "sub/data.txt"])

    def test_rejects_helper_with_forbidden_name(self):
        with open(os.path.join(self.cases, "bad name.sh"), "w") as fh:
            fh.write("x\n")
        with self.assertRaises(ValueError):
            vt.collect_attachments(self.cases, self.entry)


class TestBuildRequest(unittest.TestCase):
    def test_shape_omits_tests_and_scriptpath_and_defaults(self):
        req = vt.build_request("#!/bin/bash\n", ["aaa", "bbb"],
                               ["h:8090"], callback_url="http://cb/callback")
        self.assertNotIn("tests", req)
        self.assertNotIn("customScriptTestPath", req)
        self.assertEqual(req["commits"], ["aaa", "bbb"])
        self.assertEqual(req["customShellScript"], "#!/bin/bash\n")
        self.assertEqual(req["workerIps"], ["h:8090"])
        self.assertEqual(req["runMode"], "fixed-runs")
        self.assertEqual(req["minRuns"], 2)
        self.assertEqual(req["maxRuns"], 2)
        self.assertEqual(req["buildType"], "debug")
        self.assertEqual(req["commitBuildMode"], "checkout")
        self.assertEqual(req["callbackUrl"], "http://cb/callback")
        self.assertNotIn("customAttachments", req)

    def test_includes_attachments_when_present(self):
        atts = [{"targetPath": "a.c", "contentBase64": "eA=="}]
        req = vt.build_request("s", ["aaa"], ["h:8090"], attachments=atts,
                               callback_url="http://cb/callback")
        self.assertEqual(req["customAttachments"], atts)


class TestParseSubmitResponse(unittest.TestCase):
    def test_accepted_returns_task_id(self):
        self.assertEqual(vt.parse_submit_response(
            {"status": "accepted", "taskId": "req_1"}), "req_1")

    def test_queued_returns_task_id(self):
        self.assertEqual(vt.parse_submit_response(
            {"status": "queued", "taskId": "req_2"}), "req_2")

    def test_error_raises(self):
        with self.assertRaises(btlib.BuilderTesterError):
            vt.parse_submit_response({"status": "error", "message": "boom"})

    def test_missing_taskid_raises(self):
        with self.assertRaises(btlib.BuilderTesterError):
            vt.parse_submit_response({"status": "accepted"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `AttributeError: module 'verify_testcase' has no attribute 'validate_target'` (placeholder has none).

- [ ] **Step 3: Write minimal implementation**

Replace `cubrid-testcase-creation-common/scripts/verify_testcase.py` (drop the placeholder) with the module header, imports, and these functions plus a `main()` stub that argparse-prints help (the full CLI arrives in Task 6):

```python
#!/usr/bin/env python3
"""Verify a CTP shell test case against the Builder-Tester service (Python 3.6, stdlib).

Submits a drafted shell script in custom-script mode, builds a pre-fix and a
post-fix engine commit, and judges VERIFIED iff the post-fix build passes all
attempts and the pre-fix build fails at least one (special cases exempted).
Can also derive a .answer file from a real post-fix run.

DRY-RUN BY DEFAULT — build submission requires --yes.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btlib import (BuilderTesterError, bt_get_text, bt_request, builder_url,
                   worker_ips)
from fetch_context import parse_pr_ref
from ghlib import gh_request, token

# Characters the builder's validateAttachmentTargetPath rejects in a path segment.
_BAD_TARGET_RE = re.compile(r"""[\s"'`$]""")


def b64_file(abs_path):
    with open(abs_path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def validate_target(rel):
    """Reject any relative targetPath the builder would 400 on
    (Builder.java validateAttachmentTargetPath): leading '/', NUL, whitespace,
    quotes/backtick/'$', or a '.'/'..' path segment."""
    if not rel or rel.startswith("/") or "\x00" in rel:
        raise ValueError("attachment path not allowed by builder: %r" % rel)
    for seg in rel.split("/"):
        if seg in ("", ".", "..") or _BAD_TARGET_RE.search(seg):
            raise ValueError(
                "attachment name not allowed by builder: %r "
                "(no spaces, quotes, backtick, '$', or dot segments — rename it)"
                % rel)


def collect_attachments(case_dir, entry_abs):
    """Every non-entry, non-dot file under the entry script's own directory as
    a customAttachment, targetPath relative to that directory. Validates each
    name against the builder's rules so submission fails fast on a bad name."""
    base = os.path.abspath(case_dir)
    entry_abs = os.path.abspath(entry_abs)
    out = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith("."):
                continue
            ap = os.path.abspath(os.path.join(root, f))
            if ap == entry_abs:
                continue
            rel = os.path.relpath(ap, base).replace(os.sep, "/")
            validate_target(rel)
            out.append({"targetPath": rel, "contentBase64": b64_file(ap)})
    return sorted(out, key=lambda d: d["targetPath"])


def build_request(script_text, commits, worker_ip_list, attachments=None,
                  run_mode="fixed-runs", min_runs=2, max_runs=2,
                  build_type="debug", callback_url=None,
                  commit_build_mode="checkout"):
    req = {
        "commits": list(commits),
        "customShellScript": script_text,
        "workerIps": list(worker_ip_list),
        "runMode": run_mode,
        "minRuns": min_runs,
        "maxRuns": max_runs,
        "buildType": build_type,
        "commitBuildMode": commit_build_mode,
        "callbackUrl": callback_url or (builder_url() + "/callback"),
    }
    if attachments:
        req["customAttachments"] = attachments
    return req


def parse_submit_response(resp):
    task_id = resp.get("taskId")
    if resp.get("status") == "error" or not task_id:
        raise BuilderTesterError("build not accepted: %s" % resp)
    return task_id


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_subparsers(dest="cmd")
    ap.parse_args()
    ap.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
```

Note: `from fetch_context import parse_pr_ref` and `from ghlib import gh_request, token` at module top match house style (both siblings import from `ghlib` at top). `gh_request` is passed as an injectable default in Task 5 so unit tests never hit the network.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS (all new classes + Task 1).

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: request assembly + case-dir attachment collection"
```

---

## Task 3: Report location + verdict model

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` (add classes)

**Interfaces:**
- Produces: `locate_report(items, task_id) -> dict|None`; `results_by_commit(report) -> dict` (`{sha: {"attempts": [status,...], "logs": [logFileName,...]}}`); `judge_matrix(by_commit, pre_sha, post_sha, special_case=None) -> dict` (keys: `verdict` ∈ {VERIFIED, NOT-VERIFIED, FLAKY, INCONCLUSIVE}, `reason`, `pre_sha`, `post_sha`, `pre_attempts`, `post_attempts`, `pre_logs`, `post_logs`, `special_case`); `format_verdict_block(judged, task_id) -> str` (emits direct `/api/log/...` URLs and a copy-ready `Verified:` line); `status_phase(status_resp) -> str` (`running`|`not_found`|`error`); `inconclusive(reason, pre_sha, post_sha) -> dict` (a synthesized judged block for infra failures).

- [ ] **Step 1: Write the failing test**

Append to `test_builder_tester.py`:

```python
class TestResultsByCommit(unittest.TestCase):
    REPORT = {"results": [
        {"commit": "PRE", "status": "fail",
         "attemptLogMetadata": [{"attempt": 1, "status": "fail", "logFileName": "pre1.log"},
                                {"attempt": 2, "status": "fail", "logFileName": "pre2.log"}]},
        {"commit": "POST", "status": "pass",
         "attemptLogMetadata": [{"attempt": 1, "status": "pass", "logFileName": "post1.log"},
                                {"attempt": 2, "status": "pass", "logFileName": "post2.log"}]},
    ]}

    def test_groups_attempts_and_logs_by_commit(self):
        by = vt.results_by_commit(self.REPORT)
        self.assertEqual(by["PRE"]["attempts"], ["fail", "fail"])
        self.assertEqual(by["POST"]["logs"], ["post1.log", "post2.log"])

    def test_falls_back_to_top_level_status(self):
        by = vt.results_by_commit({"results": [{"commit": "X", "status": "pass"}]})
        self.assertEqual(by["X"]["attempts"], ["pass"])
        self.assertEqual(by["X"]["logs"], [])


class TestLocateReport(unittest.TestCase):
    def test_finds_by_id(self):
        self.assertEqual(vt.locate_report([{"id": "a"}, {"id": "req_9"}], "req_9"),
                         {"id": "req_9"})

    def test_missing_returns_none(self):
        self.assertIsNone(vt.locate_report([{"id": "a"}], "req_9"))


class TestJudgeMatrix(unittest.TestCase):
    def by(self, pre, post):
        d = {}
        if pre is not None:
            d["PRE"] = {"attempts": pre, "logs": []}
        if post is not None:
            d["POST"] = {"attempts": post, "logs": []}
        return d

    def test_verified(self):
        self.assertEqual(vt.judge_matrix(self.by(["fail", "fail"], ["pass", "pass"]),
                                         "PRE", "POST")["verdict"], "VERIFIED")

    def test_verified_with_short_sha_prefix_lookup(self):
        by = {"aaaaaaaaaaaa": {"attempts": ["fail"], "logs": []},
              "bbbbbbbbbbbb": {"attempts": ["pass", "pass"], "logs": []}}
        self.assertEqual(vt.judge_matrix(by, "aaaaaaa", "bbbbbbb")["verdict"], "VERIFIED")

    def test_not_verified_when_prefix_passes(self):
        self.assertEqual(vt.judge_matrix(self.by(["pass", "pass"], ["pass", "pass"]),
                                         "PRE", "POST")["verdict"], "NOT-VERIFIED")

    def test_not_verified_when_postfix_fails(self):
        self.assertEqual(vt.judge_matrix(self.by(["fail", "fail"], ["fail", "fail"]),
                                         "PRE", "POST")["verdict"], "NOT-VERIFIED")

    def test_flaky_when_postfix_mixed(self):
        self.assertEqual(vt.judge_matrix(self.by(["fail", "fail"], ["pass", "fail"]),
                                         "PRE", "POST")["verdict"], "FLAKY")

    def test_inconclusive_when_no_postfix_result(self):
        self.assertEqual(vt.judge_matrix(self.by(["fail"], None), "PRE", "POST")["verdict"],
                         "INCONCLUSIVE")

    def test_inconclusive_when_postfix_infra_error(self):
        self.assertEqual(vt.judge_matrix(self.by(["fail"], ["error"]), "PRE", "POST")["verdict"],
                         "INCONCLUSIVE")

    def test_special_case_waives_prefix_pass(self):
        j = vt.judge_matrix(self.by(["pass", "pass"], ["pass", "pass"]),
                            "PRE", "POST", special_case="core-dump")
        self.assertEqual(j["verdict"], "VERIFIED")
        self.assertIn("waived", j["reason"])

    def test_post_only_waives_prefix(self):
        j = vt.judge_matrix(self.by(None, ["pass", "pass"]), None, "POST")
        self.assertEqual(j["verdict"], "VERIFIED")
        self.assertIn("post-only", j["reason"])


class TestStatusPhase(unittest.TestCase):
    def test_running(self):
        for s in ("running", "queued", "accepted", "already_running"):
            self.assertEqual(vt.status_phase({"status": s}), "running")

    def test_not_found_is_its_own_phase(self):
        self.assertEqual(vt.status_phase({"status": "not_found"}), "not_found")

    def test_error(self):
        self.assertEqual(vt.status_phase({"status": "error"}), "error")

    def test_progress_negative_one_is_error(self):
        self.assertEqual(vt.status_phase({"status": "running", "progress": -1}), "error")


class TestFormatVerdictBlock(unittest.TestCase):
    def test_includes_verdict_log_urls_and_verified_line(self):
        os.environ.pop("BUILDER_TESTER_URL", None)
        judged = {"verdict": "VERIFIED", "reason": "ok",
                  "pre_sha": "aaaaaaabbb", "post_sha": "cccccccddd",
                  "pre_attempts": ["fail"], "post_attempts": ["pass", "pass"],
                  "pre_logs": ["pre1.log"], "post_logs": ["post1.log", "post2.log"],
                  "special_case": None}
        out = vt.format_verdict_block(judged, "req_x")
        self.assertIn("VERDICT: VERIFIED", out)
        self.assertIn("/api/log/req_x/tests/post1.log", out)
        self.assertIn("Verified: pre-fix aaaaaaa", out)
        self.assertIn("NOK", out)
        self.assertIn("OK", out)


class TestInconclusive(unittest.TestCase):
    def test_shape(self):
        j = vt.inconclusive("builder unreachable", "PRE", "POST")
        self.assertEqual(j["verdict"], "INCONCLUSIVE")
        self.assertEqual(j["pre_attempts"], [])
        self.assertEqual(j["post_logs"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `AttributeError: ... has no attribute 'results_by_commit'`.

- [ ] **Step 3: Write minimal implementation**

Add to `verify_testcase.py` (above `main()`):

```python
_KNOWN_STATUS = ("pass", "fail")


def locate_report(items, task_id):
    for it in items:
        if it.get("id") == task_id:
            return it
    return None


def results_by_commit(report):
    """commit sha -> {'attempts': [status,...], 'logs': [logFileName,...]}."""
    out = {}
    for r in report.get("results", []):
        commit = r.get("commit")
        if not commit:
            continue
        meta = r.get("attemptLogMetadata", [])
        attempts = [a.get("status") for a in meta if a.get("status")]
        logs = [a.get("logFileName") for a in meta if a.get("logFileName")]
        if not attempts and r.get("status"):
            attempts = [r.get("status")]
        entry = out.setdefault(commit, {"attempts": [], "logs": []})
        entry["attempts"].extend(attempts)
        entry["logs"].extend(logs)
    return out


def _lookup(by_commit, sha):
    """Exact match, else unique prefix match (allows short --pre/--post shas)."""
    if sha in by_commit:
        return by_commit[sha]
    hits = [v for k, v in by_commit.items() if k.startswith(sha) or sha.startswith(k)]
    return hits[0] if len(hits) == 1 else {}


def _all_pass(attempts):
    return bool(attempts) and all(a == "pass" for a in attempts)


def _has_infra(attempts):
    return any(a not in _KNOWN_STATUS for a in attempts)


def _mixed(attempts):
    return ("pass" in attempts) and any(a != "pass" for a in attempts)


def judge_matrix(by_commit, pre_sha, post_sha, special_case=None):
    post_e = _lookup(by_commit, post_sha) if post_sha else {}
    pre_e = _lookup(by_commit, pre_sha) if pre_sha else {}
    post, pre = post_e.get("attempts", []), pre_e.get("attempts", [])
    j = {"verdict": None, "reason": "", "pre_sha": pre_sha, "post_sha": post_sha,
         "pre_attempts": pre, "post_attempts": post,
         "pre_logs": pre_e.get("logs", []), "post_logs": post_e.get("logs", []),
         "special_case": special_case}

    if not post:
        j["verdict"] = "INCONCLUSIVE"
        j["reason"] = "no post-fix result for %s" % (post_sha or "?")[:7]
        return j
    if _has_infra(post):
        j["verdict"] = "INCONCLUSIVE"
        j["reason"] = "post-fix build/infra error (non pass/fail attempt status)"
        return j
    if _mixed(post):
        j["verdict"] = "FLAKY"
        j["reason"] = "post-fix build produced mixed pass/fail attempts"
        return j
    if not _all_pass(post):
        j["verdict"] = "NOT-VERIFIED"
        j["reason"] = "post-fix build did not pass all attempts"
        return j

    if pre_sha is None:
        j["verdict"] = "VERIFIED"
        j["reason"] = "pre-fix expectation waived: post-only run"
        return j
    if not pre or _has_infra(pre):
        if special_case:
            j["verdict"] = "VERIFIED"
            j["reason"] = "pre-fix expectation waived: %s" % special_case
        else:
            j["verdict"] = "INCONCLUSIVE"
            j["reason"] = "no clean pre-fix result for %s" % pre_sha[:7]
        return j
    if not _all_pass(pre):
        j["verdict"] = "VERIFIED"
        j["reason"] = "pre-fix reproduced the bug (>=1 attempt failed); post-fix all pass"
        return j
    if special_case:
        j["verdict"] = "VERIFIED"
        j["reason"] = "pre-fix expectation waived: %s (pre-fix did not fail)" % special_case
    else:
        j["verdict"] = "NOT-VERIFIED"
        j["reason"] = "pre-fix build passed; test does not reproduce the bug"
    return j


def inconclusive(reason, pre_sha, post_sha):
    return {"verdict": "INCONCLUSIVE", "reason": reason,
            "pre_sha": pre_sha, "post_sha": post_sha,
            "pre_attempts": [], "post_attempts": [],
            "pre_logs": [], "post_logs": [], "special_case": None}


def format_verdict_block(judged, task_id):
    base = builder_url()

    def line(label, sha, attempts, expect):
        if sha is None:
            return "  %-9s (skipped): expected %s" % (label, expect)
        got = ", ".join("attempt %d %s" % (i + 1, s)
                        for i, s in enumerate(attempts)) or "no result"
        return "  %-9s %s: %s   (expected %s)" % (label, sha[:7], got, expect)

    out = ["VERDICT: %s" % judged["verdict"],
           "  %s" % judged["reason"],
           line("pre-fix", judged["pre_sha"], judged["pre_attempts"],
                "fail" if not judged["special_case"] else "fail (waived)"),
           line("post-fix", judged["post_sha"], judged["post_attempts"], "pass")]
    for label, logs in (("pre-fix", judged["pre_logs"]), ("post-fix", judged["post_logs"])):
        for fn in logs:
            out.append("  log %s: %s/api/log/%s/tests/%s" % (label, base, task_id, fn))
    if judged["verdict"] == "VERIFIED" and judged["pre_sha"] and judged["post_sha"]:
        out.append("  Verified: pre-fix %s -> NOK / post-fix %s -> OK"
                   % (judged["pre_sha"][:7], judged["post_sha"][:7]))
    elif judged["verdict"] == "VERIFIED" and judged["post_sha"]:
        out.append("  Verified: post-fix %s -> OK (pre-fix waived)"
                   % judged["post_sha"][:7])
    return "\n".join(out)


def status_phase(status_resp):
    if status_resp.get("progress") == -1:
        return "error"
    s = status_resp.get("status")
    if s == "not_found":
        return "not_found"
    if s == "error":
        return "error"
    return "running"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: report location + pre/post verdict model with log URLs"
```

---

## Task 4: Answer-file capture transform + extraction

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` (add classes)

**Interfaces:**
- Produces: `capture_transform(script_text) -> (new_text, mappings)` where `mappings = [(n, produced_arg, answer_arg), ...]`; `extract_answers(log_text, mappings) -> dict` (`{n: bytes}`); `suggest_answer_name(answer_arg, entry_stem, n) -> str`; `has_compare_calls(script_text) -> bool` (True if the substring exists even when no line matched — used to warn).

**Design note (argument order):** confirmed against the house corpus — `compare_result_between_files <produced_log> <expected_answer> [sort]`. `capture_transform` dumps the **first** arg (the produced log) since that is what a real run outputs and what the `.answer` must capture. It tolerates an optional trailing normalization arg and a leading `if !`/`while` guard.

- [ ] **Step 1: Write the failing test**

Append to `test_builder_tester.py`:

```python
class TestCaptureTransform(unittest.TestCase):
    def test_replaces_compare_calls_and_records_mapping(self):
        src = ("#!/bin/bash\n"
               "csql ... > a.log 2>&1\n"
               "    compare_result_between_files a.log a.answer\n"
               "finish\n")
        new, mapping = vt.capture_transform(src)
        self.assertEqual(mapping, [(1, "a.log", "a.answer")])
        self.assertIn('echo "ANSWER_BEGIN_1"', new)
        self.assertIn("base64 a.log", new)
        self.assertIn('echo "ANSWER_END_1"', new)
        self.assertNotIn("compare_result_between_files", new)
        self.assertIn("    echo", new)  # indentation preserved

    def test_tolerates_trailing_arg_and_if_guard(self):
        src = ("if ! compare_result_between_files x.log x.answer sort; then\n"
               "  write_nok\nfi\n")
        new, mapping = vt.capture_transform(src)
        self.assertEqual(mapping, [(1, "x.log", "x.answer")])
        self.assertIn("base64 x.log", new)

    def test_multiple_calls_numbered(self):
        src = ("compare_result_between_files x.log x.answer\n"
               "compare_result_between_files y.log y.answer\n")
        new, mapping = vt.capture_transform(src)
        self.assertEqual([m[0] for m in mapping], [1, 2])
        self.assertIn("ANSWER_BEGIN_2", new)

    def test_no_compare_calls_is_noop(self):
        src = "echo hi\nfinish\n"
        new, mapping = vt.capture_transform(src)
        self.assertEqual(mapping, [])
        self.assertEqual(new, src)
        self.assertFalse(vt.has_compare_calls(src))

    def test_has_compare_calls_true_when_present(self):
        self.assertTrue(vt.has_compare_calls("x=1; compare_result_between_files a b\n"))


class TestExtractAnswers(unittest.TestCase):
    def test_extracts_base64_between_exact_sentinels(self):
        payload = base64.b64encode(b"expected output\n").decode("ascii")
        log = ("+ echo ANSWER_BEGIN_1\n"      # sh -x trace (ignored)
               "ANSWER_BEGIN_1\n"             # real stdout sentinel
               "+ base64 a.log\n"             # trace (ignored)
               + payload + "\n"
               "ANSWER_END_1\n"
               "+ echo ANSWER_END_1\n")
        got = vt.extract_answers(log, [(1, "a.log", "a.answer")])
        self.assertEqual(got[1], b"expected output\n")

    def test_extracts_multiline_wrapped_base64(self):
        raw = b"x" * 200  # base64 wraps at 76 cols -> multiple payload lines
        payload = base64.b64encode(raw).decode("ascii")
        wrapped = "\n".join(payload[i:i + 76] for i in range(0, len(payload), 76))
        log = "ANSWER_BEGIN_1\n" + wrapped + "\nANSWER_END_1\n"
        self.assertEqual(vt.extract_answers(log, [(1, "a.log", "a.answer")])[1], raw)

    def test_missing_block_is_skipped(self):
        self.assertNotIn(1, vt.extract_answers("nothing\n", [(1, "a.log", "a.answer")]))


class TestSuggestAnswerName(unittest.TestCase):
    def test_literal_answer_arg_uses_basename(self):
        self.assertEqual(vt.suggest_answer_name("dir/cbrd_1.answer", "cbrd_1", 1),
                         "cbrd_1.answer")

    def test_variable_answer_arg_falls_back_to_stem(self):
        self.assertEqual(vt.suggest_answer_name("$db.answer", "cbrd_1", 1),
                         "cbrd_1.answer")

    def test_variable_multiple_uses_index(self):
        self.assertEqual(vt.suggest_answer_name("$db.answer", "cbrd_1", 2),
                         "cbrd_1_2.answer")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `AttributeError: ... has no attribute 'capture_transform'`.

- [ ] **Step 3: Write minimal implementation**

Add to `verify_testcase.py` (above `main()`):

```python
# Matches `compare_result_between_files <a1> <a2>` optionally preceded by an
# `if`/`while`/`!` guard token, capturing the first two arguments.
_COMPARE_RE = re.compile(
    r"^(?P<indent>\s*)(?:(?:if|while)\s+)?(?:!\s+)?"
    r"compare_result_between_files\s+(?P<a1>\S+)\s+(?P<a2>[^\s;&|]+)")
_B64_LINE_RE = re.compile(r"^[A-Za-z0-9+/=]+$")


def has_compare_calls(script_text):
    return "compare_result_between_files" in script_text


def capture_transform(script_text):
    """Replace each `compare_result_between_files <produced> <answer> [norm]`
    call with a sentinel base64 dump of its first (produced-log) argument.
    Returns (new_text, mappings=[(n, produced_arg, answer_arg), ...])."""
    lines = script_text.splitlines()
    out, mappings, n = [], [], 0
    for ln in lines:
        m = _COMPARE_RE.match(ln)
        if m:
            n += 1
            produced, answer, indent = m.group("a1"), m.group("a2"), m.group("indent")
            mappings.append((n, produced, answer))
            out.append('%secho "ANSWER_BEGIN_%d"; base64 %s; echo "ANSWER_END_%d"'
                       % (indent, n, produced, n))
        else:
            out.append(ln)
    text = "\n".join(out)
    if script_text.endswith("\n"):
        text += "\n"
    return text, mappings


def extract_answers(log_text, mappings):
    """Decode the base64 payload between the exact-line sentinels for each n.
    Robust to interleaved `sh -x` trace lines (they never equal the bare
    sentinel and are not pure base64)."""
    lines = log_text.splitlines()
    out = {}
    for n, _produced, _answer in mappings:
        begin, end = "ANSWER_BEGIN_%d" % n, "ANSWER_END_%d" % n
        try:
            bi = lines.index(begin)
            ei = lines.index(end, bi + 1)
        except ValueError:
            continue
        payload = "".join(x.strip() for x in lines[bi + 1:ei]
                          if _B64_LINE_RE.match(x.strip()))
        if not payload:
            continue
        try:
            out[n] = base64.b64decode(payload)
        except Exception:
            continue
    return out


def suggest_answer_name(answer_arg, entry_stem, n):
    """Target filename for a derived answer: the literal basename if the source
    used one, else <entry_stem>[_n].answer when it was a shell variable."""
    if "$" not in answer_arg and answer_arg not in (".", ".."):
        return os.path.basename(answer_arg)
    return "%s.answer" % entry_stem if n == 1 else "%s_%d.answer" % (entry_stem, n)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: answer-file capture transform + extraction"
```

---

## Task 5: Commit-pair resolution from an engine PR or JIRA key

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` (add class)

**Interfaces:**
- Consumes: `parse_pr_ref` (fetch_context), `gh_request` (ghlib).
- Produces: `merged_pair(merge_sha, first_parent_sha) -> (pre, post)`; `open_pair(merge_base_sha, head_sha) -> (pre, post)`; `resolve_commit_pair(ref, tok, gh=None) -> (pre_sha, post_sha)`; `resolve_issue_to_ref(issue_key, tok, gh=None) -> str` (unique `OWNER/REPO#N`, raises `BuilderTesterError` listing candidates on 0 or >1); `commit_subject(owner, repo, sha, tok, gh=None) -> str` (best-effort first line, "" on failure).

- [ ] **Step 1: Write the failing test**

Append to `test_builder_tester.py`:

```python
class TestCommitPairResolution(unittest.TestCase):
    def test_merged_pair(self):
        self.assertEqual(vt.merged_pair("MERGE", "PARENT"), ("PARENT", "MERGE"))

    def test_open_pair(self):
        self.assertEqual(vt.open_pair("BASE", "HEAD"), ("BASE", "HEAD"))

    def test_resolve_merged_pr_uses_first_parent_and_merge(self):
        def fake_gh(path, tok):
            if path.endswith("/pulls/7213"):
                return {"merged_at": "2026-01-01T00:00:00Z", "merge_commit_sha": "MERGE",
                        "base": {"ref": "develop"}, "head": {"sha": "HEAD"}}
            if "/commits/MERGE" in path:
                return {"parents": [{"sha": "PARENT"}, {"sha": "HEAD"}]}
            raise AssertionError("unexpected " + path)
        self.assertEqual(
            vt.resolve_commit_pair("https://github.com/CUBRID/cubrid/pull/7213", "t", gh=fake_gh),
            ("PARENT", "MERGE"))

    def test_resolve_open_pr_uses_merge_base_and_head(self):
        def fake_gh(path, tok):
            if path.endswith("/pulls/42"):
                return {"merged_at": None, "base": {"ref": "develop"}, "head": {"sha": "HEAD"}}
            if "/compare/" in path:
                return {"merge_base_commit": {"sha": "MB"}}
            raise AssertionError("unexpected " + path)
        self.assertEqual(vt.resolve_commit_pair("CUBRID/cubrid#42", "t", gh=fake_gh),
                         ("MB", "HEAD"))

    def test_resolve_issue_single_match(self):
        def fake_gh(path, tok):
            return {"items": [{"number": 55, "title": "[CBRD-26893] fix",
                               "repository_url": "https://api.github.com/repos/CUBRID/cubrid"}]}
        self.assertEqual(vt.resolve_issue_to_ref("CBRD-26893", "t", gh=fake_gh),
                         "CUBRID/cubrid#55")

    def test_resolve_issue_ambiguous_raises(self):
        def fake_gh(path, tok):
            return {"items": [
                {"number": 1, "title": "a", "repository_url": ".../CUBRID/cubrid"},
                {"number": 2, "title": "b", "repository_url": ".../CUBRID/cubrid"}]}
        with self.assertRaises(btlib.BuilderTesterError):
            vt.resolve_issue_to_ref("CBRD-26893", "t", gh=fake_gh)

    def test_resolve_issue_none_raises(self):
        with self.assertRaises(btlib.BuilderTesterError):
            vt.resolve_issue_to_ref("CBRD-1", "t", gh=lambda p, t: {"items": []})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `AttributeError: ... has no attribute 'merged_pair'`.

- [ ] **Step 3: Write minimal implementation**

Add to `verify_testcase.py` (above `main()`):

```python
def merged_pair(merge_sha, first_parent_sha):
    return (first_parent_sha, merge_sha)


def open_pair(merge_base_sha, head_sha):
    return (merge_base_sha, head_sha)


def resolve_commit_pair(ref, tok, gh=None):
    """Resolve an engine PR reference to (pre_fix_sha, post_fix_sha).
    Merged PR: (merge commit's first parent, merge commit) — robust to squash
    and true merges. Open PR: (merge-base against base branch, head)."""
    gh = gh or gh_request
    owner, repo, num = parse_pr_ref(ref)
    pr = gh("/repos/%s/%s/pulls/%d" % (owner, repo, num), tok)
    if pr.get("merged_at"):
        merge_sha = pr.get("merge_commit_sha")
        if not merge_sha:
            raise BuilderTesterError("merged PR #%d has no merge_commit_sha" % num)
        commit = gh("/repos/%s/%s/commits/%s" % (owner, repo, merge_sha), tok)
        parents = commit.get("parents", [])
        if not parents:
            raise BuilderTesterError("merge commit %s has no parents" % merge_sha[:7])
        return merged_pair(merge_sha, parents[0]["sha"])
    base = pr["base"]["ref"]
    head_sha = pr["head"]["sha"]
    cmp = gh("/repos/%s/%s/compare/%s...%s" % (owner, repo, base, head_sha), tok)
    mb = cmp.get("merge_base_commit", {}).get("sha")
    if not mb:
        raise BuilderTesterError("cannot resolve merge base for PR #%d" % num)
    return open_pair(mb, head_sha)


def resolve_issue_to_ref(issue_key, tok, gh=None):
    """Find the single CUBRID/cubrid PR whose title contains the CBRD key.
    Returns 'CUBRID/cubrid#N'; raises listing candidates on 0 or >1 matches."""
    gh = gh or gh_request
    q = "%s repo:CUBRID/cubrid in:title type:pr" % issue_key
    res = gh("/search/issues?q=" + urllib.parse.quote(q), tok)
    items = res.get("items", [])
    if not items:
        raise BuilderTesterError(
            "no CUBRID/cubrid PR found with %s in the title; pass --engine-pr" % issue_key)
    if len(items) > 1:
        listing = "; ".join("#%d %s" % (it["number"], it.get("title", "")) for it in items)
        raise BuilderTesterError(
            "%d PRs match %s — pass --engine-pr to pick one: %s"
            % (len(items), issue_key, listing))
    return "CUBRID/cubrid#%d" % items[0]["number"]


def commit_subject(owner, repo, sha, tok, gh=None):
    gh = gh or gh_request
    try:
        c = gh("/repos/%s/%s/commits/%s" % (owner, repo, sha), tok)
        return (c.get("commit", {}).get("message", "") or "").splitlines()[0]
    except Exception:
        return ""
```

Note: add `import urllib.parse` to the module-top imports (used by `resolve_issue_to_ref`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: engine-PR + JIRA-key commit-pair resolution"
```

---

## Task 6: CLI wiring (submit / wait / judge / run / derive-answer / health)

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` (add classes + the final `__main__` guard)

**Interfaces:**
- Consumes: every helper from Tasks 1–5.
- Produces: pure helpers `plan_commits(pre, post, engine_pair, post_only) -> (commits, pre, post)` and `elide_payload(req) -> dict`; the CLI subcommands. Exit codes from `judge`/`run`: `0` VERIFIED, `2` NOT-VERIFIED, `3` FLAKY, `4` INCONCLUSIVE, `1` operational error.

**Design note (`_wait` and the queued-task trap):** `/status?taskId=` returns `not_found` for a **queued** task (not just a finished one), so `not_found` is never treated as completion. `_wait` resolves it: on `not_found`, fetch the report — if present, done; else consult the all-tasks view (`GET /api/builder/status`) and, if the id is in `queuedTaskIds` or `activeTasks`, keep polling until `--timeout`. Only when the report is absent AND the id is neither queued nor active is the run considered finished-without-report (→ INCONCLUSIVE).

- [ ] **Step 1: Write the failing test**

Append to `test_builder_tester.py` (this block ends with the file's single `__main__` guard):

```python
class TestPlanCommits(unittest.TestCase):
    def test_post_only_from_pair(self):
        self.assertEqual(vt.plan_commits(None, None, ("PRE", "POST"), True),
                         (["POST"], None, "POST"))

    def test_explicit_pair(self):
        self.assertEqual(vt.plan_commits("PRE", "POST", None, False),
                         (["PRE", "POST"], "PRE", "POST"))

    def test_pair_from_engine(self):
        self.assertEqual(vt.plan_commits(None, None, ("PRE", "POST"), False),
                         (["PRE", "POST"], "PRE", "POST"))

    def test_explicit_overrides_engine(self):
        self.assertEqual(vt.plan_commits("X", "Y", ("PRE", "POST"), False),
                         (["X", "Y"], "X", "Y"))

    def test_post_only_needs_post(self):
        with self.assertRaises(ValueError):
            vt.plan_commits(None, None, None, True)

    def test_missing_pair_raises(self):
        with self.assertRaises(ValueError):
            vt.plan_commits("PRE", None, None, False)


class TestElidePayload(unittest.TestCase):
    def test_elides_script_and_attachments_with_sha256(self):
        req = vt.build_request("abc", ["a"], ["h:1"],
                               attachments=[{"targetPath": "x.c", "contentBase64": "eA=="}],
                               callback_url="http://c/callback")
        e = vt.elide_payload(req)
        self.assertIn("sha256:", e["customShellScript"])
        self.assertNotEqual(e["customShellScript"], "abc")
        self.assertIn("sha256:", e["customAttachments"][0]["contentBase64"])
        self.assertEqual(e["customAttachments"][0]["targetPath"], "x.c")
        self.assertEqual(e["commits"], ["a"])  # non-elided fields preserved


class TestCliDryRun(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cases = os.path.join(self.d, "shell", "cbrd_1", "cases")
        os.makedirs(self.cases)
        self.entry = os.path.join(self.cases, "cbrd_1.sh")
        with open(self.entry, "w") as fh:
            fh.write("#!/bin/bash\nfinish\n")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_submit_dry_run_prints_payload_without_network(self):
        env = dict(os.environ)
        env["BUILDER_TESTER_URL"] = "http://127.0.0.1:1"  # unreachable on purpose
        vt_path = os.path.join(os.path.dirname(__file__), "..", "verify_testcase.py")
        out = subprocess.run(
            [sys.executable, vt_path, "submit", "--script", self.entry,
             "--pre", "AAA", "--post", "BBB"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        text = out.stdout.decode("utf-8")
        self.assertEqual(out.returncode, 0, text)
        self.assertIn("[dry-run]", text)
        self.assertIn("AAA", text)
        self.assertIn("BBB", text)
        self.assertIn("customShellScript", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `AttributeError: ... has no attribute 'plan_commits'` (and the subprocess submit prints help / exits non-zero).

- [ ] **Step 3: Write minimal implementation**

Replace the `main()` stub in `verify_testcase.py` with the pure helpers, I/O helpers, command handlers, and the full argparse CLI:

```python
def plan_commits(pre, post, engine_pair, post_only):
    """Decide the commits list + (pre, post). engine_pair is a resolved
    (pre, post) tuple or None; explicit pre/post override it."""
    if engine_pair:
        pre = pre or engine_pair[0]
        post = post or engine_pair[1]
    if post_only:
        if not post:
            raise ValueError("--post-only requires a post-fix commit (--post or --engine-pr/--issue)")
        return ([post], None, post)
    if not pre or not post:
        raise ValueError("need a pre/post pair: pass --engine-pr/--issue REF or --pre SHA --post SHA")
    return ([pre, post], pre, post)


def elide_payload(req):
    """A print-safe copy: large content fields shown as size + sha256."""
    def mark(s):
        b = s.encode("utf-8")
        return "<%d bytes sha256:%s>" % (len(b), hashlib.sha256(b).hexdigest()[:12])
    safe = dict(req)
    safe["customShellScript"] = mark(req.get("customShellScript", ""))
    if "customAttachments" in req:
        safe["customAttachments"] = [
            {"targetPath": a["targetPath"], "contentBase64": mark(a["contentBase64"])}
            for a in req["customAttachments"]]
    return safe


def _engine_pair_and_owner(args):
    """Resolve --engine-pr/--issue to ((pre,post) or None, owner, repo). Explicit
    --pre/--post leave the pair None and default owner/repo to CUBRID/cubrid."""
    ref = args.engine_pr
    if getattr(args, "issue", None) and not ref:
        ref = resolve_issue_to_ref(args.issue, token())
        print("resolved %s -> %s" % (args.issue, ref))
    if ref:
        owner, repo, _num = parse_pr_ref(ref)
        return (resolve_commit_pair(ref, token()), owner, repo)
    return (None, "CUBRID", "cubrid")


def _echo_pair(owner, repo, pre, post):
    # Best-effort subjects: soft-read the token (never sys.exit here) so the
    # --pre/--post path needs no GITHUB_TOKEN; commit_subject swallows errors.
    tok = os.environ.get("GITHUB_TOKEN")
    for label, sha in (("pre-fix", pre), ("post-fix", post)):
        if sha:
            subj = commit_subject(owner, repo, sha, tok) if tok else ""
            print("  %-8s %s  %s" % (label, sha[:9], subj))


def _resolve_and_echo(args):
    pair, owner, repo = _engine_pair_and_owner(args)
    try:
        commits, pre, post = plan_commits(
            getattr(args, "pre", None), getattr(args, "post", None),
            pair, getattr(args, "post_only", False))
    except ValueError as e:
        sys.exit(str(e))
    print("Commit pair to build:")
    _echo_pair(owner, repo, pre, post)
    return commits, pre, post


def _load_script(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _post_build(req):
    print("Submitting to %s (consumes shared builder/tester capacity)..." % builder_url())
    return parse_submit_response(bt_request("/api/builder/build", method="POST", data=req))


def _submit(script_text, entry_abs, commits, args, yes):
    case_dir = os.path.dirname(os.path.abspath(entry_abs))
    atts = collect_attachments(case_dir, entry_abs)
    req = build_request(script_text, commits, worker_ips(), attachments=atts,
                        run_mode=args.run_mode, min_runs=args.min_runs,
                        max_runs=args.max_runs, build_type=args.build_type)
    if not yes:
        print("[dry-run] POST %s/api/builder/build" % builder_url())
        print(json.dumps(elide_payload(req), indent=2))
        print("[dry-run] pass --yes to submit")
        return None
    task_id = _post_build(req)
    print("taskId: %s" % task_id)
    return task_id


def _fetch_report(task_id):
    data = bt_request("/api/reports?q=%s&pageSize=50" % task_id)
    rep = locate_report(data.get("items", []), task_id)
    if rep is not None:
        return rep
    data = bt_request("/api/reports?pageSize=100")
    return locate_report(data.get("items", []), task_id)


def _pending(task_id):
    """True if task_id is currently queued or actively building."""
    try:
        st = bt_request("/api/builder/status")
    except BuilderTesterError:
        return False
    if task_id in st.get("queuedTaskIds", []):
        return True
    return any(t.get("taskId") == task_id for t in st.get("activeTasks", []))


def _wait(task_id, timeout):
    """Block until the report for task_id lands. Returns the report dict, or
    raises BuilderTesterError on timeout / finished-without-report."""
    print("Waiting for %s (timeout %ds)..." % (task_id, timeout))
    deadline = time.time() + timeout
    delay = 10
    while time.time() < deadline:
        st = bt_request("/api/builder/status?taskId=%s" % task_id)
        phase = status_phase(st)
        if phase == "error":
            raise BuilderTesterError("builder reported error for %s" % task_id)
        if phase == "running":
            print("  ... running %s" % (st.get("progressSummary") or st.get("progress") or ""))
        else:  # not_found: queued, finished, or absent
            rep = _fetch_report(task_id)
            if rep is not None:
                return rep
            if not _pending(task_id):
                raise BuilderTesterError(
                    "%s is neither building, queued, nor reported — it finished "
                    "without a report or never started; inspect the dashboard" % task_id)
            print("  ... queued (waiting for the build slot)")
        time.sleep(delay)
        delay = min(delay + 5, 30)
    raise BuilderTesterError(
        "timed out after %ds waiting for %s (still queued/running)" % (timeout, task_id))


_EXIT = {"VERIFIED": 0, "NOT-VERIFIED": 2, "FLAKY": 3, "INCONCLUSIVE": 4}


def _print_and_exit(judged, task_id):
    print(format_verdict_block(judged, task_id))
    sys.exit(_EXIT.get(judged["verdict"], 1))


def cmd_submit(args):
    commits, _pre, _post = _resolve_and_echo(args)
    _submit(_load_script(args.script), args.script, commits, args, args.yes)


def cmd_wait(args):
    _wait(args.task_id, args.timeout)
    print("report available for %s" % args.task_id)


def cmd_judge(args):
    _commits, pre, post = _resolve_and_echo(args)
    report = _fetch_report(args.task_id)
    if report is None:
        _print_and_exit(inconclusive("no report found for %s" % args.task_id, pre, post),
                        args.task_id)
    _print_and_exit(judge_matrix(results_by_commit(report), pre, post, args.special_case),
                    args.task_id)


def cmd_run(args):
    commits, pre, post = _resolve_and_echo(args)
    task_id = _submit(_load_script(args.script), args.script, commits, args, args.yes)
    if task_id is None:
        return  # dry-run
    try:
        report = _wait(task_id, args.timeout)
    except BuilderTesterError as e:
        _print_and_exit(inconclusive(str(e), pre, post), task_id)
    _print_and_exit(judge_matrix(results_by_commit(report), pre, post, args.special_case),
                    task_id)


def _derive_meta(report, post_sha):
    """Pick the post-fix results entry's first attempt log, guarding structure."""
    results = report.get("results") or []
    entry = next((r for r in results if (r.get("commit") or "").startswith(post_sha[:7])
                  or post_sha.startswith((r.get("commit") or "x")[:7])), None)
    entry = entry or (results[0] if results else None)
    if not entry:
        return None
    for a in entry.get("attemptLogMetadata", []):
        if a.get("logFileName"):
            return a["logFileName"]
    return None


def cmd_derive_answer(args):
    entry_abs = os.path.abspath(args.script)
    script_text = _load_script(args.script)
    if not has_compare_calls(script_text):
        sys.exit("no compare_result_between_files call found; nothing to derive")
    capture, mappings = capture_transform(script_text)
    if not mappings:
        sys.exit("compare_result_between_files present but no line matched the expected "
                 "'compare_result_between_files <log> <answer>' form; check the script")
    pair, owner, repo = _engine_pair_and_owner(args)
    post = args.post or (pair[1] if pair else None)
    if not post:
        sys.exit("need a post-fix commit: pass --post SHA or --engine-pr/--issue REF")
    print("Deriving answers from post-fix build:")
    _echo_pair(owner, repo, None, post)
    if not args.yes:
        print("[dry-run] would submit the capture variant (post-only) to derive %d answer(s)"
              % len(mappings))
        print(capture)
        print("[dry-run] pass --yes to submit")
        return
    case_dir = os.path.dirname(entry_abs)
    atts = collect_attachments(case_dir, entry_abs)
    req = build_request(capture, [post], worker_ips(), attachments=atts,
                        run_mode="fixed-runs", min_runs=1, max_runs=1,
                        build_type=args.build_type)
    task_id = _post_build(req)
    print("taskId: %s" % task_id)
    report = _wait(task_id, args.timeout)
    log_name = _derive_meta(report, post)
    if not log_name:
        sys.exit("post-fix run produced no attempt log for %s; cannot derive "
                 "(the build may have failed) — inspect report %s" % (post[:7], task_id))
    log = bt_get_text("/api/log/%s/tests/%s" % (task_id, log_name))
    answers = extract_answers(log, mappings)
    if not answers:
        sys.exit("no answer payload found in the post-fix run log; inspect %s" % task_id)
    entry_stem = os.path.splitext(os.path.basename(entry_abs))[0]
    for n, produced, answer_arg in mappings:
        if n not in answers:
            print("WARNING: no captured content for compare #%d (%s)" % (n, produced))
            continue
        dest = os.path.join(case_dir, suggest_answer_name(answer_arg, entry_stem, n))
        with open(dest, "wb") as fh:
            fh.write(answers[n])
        print("\n=== derived answer #%d -> %s (%d bytes) ===" % (n, dest, len(answers[n])))
        sys.stdout.buffer.write(answers[n])
        print("\n=== end answer #%d ===" % n)
    print("\nREVIEW REQUIRED: confirm each derived .answer matches the JIRA to-be "
          "behavior before using it. It was machine-derived from a real run.")


def cmd_health(args):
    ok = False
    for ep in ("/health", "/api/builder/health", "/api/reports?pageSize=1"):
        try:
            print("%s -> %s" % (ep, json.dumps(bt_request(ep))[:200]))
            ok = True
        except BuilderTesterError as e:
            print("%s -> UNREACHABLE: %s" % (ep, e))
    if not ok:
        sys.exit(1)


def _add_commit_args(p):
    p.add_argument("--engine-pr", help="engine PR ref (URL or OWNER/REPO#N)")
    p.add_argument("--issue", help="CBRD-XXXXX; resolves to its CUBRID/cubrid PR")
    p.add_argument("--pre", help="explicit pre-fix commit sha")
    p.add_argument("--post", help="explicit post-fix commit sha")
    p.add_argument("--post-only", action="store_true",
                   help="submit only the post-fix commit")


def _add_run_args(p):
    p.add_argument("--run-mode", default="fixed-runs")
    p.add_argument("--min-runs", type=int, default=2)
    p.add_argument("--max-runs", type=int, default=2)
    p.add_argument("--build-type", default="debug")
    p.add_argument("--special-case", default=None,
                   choices=["core-dump", "flaky-repro", "feature"],
                   help="waive the pre-fix-must-fail expectation")
    p.add_argument("--timeout", type=int, default=10800)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    ps = sub.add_parser("submit")
    ps.add_argument("--script", required=True)
    _add_commit_args(ps)
    _add_run_args(ps)
    ps.add_argument("--yes", action="store_true")

    pw = sub.add_parser("wait")
    pw.add_argument("--task-id", required=True)
    pw.add_argument("--timeout", type=int, default=10800)

    pj = sub.add_parser("judge")
    pj.add_argument("--task-id", required=True)
    _add_commit_args(pj)
    pj.add_argument("--special-case", default=None,
                    choices=["core-dump", "flaky-repro", "feature"])

    prn = sub.add_parser("run")
    prn.add_argument("--script", required=True)
    _add_commit_args(prn)
    _add_run_args(prn)
    prn.add_argument("--yes", action="store_true")

    pd = sub.add_parser("derive-answer")
    pd.add_argument("--script", required=True)
    pd.add_argument("--engine-pr")
    pd.add_argument("--issue")
    pd.add_argument("--post")
    pd.add_argument("--build-type", default="debug")
    pd.add_argument("--timeout", type=int, default=10800)
    pd.add_argument("--yes", action="store_true")

    sub.add_parser("health")

    args = ap.parse_args()
    try:
        handler = {"submit": cmd_submit, "wait": cmd_wait, "judge": cmd_judge,
                   "run": cmd_run, "derive-answer": cmd_derive_answer,
                   "health": cmd_health}.get(args.cmd)
        if handler is None:
            ap.print_help()
            sys.exit(2)
        handler(args)
    except BuilderTesterError as e:
        sys.exit("Builder-Tester unavailable: %s" % e)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS — including the subprocess dry-run submit (prints `[dry-run]`, `AAA`, `BBB`, `customShellScript`, exit 0, no network; the `_echo_pair` best-effort `commit_subject` fails silently to "" against the unreachable host).

Also sanity-check help:

Run: `python3 cubrid-testcase-creation-common/scripts/verify_testcase.py --help`
Expected: subcommands `submit`, `wait`, `judge`, `run`, `derive-answer`, `health`.

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: CLI (submit/wait/judge/run/derive-answer/health) with queued-task-safe wait"
```

---

## Task 7: Reference doc — `builder-tester-verification.md`

**Files:**
- Create: `cubrid-testcase-creation-common/references/builder-tester-verification.md`

- [ ] **Step 1: Write the reference doc**

Create `cubrid-testcase-creation-common/references/builder-tester-verification.md`:

```markdown
# Builder-Tester verification (shared reference)

Remote build+run verification for shell test cases. `verify_testcase.py`
submits a drafted `.sh` in custom-script mode, builds a pre-fix and a post-fix
engine commit, and judges whether the test reproduces the bug pre-fix and
passes post-fix. Shell only — the executor does not run SQL cases.

## Config

- `BUILDER_TESTER_URL` — report-server gateway. Default
  `http://192.168.2.154:8091`. Unset/unreachable → the skill degrades to the
  next verification rung (local CTP, then printed handoff).
- `BUILDER_TESTER_WORKER_IPS` — comma-separated tester nodes. Default
  `192.168.2.154:8090`.

Every subcommand talks only to the gateway; no test runs on this host.

## Commands

Run via `bash -lc 'export GITHUB_TOKEN; python3 $COMMON/scripts/verify_testcase.py <cmd> ...'`
(the token is only needed for `--engine-pr`/`--issue` resolution). Helper and
answer files are picked up automatically from the entry script's own directory
(`cases/`), so point `--script` at the entry `.sh` — there is no `--package`.

- `health` — read-only reachability check (tries `/health`,
  `/api/builder/health`, and `/api/reports`; healthy if any responds).
- `submit --script S (--engine-pr REF | --issue CBRD-XXXXX | --pre SHA --post SHA) [--yes]`
  — dry-run prints the payload (script/attachments elided to size+sha256);
  `--yes` submits and prints the `taskId`.
- `wait --task-id ID [--timeout 10800]` — block until the report lands.
- `judge --task-id ID (--engine-pr REF | --issue KEY | --pre SHA --post SHA) [--special-case X]`
  — print the verdict block; exit code encodes the verdict.
- `run ...` — submit + wait + judge in one call (still gated by `--yes`).
- `derive-answer --script S (--engine-pr REF | --issue KEY | --post SHA) [--yes]`
  — for drafts using `compare_result_between_files` before an answer exists.

`--special-case core-dump|flaky-repro|feature` waives only the
pre-fix-must-fail half (post-fix-must-pass is never waived).

## Commit pair

`--engine-pr` resolves the pair from the CUBRID/cubrid PR: merged →
(merge commit's first parent, merge commit); open → (merge-base vs base
branch, head). `--issue CBRD-XXXXX` searches CUBRID/cubrid PR titles for the
key and resolves the single match (lists candidates and asks for `--engine-pr`
if there are several). `--pre/--post` override explicitly. The resolved pair —
short SHA + commit subject — is echoed before every submission.

## Verdict semantics

VERIFIED iff **post-fix passes all attempts AND pre-fix fails ≥1 attempt**.

- Post-fix mixed pass/fail → FLAKY (never VERIFIED) — a drafting defect.
- Post-fix not all-pass → NOT-VERIFIED.
- Pre-fix all-pass → NOT-VERIFIED unless `--special-case` waives it.
- Missing report / non-pass-fail attempt status / builder error / timeout →
  INCONCLUSIVE (environment/tooling, never a product/test verdict).
- Post-only run → VERIFIED on post-fix pass, with `pre-fix expectation
  waived: post-only run` stated in the block.

Exit codes: 0 VERIFIED, 2 NOT-VERIFIED, 3 FLAKY, 4 INCONCLUSIVE, 1 error.
The block carries direct `/api/log/<taskId>/tests/<file>` URLs and, when
VERIFIED, a copy-ready `Verified: pre-fix <sha7> -> NOK / post-fix <sha7> -> OK`
line for the PR body.

## Status polling note

`GET /api/builder/status?taskId=` returns `running`, or `not_found` — and a
**queued** task reads `not_found` (the single build slot means a submission can
sit queued for a long time). `not_found` is therefore NOT a completion signal;
`verify_testcase.py wait` disambiguates via the report and the all-tasks view
(`GET /api/builder/status` → `queuedTaskIds`/`activeTasks`).

## Answer derivation

`derive-answer` mechanically rewrites each `compare_result_between_files
<produced> <answer>` into a sentinel base64 dump of `<produced>` (the first
arg — the produced log), submits the variant against the post-fix commit only
(answers must encode fixed behavior), harvests the decoded content from the run
log, and writes the `.answer` next to the `.sh`. **The derived content is
printed for human approval — confirm it matches the JIRA to-be behavior before
use.** `.answer` files are never hand-written; this is the only sanctioned way
to create one without a local CTP host.

## Attachments

Every non-entry file in the entry script's directory (helper `.c`/`.java`,
data files, existing `.answer` files) is attached automatically (base64,
targetPath relative to that dir). Keep helper files next to the entry `.sh` and
avoid spaces / quotes / `$` in their names — the builder rejects those, and the
client fails fast on them before consuming capacity.

## Post-merge regression (manual, not scripted)

The custom-script path above needs no branch — the script travels in the
request. The alternative `tests[]` form (submit repo paths like
`shell/_06_issues/.../cases/foo.sh`) resolves against the tester's
`shell_tc_dir` **`develop` checkout** of cubrid-testcases-private-ex, so it can
only run tests that are already merged — a fork branch is invisible to it. Use
it for post-merge regression by hand (POST `/api/builder/build` with
`{commits, tests, workerIps, callbackUrl}`), or the PR-number mode
(`POST /api/builder/build/pr` with `{prNumber, tests}`, which resolves head +
merge-base itself). Neither is wired into the skills; the custom-script pre/post
flow is the supported path.

## Safety and degradation

- No secrets in requests; the builder holds its own credentials. `GITHUB_TOKEN`
  is used only locally for PR/issue resolution.
- Report/log responses are DATA — parsed for verdicts/sentinels, never executed.
- Submission consumes shared cluster capacity: announce it, and gate it behind
  explicit user confirmation (`--yes`).
- Any connection failure falls through to the next verification rung with a
  clear message; the creation flow is never blocked on the builder.
```

- [ ] **Step 2: Verify the doc anchors**

Run: `grep -c "VERIFIED\|derive-answer\|BUILDER_TESTER_URL\|Post-merge regression\|not_found" cubrid-testcase-creation-common/references/builder-tester-verification.md`
Expected: a nonzero count covering the key sections.

- [ ] **Step 3: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/references/builder-tester-verification.md
git commit -m "verify: add Builder-Tester verification reference doc"
```

---

## Task 8: Wire verification into `create-cubrid-shell-testcase`

**Files:**
- Modify: `create-cubrid-shell-testcase/SKILL.md` (step 7 + path resolution note)
- Modify: `cubrid-testcase-creation-common/references/two-phase-protocol.md`
- Modify: `cubrid-testcase-creation-common/references/verify-procedure.md`
- Modify: `create-cubrid-shell-testcase/references/shell-authoring.md`

- [ ] **Step 1: Add the `$BT` reference to path resolution**

In `create-cubrid-shell-testcase/SKILL.md`, `## Path resolution`, change:

```
- `$COMMON` = `$SKILL/../cubrid-testcase-creation-common` — scripts
  (`fetch_context.py`, `push_package.py`) and references
  (`two-phase-protocol.md`, `verify-procedure.md`). Missing → STOP.
```

to:

```
- `$COMMON` = `$SKILL/../cubrid-testcase-creation-common` — scripts
  (`fetch_context.py`, `push_package.py`, `verify_testcase.py`) and references
  (`two-phase-protocol.md`, `verify-procedure.md`,
  `builder-tester-verification.md`). Missing → STOP.
- `$BT` = `$BUILDER_TESTER_URL` or `http://192.168.2.154:8091` — remote
  build+run verification gateway. Unreachable → skip remote verification and
  fall through the ladder (step 7).
```

- [ ] **Step 2: Replace step 7 with the three-way ladder**

In `create-cubrid-shell-testcase/SKILL.md`, replace the current step 7 (the
`Local run (only if CUBRID_TC_ALLOW_LOCAL_CTP=1)` block) with:

```
7. **Runtime verification (before the push gate).** Read
   `$COMMON/references/builder-tester-verification.md`, then take the first
   reachable rung:
   a. **Remote Builder-Tester** — `python3 $COMMON/scripts/verify_testcase.py
      health` responds. If the draft uses `compare_result_between_files` with
      no checked-in answer, first derive it:
      `verify_testcase.py derive-answer --script <entry.sh>
      --engine-pr <ref>` (dry-run, then `--yes` on confirmation) and get the
      printed answer approved by the user before continuing. Then verify:
      `verify_testcase.py run --script <entry.sh> --engine-pr <ref>`
      (dry-run first; `--yes` after announcing it consumes shared builder
      capacity). Helper/answer files next to the `.sh` are attached
      automatically — no `--package`. Fold the printed verdict block into the
      render (step 8) and the eventual PR body. VERIFIED → proceed.
      NOT-VERIFIED/FLAKY → diagnose and fix (re-enter steps 5–6); do not push a
      test that fails to reproduce or is flaky. INCONCLUSIVE → treat as a
      builder/env issue, report it, fall to rung b/c. A genuine special case
      (crash that will not reproduce in Docker, probabilistic repro, feature
      test) uses `--special-case core-dump|flaky-repro|feature` with a stated
      justification.
   b. **Local CTP** — only if `CUBRID_TC_ALLOW_LOCAL_CTP=1`: follow
      `$COMMON/references/verify-procedure.md` (shell section); expect `OK` in
      `.result`; on NOK diagnose before pushing; re-run the gate once if the
      script changed.
   c. **Printed handoff** — neither reachable: print the verify handoff from
      `two-phase-protocol.md` and continue static-only (Phase 2 resumes with
      evidence).
```

- [ ] **Step 3: Note remote evidence in the render/push step**

In step 8 (`Render + push gate`), change the first sentence from:

```
8. **Render + push gate.** Show the package, placement rationale, coverage
   map, KB checklist satisfaction, `bash -n` results.
```

to:

```
8. **Render + push gate.** Show the package, placement rationale, coverage
   map, KB checklist satisfaction, `bash -n` results, and — when remote
   verification ran — the `verify_testcase.py` verdict block (pre-fix NOK /
   post-fix OK) as first-class evidence.
```

- [ ] **Step 4: Add the remote path to `two-phase-protocol.md`**

In `cubrid-testcase-creation-common/references/two-phase-protocol.md`, in
`## Execution policy (host-conditional)`, after the existing paragraph add:

```

Shell cases have a third option that needs no CTP host and no fork branch:
remote Builder-Tester verification via `verify_testcase.py` (see
`builder-tester-verification.md`). When the gateway is reachable it runs
before the push gate and collapses the handoff — the verdict block becomes the
run evidence carried into the PR body. Order of preference for shell:
remote Builder-Tester → local CTP (`CUBRID_TC_ALLOW_LOCAL_CTP=1`) → printed
handoff. SQL cases have no remote option (the executor is shell-only).
```

- [ ] **Step 5: Note remote-primary in `verify-procedure.md`**

In `cubrid-testcase-creation-common/references/verify-procedure.md`, under the
top heading's intro paragraph, add:

```

> For shell cases, prefer remote Builder-Tester verification
> (`builder-tester-verification.md`) — it needs no local CTP install and
> proves pre-fix NOK / post-fix OK directly. Use the local runbook below only
> when the Builder-Tester gateway is unreachable and
> `CUBRID_TC_ALLOW_LOCAL_CTP=1` is set.
```

- [ ] **Step 6: Confirm the Verified header wording in `shell-authoring.md`**

Run: `grep -n "Verified: pre-fix" create-cubrid-shell-testcase/references/shell-authoring.md`
Expected: one match. If absent, add to the header bullet:
`A "Verified: pre-fix <sha> → NOK / post-fix <sha> → OK" line is encouraged once verify_testcase.py has produced a VERIFIED verdict.`

- [ ] **Step 7: Verify edits landed and files are well-formed**

Run:
```bash
python3 - <<'PY'
import io
for f in ["create-cubrid-shell-testcase/SKILL.md",
          "cubrid-testcase-creation-common/references/two-phase-protocol.md",
          "cubrid-testcase-creation-common/references/verify-procedure.md"]:
    io.open(f, encoding="utf-8").read()
print("all readable")
PY
grep -n "Runtime verification\|verify_testcase.py run\|derive-answer" create-cubrid-shell-testcase/SKILL.md
```
Expected: `all readable`, plus matches for each grep term.

- [ ] **Step 8: Commit**

```bash
cd ~/worktrees/skills-main
git add create-cubrid-shell-testcase/SKILL.md \
        create-cubrid-shell-testcase/references/shell-authoring.md \
        cubrid-testcase-creation-common/references/two-phase-protocol.md \
        cubrid-testcase-creation-common/references/verify-procedure.md
git commit -m "verify: wire remote verification into shell-testcase flow"
```

---

## Task 9: Reviewer opt-in verification + SQL skill note

**Files:**
- Modify: `review-cubrid-testcase-pr/SKILL.md`
- Modify: `create-cubrid-sql-testcase/SKILL.md`

- [ ] **Step 1: Locate the reviewer skill's step numbering + path section**

Run: `grep -n "^## \|Path resolution\|\$SKILL\|fetch_pr.py\|render\|verdict line" review-cubrid-testcase-pr/SKILL.md`
Expected: the section headers, the path-resolution block, and the numbered
review steps — so the new step is inserted after the review is rendered (never
before — verification is an optional add-on, not a gate).

- [ ] **Step 2: Add a `$COMMON` path resolution line to the reviewer skill**

The reviewer skill defines `$SKILL` but not `$COMMON`. In its path-resolution
section, add:

```
- `$COMMON` = `$SKILL/../cubrid-testcase-creation-common` — shared scripts
  (`fetch_context.py`, `verify_testcase.py`). Present only when the creation
  suite is installed; the optional verification step below needs it.
```

- [ ] **Step 3: Add the optional verification step**

After the step that renders the review (the last content step before posting),
insert:

```
### Optional: runtime verification of a shell TC PR (ask first)

For a shell test-case PR only, offer — never run unprompted — a remote
Builder-Tester check. It spends shared cluster capacity, so ask the user
first, and skip silently if `$COMMON` is absent or the gateway is unreachable.
On agreement, read `$COMMON/references/builder-tester-verification.md`, fetch
the PR's shell package into a scratch dir with
`python3 $COMMON/scripts/fetch_context.py get <owner/repo> <case-dir paths> --out $scratch --ref <pr-head-sha>`,
then run against the PR head's entry script and the issue's engine PR:

`python3 $COMMON/scripts/verify_testcase.py run --script <fetched entry.sh>
--engine-pr <engine ref>` (dry-run first, `--yes` after the user confirms).

The script travels in the custom-script request, so a fork branch is fine.
Fold the verdict block into the review as supporting evidence: VERIFIED
strengthens an approval; NOT-VERIFIED/FLAKY is a `NEEDS FIX` with the run as
proof; INCONCLUSIVE is a builder/env issue, reported as such — not a finding
against the PR. Never block a review on the gateway being reachable.
```

- [ ] **Step 4: Add the shell-only note to the SQL skill**

In `create-cubrid-sql-testcase/SKILL.md`, in its execution-policy or verify
section, add:

```
Note: remote Builder-Tester verification (create-cubrid-shell-testcase) does
not apply here — its executor runs shell cases only. SQL answer generation
uses the local CTP path or the printed verify handoff.
```

- [ ] **Step 5: Verify**

Run:
```bash
grep -n "runtime verification\|Builder-Tester\|\$COMMON" review-cubrid-testcase-pr/SKILL.md
grep -n "Builder-Tester" create-cubrid-sql-testcase/SKILL.md
python3 -c "import io; [io.open(f,encoding='utf-8').read() for f in ['review-cubrid-testcase-pr/SKILL.md','create-cubrid-sql-testcase/SKILL.md']]; print('ok')"
```
Expected: matches in both files; `ok`.

- [ ] **Step 6: Commit**

```bash
cd ~/worktrees/skills-main
git add review-cubrid-testcase-pr/SKILL.md create-cubrid-sql-testcase/SKILL.md
git commit -m "verify: reviewer opt-in shell verification + SQL shell-only note"
```

---

## Task 10: Live integration check + CBRD-26893 calibration runbook

**Files:**
- Create: `cubrid-testcase-creation-common/scripts/tests/live_check.sh`
- Create: `docs/superpowers/plans/2026-07-15-builder-tester-calibration.md`

- [ ] **Step 1: Write the read-only live check**

Create `cubrid-testcase-creation-common/scripts/tests/live_check.sh`:

```bash
#!/bin/bash
# Read-only Builder-Tester check. Submits NOTHING. Exercises the four §10
# read paths: /health, /api/builder/health, /api/reports, one attempt-log.
set -u
here=$(cd "$(dirname "$0")/.." && pwd)
echo "== health =="
python3 "$here/verify_testcase.py" health || exit 1
echo "== reports + one attempt log =="
python3 - "$here" <<'PY'
import sys, os
sys.path.insert(0, sys.argv[1])
import btlib
data = btlib.bt_request("/api/reports?pageSize=25")
assert "items" in data, data
print("reports OK: totalItems=%s" % data.get("totalItems"))
for item in data.get("items", []):
    for r in item.get("results", []):
        meta = r.get("attemptLogMetadata") or []
        if meta and meta[0].get("logFileName"):
            fn = meta[0]["logFileName"]
            txt = btlib.bt_get_text("/api/log/%s/tests/%s" % (item["id"], fn))
            assert txt, "empty log"
            print("attempt-log OK: %s/%s (%d bytes)" % (item["id"], fn, len(txt)))
            sys.exit(0)
print("no attempt log available to sample (reports have no results yet)")
PY
```

- [ ] **Step 2: Run the live check (informational)**

Run: `bash cubrid-testcase-creation-common/scripts/tests/live_check.sh`
Expected (gateway up): health lines, `reports OK: totalItems=<n>`, and
`attempt-log OK: ...`. Gateway down → `UNREACHABLE` and exit 1 — a valid
environment state, not a code failure.

- [ ] **Step 3: Write the calibration runbook**

Create `docs/superpowers/plans/2026-07-15-builder-tester-calibration.md`:

```markdown
# CBRD-26893 calibration run (manual, gated)

End-to-end proof of `verify_testcase.py` against a known real fix. Consumes
builder/tester capacity — run once, with user confirmation.

## Inputs
- Draft: the CBRD-26893 v3 shell TC (SIGSEGV on `IS NOT NULL` folding over
  db_class). Stage it so the entry script and its helpers sit together in a
  `cases/` dir; point `--script` at `cbrd_26893.sh`.
- Engine PR: the CUBRID/cubrid PR that fixed CBRD-26893 (or `--issue CBRD-26893`).

## Steps
1. `bash -lc 'export GITHUB_TOKEN; python3 $COMMON/scripts/verify_testcase.py \
   run --script <path>/cbrd_26893.sh --issue CBRD-26893'`  (dry-run — inspect
   the elided payload and the echoed pre/post pair with subjects)
2. Re-run with `--yes` after confirming the pair.
3. Expected verdict: **VERIFIED** — pre-fix build crashes (Test 1 exit ≠ 0 /
   Test 2 new coredump → NOK), post-fix build passes all three tests.
4. If FLAKY: the crash may not reproduce deterministically in Docker → re-run
   with `--special-case core-dump` and record the caveat.

## Record
Capture the verdict block (incl. the direct log URLs and the `Verified:` line)
and the report id. This both validates the tool and discharges the outstanding
runtime verification of the CBRD-26893 TC.
```

- [ ] **Step 4: Commit**

```bash
cd ~/worktrees/skills-main
chmod +x cubrid-testcase-creation-common/scripts/tests/live_check.sh
git add cubrid-testcase-creation-common/scripts/tests/live_check.sh \
        docs/superpowers/plans/2026-07-15-builder-tester-calibration.md
git commit -m "verify: live reachability check + CBRD-26893 calibration runbook"
```

---

## Final verification (after all tasks)

- [ ] **Run the full unit suite**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: all pass (existing `test_fetch_context`, `test_push_package`, plus the new `test_builder_tester`).

- [ ] **Confirm no bytecode is staged**

Run: `git status --porcelain | grep -E "\.pyc|__pycache__" || echo "clean"`
Expected: `clean` (the repo `.gitignore` already excludes them).

- [ ] **Confirm no watermark leaked into commits**

Run:
```bash
base=$(git merge-base feat/shell-verdict-mining HEAD)
git log --format='%an %s' "$base"..HEAD | grep -iE "claude|anthropic|co-authored" && echo "WATERMARK FOUND" || echo "clean"
```
Expected: `clean`.
