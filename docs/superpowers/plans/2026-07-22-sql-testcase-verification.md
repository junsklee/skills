# SQL Test-Case Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `verify_testcase.py` with a SQL mode that verifies drafted SQL test cases against the Builder-Tester (custom-SQL API: pre-fix fails, post-fix passes) and derives `.answer` files from a real post-fix run, and wire it into `create-cubrid-sql-testcase` — bringing the SQL creator to the shell creator's production grade.

**Architecture:** One tool serves both test types. The hardened lifecycle (`_wait`/`_pending`/`status_phase`/`judge_matrix`/commit-pair resolution) is reused unchanged; only request assembly, artifact location/fetch, and answer write-back are new. The SQL skill gains the same three-rung verification ladder the shell skill has. Authoring doctrine gets a light alignment pass from `sql_guide.md` + a 15-case spot-check.

**Tech Stack:** Python 3.6 stdlib only (no third-party); Builder-Tester report-server over plain HTTP; `unittest`.

## Global Constraints

- **Python 3.6, stdlib only.** Match the style of the existing `verify_testcase.py` / `btlib.py` — `%`-formatting, no f-strings, no 3.7+ stdlib.
- **Dry-run by default; `--yes` performs the only network write (build submission).** Local file writes (a derived `.answer`) are allowed without `--yes`, but the submission that produces them is gated.
- **This host never executes tests/CTP/csql/cubrid.** The tool only talks HTTP to the remote Builder-Tester.
- **No Claude/Anthropic watermark** anywhere — code, comments, commit messages, PR bodies. No `Co-Authored-By`, no 🤖.
- **`.answer` files are never hand-written** — machine-derived from a real run and shown to the user for approval before use.
- **Config (unchanged):** `BUILDER_TESTER_URL` default `http://192.168.2.154:8091`; `BUILDER_TESTER_WORKER_IPS` default `192.168.2.154:8090`.
- **PR titles English; PR bodies + JIRA Korean.**
- **Work on branch `feat/sql-testcase-verify`** (already created off `main` in `~/worktrees/skills-main`). Do not open a PR unless asked.
- **Test command** (from `~/worktrees/skills-main`): `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`

## Server contract (SQL custom mode — verified live 2026-07-22)

- `POST /api/builder/build` custom-SQL body: `{commits, testType:"sql", customSqlScript, customSqlAnswer, workerIps, runMode/minRuns/maxRuns, buildType, commitBuildMode, callbackUrl}`. **No `tests[]`** (a `custom_script_test` placeholder is inserted). `customSqlAnswer` REQUIRED non-empty (else HTTP 400). `customShellScript`/`customScriptTestPath`/`customAttachments` rejected in SQL mode.
- Runs in a **fresh per-case container**, once per commit; `testName = custom_sql_case`.
- Statuses: `pass`/`fail`/`execution_error`/`environment_error`/`build_error`/`flaky`/`cancelled`. `fail` = answer mismatch; `execution_error` = missing answer / timeout / no verdict; `environment_error` = provisioning/Docker. Exit code is always 0 (verdict is parsed).
- `attemptLogMetadata[]`: plain attempt logs `{attempt, logFileName, status}`; artifact entries `{attempt, logFileName, artifactType, executionEnv?}` (**no `status`**). Artifact types: `answer_diff`, `actual_result`, `expected_answer`, `case_source`, `warm_console`, `core_list`.
- Custom-SQL artifact filenames use `testName=custom_sql_case`, e.g. `sql_actual_<c7>_custom_sql_case.result`. Fetch any via `GET /api/log/<requestId>/tests/<filename>` (text/plain).
- Answer-derivation protocol: submit with a placeholder answer → the run `fail`s → read the `actual_result` artifact → that is the real output.
- `/api/reports` items carry `testType`.

---

## Task 1: SQL request assembly + artifact/answer helpers (pure)

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py`

**Interfaces:**
- Consumes: `builder_url` (btlib).
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
Expected: FAIL — `AttributeError: module 'verify_testcase' has no attribute 'build_sql_request'` (and the elide/logs tests fail on current behavior).

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

(b) Replace `results_by_commit`'s `logs` line so artifact entries (which carry `artifactType`) are excluded from attempt logs:

Find:
```python
        logs = [a.get("logFileName") for a in meta if a.get("logFileName")]
