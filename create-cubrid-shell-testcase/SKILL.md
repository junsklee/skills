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
3. **Commit + PR gate.** On explicit user confirmation of the validated
   run evidence and any changed files: `push_package.py push … --update
   --yes`. Then render the Korean PR body (two-phase-protocol.md PR
   conventions, including the run evidence). On a second explicit
   confirmation:
   `push_package.py pr --upstream CUBRID/cubrid-testcases-private-ex
   --fork-owner junsklee --branch cbrd_NNNNN_tc --title "[CBRD-NNNNN] <english>"
   --body-file $work/pr_body.md --yes`.

## Failure conditions

- `GITHUB_TOKEN` missing → stop. `$COMMON`/`$REVIEWER` missing → stop.
- `cubrid-jira` missing/issue restricted → proceed only with user-supplied
  scenario text + visible accuracy note.
- Push/PR HTTP failure → payload preserved + curl fallback; relay both.
- Gate still NEEDS FIX after 2 loops → show findings; user decides.
