# Builder-Tester Verification Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the CUBRID shell test-creation suite a `verify_testcase.py` tool that submits a freshly drafted shell script to the Builder-Tester service, proving it fails on the pre-fix build and passes on the post-fix build (special cases exempted), and can derive `.answer` files from a real post-fix run — removing the human CTP handoff for shell TCs.

**Architecture:** A thin HTTP-primitives module (`btlib.py`, mirroring `ghlib.py`) plus one CLI orchestrator (`verify_testcase.py`, mirroring `push_package.py`) in the shared `cubrid-testcase-creation-common/scripts/`. All decision logic (request assembly, verdict computation, capture transform, commit-pair resolution) lives as pure module-level functions with unit tests; network I/O is isolated. The two creation/review skills call the CLI and degrade gracefully when the service is unreachable.

**Tech Stack:** Python 3.6 stdlib only (`urllib`, `json`, `base64`, `argparse`, `re`, `unittest`) — no third-party packages, no `gh`/`jq`/`curl` dependency. Talks only to the report-server gateway over plain HTTP on the LAN.

## Global Constraints

- **Python 3.6, stdlib only.** No third-party imports. Match the style of `ghlib.py` / `push_package.py` / `fetch_context.py`.
- **Dry-run by default; `--yes` to perform any network write** (build submission). Local file writes (deriving an answer into the staging dir) are allowed without `--yes`, but the *submission that produces them* is gated.
- **Never execute tests, CTP, csql, cubrid, or `run_cubrid_install` on this host.** This tool only talks HTTP to the remote Builder-Tester; it never runs a build or test locally.
- **No secrets in requests.** `GITHUB_TOKEN` is used only for local GitHub commit-pair resolution and is never placed in a Builder-Tester payload. Never read or print credentials embedded in git remote URLs.
- **No Claude/Anthropic watermark** anywhere — not in code comments, commit messages, docs, or PR bodies. No `Co-Authored-By`, no 🤖.
- **`.answer` files are never hand-written** — only machine-derived from a real run, and always shown to the user for approval before use.
- **Config via env, with documented defaults:** `BUILDER_TESTER_URL` (default `http://192.168.2.154:8091`), `BUILDER_TESTER_WORKER_IPS` (default `192.168.2.154:8090`).
- **Commit to the existing branch** `feat/builder-tester-verify` in `~/worktrees/skills-main`. Do not open a PR unless the user asks.

## Server contract (verified against source + live service 2026-07-15)

Gateway = report-server at `BUILDER_TESTER_URL`. Endpoints:

- `POST /api/builder/build` — body is the raw build request; returns `{"status": "accepted"|"queued"|"already_running"|"error", "taskId": "req_...", ...}`.
- `GET /api/builder/status?taskId=ID` — `{"status": "running"|"queued"|"not_found"|"error", "progress": ..., "progressSummary": ...}`. A completed task is removed from the active set, so its status becomes `not_found`.
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

Facts that drive the design:
- `tests` is **omitted** — the Builder injects `["custom_script_test"]` itself when `customShellScript` is present (Builder.java validation), and `custom_script_test` runs in a temp dir, so `customScriptTestPath` is unnecessary.
- `customAttachments` is only accepted alongside `customShellScript`; `targetPath` must be strictly relative (no `..`), `contentBase64` is the file bytes.
- `workerIps` is required for non-buildOnly requests.
- `commitBuildMode: "checkout"` builds each commit's actual tree independently (correct for a real pre/post pair); `baseline_cherrypick` would cherry-pick and is wrong here.
- The report `id` equals the `taskId` returned by submit.

## File Structure

- **Create** `cubrid-testcase-creation-common/scripts/btlib.py` — Builder-Tester HTTP primitives + config (`builder_url`, `worker_ips`, `bt_request`, `bt_get_text`, `BuilderTesterError`). Mirrors `ghlib.py`.
- **Create** `cubrid-testcase-creation-common/scripts/verify_testcase.py` — CLI + all pure orchestration helpers. Mirrors `push_package.py`.
- **Create** `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` — unit tests for the pure helpers of both new modules.
- **Create** `cubrid-testcase-creation-common/references/builder-tester-verification.md` — reference doc the skills read: flow, verdict semantics, config, degradation.
- **Modify** `create-cubrid-shell-testcase/SKILL.md` — step 7 becomes the three-way verification ladder + the answer-derivation sub-step.
- **Modify** `cubrid-testcase-creation-common/references/two-phase-protocol.md` — add the remote-verification path.
- **Modify** `cubrid-testcase-creation-common/references/verify-procedure.md` — note the remote path as the primary verification for shell.
- **Modify** `review-cubrid-testcase-pr/SKILL.md` — add the optional, ask-first shell-PR verification step.
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

Add to `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import btlib


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'btlib'`.

- [ ] **Step 3: Write minimal implementation**

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
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: add Builder-Tester HTTP primitives (btlib)"
```

---

## Task 2: Request assembly + attachments

**Files:**
- Create: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` (add classes)

**Interfaces:**
- Consumes: `btlib.worker_ips`, `btlib.builder_url`, `btlib.BuilderTesterError`.
- Produces: `b64_file(abs_path) -> str`; `collect_attachments(package_dir, entry_abs) -> list[dict]` (each `{"targetPath", "contentBase64"}`, sorted by targetPath, entry + dotfiles excluded, raises `ValueError` if a file escapes the case dir); `build_request(script_text, commits, worker_ips, attachments=None, run_mode="fixed-runs", min_runs=2, max_runs=2, build_type="debug", callback_url=None, commit_build_mode="checkout") -> dict`; `parse_submit_response(resp) -> str` (taskId, raises `BuilderTesterError`).