```
Replace with:
```python
        logs = [a.get("logFileName") for a in meta
                if a.get("logFileName") and not a.get("artifactType")]
```

(c) Replace `elide_payload` so it only elides content keys that are present (fixing the spurious `customShellScript` on SQL requests) and covers the SQL fields:

Find the whole `elide_payload` function and replace with:
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
Expected: PASS (all new classes + existing suite unchanged — the existing `TestResultsByCommit`/`TestElidePayload` still pass because shell reports have no `artifactType` and shell requests still carry `customShellScript`).

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
- Consumes: Task 1 helpers; `build_sql_request`, `resolve_answer_path`, `find_artifacts`, `report_test_type`, existing `build_request`/`collect_attachments`/`_wait`/`judge_matrix`/`_print_and_exit`.
- Produces: `test_type_of(args) -> "shell"|"sql"`; `resolve_runs(args, test_type) -> None` (mutates args); `show_sql_diff(report, judged, task_id) -> None`. `_submit` gains a `test_type` param and a SQL branch. `submit`/`run` parsers gain `--test-type {shell,sql}` and `--answer`; `--min-runs`/`--max-runs` default to `None`.

- [ ] **Step 1: Write the failing test** — append:

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


class TestCliSqlDryRun(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        cases = os.path.join(self.d, "sql", "_13_issues", "_26_2h", "cases")
        answers = os.path.join(self.d, "sql", "_13_issues", "_26_2h", "answers")
        os.makedirs(cases); os.makedirs(answers)
        self.sql = os.path.join(cases, "cbrd_1.sql")
        with open(self.sql, "w") as fh:
            fh.write("select 1;\n")
        with open(os.path.join(answers, "cbrd_1.answer"), "w") as fh:
            fh.write("===\n1\n")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_sql_submit_dry_run(self):
        env = dict(os.environ); env["BUILDER_TESTER_URL"] = "http://127.0.0.1:1"
        vt_path = os.path.join(os.path.dirname(__file__), "..", "verify_testcase.py")
        out = subprocess.run(
            [sys.executable, vt_path, "submit", "--script", self.sql,
             "--pre", "AAA", "--post", "BBB"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        text = out.stdout.decode("utf-8")
        self.assertEqual(out.returncode, 0, text)
        self.assertIn("[dry-run]", text)
        self.assertIn('"testType": "sql"', text)
        self.assertIn("customSqlAnswer", text)

    def test_sql_submit_missing_answer_errors(self):
        os.remove(os.path.join(self.d, "sql", "_13_issues", "_26_2h", "answers", "cbrd_1.answer"))
        env = dict(os.environ); env["BUILDER_TESTER_URL"] = "http://127.0.0.1:1"
        vt_path = os.path.join(os.path.dirname(__file__), "..", "verify_testcase.py")
        out = subprocess.run(
            [sys.executable, vt_path, "submit", "--script", self.sql,
             "--pre", "AAA", "--post", "BBB"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("derive-answer", out.stdout.decode("utf-8"))
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `AttributeError: ... 'test_type_of'`; the CLI SQL dry-run prints a shell payload / errors.

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
    """On a non-VERIFIED SQL run, print the answer_diff of the failing commit."""
    if report_test_type(report) != "sql" or judged["verdict"] == "VERIFIED":
        return
    for sha in (judged.get("post_sha"), judged.get("pre_sha")):
        if not sha:
            continue
        diffs = find_artifacts(report, sha, "answer_diff")
        if diffs:
            print("\n--- answer_diff (%s) ---" % sha[:7])
            print(bt_get_text("/api/log/%s/tests/%s" % (task_id, diffs[0]))[:4000])
            break
```

(b) Replace `_submit` to branch on `test_type`:

```python
def _submit(script_text, entry_abs, commits, args, yes, test_type):
    if test_type == "sql":
        answer_path = getattr(args, "answer", None) or resolve_answer_path(entry_abs)
        try:
            answer_text = _load_script(answer_path)
        except (IOError, OSError):
            sys.exit("no answer file at %s — derive it first: verify_testcase.py "
                     "derive-answer --test-type sql --script %s (--engine-pr/--issue/--post)"
                     % (answer_path, entry_abs))
        req = build_sql_request(script_text, answer_text, commits, worker_ips(),
                                run_mode=args.run_mode, min_runs=args.min_runs,
                                max_runs=args.max_runs, build_type=args.build_type)
    else:
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
```

