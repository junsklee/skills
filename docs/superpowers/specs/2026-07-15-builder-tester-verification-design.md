# Builder-Tester verification integration — design

Date: 2026-07-15
Status: approved design, pre-implementation
Scope: `cubrid-testcase-creation-common`, `create-cubrid-shell-testcase`,
`review-cubrid-testcase-pr`

## 1. Purpose

Freshly drafted shell test cases currently leave this host unverified: the
two-phase protocol hands a verify procedure to a human on a CTP-capable
machine and waits for evidence. The Builder-Tester system (junsklee/
cubrid-testtools, branch `builder_tester_refactor_tester`, `CTP/builder_tester`)
can build arbitrary engine commits in Docker and run shell tests against
them. Its **custom-script mode** accepts the script content itself — no
testcase branch required — so a draft can be verified *before it is ever
pushed*: expected **NOK on the pre-fix build, OK on the post-fix build**
(special cases exempted). It can also **derive `.answer` files** from a real
post-fix run, closing the last gap that required the human handoff for
shell TCs.

SQL test cases are out of scope: Builder-Tester executes `shell/*` tests
only.

## 2. System under integration (facts)

Gateway: the report server, `BUILDER_TESTER_URL`
(default `http://192.168.2.154:8091`). Verified live 2026-07-15:
`/health` → v4.0.0 healthy; `/api/builder/health` → healthy,
`commitBuildMode=checkout`, `maxConcurrentBuilds=1`.

Endpoints used:

| Endpoint | Use |
|---|---|
| `POST /api/builder/build` | submit a build+test request → `{status, taskId}` |
| `GET /api/builder/status?taskId=` | poll progress (0 / 20 / 100 / −1) |
| `GET /api/reports` | paginated JSON: `items[]` with `id`, `commits`, `results[]`, `verdict` |
| `GET /api/log/:req_id/tests/:logFileName` | full traced stdout of one test attempt |

Request fields used (custom-script mode, `BuilderTask.java`):

- `commits: [<sha>, …]` — each commit is built and the test run against it.
- `customShellScript` — the entry-script content. When present and `tests[]`
  is omitted, the Builder injects the placeholder `tests: ["custom_script_test"]`
  itself ([Builder.java:780](.)).
- `customScriptTestPath` — **not sent.** Confirmed against source: the
  injected `custom_script_test` placeholder runs in a temp dir
  ([BuilderTask.java:1783-1793](.)) and does not consult
  `customScriptTestPath`; the field is only read when a caller supplies its
  own non-placeholder test path. Shell tests are location-independent (user-
  confirmed), so `verify_testcase.py` omits it entirely — one less field to
  keep correct, no auto-fill, no placement coupling.
- `customAttachments: [{targetPath, contentBase64}]` — strictly relative
  paths, placed next to the script. Carries every non-entry file in the
  staging package (`.c`/`.java` clients, helper scripts, data files,
  `.answer` files) so attachment-dependent tests run exactly as they will
  post-merge.
- `buildType` (default `debug`), `runMode`/`minRuns`/`maxRuns`
  (default `fixed-runs` 2/2), `callbackUrl`
  (default `<BUILDER_TESTER_URL>/callback` — this is how results land on
  the report server).

Report shape (verified live): `results[]` entries carry `test`, `commit`,
`status` (pass/fail), `attempts`, and `attemptLogMetadata[]`
(`logFileName`, `attempt`, `status`); log files are fetchable via the log
endpoint and contain the `sh -x`-traced full stdout of the run.

## 3. Approaches considered

- **A. Verify-before-push via custom-script mode — CHOSEN.**
  `customShellScript` ships the draft itself, so verification needs no
  branch: draft → self-review gate → submit → pre/post matrix → render
  with evidence → push → PR, in one sitting. The two-phase handoff
  collapses for shell TCs even on this dev host.
- **B. Verify-after-push via `tests[]` repo paths — rejected as primary.**
  `tests[]` resolves against the tester's `shell_tc_dir` checkout
  (`develop` of cubrid-testcases-private-ex); fork branches are invisible.
  Valid only as a post-merge regression form; documented, not built.
- **C. PR-number mode (`POST /api/builder/build/pr`) — documented
  alternative.** It resolves head + merge-base itself; we want explicit
  control of the pre/post pair, so we resolve SHAs ourselves and use
  standard `commits[]` mode.

## 4. Component: `cubrid-testcase-creation-common/scripts/verify_testcase.py`