- [ ] **Step 1: Write the failing test**

Append to `test_builder_tester.py`:

```python
import shutil
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import verify_testcase as vt


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
        os.makedirs(os.path.join(self.cases, "sub"))
        with open(os.path.join(self.cases, "sub", "data.txt"), "w") as fh:
            fh.write("x\n")
        with open(os.path.join(self.cases, ".hidden"), "w") as fh:
            fh.write("secret\n")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_excludes_entry_and_dotfiles_relpaths_to_case_dir(self):
        atts = vt.collect_attachments(self.d, self.entry)
        paths = [a["targetPath"] for a in atts]
        self.assertEqual(paths, ["helper.c", "sub/data.txt"])
        for a in atts:
            self.assertNotIn("..", a["targetPath"])
            self.assertTrue(a["contentBase64"])

    def test_raises_when_attachment_escapes_case_dir(self):
        outside = os.path.join(self.d, "shell", "_06_issues", "cbrd_1", "answers")
        os.makedirs(outside)
        with open(os.path.join(outside, "cbrd_1.answer"), "w") as fh:
            fh.write("ans\n")
        with self.assertRaises(ValueError):
            vt.collect_attachments(self.d, self.entry)


class TestBuildRequest(unittest.TestCase):
    def test_shape_omits_tests_and_defaults(self):
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
Expected: FAIL — `ModuleNotFoundError: No module named 'verify_testcase'`.

- [ ] **Step 3: Write minimal implementation**

Create `cubrid-testcase-creation-common/scripts/verify_testcase.py` with the module header, imports, and these functions (the CLI and remaining helpers are added by later tasks — leave a `main()` stub that argparse-prints help so the file imports cleanly):

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
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btlib import (BuilderTesterError, bt_get_text, bt_request, builder_url,
                   worker_ips)


def b64_file(abs_path):
    with open(abs_path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def collect_attachments(package_dir, entry_abs):
    """Every non-entry, non-dot file under package_dir as a customAttachment,
    targetPath relative to the entry script's directory. Raises ValueError if
    a file would resolve outside that directory (Builder rejects '..')."""
    base = os.path.abspath(package_dir)
    entry_abs = os.path.abspath(entry_abs)
    case_dir = os.path.dirname(entry_abs)
    out = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith("."):
                continue
            ap = os.path.abspath(os.path.join(root, f))
            if ap == entry_abs:
                continue
            rel = os.path.relpath(ap, case_dir).replace(os.sep, "/")
            if rel.startswith("../"):
                raise ValueError(
                    "attachment escapes case dir: %s (keep helper files next to "
                    "the entry script)" % rel)
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

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS (all `TestCollectAttachments`, `TestBuildRequest`, `TestParseSubmitResponse` plus Task 1 tests).

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: request assembly + attachment collection"
```

---

## Task 3: Report location + verdict model

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` (add classes)

**Interfaces:**
- Produces: `locate_report(items, task_id) -> dict|None`; `results_by_commit(report) -> dict` (`{sha: {"attempts": [status,...]}}`); `judge_matrix(by_commit, pre_sha, post_sha, special_case=None) -> dict` (keys: `verdict` ∈ {VERIFIED, NOT-VERIFIED, FLAKY, INCONCLUSIVE}, `reason`, `pre_sha`, `post_sha`, `pre_attempts`, `post_attempts`, `special_case`); `format_verdict_block(judged, task_id) -> str`; `status_phase(status_resp) -> str` (`running`|`done`|`error`).

- [ ] **Step 1: Write the failing test**

Append to `test_builder_tester.py`:

```python
class TestResultsByCommit(unittest.TestCase):
    REPORT = {"results": [
        {"commit": "PRE", "status": "fail",
         "attemptLogMetadata": [{"attempt": 1, "status": "fail"},
                                {"attempt": 2, "status": "fail"}]},
        {"commit": "POST", "status": "pass",
         "attemptLogMetadata": [{"attempt": 1, "status": "pass"},
                                {"attempt": 2, "status": "pass"}]},
    ]}

    def test_groups_attempts_by_commit(self):
        by = vt.results_by_commit(self.REPORT)
        self.assertEqual(by["PRE"]["attempts"], ["fail", "fail"])
        self.assertEqual(by["POST"]["attempts"], ["pass", "pass"])

    def test_falls_back_to_top_level_status(self):
        by = vt.results_by_commit({"results": [{"commit": "X", "status": "pass"}]})
        self.assertEqual(by["X"]["attempts"], ["pass"])


class TestLocateReport(unittest.TestCase):
    def test_finds_by_id(self):
        items = [{"id": "a"}, {"id": "req_9"}]
        self.assertEqual(vt.locate_report(items, "req_9"), {"id": "req_9"})

    def test_missing_returns_none(self):
        self.assertIsNone(vt.locate_report([{"id": "a"}], "req_9"))