(c) Update `cmd_submit`, `cmd_run`, `cmd_judge` to resolve/thread `test_type` and show the SQL diff:

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

(d) In `_add_run_args`, change the run-count defaults to `None` and add `--test-type`/`--answer`:

Find:
```python
def _add_run_args(p):
    p.add_argument("--run-mode", default="fixed-runs")
    p.add_argument("--min-runs", type=int, default=2)
    p.add_argument("--max-runs", type=int, default=2)
    p.add_argument("--build-type", default="debug")
```
Replace with:
```python
def _add_run_args(p):
    p.add_argument("--run-mode", default="fixed-runs")
    p.add_argument("--min-runs", type=int, default=None)
    p.add_argument("--max-runs", type=int, default=None)
    p.add_argument("--build-type", default="debug")
    p.add_argument("--test-type", choices=["shell", "sql"], default=None,
                   help="default shell; inferred sql from a .sql --script")
    p.add_argument("--answer", default=None,
                   help="SQL only: answer file (default: sibling answers/<name>.answer)")
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS — SQL submit dry-run prints `"testType": "sql"` + `customSqlAnswer`, hermetic (no network); missing-answer errors with a `derive-answer` hint. Shell dry-run test (`TestCliDryRun`) still passes (shell path unchanged; `resolve_runs` gives it 2/2).

Also confirm shell run defaults unchanged:
Run: `python3 cubrid-testcase-creation-common/scripts/verify_testcase.py submit --script /tmp/x.sh --pre A --post B 2>&1 | grep -E '"minRuns"|customShellScript'` — expected `"minRuns": 2` (create `/tmp/x.sh` with `echo hi` first, or ignore if it errors on missing file — the point is the shell default path).

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: CLI SQL mode for submit/run/judge (--test-type/--answer, 1/1 default, diff on fail)"
```

---

## Task 3: SQL answer derivation (`derive-answer --test-type sql`)

**Files:**
- Modify: `cubrid-testcase-creation-common/scripts/verify_testcase.py`
- Test: `cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py`

**Interfaces:**
- Consumes: Task 1 helpers (`build_sql_request`, `resolve_answer_path`, `has_queryplan_sidecar`, `find_artifacts`), `_wait`, `_post_build`, `bt_get_text`, `results_by_commit`, `_lookup`.
- Produces: `_derive_answer_sql(args)`; `cmd_derive_answer` routes by `test_type_of(args)` to it or the renamed existing `_derive_answer_shell(args)`. `derive-answer` parser gains `--test-type`, `--answer`.

- [ ] **Step 1: Write the failing test** — append (dry-run + sidecar guard, no network):

