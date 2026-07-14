# Design: CUBRID Test-Case Creation Suite (create-cubrid-sql-testcase / create-cubrid-shell-testcase)

Date: 2026-07-14
Status: approved (brainstorming session with junsklee)

## Purpose

Two Claude Code skills that create CUBRID CTP test cases from a CBRD JIRA
issue — one for SQL cases, one for shell cases — routed by the mined
test-creation knowledge base, drafted against vendored tw-kang authoring
doctrine, gated by the existing reviewer suite before anything is pushed,
and finished as a fork-branch + PR after explicit user confirmation.

## Locked decisions

| Decision | Choice |
|---|---|
| Form factor | TWO separate skills (`create-cubrid-sql-testcase`, `create-cubrid-shell-testcase`), house verb-first naming; shared plumbing in a non-skill sibling dir `cubrid-testcase-creation-common/` |
| Pipeline end | Draft → self-review gate → render → (confirm) push branch to fork → verify → (confirm) open PR |
| Answer files | Never hand-written. Two-phase protocol by default (phase 1: package + seeded empty `.answer`, verify handoff; phase 2: answer intake → semantic validation → commit → PR). When local CTP execution is enabled (see Execution policy), answers are generated locally and the phases collapse into one sitting |
| Self-review gate | Mandatory, both phases. Reuses the reviewer suite verbatim (review-core + category rules + calibration-exclusions + mined rubric Tier 1+2) + the routed KB topic doc; max 2 fix loops then surface to user |
| KB integration | `CUBRID_TESTCREATE_KB_DIR` (default `~/pr-review-mining/test_creation_kb`): INDEX keyword routing → topic doc(s) + category pre-flight checklist injected into drafter context; graceful degradation with a note; KB is generated — never hand-edit |
| Vendoring | Copy useful tw-kang/skills@develop assets with provenance headers: shell references (init_sh_helpers, crash_cas_patterns, directory_guide) + 6 shell examples; 3 SQL examples; verify-skill procedures distilled into `verify-procedure.md` |
| Repo writes | Clone-free GitHub REST (contents API): branch `cbrd_XXXXX_tc` on the junsklee fork from upstream `develop` head, PUT files, PR fork→CUBRID. Dry-run default; `--yes` to execute. Nothing pushed/opened without explicit in-session confirmation |
| PR conventions | Title `[CBRD-XXXXX] <English>`; Korean body with `Refer to: http://jira.cubrid.org/browse/CBRD-XXXXX` as line 1; verification evidence included |

## Execution policy (host-conditional — NOT universal doctrine)

Local execution of CTP/csql/cubrid is governed by an explicit opt-in flag:
`CUBRID_TC_ALLOW_LOCAL_CTP=1` (env) enables the local-execution path.

- **Default (flag absent): deny.** The skills do static work only and use the
  two-phase verify handoff. On THIS development host the flag must never be
  set — it runs the production QAHome CUBRID (`~/CUBRID`, `qaresu` DB), and
  CTP runs would destroy it.
- **Deployment machine (flag set): allow.** The machine that will actually run
  this suite runs CTP locally by design. There, phase 1 extends to answer
  generation: install build (if URL given), locale lib + JDK checks, seed
  empty `.answer`, CTP interactive run, promote `.result` → `.answer`, re-run
  to confirm `Success:1` — the procedure vendored from the tw-kang verify
  skills into `verify-procedure.md`. The same file doubles as the printed
  handoff runbook when the flag is off.

## Environment facts the design depends on

- No local clones of the testcase repos on this host; no `gh`/`jq`. GitHub =
  REST with `GITHUB_TOKEN` (`bash -lc 'export GITHUB_TOKEN; …'`), Python
  3.6.8 stdlib only.
- junsklee forks exist for all three testcase repos; upstream push permission
  also exists but convention is fork → CUBRID PRs.
- JIRA via `cubrid-jira` CLI (read-only enrichment).
- The reviewer suite is deployed at `~/.claude/skills/review-cubrid-testcase-pr`
  (symlink); its references + `~/pr-review-mining/reviewer_rubric` are the
  self-review gate's doctrine. Reviewer references missing → the gate cannot
  run → STOP (the gate is a core feature). KB/rubric missing → degrade with
  a note.
- tw-kang/skills clone available for vendoring (develop @ 1e6dfba or later).