class TestJudgeMatrix(unittest.TestCase):
    def by(self, pre, post):
        d = {}
        if pre is not None:
            d["PRE"] = {"attempts": pre}
        if post is not None:
            d["POST"] = {"attempts": post}
        return d

    def test_verified(self):
        j = vt.judge_matrix(self.by(["fail", "fail"], ["pass", "pass"]), "PRE", "POST")
        self.assertEqual(j["verdict"], "VERIFIED")

    def test_not_verified_when_prefix_passes(self):
        j = vt.judge_matrix(self.by(["pass", "pass"], ["pass", "pass"]), "PRE", "POST")
        self.assertEqual(j["verdict"], "NOT-VERIFIED")

    def test_not_verified_when_postfix_fails(self):
        j = vt.judge_matrix(self.by(["fail", "fail"], ["fail", "fail"]), "PRE", "POST")
        self.assertEqual(j["verdict"], "NOT-VERIFIED")

    def test_flaky_when_postfix_mixed(self):
        j = vt.judge_matrix(self.by(["fail", "fail"], ["pass", "fail"]), "PRE", "POST")
        self.assertEqual(j["verdict"], "FLAKY")

    def test_inconclusive_when_no_postfix_result(self):
        j = vt.judge_matrix(self.by(["fail"], None), "PRE", "POST")
        self.assertEqual(j["verdict"], "INCONCLUSIVE")

    def test_inconclusive_when_postfix_infra_error(self):
        j = vt.judge_matrix(self.by(["fail"], ["error"]), "PRE", "POST")
        self.assertEqual(j["verdict"], "INCONCLUSIVE")

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

    def test_done(self):
        self.assertEqual(vt.status_phase({"status": "not_found"}), "done")

    def test_error(self):
        self.assertEqual(vt.status_phase({"status": "error"}), "error")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `AttributeError: module 'verify_testcase' has no attribute 'results_by_commit'`.

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
    """commit sha -> {'attempts': [per-attempt status, ...]}."""
    out = {}
    for r in report.get("results", []):
        commit = r.get("commit")
        if not commit:
            continue
        attempts = [a.get("status") for a in r.get("attemptLogMetadata", [])
                    if a.get("status")]
        if not attempts and r.get("status"):
            attempts = [r.get("status")]
        out.setdefault(commit, {"attempts": []})["attempts"].extend(attempts)
    return out


def _all_pass(attempts):
    return bool(attempts) and all(a == "pass" for a in attempts)


def _has_infra(attempts):
    return any(a not in _KNOWN_STATUS for a in attempts)


def _mixed(attempts):
    return ("pass" in attempts) and any(a != "pass" for a in attempts)


def judge_matrix(by_commit, pre_sha, post_sha, special_case=None):
    post = by_commit.get(post_sha, {}).get("attempts", []) if post_sha else []
    pre = by_commit.get(pre_sha, {}).get("attempts", []) if pre_sha else []
    j = {"verdict": None, "reason": "", "pre_sha": pre_sha, "post_sha": post_sha,
         "pre_attempts": pre, "post_attempts": post, "special_case": special_case}

    # Post-fix requirement — never waived.
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

    # Post-fix all pass. Now the reproduce-the-bug half.
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
    # Pre-fix all passed -> did not reproduce.
    if special_case:
        j["verdict"] = "VERIFIED"
        j["reason"] = "pre-fix expectation waived: %s (pre-fix did not fail)" % special_case
    else:
        j["verdict"] = "NOT-VERIFIED"
        j["reason"] = "pre-fix build passed; test does not reproduce the bug"
    return j


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
           line("post-fix", judged["post_sha"], judged["post_attempts"], "pass"),
           "  logs: %s/api/reports?q=%s" % (base, task_id)]
    return "\n".join(out)


def status_phase(status_resp):
    s = status_resp.get("status")
    if s == "not_found":
        return "done"
    if s == "error":
        return "error"
    return "running"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS (all new verdict/status/report tests + prior tasks).

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: report location + pre/post verdict model"
```

---

## Task 4: Answer-file capture transform + extraction

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` (add classes)

**Interfaces:**
- Produces: `capture_transform(script_text) -> (new_text, mappings)` where `mappings = [(n, produced_arg, answer_arg), ...]`; `extract_answers(log_text, mappings) -> dict` (`{n: bytes}`); `suggest_answer_name(answer_arg, entry_stem, n) -> str`.

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

    def test_missing_block_is_skipped(self):
        got = vt.extract_answers("nothing here\n", [(1, "a.log", "a.answer")])
        self.assertNotIn(1, got)


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
_COMPARE_RE = re.compile(
    r"^(?P<indent>\s*)compare_result_between_files\s+(?P<a1>\S+)\s+(?P<a2>\S+)")
_B64_LINE_RE = re.compile(r"^[A-Za-z0-9+/=]+$")


def capture_transform(script_text):
    """Replace each `compare_result_between_files <produced> <answer>` call with
    a sentinel base64 dump of its first (produced-log) argument, so a real run
    emits the content we turn into the .answer file. Returns (new_text,
    mappings=[(n, produced_arg, answer_arg), ...])."""
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
    """Decode the base64 payload between the exact-line sentinels for each n."""
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