```python
class TestDeriveAnswerSqlDryRun(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        cases = os.path.join(self.d, "cases"); os.makedirs(cases)
        self.sql = os.path.join(cases, "cbrd_1.sql")
        with open(self.sql, "w") as fh:
            fh.write("select 1;\n")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_dry_run_shows_placeholder_submit(self):
        env = dict(os.environ); env["BUILDER_TESTER_URL"] = "http://127.0.0.1:1"
        vt_path = os.path.join(os.path.dirname(__file__), "..", "verify_testcase.py")
        out = subprocess.run(
            [sys.executable, vt_path, "derive-answer", "--test-type", "sql",
             "--script", self.sql, "--post", "BBB"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        text = out.stdout.decode("utf-8")
        self.assertEqual(out.returncode, 0, text)
        self.assertIn("[dry-run]", text)
        self.assertIn('"testType": "sql"', text)

    def test_queryplan_sidecar_blocks_derivation(self):
        open(os.path.join(self.d, "cases", "cbrd_1.queryPlan"), "w").close()
        env = dict(os.environ); env["BUILDER_TESTER_URL"] = "http://127.0.0.1:1"
        vt_path = os.path.join(os.path.dirname(__file__), "..", "verify_testcase.py")
        out = subprocess.run(
            [sys.executable, vt_path, "derive-answer", "--test-type", "sql",
             "--script", self.sql, "--post", "BBB"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("queryPlan", out.stdout.decode("utf-8"))
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: FAIL — `derive-answer` has no `--test-type`; current path assumes shell (`has_compare_calls`).

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
    arts = find_artifacts(report, post, "actual_result")
    if not arts:
        by = results_by_commit(report)
        st = (_lookup(by, post).get("attempts") or ["<none>"])[0]
        sys.exit("no actual_result artifact for %s (status=%s) — a syntax error/timeout in "
                 "the draft gives execution_error with no artifact, and a placeholder that "
                 "somehow matched gives pass. Fix the draft and retry. Inspect report %s"
                 % (post[:7], st, task_id))
    content = bt_get_text("/api/log/%s/tests/%s" % (task_id, arts[0]))
    if not content:
        sys.exit("actual_result artifact %s was empty; inspect report %s" % (arts[0], task_id))
    answers_dir = os.path.dirname(answer_path)
    if answers_dir and not os.path.isdir(answers_dir):
        os.makedirs(answers_dir)
    with open(answer_path, "w", encoding="utf-8") as fh:
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

(c) Extend the `derive-answer` subparser (in `main`) with `--test-type` and `--answer`:

Find the `pd = sub.add_parser("derive-answer")` block and add, after `pd.add_argument("--post")`:
```python
    pd.add_argument("--test-type", choices=["shell", "sql"], default=None,
                    help="default shell; inferred sql from a .sql --script")
    pd.add_argument("--answer", default=None,
                    help="SQL only: answer file to write (default: sibling answers/<name>.answer)")
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v`
Expected: PASS — SQL derive dry-run prints the placeholder-answer submit; the `.queryPlan` sidecar guard errors before any submit. Shell `derive-answer` path unchanged (existing shell derive still routes to `_derive_answer_shell`).

- [ ] **Step 5: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/scripts/verify_testcase.py \
        cubrid-testcase-creation-common/scripts/tests/test_builder_tester.py
git commit -m "verify: SQL answer derivation via actual_result artifact (+ queryPlan guard)"
```

---

## Task 4: Reference doc — SQL section in `builder-tester-verification.md`

**Files:**
- Modify: `cubrid-testcase-creation-common/references/builder-tester-verification.md`

- [ ] **Step 1: Fix the opening** — replace the first paragraph:

Find:
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
throughout; the SQL differences are collected in "SQL test cases" below.
```

- [ ] **Step 2: Append the SQL section** at the end of the file:

```markdown
## SQL test cases (`--test-type sql`)

