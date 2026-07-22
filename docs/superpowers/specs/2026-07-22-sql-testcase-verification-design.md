# SQL test-case creation — Builder-Tester verification design

Date: 2026-07-22
Status: approved design, pre-implementation
Scope: `cubrid-testcase-creation-common`, `create-cubrid-sql-testcase`,
`review-cubrid-testcase-pr` (docs only)

## 1. Purpose

Bring the SQL TC creator to the same production grade as the shell one.
Three gaps close:

1. **Remote verification + answer derivation.** The Builder-Tester now
   executes SQL cases (CTP develop + PR #757 in Docker) and accepts a
   **custom SQL case inline** (`customSqlScript` + `customSqlAnswer`) — no
   repo branch needed. A drafted case can therefore be verified pre-push
   (pre-fix build fails, post-fix passes) and its `.answer` derived from a
   real post-fix run via the `actual_result` failure artifact — removing
   the human CTP handoff for most SQL TCs, exactly as `verify_testcase.py`
   did for shell.
2. **Authoring doctrine alignment** (light pass): fold the official
   `cubrid-testtools/doc/sql_guide.md` specifics and a ~15-case spot-check
   of recently added `cubrid-testcases` SQL cases into
   `references/sql-authoring.md`.
3. The skill's "Builder-Tester is shell-only" note is obsolete — replaced
   by the same three-rung verification ladder the shell skill has.

This host still never executes tests/CTP/csql/cubrid locally; everything
runs over HTTP against the report-server gateway.

## 2. Server contract (SQL additions; verified live 2026-07-22)

Same gateway, lifecycle, and endpoints as shell (`POST /api/builder/build`,
`GET /api/builder/status[?taskId=]`, `GET /api/reports`,
`GET /api/log/:req_id/tests/:filename`). Live server confirmed running SQL
requests (`testType: "sql"` visible in `/api/reports` items).

**Custom SQL request** (the mode this design uses — operator-verified
end-to-end, wrong-answer → correct diff + artifacts):

```json
{
  "commits": ["<pre_sha>", "<post_sha>"],
  "testType": "sql",
  "customSqlScript": "<case .sql content>",
  "customSqlAnswer": "<expected output, CTP answer format>",
  "buildType": "debug",
  "runMode": "fixed-runs", "minRuns": 1, "maxRuns": 1,
  "commitBuildMode": "checkout",
  "workerIps": ["192.168.2.154:8090"],
  "callbackUrl": "http://192.168.2.154:8091/callback"
}
```

Field rules that drive the design:

- `testType: "sql"` is REQUIRED with `customSqlScript` (else 400).
- `customSqlAnswer` is REQUIRED and non-empty (else 400 — no verdict is
  possible without it). Newline differences are ignored in comparison;
  **intra-line whitespace matters** — answers must come from a real run,
  never hand-formatted.
- No `tests[]` (a `custom_script_test` placeholder is inserted; if sent it
  is ignored). `customShellScript`/`customScriptTestPath`/
  `customAttachments` are shell-only and rejected in SQL mode — so there
  is **no channel for a `.queryPlan` sidecar or extra files**.
- Runs in a **fresh per-case container always** (never a warm pool agent),
  once per commit in `commits[]`.
- CTP directives inside the script (`--+ holdcas on`, …) are honored.

**Statuses:** same enum as shell. SQL meanings: `fail` = ran, output
differed from the answer ([NOK]; message notes a core file if produced);
`execution_error` = missing/empty answer, per-case timeout, or no
[OK]/[NOK] verdict; `environment_error` = provisioning/Docker/CTP-payload
failure. Exit code of `run_sql.sh` is always 0 — verdicts are parsed, never
inferred from exit codes (server-side concern, documented for operators).

**Artifacts** (per commit × attempt, `testName = custom_sql_case`), in
`attemptLogMetadata[]`: plain attempt logs are `{attempt, logFileName,
status}`; artifact entries add `artifactType` (and carry NO `status` — so
attempt counting by `status`-bearing entries is already correct in
`results_by_commit`, verified against a live SQL report):

| artifactType | file | when |
|---|---|---|
| (attempt log) | `sql_<c7>_custom_sql_case[.N].log` | always |
| `answer_diff` | `sql_diff_<c7>_custom_sql_case[.N].diff` | on failure |
| `actual_result` | `sql_actual_<c7>_custom_sql_case[.N].result` | on failure |
| `expected_answer` | `sql_expected_<c7>_custom_sql_case[.N].answer` | on failure |
| `case_source` | `sql_case_<c7>_custom_sql_case.sql` | attempt 1 |
| `warm_console` / `core_list` | … | warm-overrule / crash |

All fetchable as text via `GET /api/log/<requestId>/tests/<filename>`.

**Answer derivation protocol** (operator-documented): submit once with any
placeholder answer → read the produced `actual_result` artifact (the real
output) → resubmit with it as `customSqlAnswer`.

**Repo-path form** (`tests[]` + `sqlTcBranch`): resolves against the
tester's `sql_tc_dir` clone, which tracks **upstream
CUBRID/cubrid-testcases only** — fork branches (`cbrd_NNNNN_tc`) are
invisible, so this form is post-merge regression only; documented, not
wired.

## 3. Approaches considered

- **A. Extend `verify_testcase.py` with a SQL mode — CHOSEN.** One tool,
  both test types; the hardened lifecycle (`_wait`/`_pending`/
  `status_phase`) and the verdict matrix (`judge_matrix`) are reused
  unchanged — same endpoints, same status enum (`execution_error`/
  `environment_error`/`build_error` are non-pass/fail and already route to
  INCONCLUSIVE via the infra handling). Only request assembly, artifact
  location/fetch, and answer write-back are new.
- **B. Separate `verify_sql_testcase.py`** — rejected: duplicates the
  wait/judge code for no boundary benefit.
- **C. Verify via `sqlTcBranch` after pushing the fork branch** — rejected
  as primary: fork branches are invisible to the upstream-only clone.
  Post-merge regression form only.

## 4. `verify_testcase.py` SQL mode

New `--test-type {shell,sql}` on `submit`, `run`, `judge`, and
`derive-answer`; default `shell`; **inferred `sql` when `--script` ends in
`.sql`** (explicit flag always wins). Python 3.6 stdlib, dry-run by
default, `--yes` to submit — all unchanged.

### Request assembly (new pure helper)

`build_sql_request(script_text, answer_text, commits, worker_ip_list, …)`
→ the §2 payload. Defaults for SQL: **`buildType=debug`** (same as shell;
`--build-type` overrides), **`runMode=fixed-runs, minRuns=1, maxRuns=1`**
(fresh-container-per-case already de-flakes; `--min-runs/--max-runs`
override). Raises `ValueError` if `answer_text` is empty (mirrors the
server's 400 locally).

### `submit` / `run` (SQL)

- `--script <cases/name.sql>` — case content becomes `customSqlScript`.
- `--answer <path>` — answer content becomes `customSqlAnswer`; defaults to
  the sibling `answers/<name>.answer` resolved from the script path (a
  script in `…/cases/` looks in `…/answers/`; otherwise alongside).
  Missing/empty answer → clear error pointing at `derive-answer`.
- Commit pair, dry-run elision, `_wait`, and `judge_matrix` are the shared
  code paths. Pre-fix `fail` + post-fix `pass` ⇒ VERIFIED; `--special-case`
  semantics unchanged.
- On NOT-VERIFIED (e.g. pre-fix passed) or post-fix `fail`, the verdict
  block additionally fetches and prints the post-fix (or offending)
  **`answer_diff`** artifact so the mismatch is self-explanatory.

### `derive-answer` (SQL)

1. Submit **post-fix only** with `customSqlAnswer = "PLACEHOLDER\n"`.
2. Expect status `fail`; locate the `actual_result` artifact for the
   post-fix commit **by `artifactType`** (never by filename convention).
   Any other status — `pass` against the placeholder (impossible output),
   `execution_error` (e.g. a syntax error or timeout in the draft itself;
   produces no `actual_result`), `environment_error` — or a missing
   artifact → clear error naming the status; fix the draft first.
3. Fetch it, print the FULL content for human approval (the standing rule:
   `.answer` is never hand-written, and a human confirms it matches the
   JIRA to-be behavior before use).
4. Write to the sibling `answers/<name>.answer` (creating `answers/` if
   needed) — byte-exact from the run, satisfying the whitespace-exactness
   requirement by construction.

### Artifact helpers (new, pure + fetch)

- `find_artifacts(report, commit_sha, artifact_type) -> [logFileName]` —
  prefix-tolerant commit match, filters `attemptLogMetadata` entries by
  `artifactType`.
- Verdict-block `logs` lines exclude artifact entries (attempt logs only);
  artifacts get their own lines when fetched.

### Multi-file packages

One case per request (server contract). The tool stays single-case; the
**skill loops** over the package's `.sql` files for both `derive-answer`
and `run`, and requires ALL files VERIFIED. Builds are cached after the
first request, so the loop cost is per-case runtime only.

## 5. Verdict semantics (unchanged, SQL-mapped)

VERIFIED ⇔ post-fix all attempts `pass` AND pre-fix ≥1 attempt `fail`.
`execution_error`/`environment_error`/`build_error` are non-pass/fail →
INCONCLUSIVE (environment/tooling, never a product/test verdict) — for
SQL this correctly covers missing-answer, timeout, and provisioning
failures. FLAKY on mixed post-fix attempts. `--special-case` waives only
the pre-fix half. Exit codes 0/2/3/4/1 unchanged.

## 6. `.queryPlan` sidecar rule (design consequence)

House convention (user-confirmed): plan tests use an **empty
`cases/<name>.queryPlan` sidecar** to make CTP emit plan output into the
result/answer — NOT the inline `--@queryplan` directive. Custom SQL mode
has no sidecar channel, so for any file with a `.queryPlan` sidecar:

- Remote **answer derivation is not applicable** (the derived answer would
  lack plan output and must not be committed).
- Remote pre/post verification is skipped for that file (comparing without
  plan output would be misleading); it routes to the local-CTP or handoff
  rung, stated explicitly in the render.
- Non-sidecar files in the same package still use the remote rung.

## 7. Skill flow (`create-cubrid-sql-testcase`)

- Delete the "Builder-Tester … shell only" note.
- Step 7 becomes the shell-style three-rung ladder:
  a. **Remote Builder-Tester (custom SQL)** — `verify_testcase.py health`
     reachable. Per package `.sql` file (excluding `.queryPlan`-sidecar
     files, §6): `derive-answer` (dry-run → `--yes` on confirmation →
     human approves the printed answer) → gate re-run over the now-real
     answers → `run` pre/post per file (all VERIFIED required; announce
     capacity use; `--yes` gated). Verdict blocks fold into the render and
     PR body. NOT-VERIFIED/FLAKY → diagnose, fix, re-enter the gate; do
     not push. INCONCLUSIVE → builder/env issue; fall to rung b/c.
  b. **Local CTP** — `CUBRID_TC_ALLOW_LOCAL_CTP=1`, per
     `verify-procedure.md` (SQL section), unchanged.
  c. **Printed handoff** — unchanged two-phase behavior.
- On the remote rung, Phase 1 completes in one sitting (real answers +
  verification before the push gate); the push carries real answers and
  the PR follows immediately. Phase 2 remains for rungs b/c (empty-answer
  push → handoff → answer intake), unchanged.
- Phase-2 intake validation gains one line: remotely derived answers are
  already byte-exact from a run; hand-supplied answers keep the existing
  semantic validation.

## 8. Authoring doc — light alignment pass

`references/sql-authoring.md` additions (distilled from `sql_guide.md`
develop + a ~15-case spot-check of recently added SQL cases in
`cubrid-testcases` for current-format confirmation; no counted-evidence
corpus treatment):

- Plan tests: empty `cases/<name>.queryPlan` sidecar is the convention
  (case-sensitive extension; already present — reaffirmed, with the §6
  remote-verification consequence noted for the drafter).
- Answer variants and their sync rule: `answers/<name>.answer_cci` (CCI
  divergence) and `.answer_WIN` (Windows divergence) — created only when a
  real divergence exists, kept in sync with the base answer thereafter;
  not derivable remotely (reduced-evidence note when applicable).
- Don't overload one file: split many-query scenarios into several case
  files (failure triage readability); avoid time-consuming queries.
- Bug-fix naming: `cbrd_xxxxx.sql`, `_1`, `_2`, `_{keyword}` (e.g.
  `_xasl`) suffixes sharing one `cases/`+`answers/` pair.
- Whatever the spot-check confirms as current norm (header style,
  `evaluate 'Case N:'` usage) — folded with a "confirmed against recent
  cases, 2026-07" note.

Explicitly NOT added (user decision): `autocommit off;` guidance; inline
`--@queryplan` preference.

## 9. Reference/docs updates

- `builder-tester-verification.md`: new "SQL test cases" section — custom
  contract (§2), defaults (debug, 1/1), artifact table, derivation
  protocol, `.queryPlan` limitation, statuses + exit-code caveat, and the
  post-merge `tests[]`/`sqlTcBranch` manual form.
- `two-phase-protocol.md` / `verify-procedure.md`: "SQL cases have no
  remote option" statements replaced with the custom-SQL rung + pointers.
- `review-cubrid-testcase-pr` optional-verification step: extended to
  offer SQL TC PRs the same ask-first check (PR head's `.sql` + committed
  `.answer` as `customSqlAnswer` — no derivation needed for review, the
  answer is in the PR). The §6 sidecar exclusion applies here too: files
  with a `.queryPlan` sidecar are skipped with a note.

## 10. Safety, degradation

Unchanged posture: dry-run by default, `--yes` gates every submission
(announced — shared capacity); no secrets in payloads; report/log
responses parsed as data, never executed; unreachable gateway degrades to
the next rung with a message; never blocks the creation flow. Derived
answers always pass a human approval gate before entering the package.

## 11. Testing

- **Unit** (pure, no network): `build_sql_request` (field shape, debug/1-1
  defaults, empty-answer ValueError, no `tests[]`), answer-path resolution
  (`cases/` → `answers/` sibling; non-standard layout fallback),
  `find_artifacts` selection by type + commit (incl. artifact entries
  never counted as attempts), `.queryPlan`-sidecar detection.
- **Live read-only**: extend `live_check.sh` — find a `testType: "sql"`
  report, fetch one artifact, assert non-empty.
- **Calibration** (gated, consumes capacity): take an already-merged SQL
  TC with a known engine pair (e.g. CBRD-26900 / CUBRID/cubrid#7269):
  (1) `derive-answer` against the post-fix commit must produce an answer
  that **matches the repo's committed `.answer`** (ground-truth check for
  the derivation path; newline-level differences tolerated per server
  comparison rules); (2) `run` pre/post must yield VERIFIED. Discharges
  end-to-end proof without inventing a TC.

## 12. Out of scope

- `medium/`, `isolation/`, CCI-interface runs; `.answer_cci`/`.answer_WIN`
  remote derivation (server limitation).
- Warm-pool tuning, CTP provenance pinning (`ctp_sql_*`) — operator
  config.
- Wiring the post-merge `tests[]` form into any skill (documented manual
  form only).
- Builder-Tester server-side changes; we integrate against the deployed
  contract as operator-verified.
