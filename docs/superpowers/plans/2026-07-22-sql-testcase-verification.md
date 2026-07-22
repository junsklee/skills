# SQL Test-Case Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `verify_testcase.py` with a SQL mode that verifies drafted SQL test cases against the Builder-Tester (custom-SQL API: pre-fix fails, post-fix passes) and derives `.answer` files from a real post-fix run, and wire it into `create-cubrid-sql-testcase` — bringing the SQL creator to the shell creator's production grade.

**Architecture:** One tool serves both test types. The hardened lifecycle (`_wait`/`_pending`/`status_phase`/`judge_matrix`/commit-pair resolution) is reused unchanged; only request assembly, artifact location/fetch, and answer write-back are new. The SQL skill gains the same three-rung verification ladder the shell skill has. Authoring doctrine gets a light alignment pass from `sql_guide.md` + a 15-case spot-check.

**Tech Stack:** Python 3.6 stdlib only (no third-party); Builder-Tester report-server over plain HTTP; `unittest`.

## Global Constraints

- **Python 3.6, stdlib only.** Match the existing `verify_testcase.py`/`btlib.py` style — `%`-formatting, no f-strings, no 3.7+ stdlib.
- **Dry-run by default; `--yes` performs the only network write (build submission).** A derived `.answer` write is local, but the submission that produces it is gated.
- **This host never executes tests/CTP/csql/cubrid.** The tool only talks HTTP to the remote Builder-Tester.
- **No Claude/Anthropic watermark** anywhere. No `Co-Authored-By`, no 🤖.
- **`.answer` files are never hand-written** — machine-derived from a real run, shown to the user for approval before use.
- **Config (unchanged):** `BUILDER_TESTER_URL` default `http://192.168.2.154:8091`; `BUILDER_TESTER_WORKER_IPS` default `192.168.2.154:8090`.
- **PR titles English; PR bodies + JIRA Korean.**
- **Work on branch `feat/sql-testcase-verify`** (already created off `main` in `~/worktrees/skills-main`). Do not open a PR unless asked.
- **Test command** (from `~/worktrees/skills-main`): `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`

## Server contract (SQL custom mode)

The **custom-SQL request surface** below (`customSqlScript`/`customSqlAnswer`, `custom_sql_case` artifacts, fresh-per-case container) was **discovered and confirmed by live probing** of the deployed server on 2026-07-22 — request fields, `testType`, the `custom_script_test` placeholder, artifact `artifactType` values, and the derive side-effect were all reproduced against real reports. It is **NOT documented in the upstream `SQL_TESTER.md`** (which covers only the repo-path `tests[]` form). Treat it as a live-verified but unofficial surface: **if behavior seems to drift, re-probe the live server** rather than trusting a doc.

- `POST /api/builder/build` custom-SQL body: `{commits, testType:"sql", customSqlScript, customSqlAnswer, workerIps, runMode/minRuns/maxRuns, buildType, commitBuildMode, callbackUrl}`. **No `tests[]`** (a `custom_script_test` placeholder is inserted server-side). `customSqlAnswer` REQUIRED non-empty (HTTP 400 otherwise). `customShellScript`/`customScriptTestPath`/`customAttachments` rejected in SQL mode.
- Runs in a **fresh per-case container**, once per commit; top-level `test` is `custom_script_test`, artifacts use `testName = custom_sql_case`.
- Statuses observed/handled: `pass`, `fail`, and infra/other. `fail` = answer mismatch; a missing/empty answer, per-case timeout, or no verdict → `execution_error`; provisioning/Docker → `environment_error`; build-phase failures surface as `build_failed`. **Any status other than `pass`/`fail`** is treated as infra → INCONCLUSIVE by the existing `judge_matrix` (`_KNOWN_STATUS = ("pass","fail")`), so the exact non-pass/fail spelling doesn't matter to correctness. `run_sql.sh` exit code is always 0 — verdict is parsed.
- `attemptLogMetadata[]`: plain attempt logs `{attempt, logFileName, status}`; artifact entries `{attempt, logFileName, artifactType, executionEnv?}` (**no `status`**). Artifact types: `answer_diff`, `actual_result`, `expected_answer`, `case_source`, `warm_console`, `core_list`.
- Custom-mode artifact filenames, e.g. `sql_actual_<c7>_custom_sql_case.result`. Fetch any via `GET /api/log/<requestId>/tests/<filename>` (text/plain).
- **Answer-derivation is a side-channel, not an official feature.** `SQL_TESTER.md` lists answer-file generation as out of scope. The mechanism used here — submit a *deliberately-wrong placeholder* answer, let the case `fail`, and harvest the incidental `actual_result` artifact (the real output) — was reproduced live and is byte-identical to what a passing re-submit uses as `expected_answer`, but it rides a failure side effect the maintainers have not committed to. Documented as a known fragility (re-probe if it breaks).
- `/api/reports` items carry `testType`.
- **`buildType`:** every live SQL report observed used `release`; this plan defaults SQL to **`debug`** (a deliberate choice, matching the shell default and the CTP debug-build convention). `--build-type` overrides. The Task 9 calibration run is the first real `debug`-SQL submission and confirms it end-to-end before reliance.

---

## Task 1: SQL request assembly + artifact/answer helpers (pure)

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py`

**Interfaces:**
- Produces: `build_sql_request(script_text, answer_text, commits, worker_ip_list, run_mode="fixed-runs", min_runs=1, max_runs=1, build_type="debug", callback_url=None, commit_build_mode="checkout") -> dict` (raises `ValueError` on empty answer); `resolve_answer_path(script_path) -> str`; `has_queryplan_sidecar(script_path) -> bool`; `find_artifacts(report, commit_sha, artifact_type) -> [str]`; `report_test_type(report) -> str`. Modifies `elide_payload` (elide only present content keys; add SQL keys) and `results_by_commit` (exclude artifact entries from `logs`).

- [ ] **Step 1: Write the failing tests** — append to `test_builder_tester.py` (before the `if __name__` guard):

```python
class TestBuildSqlRequest(unittest.TestCase):
    def test_shape_and_defaults(self):
        req = vt.build_sql_request("select 1;\n", "===\n1\n", ["aaa", "bbb"],
                                   ["h:8090"], callback_url="http://cb/callback")
        self.assertEqual(req["testType"], "sql")
        self.assertEqual(req["customSqlScript"], "select 1;\n")
        self.assertEqual(req["customSqlAnswer"], "===\n1\n")
        self.assertEqual(req["commits"], ["aaa", "bbb"])
        self.assertEqual(req["minRuns"], 1)
        self.assertEqual(req["maxRuns"], 1)
        self.assertEqual(req["buildType"], "debug")
        self.assertEqual(req["commitBuildMode"], "checkout")
        self.assertNotIn("tests", req)
        self.assertNotIn("customShellScript", req)
        self.assertNotIn("customAttachments", req)

    def test_empty_answer_raises(self):
        with self.assertRaises(ValueError):
            vt.build_sql_request("select 1;\n", "", ["aaa"], ["h:8090"])


class TestResolveAnswerPath(unittest.TestCase):
    def test_cases_sibling_answers(self):
        p = vt.resolve_answer_path("/x/sql/_13_issues/_26_2h/cases/cbrd_1.sql")
        self.assertEqual(p, "/x/sql/_13_issues/_26_2h/answers/cbrd_1.answer")

    def test_non_cases_alongside(self):
        p = vt.resolve_answer_path("/tmp/scratch/cbrd_1.sql")
        self.assertEqual(p, "/tmp/scratch/cbrd_1.answer")