SQL cases run through the Builder-Tester **custom SQL** API (CTP develop +
PR #757, fresh per-case Docker container). The case `.sql` travels inline —
no repo branch needed — so a drafted case verifies before any push, exactly
like shell custom-script mode.

- `submit`/`run --script cases/<name>.sql [--answer PATH]` — the `.sql`
  content is `customSqlScript`; the answer is `customSqlAnswer`, read from
  `--answer` or the sibling `answers/<name>.answer`. The answer must be
  non-empty (the builder 400s otherwise) and byte-exact from a real run —
  derive it, never hand-write it. Defaults: `buildType=debug`,
  `runMode=fixed-runs 1/1` (a fresh container per case already de-flakes).
- `derive-answer --test-type sql --script cases/<name>.sql (--engine-pr REF |
  --issue KEY | --post SHA)` — submits the case post-only with a placeholder
  answer, reads the resulting `actual_result` failure artifact (the real
  output), writes it to the sibling `answers/<name>.answer`, and prints it
  for approval. On `execution_error`/`pass`/no artifact it stops with a clear
  message — fix the draft (e.g. a syntax error surfaces as `execution_error`
  with no artifact) and retry.
- Verdict semantics, commit-pair resolution, `_wait`, exit codes, and the
  copy-ready `Verified:` line are identical to shell. SQL statuses
  `execution_error`/`environment_error`/`build_error` are non-pass/fail →
  INCONCLUSIVE. On a non-VERIFIED SQL run the block also prints the failing
  commit's `answer_diff` artifact so the mismatch is self-explanatory.
- `run_sql.sh` exit code is always 0; verdicts are parsed — never inferred.

**Artifacts** (custom mode, `testName = custom_sql_case`), fetchable at
`GET /api/log/<requestId>/tests/<filename>`:
`answer_diff` (unified diff), `actual_result` (real output), `expected_answer`
(the answer compared against), `case_source`, `warm_console`, `core_list`.
Artifact entries carry `artifactType` and no `status`, so they are excluded
from attempt counting and from the verdict block's log lines.

**`.queryPlan` limitation.** Custom SQL mode has no channel for a `.queryPlan`
sidecar. For a case with a sibling `<name>.queryPlan`, remote derivation is
refused and remote verification is skipped (the derived answer would lack
plan output); route those to the local-CTP or handoff rung.

**Answer variants.** `.answer_cci` / `.answer_WIN` cannot be derived remotely
(single execution env); note as reduced-evidence when a case needs them.

**Post-merge regression (manual).** The repo-path form (`tests[]` +
`testType:"sql"` + optional `sqlTcBranch`) resolves against the tester's
`sql_tc_dir` clone, which tracks **upstream CUBRID/cubrid-testcases only** —
fork branches are invisible. Use it by hand for post-merge regression; it is
not wired into the skills.
```

- [ ] **Step 3: Verify**

Run: `grep -c "test-type sql\|custom_sql_case\|queryPlan limitation\|derive-answer --test-type sql" cubrid-testcase-creation-common/references/builder-tester-verification.md`
Expected: nonzero.

- [ ] **Step 4: Commit**

```bash
cd ~/worktrees/skills-main
git add cubrid-testcase-creation-common/references/builder-tester-verification.md
git commit -m "verify: document SQL custom-mode verification + derivation"
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

In `## Path resolution`, change the `$COMMON` bullet to add `verify_testcase.py` and a `$BT` line. Find:
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

- [ ] **Step 2: Replace step 7** — find the current step 7 (the `Local answers (only if CUBRID_TC_ALLOW_LOCAL_CTP=1)` block) and replace with the three-rung ladder:

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
        confirmation). VERIFIED → proceed. NOT-VERIFIED/FLAKY → diagnose
        (the printed `answer_diff` helps) and fix, re-entering steps 5–6; do
        not push a case that fails to reproduce or is flaky. INCONCLUSIVE →
        builder/env issue; report and fall to rung b/c. `--special-case`
        applies as for shell.
      Files WITH a `.queryPlan` sidecar cannot be derived/verified in custom
      mode (no sidecar channel) — leave their answers empty and route them to
      rung b/c, noting it in the render. Fold each verdict block into the
      render (step 8) and the PR body. All non-sidecar files must be VERIFIED
      before the push.
   b. **Local CTP** — only if `CUBRID_TC_ALLOW_LOCAL_CTP=1`: follow
      `$COMMON/references/verify-procedure.md` (SQL section): seed → run →
      promote `.result` → re-run `Success:1`; fold real answers into the
      package; re-run the gate once.
   c. **Printed handoff** — neither reachable: seed empty answers, print the
      verify handoff from `two-phase-protocol.md`, and STOP (Phase 2 resumes
      with supplied answers).
```

- [ ] **Step 3: Update Phase 2 intake** — in Phase 2 step 1 (`Intake`), append one sentence:

Find the end of the `1. **Intake.**` paragraph and add:
```markdown
   Answers already derived on the remote rung are byte-exact from a real run
   (no re-validation needed beyond confirming the approved content landed);
   apply the full semantic validation only to hand-supplied answers.
```

- [ ] **Step 4: Verify**

Run:
```bash
grep -n "Runtime verification + answer generation\|derive-answer --test-type sql\|run --test-type sql\|\$BT" create-cubrid-sql-testcase/SKILL.md
grep -c "shell only\|shell cases only" create-cubrid-sql-testcase/SKILL.md
python3 -c "import io; io.open('create-cubrid-sql-testcase/SKILL.md',encoding='utf-8').read(); print('ok')"
```
Expected: matches for the ladder terms; `0` for the deleted shell-only note; `ok`.

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

Findings from the 2026-07 spot-check (N=15 recent cubrid-testcases SQL cases) + `sql_guide.md` develop. All additions are marked as current-format observations.

- [ ] **Step 1: Header block rule** — replace the `## File structure` first bullet:

Find:
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

- [ ] **Step 2: evaluate-label rule** — replace the `evaluate 'Case N:'` bullet:

Find:
```markdown
- `evaluate 'Case N: description';` before each scenario, numbered
  sequentially, captions truthful. 3–10 scenarios per file is the norm.
```
Replace with:
```markdown
- Label each scenario with `evaluate '<label>';` before it, numbered
  sequentially, captions truthful (they land in the `.answer` for traceability).
  The label wording is not standardized — recent cases use `[TEST N] <desc>`
  or `[N] <desc>` as often as `Case N:`; any consistent, descriptive scheme is
  fine. 3–10 scenarios per file is the norm.
```