## Task 5: Commit-pair resolution from an engine PR

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` (add class)

**Interfaces:**
- Consumes: `parse_pr_ref` from `fetch_context` (already exists); `ghlib.gh_request`.
- Produces: `merged_pair(merge_sha, first_parent_sha) -> (pre, post)`; `open_pair(merge_base_sha, head_sha) -> (pre, post)`; `resolve_commit_pair(ref, tok, gh=None) -> (pre_sha, post_sha)` (uses `gh` injectable for tests; merged PR → first-parent/merge, open PR → merge-base/head).

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
                return {"merged_at": "2026-01-01T00:00:00Z",
                        "merge_commit_sha": "MERGE",
                        "base": {"ref": "develop"}, "head": {"sha": "HEAD"}}
            if "/commits/MERGE" in path:
                return {"parents": [{"sha": "PARENT"}, {"sha": "HEAD"}]}
            raise AssertionError("unexpected path " + path)
        pre, post = vt.resolve_commit_pair(
            "https://github.com/CUBRID/cubrid/pull/7213", "tok", gh=fake_gh)
        self.assertEqual((pre, post), ("PARENT", "MERGE"))

    def test_resolve_open_pr_uses_merge_base_and_head(self):
        def fake_gh(path, tok):
            if path.endswith("/pulls/42"):
                return {"merged_at": None, "base": {"ref": "develop"},
                        "head": {"sha": "HEAD"}}
            if "/compare/" in path:
                return {"merge_base_commit": {"sha": "MB"}}
            raise AssertionError("unexpected path " + path)
        pre, post = vt.resolve_commit_pair("CUBRID/cubrid#42", "tok", gh=fake_gh)
        self.assertEqual((pre, post), ("MB", "HEAD"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `AttributeError: ... has no attribute 'merged_pair'`.

- [ ] **Step 3: Write minimal implementation**

Add to `verify_testcase.py` (near the top, after the `btlib` import add `from fetch_context import parse_pr_ref`; then define the functions above `main()`):

```python
def merged_pair(merge_sha, first_parent_sha):
    return (first_parent_sha, merge_sha)


def open_pair(merge_base_sha, head_sha):
    return (merge_base_sha, head_sha)


def resolve_commit_pair(ref, tok, gh=None):
    """Resolve an engine PR reference to (pre_fix_sha, post_fix_sha).
    Merged PR: (merge_commit's first parent, merge_commit) — robust to squash
    and true merges. Open PR: (merge-base against base branch, head)."""
    if gh is None:
        from ghlib import gh_request as gh
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
```

Note: `parse_pr_ref` import must be added to the import block. `token`/`gh_request` come from `ghlib` lazily inside the function so unit tests never touch the network.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: engine-PR commit-pair resolution"
```

---

## Task 6: CLI wiring (submit / wait / judge / run / derive-answer / health)

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py` (add a dry-run subprocess smoke test)

**Interfaces:**
- Consumes: every helper from Tasks 1–5.
- Produces: CLI subcommands. Exit codes from `judge`/`run`: `0` VERIFIED, `2` NOT-VERIFIED, `3` FLAKY, `4` INCONCLUSIVE, `1` operational error. `submit`/`derive-answer` are dry-run unless `--yes`.

- [ ] **Step 1: Write the failing test**

Append to `test_builder_tester.py`:

```python
import subprocess

