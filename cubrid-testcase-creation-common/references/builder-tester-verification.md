# Builder-Tester verification (shared reference)

Remote build+run verification for **shell and SQL** test cases.
`verify_testcase.py` submits a drafted case in custom mode, builds a pre-fix
and a post-fix engine commit, and judges whether the test reproduces the bug
pre-fix and passes post-fix. Test type is `--test-type shell|sql` (default
shell; inferred `sql` from a `.sql --script`). The shell path is documented
throughout; the SQL differences are in "SQL test cases" below.

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