## Component layout

```
~/skills/create-cubrid-sql-testcase/
  SKILL.md                       # SQL orchestrator (<200 lines)
  references/sql-authoring.md    # drafting doctrine: header block, evaluate 'Case N:',
                                 # DROP IF EXISTS + shared-one-DB self-containment,
                                 # determinism-by-construction, error-code norms,
                                 # .queryPlan sidecar, cases/+answers/ pairing,
                                 # copy-paste-artifact proofreading
  examples/                      # vendored: bug_fix_error_cases.sql,
                                 # bug_fix_select.sql, feature_query_plan.sql

~/skills/create-cubrid-shell-testcase/
  SKILL.md                       # shell orchestrator (<200 lines)
  references/shell-authoring.md  # drafting doctrine: lifecycle contract, helpers-over-raw,
                                 # bounded loops, PID tracking, cleanup-on-every-path,
                                 # platform macros, broker1/single-CAS/coredump idioms
  references/init_sh_helpers.md  # vendored
  references/crash_cas_patterns.md  # vendored
  references/directory_guide.md  # vendored
  examples/                      # vendored: basic_entry.sh, config_change.sh,
                                 # utility_test.sh, output_comparison.sh,
                                 # cci_crash_repro.sh, cci_crash_repro.c

~/skills/cubrid-testcase-creation-common/    # NOT a skill (no SKILL.md)
  scripts/fetch_context.py       # read-only REST: engine-PR meta, target-dir sibling
                                 # listing, prior-art file fetch, same-CBRD search
  scripts/push_package.py        # contents-API writes: create branch on fork from
                                 # upstream develop head, PUT files, open PR;
                                 # dry-run default, --yes to execute
  scripts/tests/                 # unit tests for pure helpers
  references/two-phase-protocol.md  # shared workflow contract both SKILL.mds follow
  references/verify-procedure.md    # distilled from tw-kang cubrid-{sql,shell}-tc-verify:
                                    # build install, make_locale, JAVA_HOME=JDK, CTP
                                    # interactive run, verdict reading, answer promotion,
                                    # common pitfalls. Dual use: local runbook when
                                    # CUBRID_TC_ALLOW_LOCAL_CTP=1, printed handoff otherwise
```

Vendored files carry a one-line provenance header:
`<!-- Vendored from tw-kang/skills@develop (<commit>). Refresh from upstream; do not fork content silently. -->`
(shell comment form for .sh/.c files).

## Flow — phase 1 (draft)

Input: `CBRD-XXXXX` + optional scenario hints / target release dir / build URL.

1. **Context.** `cubrid-jira search CBRD-XXXXX` → expected behavior, repro,
   acceptance criteria, linked engine PR; `fetch_context.py` → engine-PR
   title/description/changed files. Category sanity check: if the issue is
   clearly the other category's shape (e.g. csql-only repro needing a shell
   test while the SQL skill was invoked), STOP with reasoning and point to
   the sibling skill — never silently cross over.
2. **KB routing.** Match feature → INDEX keywords → inject matching
   `topics/<slug>.md` + `categories/{sql,shell}.md` into drafter context.
   No topic match → category checklist only + visible note.
3. **Placement.** Propose target dir per convention (`sql/_13_issues/_{yy}_{1|2}h/`
   or release dir `_{no}_{release_code}/cbrd_XXXXX/`; shell
   `_06_issues/_{yy}_{1|2}h/{name}/cases/`), VERIFIED against where sibling
   issues of the same release actually landed (live API listing — the
   calibrated lesson: release targeting beats creation date). Same-CBRD
   existing tests → the draft becomes a supplement (`cbrd_XXXXX_1` /
   `cbrd_XXXXX_{keyword}` suffix conventions) anchored on the existing files.
4. **Prior art.** Fetch 1–2 similar cases from target/related dirs as style
   anchors, plus the skill's vendored `examples/`.
5. **Drafter subagent** writes the package to a staging dir mirroring repo
   paths: `.sql` files + seeded empty `.answer` (+ empty `.queryPlan` for
   optimizer tests) — or `{name}/cases/{name}.sh` (+ helpers/`.c`). Never a
   hand-written answer body.