- [ ] **Step 3: Cleanup / DROP rule** — replace the shared-database bullet:

Find:
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
  PARAMETERS` to its original value. `DROP ... IF EXISTS` is required at
  CREATE time (re-run safety); end-of-file cleanup DROPs need NOT be
  `IF EXISTS` (bare `DROP TABLE t;` is the dominant real pattern). A
  fully-symmetric IF-EXISTS teardown is optional best practice for suites
  likely to be re-run after a mid-file failure.
```

- [ ] **Step 4: Plan-test rule** — replace the plan-tests bullet under `## Determinism by construction`:

Find:
```markdown
- Plan tests: pin the plan — hints (`NO_ELIMINATE_JOIN`, `ORDERED`,
  `MATERIALIZE`, `/*+ recompile */`) where needed; `UPDATE STATISTICS ON
  <tables>` scoped to the tables under test, never `all classes`.
```
Replace with:
```markdown
- Plan tests: create an EMPTY `cases/<name>.queryPlan` sidecar
  (case-sensitive extension) to make CTP emit the query plan into the result
  — this is the house convention; do NOT use the inline `--@queryplan`
  directive for new drafts. Pin the plan with hints (`NO_ELIMINATE_JOIN`,
  `ORDERED`, `MATERIALIZE`, `/*+ recompile */`) where needed; scope
  `UPDATE STATISTICS ON <tables>` to the tables under test, never
  `all classes`. Note: a `.queryPlan` case cannot be verified via remote
  Builder-Tester (no sidecar channel — see builder-tester-verification.md);
  generate/verify its answer on a local CTP host.
```

- [ ] **Step 5: Answer-variants + error-case notes** — under `## Error cases`, after the existing bullets add:

```markdown
- Answer variants are opt-in, created only on a real divergence and kept in
  sync thereafter: `answers/<name>.answer_cci` (CCI output differs — rare,
  seen mainly in older plan/trace cases) and `.answer_WIN` (Windows differs —
  effectively unused in recent cases). Do not add them speculatively.
- For files with several negative cases, a recommended enhancement (seen in
  recent `_36_guava` cases) is a defensive `SELECT COUNT(*)` catalog/state
  sanity-check after each error, using a distinct object name per negative
  case, so a masked failure can't pass silently.
```

- [ ] **Step 6: Naming rule** — replace the package-shape naming bullet:

Find:
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

- [ ] **Step 1: two-phase-protocol.md** — replace the SQL-exclusion sentence (verified present verbatim at line 42). Find:
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

- [ ] **Step 2: verify-procedure.md** — after the existing shell-prefer note (lines 9–13), add a SQL analog:

```markdown
> For SQL cases, prefer remote Builder-Tester verification too
> (`builder-tester-verification.md`, `--test-type sql`) — it derives the
> `.answer` from a real run and proves pre-fix fail / post-fix pass without a
> local CTP install. Use the local SQL runbook below only when the gateway is
> unreachable and `CUBRID_TC_ALLOW_LOCAL_CTP=1`, or for `.queryPlan`-sidecar
> cases (which custom SQL mode cannot verify).
```

- [ ] **Step 3: Verify**

Run: `grep -c "custom SQL\|--test-type sql" cubrid-testcase-creation-common/references/two-phase-protocol.md cubrid-testcase-creation-common/references/verify-procedure.md`
Expected: nonzero in both; both files still parse (`python3 -c "import io;[io.open(f,encoding='utf-8').read() for f in ['cubrid-testcase-creation-common/references/two-phase-protocol.md','cubrid-testcase-creation-common/references/verify-procedure.md']];print('ok')"`).

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

- [ ] **Step 1: Generalize the header** — find:
```markdown
### Optional: runtime verification of a shell TC PR (ask first)

For a shell test-case PR only, offer — never run unprompted — a remote
```
Replace with:
```markdown
### Optional: runtime verification of a shell or SQL TC PR (ask first)

For a shell or SQL test-case PR, offer — never run unprompted — a remote
```

