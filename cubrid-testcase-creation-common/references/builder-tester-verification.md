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