class TestQueryPlanSidecar(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.sql = os.path.join(self.d, "cbrd_1.sql")
        open(self.sql, "w").close()

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_absent(self):
        self.assertFalse(vt.has_queryplan_sidecar(self.sql))

    def test_present(self):
        open(os.path.join(self.d, "cbrd_1.queryPlan"), "w").close()
        self.assertTrue(vt.has_queryplan_sidecar(self.sql))


class TestFindArtifacts(unittest.TestCase):
    REPORT = {"results": [{"commit": "aa136ea1111", "attemptLogMetadata": [
        {"attempt": 1, "logFileName": "sql_aa136ea_x.log", "status": "fail"},
        {"attempt": 1, "logFileName": "sql_actual_aa136ea_x.result", "artifactType": "actual_result"},
        {"attempt": 1, "logFileName": "sql_diff_aa136ea_x.diff", "artifactType": "answer_diff"},
    ]}]}

    def test_selects_by_type_and_commit(self):
        self.assertEqual(vt.find_artifacts(self.REPORT, "aa136ea", "actual_result"),
                         ["sql_actual_aa136ea_x.result"])
        self.assertEqual(vt.find_artifacts(self.REPORT, "aa136ea1111", "answer_diff"),
                         ["sql_diff_aa136ea_x.diff"])

    def test_missing_type(self):
        self.assertEqual(vt.find_artifacts(self.REPORT, "aa136ea", "core_list"), [])

    def test_empty_commit_matches_nothing(self):
        self.assertEqual(vt.find_artifacts(self.REPORT, "", "actual_result"), [])


class TestReportTestType(unittest.TestCase):
    def test_top_level(self):
        self.assertEqual(vt.report_test_type({"testType": "sql", "results": []}), "sql")

    def test_from_results(self):
        self.assertEqual(vt.report_test_type({"results": [{"testType": "sql"}]}), "sql")

    def test_default_shell(self):
        self.assertEqual(vt.report_test_type({"results": [{}]}), "shell")


class TestElideSqlAndLogsFilter(unittest.TestCase):
    def test_elides_sql_fields_only_when_present(self):
        req = vt.build_sql_request("select 1;\n", "===\n1\n", ["a"], ["h:1"],
                                   callback_url="http://c/callback")
        e = vt.elide_payload(req)
        self.assertIn("sha256:", e["customSqlScript"])
        self.assertIn("sha256:", e["customSqlAnswer"])
        self.assertNotIn("customShellScript", e)   # not spuriously added
        self.assertEqual(e["commits"], ["a"])

    def test_results_by_commit_excludes_artifacts_from_logs(self):
        by = vt.results_by_commit(TestFindArtifacts.REPORT)
        self.assertEqual(by["aa136ea1111"]["attempts"], ["fail"])
        self.assertEqual(by["aa136ea1111"]["logs"], ["sql_aa136ea_x.log"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `AttributeError: module 'verify_testcase' has no attribute 'build_sql_request'`.

- [ ] **Step 3: Implement** — in `verify_testcase.py`:

(a) Add after `build_request` (near line 88):

```python
def build_sql_request(script_text, answer_text, commits, worker_ip_list,
                      run_mode="fixed-runs", min_runs=1, max_runs=1,
                      build_type="debug", callback_url=None,
                      commit_build_mode="checkout"):
    if not answer_text:
        raise ValueError(
            "customSqlAnswer must be non-empty (the builder 400s without it); "
            "derive it first with 'derive-answer --test-type sql'")
    return {
        "commits": list(commits),
        "testType": "sql",
        "customSqlScript": script_text,
        "customSqlAnswer": answer_text,
        "workerIps": list(worker_ip_list),
        "runMode": run_mode, "minRuns": min_runs, "maxRuns": max_runs,
        "buildType": build_type, "commitBuildMode": commit_build_mode,
        "callbackUrl": callback_url or (builder_url() + "/callback"),
    }


def resolve_answer_path(script_path):
    """Sibling answers/<name>.answer for a cases/<name>.sql; else alongside."""
    d = os.path.dirname(os.path.abspath(script_path))
    stem = os.path.splitext(os.path.basename(script_path))[0]
    if os.path.basename(d) == "cases":
        return os.path.join(os.path.dirname(d), "answers", stem + ".answer")
    return os.path.join(d, stem + ".answer")


def has_queryplan_sidecar(script_path):
    """True if a sibling <name>.queryPlan exists next to the .sql (plan test)."""
    stem = os.path.splitext(os.path.abspath(script_path))[0]
    return os.path.exists(stem + ".queryPlan")


def find_artifacts(report, commit_sha, artifact_type):
    """logFileNames of artifact entries of the given type for the commit."""
    if not commit_sha:
        return []
    out = []
    for r in report.get("results", []):
        c = r.get("commit") or ""
        if not (c.startswith(commit_sha[:7]) or commit_sha.startswith(c[:7] or "x")):
            continue
        for a in r.get("attemptLogMetadata", []):
            if a.get("artifactType") == artifact_type and a.get("logFileName"):
                out.append(a["logFileName"])
    return out


def report_test_type(report):
    tt = report.get("testType")
    if tt:
        return tt
    for r in report.get("results", []):
        if r.get("testType"):
            return r["testType"]
    return "shell"
```

(b) Replace `results_by_commit`'s `logs` line so artifact entries (which carry `artifactType`) are excluded from attempt logs. Find:
```python
        logs = [a.get("logFileName") for a in meta if a.get("logFileName")]
```
Replace with:
```python
        logs = [a.get("logFileName") for a in meta
                if a.get("logFileName") and not a.get("artifactType")]
```

(c) Replace `elide_payload` (only elide content keys that are present — fixing a spurious `customShellScript` on SQL requests — and cover the SQL fields). Find:
```python
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
```
Replace with:
```python
def elide_payload(req):
    """A print-safe copy: large content fields shown as size + sha256."""
    def mark(s):
        b = s.encode("utf-8")
        return "<%d bytes sha256:%s>" % (len(b), hashlib.sha256(b).hexdigest()[:12])
    safe = dict(req)
    for k in ("customShellScript", "customSqlScript", "customSqlAnswer"):
        if k in req:
            safe[k] = mark(req[k])
    if "customAttachments" in req:
        safe["customAttachments"] = [
            {"targetPath": a["targetPath"], "contentBase64": mark(a["contentBase64"])}
            for a in req["customAttachments"]]
    return safe
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS (all new classes; the existing `TestResultsByCommit`/`TestElidePayload` still pass — shell reports have no `artifactType`, shell requests still carry `customShellScript`).

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: SQL request assembly + artifact/answer helpers"
```

---

## Task 2: CLI SQL wiring (submit / run / judge)

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py`

**Interfaces:**
- Consumes: Task 1 helpers; existing `build_request`/`collect_attachments`/`_wait`/`judge_matrix`/`_print_and_exit`/`bt_get_text`/`BuilderTesterError`.
- Produces: `test_type_of(args) -> "shell"|"sql"`; `resolve_runs(args, test_type) -> None` (mutates); `show_sql_diff(report, judged, task_id) -> None` (best-effort, never raises); `_add_sql_type_args(p)`. `_submit` gains a `test_type` param with a SQL branch (empty-answer + sidecar guards). `submit`/`run` parsers gain `--test-type`/`--answer` (via `_add_sql_type_args`); `--min-runs`/`--max-runs` default `None`; `judge` gains `--test-type` (accepted for symmetry).

- [ ] **Step 1: Write the failing tests** — append:

```python
class TestTestTypeOf(unittest.TestCase):
    def _ns(self, **k):
        import argparse
        return argparse.Namespace(**k)

    def test_explicit_wins(self):
        self.assertEqual(vt.test_type_of(self._ns(test_type="sql", script="x.sh")), "sql")

    def test_inferred_from_sql_suffix(self):
        self.assertEqual(vt.test_type_of(self._ns(test_type=None, script="a/b.sql")), "sql")

    def test_defaults_shell(self):
        self.assertEqual(vt.test_type_of(self._ns(test_type=None, script="a/b.sh")), "shell")


class TestResolveRuns(unittest.TestCase):
    def _ns(self, mn, mx):
        import argparse
        return argparse.Namespace(min_runs=mn, max_runs=mx)

    def test_sql_defaults_1_1(self):
        a = self._ns(None, None); vt.resolve_runs(a, "sql")
        self.assertEqual((a.min_runs, a.max_runs), (1, 1))

    def test_shell_defaults_2_2(self):
        a = self._ns(None, None); vt.resolve_runs(a, "shell")
        self.assertEqual((a.min_runs, a.max_runs), (2, 2))

    def test_explicit_preserved(self):
        a = self._ns(3, 5); vt.resolve_runs(a, "sql")
        self.assertEqual((a.min_runs, a.max_runs), (3, 5))


class TestShowSqlDiff(unittest.TestCase):
    def setUp(self):
        self._orig = vt.bt_get_text

    def tearDown(self):
        vt.bt_get_text = self._orig

    REPORT = {"testType": "sql", "results": [{"commit": "POSTsha", "attemptLogMetadata": [
        {"attempt": 1, "logFileName": "sql_POST_x.log", "status": "fail"},
        {"attempt": 1, "logFileName": "sql_diff_POST_x.diff", "artifactType": "answer_diff"}]}]}

    def _judged(self, verdict):
        return {"verdict": verdict, "pre_sha": "PREsha", "post_sha": "POSTsha"}

    def test_prints_diff_on_not_verified(self):
        calls = []
        vt.bt_get_text = lambda path, **k: calls.append(path) or "DIFF-TEXT-HERE"
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            vt.show_sql_diff(self.REPORT, self._judged("NOT-VERIFIED"), "req_1")
        self.assertIn("DIFF-TEXT-HERE", buf.getvalue())
        self.assertTrue(calls)

    def test_verified_fetches_nothing(self):
        calls = []
        vt.bt_get_text = lambda path, **k: calls.append(path) or "x"
        vt.show_sql_diff(self.REPORT, self._judged("VERIFIED"), "req_1")
        self.assertEqual(calls, [])

    def test_fetch_failure_is_soft(self):
        def boom(path, **k):
            raise vt.BuilderTesterError("blip")
        vt.bt_get_text = boom
        # must NOT raise — the verdict must still be printable afterwards
        vt.show_sql_diff(self.REPORT, self._judged("NOT-VERIFIED"), "req_1")


class TestCliSqlDryRun(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cases = os.path.join(self.d, "sql", "_13_issues", "_26_2h", "cases")
        self.answers = os.path.join(self.d, "sql", "_13_issues", "_26_2h", "answers")
        os.makedirs(self.cases); os.makedirs(self.answers)
        self.sql = os.path.join(self.cases, "cbrd_1.sql")
        with open(self.sql, "w") as fh:
            fh.write("select 1;\n")
        self.ans = os.path.join(self.answers, "cbrd_1.answer")
        with open(self.ans, "w") as fh:
            fh.write("===\n1\n")
        self.vt_path = os.path.join(os.path.dirname(__file__), "..", "verify_testcase.py")

    def tearDown(self):
        shutil.rmtree(self.d)

    def _run(self, *extra):
        env = dict(os.environ); env["BUILDER_TESTER_URL"] = "http://127.0.0.1:1"
        return subprocess.run([sys.executable, self.vt_path, "submit", "--script", self.sql,
                               "--pre", "AAA", "--post", "BBB"] + list(extra),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)

    def test_sql_submit_dry_run(self):
        out = self._run(); text = out.stdout.decode("utf-8")
        self.assertEqual(out.returncode, 0, text)
        self.assertIn("[dry-run]", text)
        self.assertIn('"testType": "sql"', text)
        self.assertIn("customSqlAnswer", text)

    def test_missing_answer_errors(self):
        os.remove(self.ans)
        out = self._run()
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("derive-answer", out.stdout.decode("utf-8"))

    def test_empty_answer_errors_not_traceback(self):
        open(self.ans, "w").close()  # exists but 0 bytes
        out = self._run()
        self.assertNotEqual(out.returncode, 0)
        text = out.stdout.decode("utf-8")
        self.assertIn("derive-answer", text)
        self.assertNotIn("Traceback", text)

    def test_queryplan_sidecar_blocks_run(self):
        open(os.path.join(self.cases, "cbrd_1.queryPlan"), "w").close()
        out = self._run()
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("queryPlan", out.stdout.decode("utf-8"))
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `AttributeError: ... 'test_type_of'`; SQL submit prints a shell payload / crashes.

- [ ] **Step 3: Implement** — in `verify_testcase.py`:

(a) Add helpers above `cmd_submit`:

```python
def test_type_of(args):
    if getattr(args, "test_type", None):
        return args.test_type
    script = getattr(args, "script", None)
    if script and script.endswith(".sql"):
        return "sql"
    return "shell"


def resolve_runs(args, test_type):
    lo, hi = (1, 1) if test_type == "sql" else (2, 2)
    if getattr(args, "min_runs", None) is None:
        args.min_runs = lo
    if getattr(args, "max_runs", None) is None:
        args.max_runs = hi


def show_sql_diff(report, judged, task_id):
    """Best-effort: on a non-VERIFIED SQL run, print the failing commit's
    answer_diff. Never raises — a fetch blip must not swallow the verdict."""
    if report_test_type(report) != "sql" or judged.get("verdict") == "VERIFIED":
        return
    for sha in (judged.get("post_sha"), judged.get("pre_sha")):
        diffs = find_artifacts(report, sha, "answer_diff")
        if not diffs:
            continue
        try:
            text = bt_get_text("/api/log/%s/tests/%s" % (task_id, diffs[0]))
        except BuilderTesterError as e:
            print("  (could not fetch answer_diff: %s)" % e)
            return
        if text:
            print("\n--- answer_diff (%s) ---" % sha[:7])
            print(text[:4000])
        return
```

(b) Replace `_submit` to branch on `test_type` (SQL guards: empty answer, `.queryPlan` sidecar):

Find the whole current `_submit` function and replace with:
```python
def _submit(script_text, entry_abs, commits, args, yes, test_type):
    entry_abs = os.path.abspath(entry_abs)
    if test_type == "sql":
        if has_queryplan_sidecar(entry_abs):
            sys.exit("this case has a .queryPlan sidecar — its answer contains plan output "
                     "that custom SQL mode cannot reproduce; verify it on a local CTP host")
        answer_path = getattr(args, "answer", None) or resolve_answer_path(entry_abs)
        try:
            answer_text = _load_script(answer_path)
        except (IOError, OSError):
            answer_text = None
        if not answer_text:
            sys.exit("no usable answer at %s (missing or empty) — derive it first: "
                     "verify_testcase.py derive-answer --test-type sql --script %s "
                     "(--engine-pr/--issue/--post)" % (answer_path, entry_abs))
        req = build_sql_request(script_text, answer_text, commits, worker_ips(),
                                run_mode=args.run_mode, min_runs=args.min_runs,
                                max_runs=args.max_runs, build_type=args.build_type)
    else:
        case_dir = os.path.dirname(entry_abs)
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
```

(c) Replace `cmd_submit`, `cmd_run`, `cmd_judge`:

```python
def cmd_submit(args):
    tt = test_type_of(args)
    resolve_runs(args, tt)
    commits, _pre, _post = _resolve_and_echo(args)
    _submit(_load_script(args.script), args.script, commits, args, args.yes, tt)


def cmd_run(args):
    tt = test_type_of(args)
    resolve_runs(args, tt)
    commits, pre, post = _resolve_and_echo(args)
    task_id = _submit(_load_script(args.script), args.script, commits, args, args.yes, tt)
    if task_id is None:
        return  # dry-run
    try:
        report = _wait(task_id, args.timeout)
    except BuilderTesterError as e:
        _print_and_exit(inconclusive(str(e), pre, post), task_id)
    judged = judge_matrix(results_by_commit(report), pre, post, args.special_case)
    show_sql_diff(report, judged, task_id)
    _print_and_exit(judged, task_id)


def cmd_judge(args):
    _commits, pre, post = _resolve_and_echo(args)
    report = _fetch_report(args.task_id)
    if report is None:
        _print_and_exit(inconclusive("no report found for %s" % args.task_id, pre, post),
                        args.task_id)
    judged = judge_matrix(results_by_commit(report), pre, post, args.special_case)
    show_sql_diff(report, judged, args.task_id)
    _print_and_exit(judged, args.task_id)
```

(d) Add `_add_sql_type_args`, use it in `_add_run_args`, and change the run-count defaults to `None`. Find:
```python
def _add_run_args(p):
    p.add_argument("--run-mode", default="fixed-runs")
    p.add_argument("--min-runs", type=int, default=2)
    p.add_argument("--max-runs", type=int, default=2)
    p.add_argument("--build-type", default="debug")
```
Replace with:
```python
def _add_sql_type_args(p):
    p.add_argument("--test-type", choices=["shell", "sql"], default=None,
                   help="default shell; inferred sql from a .sql --script")
    p.add_argument("--answer", default=None,
                   help="SQL only: answer file (default: sibling answers/<name>.answer)")


def _add_run_args(p):
    p.add_argument("--run-mode", default="fixed-runs")
    p.add_argument("--min-runs", type=int, default=None)
    p.add_argument("--max-runs", type=int, default=None)
    p.add_argument("--build-type", default="debug")
    _add_sql_type_args(p)
```

(e) Add `--test-type` to the `judge` subparser (spec §4 lists it; `cmd_judge` auto-detects via the report). Find:
```python
    pj = sub.add_parser("judge")
    pj.add_argument("--task-id", required=True)
    _add_commit_args(pj)
    pj.add_argument("--special-case", default=None,
                    choices=["core-dump", "flaky-repro", "feature"])
```
Replace with:
```python
    pj = sub.add_parser("judge")
    pj.add_argument("--task-id", required=True)
    _add_commit_args(pj)
    pj.add_argument("--special-case", default=None,
                    choices=["core-dump", "flaky-repro", "feature"])
    pj.add_argument("--test-type", choices=["shell", "sql"], default=None,
                    help="accepted for symmetry; judge auto-detects from the report")
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS — SQL submit dry-run prints `"testType": "sql"` + `customSqlAnswer` (hermetic); missing/empty answer both exit non-zero with a `derive-answer` hint and no traceback; a `.queryPlan` sidecar blocks the run; `show_sql_diff` prints on NOT-VERIFIED, fetches nothing on VERIFIED, and swallows a fetch blip. Shell behavior is unchanged (`TestCliDryRun`, `TestResolveRuns.test_shell_defaults_2_2`).

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: CLI SQL mode for submit/run/judge (--test-type, 1/1 default, guards, diff-on-fail)"
```

---

## Task 3: SQL answer derivation (`derive-answer --test-type sql`)

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py`

**Interfaces:**
- Consumes: Task 1/2 helpers (`build_sql_request`, `resolve_answer_path`, `has_queryplan_sidecar`, `find_artifacts`, `results_by_commit`, `_lookup`), `_wait`, `_post_build`, `bt_get_text`.
- Produces: `_derive_answer_sql(args)`; `cmd_derive_answer` routes by `test_type_of(args)` to it or the renamed existing `_derive_answer_shell(args)`. `derive-answer` parser gains `--test-type`/`--answer` (via `_add_sql_type_args`).

- [ ] **Step 1: Write the failing tests** — append:

```python
class TestDeriveAnswerSql(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cases = os.path.join(self.d, "cases"); os.makedirs(self.cases)
        self.sql = os.path.join(self.cases, "cbrd_1.sql")
        with open(self.sql, "w") as fh:
            fh.write("select 1;\n")
        self.vt_path = os.path.join(os.path.dirname(__file__), "..", "verify_testcase.py")
        self._req, self._txt, self._wait = vt.bt_request, vt.bt_get_text, vt._wait

    def tearDown(self):
        shutil.rmtree(self.d)
        vt.bt_request, vt.bt_get_text, vt._wait = self._req, self._txt, self._wait

    def test_dry_run_shows_placeholder_submit(self):
        env = dict(os.environ); env["BUILDER_TESTER_URL"] = "http://127.0.0.1:1"
        out = subprocess.run(
            [sys.executable, self.vt_path, "derive-answer", "--test-type", "sql",
             "--script", self.sql, "--post", "BBB"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        text = out.stdout.decode("utf-8")
        self.assertEqual(out.returncode, 0, text)
        self.assertIn("[dry-run]", text)
        self.assertIn('"testType": "sql"', text)

    def test_queryplan_sidecar_blocks(self):
        open(os.path.join(self.cases, "cbrd_1.queryPlan"), "w").close()
        env = dict(os.environ); env["BUILDER_TESTER_URL"] = "http://127.0.0.1:1"
        out = subprocess.run(
            [sys.executable, self.vt_path, "derive-answer", "--test-type", "sql",
             "--script", self.sql, "--post", "BBB"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("queryPlan", out.stdout.decode("utf-8"))

    def test_success_writes_answer_from_actual_result(self):
        # in-process (not subprocess) so we can monkeypatch the network layer
        import argparse
        report = {"testType": "sql", "results": [{"commit": "BBBsha", "status": "fail",
            "attemptLogMetadata": [
                {"attempt": 1, "logFileName": "sql_BBB_x.log", "status": "fail"},
                {"attempt": 1, "logFileName": "sql_actual_BBB_x.result",
                 "artifactType": "actual_result"}]}]}
        vt.bt_request = lambda path, **k: {"status": "accepted", "taskId": "req_D"}
        vt._wait = lambda tid, timeout: report
        vt.bt_get_text = lambda path, **k: "===\n1\n"
        args = argparse.Namespace(script=self.sql, test_type="sql", answer=None,
                                  engine_pr=None, issue=None, post="BBBsha",
                                  build_type="debug", timeout=60, yes=True)
        vt._derive_answer_sql(args)
        out_path = os.path.join(self.d, "answers", "cbrd_1.answer")
        self.assertTrue(os.path.exists(out_path))
        with open(out_path) as fh:
            self.assertEqual(fh.read(), "===\n1\n")

    def test_no_artifact_or_not_fail_errors(self):
        import argparse
        report = {"testType": "sql", "results": [{"commit": "BBBsha", "status": "pass",
            "attemptLogMetadata": [{"attempt": 1, "logFileName": "sql_BBB_x.log", "status": "pass"}]}]}
        vt.bt_request = lambda path, **k: {"status": "accepted", "taskId": "req_D"}
        vt._wait = lambda tid, timeout: report
        args = argparse.Namespace(script=self.sql, test_type="sql", answer=None,
                                  engine_pr=None, issue=None, post="BBBsha",
                                  build_type="debug", timeout=60, yes=True)
        with self.assertRaises(SystemExit):
            vt._derive_answer_sql(args)
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `derive-answer` has no `--test-type`; `_derive_answer_sql` undefined.

- [ ] **Step 3: Implement** — in `verify_testcase.py`:

(a) Rename the existing `cmd_derive_answer` function to `_derive_answer_shell` (body unchanged).

(b) Add the SQL derivation + a routing `cmd_derive_answer`:

```python
def _derive_answer_sql(args):
    entry_abs = os.path.abspath(args.script)
    if has_queryplan_sidecar(entry_abs):
        sys.exit("this case has a .queryPlan sidecar — plan output cannot be captured via "
                 "custom SQL mode; derive its answer on a local CTP host (verify-procedure.md)")
    script_text = _load_script(args.script)
    answer_path = getattr(args, "answer", None) or resolve_answer_path(entry_abs)
    pair, owner, repo = _engine_pair_and_owner(args)
    post = args.post or (pair[1] if pair else None)
    if not post:
        sys.exit("need a post-fix commit: pass --post SHA or --engine-pr/--issue REF")
    print("Deriving SQL answer from post-fix build:")
    _echo_pair(owner, repo, None, post)
    req = build_sql_request(script_text, "PLACEHOLDER\n", [post], worker_ips(),
                            run_mode="fixed-runs", min_runs=1, max_runs=1,
                            build_type=args.build_type)
    if not args.yes:
        print("[dry-run] would submit (post-only, placeholder answer) to derive the .answer")
        print(json.dumps(elide_payload(req), indent=2))
        print("[dry-run] pass --yes to submit")
        return
    task_id = _post_build(req)
    print("taskId: %s" % task_id)
    report = _wait(task_id, args.timeout)
    status = (_lookup(results_by_commit(report), post).get("attempts") or ["<none>"])[0]
    arts = find_artifacts(report, post, "actual_result")
    if status != "fail" or not arts:
        sys.exit("cannot derive: post-fix status=%s, actual_result artifact %s. A wrong "
                 "placeholder answer should yield status=fail with an actual_result artifact; "
                 "a syntax error/timeout gives execution_error (no artifact). Fix the draft and "
                 "retry. Inspect report %s"
                 % (status, "present" if arts else "missing", task_id))
    content = bt_get_text("/api/log/%s/tests/%s" % (task_id, arts[0]))
    if not content:
        sys.exit("actual_result artifact %s was empty; inspect report %s" % (arts[0], task_id))
    answers_dir = os.path.dirname(answer_path)
    if answers_dir and not os.path.isdir(answers_dir):
        os.makedirs(answers_dir)
    # newline="" keeps the run's bytes exact (the server compares intra-line whitespace).
    with open(answer_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    print("\n=== derived answer -> %s (%d bytes) ===" % (answer_path, len(content)))
    print(content)
    print("=== end answer ===")
    print("\nREVIEW REQUIRED: confirm this .answer matches the JIRA to-be behavior before "
          "using it. It was machine-derived from a real post-fix run.")


def cmd_derive_answer(args):
    if test_type_of(args) == "sql":
        _derive_answer_sql(args)
    else:
        _derive_answer_shell(args)
```

(c) Extend the `derive-answer` subparser with `--test-type`/`--answer` via the shared helper. Find:
```python
    pd = sub.add_parser("derive-answer")
    pd.add_argument("--script", required=True)
    pd.add_argument("--engine-pr")
    pd.add_argument("--issue")
    pd.add_argument("--post")
    pd.add_argument("--build-type", default="debug")
    pd.add_argument("--timeout", type=int, default=10800)
    pd.add_argument("--yes", action="store_true")
```
Replace with:
```python
    pd = sub.add_parser("derive-answer")
    pd.add_argument("--script", required=True)
    pd.add_argument("--engine-pr")
    pd.add_argument("--issue")
    pd.add_argument("--post")
    pd.add_argument("--build-type", default="debug")
    pd.add_argument("--timeout", type=int, default=10800)
    pd.add_argument("--yes", action="store_true")
    _add_sql_type_args(pd)
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS — SQL derive dry-run prints the placeholder submit; the `.queryPlan` guard errors before any submit; the monkeypatched success path writes `answers/cbrd_1.answer` byte-for-byte from the `actual_result` artifact; a non-`fail`/no-artifact report raises `SystemExit`. The shell `derive-answer` path is unchanged (`_derive_answer_shell` body identical; router dispatches `.sh` scripts to it).

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: SQL answer derivation via actual_result artifact (fail-gated, byte-exact)"
```

---

## Task 4: Reference doc — SQL section in `builder-tester-verification.md`

**Files:**
- Modify: `cubrid-testcase-creation-common/references/builder-tester-verification.md`

- [ ] **Step 1: Fix the opening** — Find:
```markdown
Remote build+run verification for shell test cases. `verify_testcase.py`
submits a drafted `.sh` in custom-script mode, builds a pre-fix and a post-fix
engine commit, and judges whether the test reproduces the bug pre-fix and
passes post-fix. Shell only — the executor does not run SQL cases.
```
Replace with:
```markdown
Remote build+run verification for **shell and SQL** test cases.
`verify_testcase.py` submits a drafted case in custom mode, builds a pre-fix
and a post-fix engine commit, and judges whether the test reproduces the bug
pre-fix and passes post-fix. Test type is `--test-type shell|sql` (default
shell; inferred `sql` from a `.sql --script`). The shell path is documented
throughout; the SQL differences are in "SQL test cases" below.
```

- [ ] **Step 2: Append the SQL section** at the end of the file:

```markdown
## SQL test cases (`--test-type sql`)

SQL cases run through the Builder-Tester **custom SQL** API (CTP develop +
PR #757, fresh per-case Docker container). The case `.sql` travels inline —
no repo branch needed — so a drafted case verifies before any push, like
shell custom-script mode.

> **Unofficial surface / known fragility.** This custom-SQL request shape
> (`customSqlScript`/`customSqlAnswer`, `custom_sql_case` artifacts) is
> confirmed by live probing but is NOT in the upstream `SQL_TESTER.md`, which
> documents only the repo-path `tests[]` form. And answer *derivation* rides a
> side effect — a deliberately-wrong placeholder answer makes the case `fail`,
> and we harvest the `actual_result` artifact — not an officially supported
> "generate answer" feature. If either behavior drifts, re-probe the live
> server rather than trusting this doc.

- `submit`/`run --script cases/<name>.sql [--answer PATH]` — the `.sql` content
  is `customSqlScript`; the answer is `customSqlAnswer`, read from `--answer` or
  the sibling `answers/<name>.answer`. The answer must be non-empty (the builder
  400s otherwise) and byte-exact from a real run — derive it, never hand-write
  it. Defaults: `buildType=debug`, `runMode=fixed-runs 1/1` (fresh container per
  case de-flakes). A `.sql` with a sibling `.queryPlan` is refused (its answer
  carries plan output custom mode can't reproduce — use local CTP).
- `derive-answer --test-type sql --script cases/<name>.sql (--engine-pr REF |
  --issue KEY | --post SHA)` — submits post-only with a placeholder answer,
  requires the run to `fail` and produce an `actual_result` artifact, writes
  that (byte-exact) to the sibling `answers/<name>.answer`, and prints it for
  approval. On `pass`/`execution_error`/no artifact it stops with guidance —
  fix the draft (a syntax error surfaces as `execution_error`, no artifact) and
  retry.
- Verdict semantics, commit-pair resolution, `_wait`, exit codes, and the
  copy-ready `Verified:` line are identical to shell. Any status other than
  `pass`/`fail` (`execution_error`, `environment_error`, `build_failed`,
  `cancelled`) is infra → INCONCLUSIVE. On a non-VERIFIED SQL run the block
  also prints the failing commit's `answer_diff` (best-effort; a fetch blip is
  a soft warning, never hides the verdict). `run_sql.sh` exit is always 0 —
  verdicts are parsed.

**Artifacts** (custom mode, `testName = custom_sql_case`), at
`GET /api/log/<requestId>/tests/<filename>`: `answer_diff`, `actual_result`,
`expected_answer`, `case_source`, `warm_console`, `core_list`. Artifact
entries carry `artifactType` and no `status`, so they are excluded from
attempt counting and from the verdict block's log lines.

**Answer variants.** `.answer_cci` / `.answer_WIN` cannot be derived remotely
(single execution env) — note as reduced-evidence when a case needs them.

**Post-merge regression (manual).** The repo-path form (`tests[]` +
`testType:"sql"` + optional `sqlTcBranch`) resolves against the tester's
`sql_tc_dir` clone, which tracks **upstream CUBRID/cubrid-testcases only** —
fork branches are invisible. Use it by hand for post-merge regression; it is
not wired into the skills.
```

- [ ] **Step 3: Verify**

Run: `grep -c "test-type sql\|custom_sql_case\|Unofficial surface\|derive-answer --test-type sql" cubrid-testcase-creation-common/references/builder-tester-verification.md`
Expected: nonzero.

- [ ] **Step 4: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/references/builder-tester-verification.md
git commit -m "verify: document SQL custom-mode verification + derivation (with fragility caveat)"
```

---

## Task 5: Wire verification into `create-cubrid-sql-testcase`

**Files:**
- Modify: `create-cubrid-sql-testcase/SKILL.md`

- [ ] **Step 1: Delete the shell-only note + add `$BT` to path resolution**

Find and DELETE:
```markdown
Note: remote Builder-Tester verification (create-cubrid-shell-testcase) does
not apply here — its executor runs shell cases only. SQL answer generation
uses the local CTP path or the printed verify handoff.
```

Find:
```markdown
- `$COMMON` = `$SKILL/../cubrid-testcase-creation-common` — scripts
  (`fetch_context.py`, `push_package.py`, `get_engine_pr.py`) and references
  (`two-phase-protocol.md`, `verify-procedure.md`). Missing → STOP.
```
Replace with:
```markdown
- `$COMMON` = `$SKILL/../cubrid-testcase-creation-common` — scripts
  (`fetch_context.py`, `push_package.py`, `get_engine_pr.py`,
  `verify_testcase.py`) and references (`two-phase-protocol.md`,
  `verify-procedure.md`, `builder-tester-verification.md`). Missing → STOP.
- `$BT` = `$BUILDER_TESTER_URL` or `http://192.168.2.154:8091` — remote
  build+run verification gateway. Unreachable → skip remote verification and
  fall through the ladder (step 7).
```

- [ ] **Step 2: Replace step 7** — Find:
```markdown
7. **Local answers (only if `CUBRID_TC_ALLOW_LOCAL_CTP=1`).** Follow
   `$COMMON/references/verify-procedure.md` (SQL section): seed → run →
   promote `.result` → re-run `Success:1`; fold real answers into the
   package; re-run the gate once.
```
Replace with:
```markdown
7. **Runtime verification + answer generation (before the push gate).** Read
   `$COMMON/references/builder-tester-verification.md`, then take the first
   reachable rung. Process each package `.sql` file individually.
   a. **Remote Builder-Tester (custom SQL)** — `python3
      $COMMON/scripts/verify_testcase.py health` responds. For each `.sql`
      WITHOUT a sibling `.queryPlan` sidecar:
      - **Derive the answer:** `verify_testcase.py derive-answer --test-type
        sql --script <cases/name.sql> --engine-pr <ref>` (dry-run, then `--yes`
        on confirmation, announcing it consumes shared builder capacity). Get
        the printed answer approved by the user; it is written to
        `answers/<name>.answer`.
      - **Verify:** `verify_testcase.py run --test-type sql --script
        <cases/name.sql> --engine-pr <ref>` (dry-run first; `--yes` after
        confirmation). VERIFIED → proceed. NOT-VERIFIED/FLAKY → diagnose (the
        printed `answer_diff` helps) and fix, re-entering steps 5–6; do not
        push a case that fails to reproduce or is flaky. INCONCLUSIVE →
        builder/env issue; report and fall to rung b/c. `--special-case`
        applies as for shell.
      Files WITH a `.queryPlan` sidecar cannot be derived/verified in custom
      mode (no sidecar channel; the tool refuses them) — leave their answers
      empty and route them to rung b/c, noting it in the render. Fold each
      verdict block into the render (step 8) and the PR body. All non-sidecar
      files must be VERIFIED before the push.
   b. **Local CTP** — only if `CUBRID_TC_ALLOW_LOCAL_CTP=1`: follow
      `$COMMON/references/verify-procedure.md` (SQL section): seed → run →
      promote `.result` → re-run `Success:1`; fold real answers into the
      package; re-run the gate once.
   c. **Printed handoff** — neither reachable: seed empty answers, print the
      verify handoff from `two-phase-protocol.md`, and STOP (Phase 2 resumes
      with supplied answers).
```

- [ ] **Step 3: Update Phase 2 intake** — Find:
```markdown
   user the concern; do not commit silently.
```
Replace with:
```markdown
   user the concern; do not commit silently. Answers already derived on the
   remote rung are byte-exact from a real run (only confirm the approved
   content landed); apply the full semantic validation to hand-supplied
   answers.
```

- [ ] **Step 4: Verify**

Run:
```bash
grep -n "Runtime verification + answer generation\|derive-answer --test-type sql\|run --test-type sql\|\$BT" create-cubrid-sql-testcase/SKILL.md
grep -c "shell cases only\|executor runs shell" create-cubrid-sql-testcase/SKILL.md
python3 -c "import io; io.open('create-cubrid-sql-testcase/SKILL.md',encoding='utf-8').read(); print('ok')"
```
Expected: matches for the ladder terms; `0` for the deleted note; `ok`.

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add create-cubrid-sql-testcase/SKILL.md
git commit -m "sql-tc: wire remote SQL verification + answer derivation into step 7"
```

---

## Task 6: `sql-authoring.md` light alignment pass

**Files:**
- Modify: `create-cubrid-sql-testcase/references/sql-authoring.md`

Findings from the 2026-07 spot-check (N=15 recent cubrid-testcases SQL cases) + `sql_guide.md` develop. All additions marked as current-format observations.

- [ ] **Step 1: Header block rule** — Find:
```markdown
- Header block first:
  `/** This test case verifies CBRD-XXXXX: <title> */` plus a numbered
  `Coverage:` list that matches what the file actually tests.
```
Replace with:
```markdown
- Header block first (current-suite convention, confirmed 2026-07 in every
  recent `_36_guava` feature case): a `/** … */` block opening
  `This test case verifies CBRD-XXXXX: <title>` plus a numbered `Coverage:`
  list that matches what the file actually tests. Legacy `_13_issues` cases
  often have no header — for NEW work always include one. A `-- ==== CBRD-…`
  banner is an accepted alternative.
```

- [ ] **Step 2: evaluate-label rule** — Find:
```markdown
- `evaluate 'Case N: description';` before each scenario, numbered
  sequentially, captions truthful. 3–10 scenarios per file is the norm.
```
Replace with:
```markdown
- Label each scenario with `evaluate '<label>';` before it, numbered
  sequentially, captions truthful (they land in the `.answer` for
  traceability). The label wording is not standardized — recent cases use
  `[TEST N] <desc>` or `[N] <desc>` as often as `Case N:`; any consistent,
  descriptive scheme is fine. 3–10 scenarios per file is the norm.
```

- [ ] **Step 3: Cleanup / DROP rule** — Find:
```markdown
- **The suite shares ONE database.** Undo everything at the end: drop every
  table/view/serial/trigger/procedure, `deallocate prepare` every
  `prepare`, `drop variable` every session variable, restore every
  `SET SYSTEM PARAMETERS` to its original value.
```
Replace with:
```markdown
- **The suite shares ONE database.** Undo everything at the end: drop every
  table/view/serial/trigger/procedure, `deallocate prepare` every `prepare`,
  `drop variable` every session variable, restore every `SET SYSTEM
  PARAMETERS` to its original value. `DROP ... IF EXISTS` is required at CREATE
  time (re-run safety); end-of-file cleanup DROPs need NOT be `IF EXISTS` (bare
  `DROP TABLE t;` is the dominant real pattern). A fully-symmetric IF-EXISTS
  teardown is optional best practice for suites likely to be re-run after a
  mid-file failure.
```

- [ ] **Step 4: Plan-test rule** — Find:
```markdown
- Plan tests: pin the plan — hints (`NO_ELIMINATE_JOIN`, `ORDERED`,
  `MATERIALIZE`, `/*+ recompile */`) where needed; `UPDATE STATISTICS ON
  <tables>` scoped to the tables under test, never `all classes`.
```
Replace with:
```markdown
- Plan tests: create an EMPTY `cases/<name>.queryPlan` sidecar (case-sensitive
  extension) to make CTP emit the query plan into the result — this is the
  house convention; do NOT use the inline `--@queryplan` directive for new
  drafts. Pin the plan with hints (`NO_ELIMINATE_JOIN`, `ORDERED`,
  `MATERIALIZE`, `/*+ recompile */`) where needed; scope `UPDATE STATISTICS ON
  <tables>` to the tables under test, never `all classes`. Note: a
  `.queryPlan` case cannot be verified via remote Builder-Tester (no sidecar
  channel — see builder-tester-verification.md); generate/verify its answer on
  a local CTP host.
```

- [ ] **Step 5: Answer-variants + error-case notes** — under `## Error cases`, Find:
```markdown
- An unexpected error/result may be a product bug: do not design the case
  to bake it in — flag it for a CBRD issue instead.
```
Replace with:
```markdown
- An unexpected error/result may be a product bug: do not design the case
  to bake it in — flag it for a CBRD issue instead.
- Answer variants are opt-in, created only on a real divergence and kept in
  sync thereafter: `answers/<name>.answer_cci` (CCI output differs — rare,
  seen mainly in older plan/trace cases) and `.answer_WIN` (Windows differs —
  effectively unused in recent cases). Do not add them speculatively.
- For files with several negative cases, a recommended enhancement (seen in
  recent `_36_guava` cases) is a defensive `SELECT COUNT(*)` catalog/state
  sanity-check after each error, using a distinct object name per negative
  case, so a masked failure can't pass silently.
```

- [ ] **Step 6: Naming rule** — Find:
```markdown
- Bug fix: `sql/_13_issues/_{yy}_{1|2}h/cases/…`; release-targeted issue:
  `sql/_{no}_{release_code}/cbrd_XXXXX/cases/…` — match where sibling
  issues of the same release actually landed (release targeting beats JIRA
  creation date). Multiple files per issue share ONE `cases/`+`answers/`
  pair with suffixes (`cbrd_XXXXX_select.sql`) — never one subdir per file.
```
Replace with:
```markdown
- Bug fix: `sql/_13_issues/_{yy}_{1|2}h/cases/cbrd_XXXXX[_n|_keyword].sql`
  (shared `cases/`+`answers/` for the bucket; simple repros are a single
  `cbrd_XXXXX.sql`). Release feature: `sql/_{no}_{release_code}/cbrd_XXXXX/
  cases/<NN_feature-description>.sql` — its own per-issue folder with
  descriptive, numbered file names (the current `_36_guava` convention for
  issues needing several independent test angles). Match where sibling issues
  of the same release actually landed (release targeting beats JIRA creation
  date). Generic regression-suite dirs legitimately use plain descriptive
  names with no CBRD number.
```

- [ ] **Step 7: Verify**

Run:
```bash
grep -c "queryPlan sidecar\|end-of-file cleanup DROPs need NOT\|\[TEST N\]\|answer_cci" create-cubrid-sql-testcase/references/sql-authoring.md
python3 -c "import io; io.open('create-cubrid-sql-testcase/references/sql-authoring.md',encoding='utf-8').read(); print('ok')"
```
Expected: nonzero; `ok`.

- [ ] **Step 8: Commit**

```bash
cd ~/worktrees/skills-main
git add create-cubrid-sql-testcase/references/sql-authoring.md
git commit -m "sql-tc: align authoring doctrine with sql_guide + 2026-07 corpus spot-check"
```

---

## Task 7: Update shared protocol references

**Files:**
- Modify: `cubrid-testcase-creation-common/references/two-phase-protocol.md`
- Modify: `cubrid-testcase-creation-common/references/verify-procedure.md`

- [ ] **Step 1: two-phase-protocol.md** — replace the SQL-exclusion sentence (present verbatim at line 42). Find:
```markdown
handoff. SQL cases have no remote option (the executor is shell-only).
```
Replace with:
```markdown
handoff. SQL cases have the same three rungs via the Builder-Tester custom
SQL API (`verify_testcase.py --test-type sql`): remote (derive answer +
pre/post verify) → local CTP → handoff. A `.sql` with a `.queryPlan` sidecar
has no remote option (no sidecar channel) and uses local CTP / handoff.
```

- [ ] **Step 2: verify-procedure.md** — after the existing shell-prefer note (the blockquote at lines 9–13), add a SQL analog. Find:
```markdown
> when the Builder-Tester gateway is unreachable and
> `CUBRID_TC_ALLOW_LOCAL_CTP=1` is set.
```
Replace with:
```markdown
> when the Builder-Tester gateway is unreachable and
> `CUBRID_TC_ALLOW_LOCAL_CTP=1` is set.

> For SQL cases, prefer remote Builder-Tester verification too
> (`builder-tester-verification.md`, `--test-type sql`) — it derives the
> `.answer` from a real run and proves pre-fix fail / post-fix pass without a
> local CTP install. Use the local SQL runbook below only when the gateway is
> unreachable and `CUBRID_TC_ALLOW_LOCAL_CTP=1`, or for `.queryPlan`-sidecar
> cases (which custom SQL mode cannot verify).
```

- [ ] **Step 3: Verify**

Run: `grep -c "custom SQL\|--test-type sql" cubrid-testcase-creation-common/references/two-phase-protocol.md cubrid-testcase-creation-common/references/verify-procedure.md`
Expected: nonzero in both. Parse check:
`python3 -c "import io;[io.open(f,encoding='utf-8').read() for f in ['cubrid-testcase-creation-common/references/two-phase-protocol.md','cubrid-testcase-creation-common/references/verify-procedure.md']];print('ok')"`

- [ ] **Step 4: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/references/two-phase-protocol.md \
        cubrid-testcase-creation-common/references/verify-procedure.md
git commit -m "verify: shared references note the SQL remote-verification rung"
```

---

## Task 8: Reviewer skill — offer SQL PR verification

**Files:**
- Modify: `review-cubrid-testcase-pr/SKILL.md`

- [ ] **Step 1: Generalize the header** — Find:
```markdown
### Optional: runtime verification of a shell TC PR (ask first)

For a shell test-case PR only, offer — never run unprompted — a remote
```
Replace with:
```markdown
### Optional: runtime verification of a shell or SQL TC PR (ask first)

For a shell or SQL test-case PR, offer — never run unprompted — a remote
```

- [ ] **Step 2: Generalize the fetch + invocation** — Find (verbatim, lines ~146–152):
```markdown
On agreement, read `$COMMON/references/builder-tester-verification.md`, fetch
the PR's shell package into a scratch dir with
`python3 $COMMON/scripts/fetch_context.py get <owner/repo> <case-dir paths> --out $scratch --ref <pr-head-sha>`,
then run against the PR head's entry script and the issue's engine PR:

`python3 $COMMON/scripts/verify_testcase.py run --script <fetched entry.sh>
--engine-pr <engine ref>` (dry-run first, `--yes` after the user confirms).
```
Replace with:
```markdown
On agreement, read `$COMMON/references/builder-tester-verification.md`, fetch
the PR's package into a scratch dir with `python3
$COMMON/scripts/fetch_context.py get <owner/repo> <paths> --out $scratch --ref
<pr-head-sha>` — for a SQL PR pass BOTH the `cases/` and sibling `answers/`
paths so the committed `.answer` is present. Then run against the PR head's
entry file and the issue's engine PR:

- **Shell TC PR:** `python3 $COMMON/scripts/verify_testcase.py run
  --script <fetched cases/name.sh> --engine-pr <engine ref>`.
- **SQL TC PR:** `python3 $COMMON/scripts/verify_testcase.py run --test-type
  sql --script <fetched cases/name.sql> --engine-pr <engine ref>` — the PR's
  committed `answers/<name>.answer` is used as `customSqlAnswer` (no
  derivation needed; the answer is in the PR). Skip a `.sql` with a
  `.queryPlan` sidecar (custom SQL mode cannot verify it) with a note.

(dry-run first, `--yes` after the user confirms.)
```

- [ ] **Step 3: Verify**

Run: `grep -c "run --test-type sql\|SQL TC PR\|sibling .answers. paths" review-cubrid-testcase-pr/SKILL.md`; expected nonzero. `python3 -c "import io; io.open('review-cubrid-testcase-pr/SKILL.md',encoding='utf-8').read(); print('ok')"`.

- [ ] **Step 4: Commit**

```bash
cd ~/worktrees/skills-main
git add review-cubrid-testcase-pr/SKILL.md
git commit -m "review: offer remote verification for SQL TC PRs too"
```

---

## Task 9: Live check extension + SQL calibration runbook

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/tests/live_check.sh`
- Create: `docs/superpowers/plans/2026-07-22-sql-calibration.md`

- [ ] **Step 1: Extend `live_check.sh`** — add this second heredoc after the existing reports/attempt-log check block in `live_check.sh` (it filters on `artifactType` so it genuinely exercises the artifact-fetch path, not a plain attempt log):

```bash
echo "== sql report + artifact (read-only) =="
python3 - "$here" <<'PY'
import sys, os
sys.path.insert(0, sys.argv[1])
import btlib
data = btlib.bt_request("/api/reports?pageSize=50")
sqlrep = next((it for it in data.get("items", []) if it.get("testType") == "sql"), None)
if not sqlrep:
    print("no SQL report available to sample yet (ok)"); sys.exit(0)
print("sql report:", sqlrep["id"])
for r in sqlrep.get("results", []):
    for a in r.get("attemptLogMetadata", []):
        if a.get("artifactType") and a.get("logFileName"):   # artifact, not a plain log
            txt = btlib.bt_get_text("/api/log/%s/tests/%s" % (sqlrep["id"], a["logFileName"]))
            assert txt is not None, "empty artifact"
            print("sql artifact OK: %s %s (%d bytes)"
                  % (a["artifactType"], a["logFileName"], len(txt)))
            sys.exit(0)
print("SQL report has no artifact to sample (ok)")
PY
```

- [ ] **Step 2: Run the live check (informational)**

Run: `bash cubrid-testcase-creation-common/scripts/tests/live_check.sh`
Expected (gateway up): the existing health/report/attempt-log lines plus `sql report: <id>` and `sql artifact OK: actual_result … `. Gateway down → `UNREACHABLE` exit 1 (a valid environment state, not a code failure).

- [ ] **Step 3: Write the calibration runbook** — create `docs/superpowers/plans/2026-07-22-sql-calibration.md`:

```markdown
# SQL verification calibration (manual, gated)

End-to-end proof of `verify_testcase.py --test-type sql` against an
already-merged SQL TC — ground-truth for the derivation path and the first
real `debug`-buildType SQL submission. Consumes builder capacity; run once
with user confirmation.

## Inputs
- An already-merged SQL TC whose answer actually CHANGED with a known engine
  fix, e.g. CBRD-26900 (engine PR CUBRID/cubrid#7269). Fetch the case `.sql`
  and its committed `answers/<name>.answer` from CUBRID/cubrid-testcases into
  a scratch dir (`fetch_context.py get`, both `cases/` and `answers/`).

## Steps
1. **Derivation ground-truth:** `verify_testcase.py derive-answer --test-type
   sql --script <scratch>/cases/<name>.sql --issue CBRD-26900` (dry-run, then
   `--yes`). The derived `answers/<name>.answer` must match the repo's
   committed answer (newline-level differences tolerated per the server's
   comparison rules; intra-line whitespace must match). A mismatch is a real
   finding — investigate before trusting derivation.
2. **Pre/post verify (debug build):** `verify_testcase.py run --test-type sql
   --script <scratch>/cases/<name>.sql --issue CBRD-26900` → expect
   **VERIFIED** (pre-fix answer mismatch/`fail`, post-fix `pass`). This is the
   first real `buildType=debug` SQL run — confirm it builds and reports
   normally. If the case's answer did NOT change with the fix it will be
   NOT-VERIFIED — pick a TC whose answer actually changed.

## Record
Capture the verdict block + report id. Validates SQL request assembly,
artifact-based derivation, and the shared verdict path against ground truth,
and confirms debug-buildType SQL works.
```

- [ ] **Step 4: Verify the runbook**

Run: `grep -c "derive-answer --test-type sql\|VERIFIED\|debug" docs/superpowers/plans/2026-07-22-sql-calibration.md && python3 -c "import io; io.open('docs/superpowers/plans/2026-07-22-sql-calibration.md',encoding='utf-8').read(); print('ok')"`
Expected: nonzero; `ok`.

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
chmod +x cubrid-testcase-creation-common/scripts/tests/live_check.sh
git add cubrid-testcase-creation-common/scripts/tests/live_check.sh \
        docs/superpowers/plans/2026-07-22-sql-calibration.md
git commit -m "verify: live SQL-report/artifact check + SQL calibration runbook"
```

---

## Final verification (after all tasks)

- [ ] **Full unit suite**: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v` — all pass.
- [ ] **No bytecode staged**: `git status --porcelain | grep -E "\.pyc|__pycache__" || echo clean`.
- [ ] **`--help` shows the new flags**: `python3 cubrid-testcase-creation-common/scripts/verify_testcase.py submit --help | grep -E "test-type|answer"`; `... judge --help | grep test-type`.
- [ ] **No watermark**: `base=$(git merge-base main HEAD); git log --format='%an %s' "$base"..HEAD | grep -iE "claude|anthropic|co-authored|🤖" && echo WATERMARK || echo clean`.