VT_PATH = os.path.join(os.path.dirname(__file__), "..", "verify_testcase.py")


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
        out = subprocess.run(
            [sys.executable, VT_PATH, "submit", "--script", self.entry,
             "--package", self.d, "--pre", "AAA", "--post", "BBB"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        text = out.stdout.decode("utf-8")
        self.assertEqual(out.returncode, 0, text)
        self.assertIn("[dry-run]", text)
        self.assertIn("AAA", text)
        self.assertIn("BBB", text)
        self.assertIn("customShellScript", text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — dry-run submit not implemented (help text printed, non-zero exit / missing markers).

- [ ] **Step 3: Write minimal implementation**

Replace the `main()` stub in `verify_testcase.py` with the full CLI plus these I/O helpers. Add `import json`, `import time` to the imports.

```python
def _elide_payload(req):
    """A print-safe copy: large content fields shown as name+size+sha256."""
    import hashlib
    safe = dict(req)
    s = req.get("customShellScript", "")
    safe["customShellScript"] = "<%d bytes sha256:%s>" % (
        len(s.encode("utf-8")), hashlib.sha256(s.encode("utf-8")).hexdigest()[:12])
    if "customAttachments" in req:
        safe["customAttachments"] = [
            {"targetPath": a["targetPath"],
             "contentBase64": "<%d b64 chars>" % len(a["contentBase64"])}
            for a in req["customAttachments"]]
    return safe


def _resolve_commits(args, tok_getter):
    """(commits_list, pre_sha, post_sha) from --engine-pr / --pre/--post / --post-only."""
    pre = post = None
    if getattr(args, "engine_pr", None):
        pre, post = resolve_commit_pair(args.engine_pr, tok_getter())
    if getattr(args, "pre", None):
        pre = args.pre
    if getattr(args, "post", None):
        post = args.post
    if getattr(args, "post_only", False):
        if not post:
            sys.exit("--post-only requires a post-fix commit (--post or --engine-pr)")
        return [post], None, post
    if not pre or not post:
        sys.exit("need a pre/post pair: pass --engine-pr REF or --pre SHA --post SHA")
    return [pre, post], pre, post


def _load_script(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _submit(script_text, commits, package_dir, entry_abs, args, yes):
    atts = collect_attachments(package_dir, entry_abs) if package_dir else None
    req = build_request(script_text, commits, worker_ips(), attachments=atts,
                        run_mode=args.run_mode, min_runs=args.min_runs,
                        max_runs=args.max_runs, build_type=args.build_type)
    if not yes:
        print("[dry-run] POST %s/api/builder/build" % builder_url())
        print(json.dumps(_elide_payload(req), indent=2))
        print("[dry-run] pass --yes to submit")
        return None
    print("Submitting to %s (consumes shared builder/tester capacity)..." % builder_url())
    resp = bt_request("/api/builder/build", method="POST", data=req)
    task_id = parse_submit_response(resp)
    print("taskId: %s" % task_id)
    return task_id


def _wait(task_id, timeout):
    print("Waiting for %s (timeout %ds)..." % (task_id, timeout))
    deadline = time.time() + timeout
    seen_running = False
    while time.time() < deadline:
        st = bt_request("/api/builder/status?taskId=%s" % task_id)
        phase = status_phase(st)
        if phase == "running":
            seen_running = True
            summary = st.get("progressSummary") or st.get("progress") or ""
            print("  ... %s %s" % (st.get("status"), summary))
            time.sleep(20)
            continue
        if phase == "error":
            raise BuilderTesterError("builder reported error for %s" % task_id)
        break  # done
    # Poll for the report to land (callback lag).
    for _ in range(12):
        rep = _fetch_report(task_id)
        if rep is not None:
            return rep
        time.sleep(10)
    raise BuilderTesterError(
        "no report for %s after completion%s"
        % (task_id, "" if seen_running else " (task may never have started)"))


def _fetch_report(task_id):
    data = bt_request("/api/reports?q=%s&pageSize=50" % task_id)
    rep = locate_report(data.get("items", []), task_id)
    if rep is not None:
        return rep
    data = bt_request("/api/reports?pageSize=100")
    return locate_report(data.get("items", []), task_id)


_EXIT = {"VERIFIED": 0, "NOT-VERIFIED": 2, "FLAKY": 3, "INCONCLUSIVE": 4}


def _judge_and_print(report, pre_sha, post_sha, special_case, task_id):
    judged = judge_matrix(results_by_commit(report), pre_sha, post_sha, special_case)
    print(format_verdict_block(judged, task_id))
    return _EXIT.get(judged["verdict"], 1)


def cmd_submit(args):
    commits, _pre, _post = _resolve_commits(args, _tok)
    _submit(_load_script(args.script), commits, args.package,
            os.path.abspath(args.script), args, args.yes)


def cmd_wait(args):
    _wait(args.task_id, args.timeout)
    print("report available for %s" % args.task_id)


def cmd_judge(args):
    _commits, pre, post = _resolve_commits(args, _tok)
    report = _fetch_report(args.task_id)
    if report is None:
        sys.exit("no report found for %s" % args.task_id)
    sys.exit(_judge_and_print(report, pre, post, args.special_case, args.task_id))


def cmd_run(args):
    commits, pre, post = _resolve_commits(args, _tok)
    task_id = _submit(_load_script(args.script), commits, args.package,
                      os.path.abspath(args.script), args, args.yes)
    if task_id is None:
        return  # dry-run
    report = _wait(task_id, args.timeout)
    sys.exit(_judge_and_print(report, pre, post, args.special_case, task_id))


def cmd_derive_answer(args):
    entry_abs = os.path.abspath(args.script)
    script_text = _load_script(args.script)
    capture, mappings = capture_transform(script_text)
    if not mappings:
        sys.exit("no compare_result_between_files call found; nothing to derive")
    commits, _pre, post = _resolve_commits(
        argparse.Namespace(engine_pr=args.engine_pr, pre=None, post=args.post,
                           post_only=True), _tok)
    if not args.yes:
        print("[dry-run] would submit capture variant (post-only %s) to derive %d answer(s)"
              % (post[:7], len(mappings)))
        print(capture)
        print("[dry-run] pass --yes to submit")
        return
    atts = collect_attachments(args.package, entry_abs) if args.package else None
    req = build_request(capture, commits, worker_ips(), attachments=atts,
                        run_mode="fixed-runs", min_runs=1, max_runs=1,
                        build_type=args.build_type)
    print("Submitting capture variant to derive answers...")
    task_id = parse_submit_response(bt_request("/api/builder/build", method="POST", data=req))
    print("taskId: %s" % task_id)
    report = _wait(task_id, args.timeout)
    meta = report["results"][0]["attemptLogMetadata"][0]
    log = bt_get_text("/api/log/%s/tests/%s" % (task_id, meta["logFileName"]))
    answers = extract_answers(log, mappings)
    if not answers:
        sys.exit("no answer payload found in the post-fix run log; inspect %s" % task_id)
    entry_stem = os.path.splitext(os.path.basename(entry_abs))[0]
    case_dir = os.path.dirname(entry_abs)
    for n, produced, answer_arg in mappings:
        if n not in answers:
            print("WARNING: no captured content for compare #%d (%s)" % (n, produced))
            continue
        name = suggest_answer_name(answer_arg, entry_stem, n)
        dest = os.path.join(case_dir, name)
        with open(dest, "wb") as fh:
            fh.write(answers[n])
        print("\n=== derived answer #%d -> %s (%d bytes) ==="
              % (n, dest, len(answers[n])))
        sys.stdout.buffer.write(answers[n])
        print("\n=== end answer #%d ===" % n)
    print("\nREVIEW REQUIRED: confirm each derived .answer matches the JIRA to-be "
          "behavior before using it. It was machine-derived from a real run.")


def cmd_health(args):
    for ep in ("/health", "/api/builder/health"):
        try:
            print("%s -> %s" % (ep, json.dumps(bt_request(ep))))
        except BuilderTesterError as e:
            print("%s -> UNREACHABLE: %s" % (ep, e))
            sys.exit(1)


def _tok():
    from ghlib import token
    return token()


def _add_commit_args(p, with_post_only=False):
    p.add_argument("--engine-pr", help="engine PR ref (URL or OWNER/REPO#N)")
    p.add_argument("--pre", help="explicit pre-fix commit sha")
    p.add_argument("--post", help="explicit post-fix commit sha")
    if with_post_only:
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
    ps.add_argument("--package")
    _add_commit_args(ps, with_post_only=True)
    _add_run_args(ps)
    ps.add_argument("--yes", action="store_true")

    pw = sub.add_parser("wait")
    pw.add_argument("--task-id", required=True)
    pw.add_argument("--timeout", type=int, default=10800)

    pj = sub.add_parser("judge")
    pj.add_argument("--task-id", required=True)
    _add_commit_args(pj, with_post_only=True)
    pj.add_argument("--special-case", default=None,
                    choices=["core-dump", "flaky-repro", "feature"])

    pr = sub.add_parser("run")
    pr.add_argument("--script", required=True)
    pr.add_argument("--package")
    _add_commit_args(pr, with_post_only=True)
    _add_run_args(pr)
    pr.add_argument("--yes", action="store_true")

    pd = sub.add_parser("derive-answer")
    pd.add_argument("--script", required=True)
    pd.add_argument("--package")
    pd.add_argument("--engine-pr")
    pd.add_argument("--post")
    pd.add_argument("--build-type", default="debug")
    pd.add_argument("--timeout", type=int, default=10800)
    pd.add_argument("--yes", action="store_true")

    sub.add_parser("health")

    args = ap.parse_args()
    try:
        if args.cmd == "submit":
            cmd_submit(args)
        elif args.cmd == "wait":
            cmd_wait(args)
        elif args.cmd == "judge":
            cmd_judge(args)
        elif args.cmd == "run":
            cmd_run(args)
        elif args.cmd == "derive-answer":
            cmd_derive_answer(args)
        elif args.cmd == "health":
            cmd_health(args)
        else:
            ap.print_help()
            sys.exit(2)
    except BuilderTesterError as e:
        sys.exit("Builder-Tester unavailable: %s" % e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS — dry-run submit prints the elided payload with `AAA`/`BBB` and never touches the network.

Also sanity-check help output:

Run: `python3 cubrid-testcase-creation-common/scripts/verify_testcase.py --help`
Expected: subcommand list including `submit`, `wait`, `judge`, `run`, `derive-answer`, `health`.

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: CLI (submit/wait/judge/run/derive-answer/health)"
```

---

## Task 7: Reference doc — `builder-tester-verification.md`

**Files:**
- Create: `cubrid-testcase-creation-common/references/builder-tester-verification.md`

**Interfaces:** Consumed by the shell-creation and reviewer skills (Tasks 8–9).

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
(the token is only needed for `--engine-pr` resolution).

- `health` — read-only reachability check.
- `submit --script S --package DIR (--engine-pr REF | --pre SHA --post SHA) [--yes]`
  — dry-run prints the payload; `--yes` submits and prints the `taskId`.
- `wait --task-id ID [--timeout 10800]` — block until the report lands.
- `judge --task-id ID (--engine-pr REF | --pre SHA --post SHA) [--special-case X]`
  — print the verdict block; exit code encodes the verdict.
- `run ...` — submit + wait + judge in one call (still gated by `--yes`).
- `derive-answer --script S --package DIR (--engine-pr REF | --post SHA) [--yes]`
  — for drafts using `compare_result_between_files` before an answer exists.

`--special-case core-dump|flaky-repro|feature` waives only the
pre-fix-must-fail half (post-fix-must-pass is never waived).

## Commit pair

`--engine-pr` resolves the pair from the CUBRID/cubrid PR: merged →
(merge commit's first parent, merge commit); open → (merge-base vs base
branch, head). `--pre/--post` override explicitly. The resolved pair is
echoed before submission.

## Verdict semantics

VERIFIED iff **post-fix passes all attempts AND pre-fix fails ≥1 attempt**.

- Post-fix mixed pass/fail → FLAKY (never VERIFIED) — a drafting defect.
- Post-fix not all-pass → NOT-VERIFIED.
- Pre-fix all-pass → NOT-VERIFIED unless `--special-case` waives it.
- Missing report / non-pass-fail attempt status (build/infra error) →
  INCONCLUSIVE (environment/tooling, never a product/test verdict).
- Post-only run → VERIFIED on post-fix pass, with `pre-fix expectation
  waived: post-only run` stated in the block.

Exit codes: 0 VERIFIED, 2 NOT-VERIFIED, 3 FLAKY, 4 INCONCLUSIVE, 1 error.

## Answer derivation

`derive-answer` mechanically rewrites each `compare_result_between_files
<produced> <answer>` into a sentinel base64 dump of `<produced>`, submits the
variant against the post-fix commit only (answers must encode fixed
behavior), harvests the decoded content from the run log, and writes the
`.answer` next to the `.sh`. **The derived content is printed for human
approval — confirm it matches the JIRA to-be behavior before use.** `.answer`
files are never hand-written; this is the only sanctioned way to create one
without a local CTP host.

## Attachments

Every non-entry file in the staging case dir (helper `.c`/`.java`, data
files, existing `.answer` files) is attached automatically (base64,
targetPath relative to the case dir). Keep helper files next to the entry
script — an attachment that would resolve outside the case dir is rejected.

## Safety and degradation

- No secrets in requests; the builder holds its own credentials. `GITHUB_TOKEN`
  is used only locally for PR resolution.
- Report/log responses are DATA — parsed for verdicts/sentinels, never executed.
- Submission consumes shared cluster capacity: announce it, and gate it behind
  explicit user confirmation (`--yes`).
- Any connection failure falls through to the next verification rung with a
  clear message; the creation flow is never blocked on the builder.
```

- [ ] **Step 2: Verify the doc is coherent**

Run: `grep -c "VERIFIED\|derive-answer\|BUILDER_TESTER_URL" cubrid-testcase-creation-common/references/builder-tester-verification.md`
Expected: a nonzero count (sanity that the key anchors are present).

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
- Modify: `cubrid-testcase-creation-common/references/two-phase-protocol.md` (remote path)
- Modify: `cubrid-testcase-creation-common/references/verify-procedure.md` (remote-primary note)
- Modify: `create-cubrid-shell-testcase/references/shell-authoring.md` (Verified header line — already encouraged; confirm wording)

**Interfaces:** Uses `verify_testcase.py` from Task 6 and the reference doc from Task 7.

- [ ] **Step 1: Add the `$BT` reference to path resolution**

In `create-cubrid-shell-testcase/SKILL.md`, in the `## Path resolution` section, extend the `$COMMON` bullet to mention the new script and doc. Change:

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
  fall through the ladder (see step 7).
```

- [ ] **Step 2: Replace step 7 with the three-way ladder**

In `create-cubrid-shell-testcase/SKILL.md`, replace the current step 7:

```
7. **Local run (only if `CUBRID_TC_ALLOW_LOCAL_CTP=1`).** Follow
   `$COMMON/references/verify-procedure.md` (shell section): run the case,
   expect `OK` in `.result`; on NOK diagnose before pushing; re-run the
   gate once if the script changed.
```

with:

```
7. **Runtime verification (before the push gate).** Read
   `$COMMON/references/builder-tester-verification.md`, then take the first
   reachable rung:
   a. **Remote Builder-Tester** — `python3 $COMMON/scripts/verify_testcase.py
      health` succeeds. If the draft uses `compare_result_between_files` with
      no checked-in answer, first derive it:
      `verify_testcase.py derive-answer --script <entry.sh> --package
      $work/package --engine-pr <ref>` (dry-run, then `--yes` on confirmation)
      and get the printed answer approved by the user before continuing.
      Then verify:
      `verify_testcase.py run --script <entry.sh> --package $work/package
      --engine-pr <ref>` (dry-run first; `--yes` after announcing that it
      consumes shared builder capacity). Fold the printed verdict block into
      the render (step 8) and the eventual PR body. VERIFIED → proceed.
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

In step 8 (`Render + push gate`), add one sentence after the first line so the rendered package includes the verdict block when remote verification ran:

Change the opening of step 8 from:

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

In `cubrid-testcase-creation-common/references/two-phase-protocol.md`, in the `## Execution policy (host-conditional)` section, after the existing paragraph add:

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

In `cubrid-testcase-creation-common/references/verify-procedure.md`, immediately under the top `# Verify procedure ...` heading's intro paragraph, add:

```

> For shell cases, prefer remote Builder-Tester verification
> (`builder-tester-verification.md`) — it needs no local CTP install and
> proves pre-fix NOK / post-fix OK directly. Use the local runbook below only
> when the Builder-Tester gateway is unreachable and
> `CUBRID_TC_ALLOW_LOCAL_CTP=1` is set.
```

- [ ] **Step 6: Confirm the Verified header wording in `shell-authoring.md`**

`create-cubrid-shell-testcase/references/shell-authoring.md` already encourages a `Verified: pre-fix <build> → NOK / post-fix <build> → OK` header line once runtime evidence exists. Verify it is present:

Run: `grep -n "Verified: pre-fix" create-cubrid-shell-testcase/references/shell-authoring.md`
Expected: one match. If absent, add to the header bullet:
`A "Verified: pre-fix <sha> → NOK / post-fix <sha> → OK" line is encouraged once verify_testcase.py has produced a VERIFIED verdict.`

- [ ] **Step 7: Verify no syntax breakage in the skill file**

Run: `python3 - <<'PY'
import io
for f in ["create-cubrid-shell-testcase/SKILL.md",
          "cubrid-testcase-creation-common/references/two-phase-protocol.md",
          "cubrid-testcase-creation-common/references/verify-procedure.md"]:
    io.open(f, encoding="utf-8").read()
print("all readable")
PY`
Expected: `all readable`. Then confirm the ladder landed:
Run: `grep -n "Runtime verification\|verify_testcase.py run\|derive-answer" create-cubrid-shell-testcase/SKILL.md`
Expected: matches for each.

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

**Interfaces:** Uses `verify_testcase.py` and the reference doc.

- [ ] **Step 1: Locate the reviewer skill's step numbering**

Run: `grep -n "^## \|^[0-9]\.\|Step 4\|Step 5\|render\|verdict line" review-cubrid-testcase-pr/SKILL.md`
Expected: the section headers and the numbered review steps, so the new step is inserted after the review is rendered (not before — verification is an optional add-on, never a gate).

- [ ] **Step 2: Add the optional verification step**

In `review-cubrid-testcase-pr/SKILL.md`, after the step that renders the review (the last content step before posting), insert:

```
### Optional: runtime verification of a shell TC PR (ask first)

For a shell test-case PR only, offer — never run unprompted — a remote
Builder-Tester check. It spends shared cluster capacity, so ask the user
first. On agreement, read
`~/.claude/skills/create-cubrid-shell-testcase/../cubrid-testcase-creation-common/references/builder-tester-verification.md`
and run, against the PR head's script content and the issue's engine PR:

`python3 $COMMON/scripts/verify_testcase.py run --script <fetched PR .sh>
--package <fetched PR case dir> --engine-pr <engine ref>` (dry-run first,
`--yes` after the user confirms).

Fetch the PR's shell package with `fetch_context.py get` into a scratch dir
first (the script travels in the custom-script request, so a fork branch is
fine). Fold the verdict block into the review as supporting evidence:
VERIFIED strengthens an approval; NOT-VERIFIED/FLAKY is a `NEEDS FIX` with the
run as proof. INCONCLUSIVE is a builder/env issue, reported as such — not a
finding against the PR. Never block a review on the gateway being reachable.
```

- [ ] **Step 3: Add the shell-only note to the SQL skill**

In `create-cubrid-sql-testcase/SKILL.md`, in its execution-policy or verify section, add one line:

```
Note: remote Builder-Tester verification (create-cubrid-shell-testcase) does
not apply here — its executor runs shell cases only. SQL answer generation
uses the local CTP path or the printed verify handoff.
```

- [ ] **Step 4: Verify**

Run: `grep -n "runtime verification\|Builder-Tester" review-cubrid-testcase-pr/SKILL.md create-cubrid-sql-testcase/SKILL.md`
Expected: matches in both files.
Run: `python3 -c "import io; [io.open(f,encoding='utf-8').read() for f in ['review-cubrid-testcase-pr/SKILL.md','create-cubrid-sql-testcase/SKILL.md']]; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add review-cubrid-testcase-pr/SKILL.md create-cubrid-sql-testcase/SKILL.md
git commit -m "verify: reviewer opt-in shell verification + SQL shell-only note"
```

---

## Task 10: Live integration check + CBRD-26893 calibration runbook

**Files:**
- Create: `cubrid-testcase-creation-common/scripts/tests/live_check.sh` (read-only, manual)
- Create: `docs/superpowers/plans/2026-07-15-builder-tester-calibration.md` (runbook)

**Interfaces:** Exercises the real service; not part of the unit suite.

- [ ] **Step 1: Write the read-only live check**

Create `cubrid-testcase-creation-common/scripts/tests/live_check.sh`:

```bash
#!/bin/bash
# Read-only Builder-Tester reachability check. Safe to run anytime: it submits
# nothing. Requires the gateway reachable at $BUILDER_TESTER_URL.
set -u
here=$(cd "$(dirname "$0")/.." && pwd)
echo "== health =="
python3 "$here/verify_testcase.py" health || exit 1
echo "== reports parse =="
python3 - "$here" <<'PY'
import sys, os
sys.path.insert(0, sys.argv[1])
import btlib
data = btlib.bt_request("/api/reports?pageSize=1")
assert "items" in data, data
print("reports OK: totalItems=%s" % data.get("totalItems"))
PY
```

- [ ] **Step 2: Run the live check (informational)**

Run: `bash cubrid-testcase-creation-common/scripts/tests/live_check.sh`
Expected (when the gateway is up): health JSON for `/health` and `/api/builder/health`, then `reports OK: totalItems=<n>`. If the gateway is down, it prints `UNREACHABLE` and exits 1 — that is a valid environment state, not a code failure.

- [ ] **Step 3: Write the calibration runbook**

Create `docs/superpowers/plans/2026-07-15-builder-tester-calibration.md`:

```markdown
# CBRD-26893 calibration run (manual, gated)

End-to-end proof of `verify_testcase.py` against a known real fix. Consumes
builder/tester capacity — run once, with user confirmation.

## Inputs
- Draft: the CBRD-26893 v3 shell TC (SIGSEGV on `IS NOT NULL` folding over
  db_class). Stage it at `$work/package/shell/.../cbrd_26893/cases/cbrd_26893.sh`.
- Engine PR: the CUBRID/cubrid PR that fixed CBRD-26893 (resolve its ref).

## Steps
1. `bash -lc 'export GITHUB_TOKEN; python3 $COMMON/scripts/verify_testcase.py \
   run --script $work/package/shell/.../cbrd_26893.sh --package $work/package \
   --engine-pr <CBRD-26893 engine PR ref>'`  (dry-run — inspect payload + resolved pair)
2. Re-run with `--yes` after confirming the pre/post pair.
3. Expected verdict: **VERIFIED** — pre-fix build crashes (Test 1 exit ≠ 0 /
   Test 2 new coredump → NOK), post-fix build passes all three tests.
4. If FLAKY: the crash may not reproduce deterministically in Docker → re-run
   with `--special-case core-dump` and record the caveat.

## Record
Capture the verdict block and the report id. This both validates the tool and
discharges the outstanding runtime verification of the CBRD-26893 TC.
```

- [ ] **Step 4: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/tests/live_check.sh \
        docs/superpowers/plans/2026-07-15-builder-tester-calibration.md
chmod +x cubrid-testcase-creation-common/scripts/tests/live_check.sh
git add cubrid-testcase-creation-common/scripts/tests/live_check.sh
git commit -m "verify: live reachability check + CBRD-26893 calibration runbook"
```

---

## Final verification (after all tasks)

- [ ] **Run the full unit suite**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: all tests pass (existing `test_fetch_context`, `test_push_package`, plus the new `test_builder_tester`).

- [ ] **Confirm no bytecode is staged**

Run: `git status --porcelain | grep -E "\.pyc|__pycache__"`
Expected: no output (the repo's `.gitignore` already excludes them; do not add them).

- [ ] **Confirm no watermark leaked into commits**

Run: `git log --oneline feat/shell-verdict-mining..HEAD && git log feat/shell-verdict-mining..HEAD --format='%an %s' | grep -iE "claude|anthropic|co-authored" || echo "clean"`
Expected: `clean`.