6. **Self-review gate.** Reviewer subagent loads the reviewer suite doctrine
   (review-core.md, category rules, calibration-exclusions.md, mined rubric
   Tier 1+2) + the routed KB topic doc and reviews the staged package as if
   it were a PR bundle. `NEEDS FIX` → drafter fixes → re-review; max 2
   loops, then surface remaining findings to the user.
7. **Answer generation (only if `CUBRID_TC_ALLOW_LOCAL_CTP=1`).** Run
   `verify-procedure.md` locally: generate answers, confirm `Success:1`
   (sql) / `OK` (shell), fold real answers into the package, re-run the
   gate once over the complete package. Flag absent → skip; answers stay
   seeded-empty.
8. **Render + confirm.** Show the full package, placement rationale,
   coverage map, KB checklist satisfaction. On explicit confirm:
   `push_package.py` creates branch `cbrd_XXXXX_tc` on the fork and pushes
   files. Then: complete package (answers real) → offer PR immediately
   (phase 2 step 3); incomplete → print the verify handoff (exact
   `cubrid-*-tc-verify` invocation + `verify-procedure.md` content) and stop.

## Flow — phase 2 (answer intake → PR)

Invocation: same skill with `CBRD-XXXXX` (or branch name) + the generated
`.result`/`.answer` file path or pasted content. Phase detected by the
existing `cbrd_XXXXX_tc` branch on the fork (package present, answers
empty, no PR).

1. **Semantic validation** of the returned answers against intent: every
   `evaluate 'Case N:'` / shell check produced the expected KIND of output;
   error cases show the intended `Error:-NNN`; no nondeterministic tokens
   (timestamps, OIDs, hashes) baked in; row counts plausible vs setup data;
   the answer does not encode unfixed behavior (answer-fix vs bug-report
   taxonomy). Suspicious → shown to the user with the concern, never
   silently committed.
2. **Gate re-run** over the complete package (scripts + real answers).
3. **Commit** answers to the branch (dry-run first), then **PR on confirm**:
   Korean body (`Refer to:` line 1, scenario/coverage summary, verification
   evidence — build used, pass output), English title `[CBRD-XXXXX] …`.

## Edge cases

- Wrong-category invocation → stop + point to sibling skill.
- Existing same-CBRD tests → supplement mode with suffix conventions.
- KB topic miss → category checklist only + note. KB dir missing → both
  degrade with note. Reviewer-suite references missing → STOP (gate is core).
- Branch already exists → offer resume / overwrite / abort; never force-push
  without asking.
- Multi-file packages (several `.sql` sharing one `cases/`+`answers/` pair;
  shell helper scripts + `.c`) supported from the start.
- Push/PR API failure → payload preserved + curl fallback printed (same
  pattern as post_review.py).
- JIRA unavailable → creation can proceed only from user-supplied scenario
  text, with a visible accuracy note; the `Refer to:` line still required.

## Testing plan

1. Unit tests (Python 3.6.8, stdlib unittest) for pure helpers: phase
   detection, placement resolution, branch naming, supplement-suffix logic,
   payload building. `push_package.py` exercised in dry-run only.
2. **Blind creation calibration**: pick 1 recent merged SQL PR + 1 shell PR;
   re-create the test from the JIRA issue alone (no peeking at the merged
   PR), then diff the draft against what was actually merged — same
   methodology that validated the reviewer. Nothing pushed (dry-run).
3. Degradation checks: KB dir absent; rubric absent; reviewer references
   absent (must stop).
4. First real push/PR only on a live issue the user chooses, after render.

## Out of scope (v1)

- Categories beyond sql/shell (cci, jdbc, ha_*, isolation…).
- Editing/updating existing PRs (creation only; review feedback loops belong
  to reflect-style skills).
- Automated remote verification over SSH (the local-CTP path covers the
  deployment machine; other hosts use the handoff).
- KB/rubric regeneration (owned by the mining pipeline).

## Hard constraints

- On this development host: never execute CTP/csql/cubrid — the opt-in flag
  must never be set here. The skills must function fully (two-phase) without it.
- `.answer` content is never authored by hand — generated by CTP or absent.
- Nothing pushed to GitHub and no PR opened without explicit in-session
  user confirmation; all write scripts dry-run by default.
- Python 3.6.8 stdlib only; no gh/jq.
- Commits English with the single suite prefix `create-cubrid-testcase:`,
  NO Co-Authored-By. PR bodies Korean.
- Never hand-edit generated artifacts (KB docs, mined rubric).