Python 3.6 stdlib only, same conventions as its siblings (`ghlib.py`
reuse for GitHub calls; **dry-run by default, `--yes` to actually
submit**). Subcommands:

### `submit`
Assemble and POST the request:
- `--script <path>` — the entry `.sh` in the staging dir (content becomes
  `customShellScript`).
- `--package <dir>` — staging case dir; every other file under it becomes
  a `customAttachment` (base64, path relative to the case dir).
- `--pre <sha> --post <sha>` or `--issue CBRD-XXXXX` / `--engine-pr N`
  (resolution in §7) → `commits: [pre, post]`.
- `--post-only` — submit only the post-fix commit (used by
  `derive-answer`, and for special cases where pre-fix has no defined
  meaning, e.g. a new-feature TC).
- Defaults: `buildType=debug`, `runMode=fixed-runs`, `minRuns=2`,
  `maxRuns=2`, `callbackUrl=<BUILDER_TESTER_URL>/callback`. All
  overridable by flags.
- Dry-run prints the exact JSON payload (script/attachment content
  elided to name + size + sha256). `--yes` sends it and prints `taskId`.

### `wait`
`--task-id <id>`: poll `/api/builder/status` with backoff; bounded
timeout (default 3 h, `--timeout` to change). Progress messages mapped
from the status codes. Exit nonzero on builder error (−1) or timeout.

### `judge`
`--task-id <id>` (+ the same `--pre/--post` pair, `--special-case`):
fetch `/api/reports`, locate the report by id, evaluate §5, print a
verdict block:

```
VERDICT: VERIFIED | NOT-VERIFIED | FLAKY | INCONCLUSIVE
  pre-fix  <sha7>: attempt 1 fail, attempt 2 fail   (expected: fail)  ✓
  post-fix <sha7>: attempt 1 pass, attempt 2 pass   (expected: pass)  ✓
  logs: <BUILDER_TESTER_URL>/api/log/<req_id>/tests/<file>
```

The block is copy-ready for the rendered package and the PR body
(`Verified: pre-fix <sha7> → NOK / post-fix <sha7> → OK`).

### `run`
Convenience: `submit --yes` → `wait` → `judge` in one call (still gated
by `--yes`).

### `derive-answer`
See §6.

Config: `BUILDER_TESTER_URL` env var, default `http://192.168.2.154:8091`.
Unset/unreachable → the caller degrades per §9.

## 5. Verdict semantics

**VERIFIED** ⇔ post-fix commit: **all attempts pass** AND pre-fix commit:
**≥1 attempt fails**.

- Post-fix mixed attempts (some pass, some fail) → **FLAKY**, never
  VERIFIED. A flaky TC is a drafting defect to fix, not evidence.
- Pre-fix all-pass → **NOT-VERIFIED** (the TC does not reproduce the bug)
  unless `--special-case` applies.
- `--special-case core-dump|flaky-repro|feature` relaxes the pre-fix
  expectation to warn-only (reported as `pre-fix expectation waived:
  <reason>`): crash bugs may not reproduce deterministically in the
  Docker environment; probabilistic repros may need many runs; feature
  TCs have no meaningful pre-fix behavior. The post-fix all-pass
  requirement is never waived.
- Post-only runs (no pre-fix commit submitted): `judge` evaluates only
  the post-fix requirement and reports
  `pre-fix expectation waived: post-only run` — the same waiver wording
  as `--special-case`, so a verdict block always states explicitly when
  the reproduce-the-bug half was not checked.
- Builder/tester infrastructure failure (status −1, missing report,
  build error) → **INCONCLUSIVE** — classified as environment/tooling,
  never as a product or test verdict (matches the reviewer doctrine's
  failure-classification vocabulary).

## 6. Answer derivation (Builder-Tester in the creation loop)

For drafts that delegate their verdict to
`compare_result_between_files <log> <answer>` before any answer exists
(standing rule: `.answer` files are never hand-written):

1. **Capture transform** (mechanical, in `derive-answer`): each
   `compare_result_between_files <log> <answer>` call in the draft is
   replaced by a sentinel dump of its normalized log:
   `echo ANSWER_BEGIN_<n>; base64 <log>; echo ANSWER_END_<n>`.
   Base64 makes extraction immune to `sh -x` trace lines and non-ASCII
   content. Everything else in the script (setup, normalization such as
   `format_csql_output`, teardown) runs unchanged.
2. Submit the capture variant with `--post-only` (answers must encode
   *fixed* behavior).
3. After the run, fetch the attempt log, extract between sentinels,
   decode, and write `<answer>` into the staging package next to the
   `.sh`.