- [ ] **Step 2: Generalize the invocation** — find (verified present verbatim at lines 149–152):
```markdown
then run against the PR head's entry script and the issue's engine PR:

`python3 $COMMON/scripts/verify_testcase.py run --script <fetched entry.sh>
--engine-pr <engine ref>` (dry-run first, `--yes` after the user confirms).
```
Replace with:
```markdown
then run against the PR head's entry file and the issue's engine PR:

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

Run: `grep -c "run --test-type sql\|SQL TC PR" review-cubrid-testcase-pr/SKILL.md`; expected nonzero. `python3 -c "import io; io.open('review-cubrid-testcase-pr/SKILL.md',encoding='utf-8').read(); print('ok')"`.

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

- [ ] **Step 1: Extend `live_check.sh`** — after the existing reports/attempt-log block, add a SQL-report probe. Append inside the existing Python heredoc (or add a second one) — add this block before the final `PY` of the reports check, adapting to the current file; the intent: find a `testType == "sql"` report and fetch one of its artifacts.

Add this second heredoc after the existing one in `live_check.sh`:
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
        if a.get("logFileName"):
            txt = btlib.bt_get_text("/api/log/%s/tests/%s" % (sqlrep["id"], a["logFileName"]))
            assert txt is not None, "empty artifact"
            print("sql artifact OK: %s (%d bytes)" % (a["logFileName"], len(txt)))
            sys.exit(0)
print("SQL report has no fetchable artifact (ok)")
PY
```

- [ ] **Step 2: Run the live check (informational)**

Run: `bash cubrid-testcase-creation-common/scripts/tests/live_check.sh`
Expected (gateway up): the existing health/report/attempt-log lines plus `sql report: <id>` and `sql artifact OK: …`. Gateway down → `UNREACHABLE` exit 1 (valid environment state, not a code failure).

- [ ] **Step 3: Write the calibration runbook** — create `docs/superpowers/plans/2026-07-22-sql-calibration.md`:

```markdown
# SQL verification calibration (manual, gated)

End-to-end proof of `verify_testcase.py --test-type sql` against an
already-merged SQL TC — ground-truth check for the derivation path. Consumes
builder capacity; run once with user confirmation.

## Inputs
- An already-merged SQL TC with a known engine pair, e.g. CBRD-26900
  (engine PR CUBRID/cubrid#7269). Fetch the case `.sql` and its committed
  `answers/<name>.answer` from CUBRID/cubrid-testcases into a scratch dir
  (`fetch_context.py get`).

## Steps
1. **Derivation ground-truth:** `verify_testcase.py derive-answer --test-type
   sql --script <scratch>/cases/<name>.sql --issue CBRD-26900` (dry-run, then
   `--yes`). The derived `answers/<name>.answer` must match the repo's
   committed answer (newline-level differences tolerated per the server's
   comparison rules; intra-line whitespace must match). A mismatch is a real
   finding — investigate before trusting derivation.
2. **Pre/post verify:** `verify_testcase.py run --test-type sql --script
   <scratch>/cases/<name>.sql --issue CBRD-26900` → expect **VERIFIED**
   (pre-fix answer mismatch/`fail`, post-fix `pass`). If the case is not a
   behavior-changing fix (answer identical pre/post) it will be NOT-VERIFIED —
   pick a TC whose answer actually changed with the fix.

## Record
Capture the verdict block + report id. This validates SQL request assembly,
artifact-based derivation, and the shared verdict path against ground truth.
```

- [ ] **Step 4: Commit**

```bash
cd ~/worktrees/skills-main
chmod +x cubrid-testcase-creation-common/scripts/tests/live_check.sh
git add cubrid-testcase-creation-common/scripts/tests/live_check.sh \
        docs/superpowers/plans/2026-07-22-sql-calibration.md
git commit -m "verify: live SQL-report check + SQL calibration runbook"
```

---

## Final verification (after all tasks)

- [ ] **Full unit suite**: `python3 -m unittest discover -s cubrid-testcase-creation-common/scripts/tests -v` — all pass.
- [ ] **No bytecode staged**: `git status --porcelain | grep -E "\.pyc|__pycache__" || echo clean`.
- [ ] **`--help` shows the new flags**: `python3 cubrid-testcase-creation-common/scripts/verify_testcase.py submit --help | grep -E "test-type|answer"`.
- [ ] **No watermark**: `base=$(git merge-base main HEAD); git log --format='%an %s' "$base"..HEAD | grep -iE "claude|anthropic|co-authored|🤖" && echo WATERMARK || echo clean`.