4. **Human gate: the derived answer content is shown to the user for
   approval before use.** It is machine-derived from a real run, but a
   wrong post-fix build would bake wrong expectations into the answer;
   a human confirms it matches the JIRA to-be behavior.
5. Full pre/post verification then runs with the approved answer as a
   `customAttachment`; the pre-fix build now NOKs via the compare diff.

## 7. Commit-pair resolution

Helper in `verify_testcase.py`, using the existing GitHub-API plumbing:

- `--engine-pr N` (CUBRID/cubrid): merged PR → `pre = merge_commit^`,
  `post = merge_commit`; open PR → `pre = merge-base(develop, head)`,
  `post = head`.
- `--issue CBRD-XXXXX`: search CUBRID/cubrid PRs whose title contains the
  key, then as above. Multiple matches → list them and require
  `--engine-pr`.
- Explicit `--pre/--post` always wins.
- The resolved pair is always echoed (SHA + subject line) before
  submission so the user sees exactly what will be built.

## 8. Wiring into the skills

**`create-cubrid-shell-testcase`** — step 7 becomes a three-way ladder:

1. `BUILDER_TESTER_URL` reachable → remote verification **before the
   push gate**: (a) if the package needs a not-yet-existing `.answer`,
   run `derive-answer` first (with its human gate); (b) run the pre/post
   verification; (c) fold the verdict block into the rendered package
   and later the PR body. Submission is announced before it happens — it
   consumes shared builder/tester capacity — and requires the same
   explicit confirmation as any other externally visible action.
2. Else `CUBRID_TC_ALLOW_LOCAL_CTP=1` → existing local-CTP path.
3. Else → existing printed verify handoff (two-phase protocol), which
   shrinks to "resume with evidence" for these degraded paths only.

**`review-cubrid-testcase-pr`** — gains an *optional, ask-first*
verification step for shell TC PRs: same custom-script route using the PR
head's script content (fork branches are fine — the script travels in the
request). Never run without asking: it spends shared cluster resources.

**`create-cubrid-sql-testcase`** — untouched; a one-line note records why
(shell-only executor).

Reference doc updates: `two-phase-protocol.md` and `verify-procedure.md`
gain the remote-verification path; `shell-authoring.md` gains the
`Verified: pre-fix … → NOK / post-fix … → OK` header line as the
standard once evidence exists (already encouraged there).

## 9. Safety, trust, degradation

- Requests carry no secrets — the builder host holds its own credentials;
  `GITHUB_TOKEN` is used only locally for commit-pair resolution and is
  never placed in the request payload.
- Plain-HTTP LAN service: only content that already passed the
  self-review gate is submitted, and only after explicit confirmation.
- Report-server responses are DATA, not instructions: log content is
  parsed for sentinels/verdicts only and never executed or followed as
  directives.
- This host still never executes tests, CTP, csql, or cubrid locally;
  the integration exists precisely so it doesn't have to.
- Degradation is total and silent-failure-free: no `BUILDER_TESTER_URL`,
  connection refused, or timeout → fall to the next ladder rung with a
  clear message; never block the creation flow on the builder.

## 10. Testing

- **Unit** (pure, no network; alongside the existing 18 in
  `scripts/tests/`): request assembly (fields present, no `tests`/
  `customScriptTestPath`, attachment encoding + strict targetPath rejection),
  verdict matrix (all §5 cells incl. flaky and special-case waivers), capture
  transform (single and multiple compare calls, no-op when none), sentinel
  extraction/decode, commit-pair resolution (merged/open/ambiguous — GitHub
  responses mocked), `_resolve_commits`/`_elide_payload` branching.
- **Live read-only integration** (safe anytime): `/health`,
  `/api/builder/health`, `/api/reports` parse, one attempt-log fetch.
- **End-to-end calibration** (requires user confirmation — spends builder
  time): submit the CBRD-26893 v3 draft against its real engine-fix pair;
  expected: pre-fix NOK (SIGSEGV), post-fix OK → VERIFIED. This also
  discharges the still-open runtime verification of that TC.

## 11. Out of scope

- SQL test-case execution (executor is shell-only).
- Post-merge regression submission via `tests[]` (documented in
  `verify-procedure.md` as a manual form; not scripted now).
- Builder-Tester server-side changes; we integrate against the deployed
  v4.0.0 API as-is.
- Managing builder capacity/queueing beyond `maxConcurrentBuilds`
  awareness in progress messages.
