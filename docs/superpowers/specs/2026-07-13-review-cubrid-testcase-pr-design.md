# Design: review-cubrid-testcase-pr — CUBRID Test-Case PR Reviewer

Date: 2026-07-13
Status: approved (brainstorming session with junsklee)

## Purpose

A Claude Code skill that reviews GitHub pull requests adding or modifying CUBRID
CTP test cases (SQL and shell primarily), judging whether the PR correctly
validates the linked CBRD issue, follows CTP conventions, is deterministic and
maintainable, and has adequate coverage — then posts the review to the PR after
explicit user confirmation.

## Locked decisions

| Decision | Choice |
|---|---|
| Form factor | Skill (thin orchestrator) + dedicated reviewer subagent per review |
| Output destination | Rendered locally first; posted to the GitHub PR only after explicit user confirmation |
| Review language | Korean body; file names, identifiers, commands, and `✅ PASS` / `❌ NEEDS FIX` markers in English |
| Verification depth | Static analysis only. Never claim fail-before/pass-after without evidence; emit the exact `cubrid-*-tc-verify` command for a test machine instead. Never execute tests on this host (production QAHome CUBRID at `~/CUBRID`) |
| Category scope | Deep rules for shell + SQL; other CTP categories (cci, jdbc, ha_repl, ha_shell, isolation, cdc_repl, unittest) reviewed with a generic checklist plus an explicit "category rules not loaded" flag |
| Architecture | Single reviewer pass normally; fan out one subagent per test case (plus synthesis) only when the PR touches >4 independent test-case directories |
| Posting semantics | One PR review with event `COMMENT` for both verdicts; optional `--request-changes` flag escalates NEEDS FIX to `REQUEST_CHANGES` |

## Environment facts the design depends on

- No `gh`, no `jq`, no local clones of the testcase repos. GitHub access is the
  REST API via python3/curl with `GITHUB_TOKEN` (loaded via
  `source ~/.bash_profile && export GITHUB_TOKEN`), the same pattern as
  `create-cubrid-testtools-pr`.
- Target repos (all reachable with the token): `CUBRID/cubrid-testcases`
  (SQL/medium, public), `CUBRID/cubrid-testcases-private` and
  `CUBRID/cubrid-testcases-private-ex` (shell, private). Default branch `develop`.
- JIRA context via `cubrid-jira search CBRD-XXXXX` (optional enrichment — skip
  with a visible accuracy note when unavailable).
- Domain doctrine source: tw-kang/skills (develop) `cubrid-shell-tc-create`,
  `cubrid-shell-tc-verify`, `cubrid-sql-tc-create`, `cubrid-sql-tc-verify`,
  including references (directory_guide, init_sh_helpers, crash_cas_patterns,
  verification_protocol) — distilled, not vendored verbatim.
- CTP exists at `~/cubrid-testtools/CTP` but MUST NOT be run here:
  `run_cubrid_install` wipes `$HOME/CUBRID` and `finish` runs
  `cubrid service stop` + `pkill cub`, which would take down QAHome/`qaresu`.

## Skill layout

```
~/skills/review-cubrid-testcase-pr/
  SKILL.md                     # thin orchestrator (house style, <200 lines)
  scripts/
    fetch_pr.py                # stdlib-only: PR meta + diff + full head-state files
                               #   + existing reviews + CI status → JSON bundle in scratchpad
    post_review.py             # posts the review; dry-run by default, --yes to send
  references/
    review-core.md             # refined review doctrine (process, severity, output format)
    shell-rules.md             # distilled shell TC rules
    sql-rules.md               # distilled SQL TC rules
    generic-rules.md           # category-agnostic checklist + per-category stubs
```

## Flow per invocation

`/review-cubrid-testcase-pr <PR URL>`:

1. **Fetch PR bundle** — `fetch_pr.py` pulls PR metadata, commits, diff, full
   file contents at the head SHA (final-state review, not diff fragments),
   existing reviews/comments (to avoid duplicating findings), CI check status
   when present. Per-file content is capped; anything truncated is listed in
   the bundle so the reviewer never silently reviews a partial file.
2. **JIRA context** — parse `Refer to: …CBRD-XXXXX` from PR body line 1
   (fallbacks: line 2, anywhere in body, `cbrd_xxxxx` in changed paths) →
   `cubrid-jira search CBRD-XXXXX`. If the issue links a CUBRID engine PR,
   fetch its title + changed-file list as enrichment.
3. **Category detection** from changed paths: `sql/`, `medium/` → sql-rules;
   `shell/` → shell-rules; other → generic-rules + flag.
4. **Reviewer subagent** — one `general-purpose` Agent call; prompt =
   review-core + matching category reference(s) + bundle paths. Fan-out per
   test-case dir (parallel) + skill-side synthesis when >4 test-case dirs;
   overall verdict = worst individual verdict.
5. **Local render** — full Korean review in the session.
6. **Post on confirm** — `post_review.py` submits one review (`COMMENT` event;
   `--request-changes` optional). On posting failure, print the payload and a
   ready-to-run curl command.

## Reviewer doctrine (references/review-core.md)

The user's draft prompt is the backbone: understand intended behavior → review
the PR as one test package → setup/cleanup → determinism → expected-result
accuracy → coverage → pre/post-patch value; severity split NEEDS FIX vs
non-blocking; concise evidence-based output with required opening line.

Refinements over the draft:

- **Checkable rules replace abstract convention references.**
  - Shell: lifecycle contract (`. $init_path/init.sh` → `init test` → exactly
    one `write_ok`/`write_nok` per code path → `finish` last on every exit
    path), helpers over raw commands (`cubrid_createdb`,
    `change_db_parameter`/`change_broker_parameter`, `xgcc`, `xkill`,
    normalization helpers before diffs), bounded loops only, background PID
    tracking, cleanup on every exit path, platform macros before init.sh,
    dir name == script filename, `_06_issues/_{yy}_{1|2}h` bucket cross-checked
    against the JIRA issue creation date, broker1/single-CAS/coredump-baseline
    idioms for crash tests, excluded-list format.
  - SQL: `evaluate 'Case N: …'` as the only section marker, header block with
    CBRD number + Coverage list, `DROP TABLE IF EXISTS` before every CREATE,
    shared-one-DB self-containment (cleanup at bottom, deallocate every
    prepare, restore every `SET SYSTEM PARAMETERS`, drop serials/views/procs),
    determinism (no OIDs/hashes/timestamps/unordered rows in `.answer`;
    `ORDER BY` for multi-row), `server-message` only for PL/CSQL or
    message-text assertions and always paired, `.queryPlan` sidecar for
    optimizer tests with result correctness checked independently of plan
    correctness, `cases/` + `answers/` basename pairing.
  - Answer-file provenance: `.answer` must be CTP-generated; hand-written
    smells (missing `===` separators, impossible formatting) are findings.
    A generated answer is still not automatically correct — check semantics.
- **answer-fix vs bug-report taxonomy** (from the verify skills) applied when
  judging whether an `.answer` preserves a product bug or encodes an
  intentional output change (cross-check the JIRA intent).
- **Static-evidence stance**: pre-patch fail / post-patch pass claims require
  evidence (CI logs, JIRA repro, engine PR linkage); otherwise the review ends
  with a "verification required" note plus the exact
  `cubrid-shell-tc-verify` / `cubrid-sql-tc-verify` invocation for a test
  machine — never run here.
- **Language rule**: Korean prose; English identifiers/paths/commands/markers.

## Edge cases

- No JIRA link → review proceeds from the diff; the missing `Refer to:` line is
  itself a finding.
- `cubrid-jira` unavailable / restricted issue → proceed with a visible
  "reviewed without JIRA context — accuracy reduced" note.
- Excluded-list edits → check `#CBRD-XXXXX (reason)` comment + valid path;
  other non-TC files flagged for scope.
- Answer-file-only PRs (baseline regeneration) → distinct review type: apply
  answer-fix vs bug-report taxonomy instead of demanding new coverage.
- Existing reviews on the PR → provided to the reviewer to avoid repetition;
  re-running posts a fresh review (no editing of prior reviews in v1).
- Very large PRs → capped fetch with explicit truncation notes.

## Testing plan

1. Script-level: `fetch_pr.py` against a known merged PR in each repo;
   `post_review.py` exercised in its default dry-run mode.
2. Calibration: run the skill (local render only) on 3–5 recent
   human-reviewed PRs from `cubrid-testcases` and
   `cubrid-testcases-private-ex`; compare agent findings against the real
   human review comments; tune references for misses and false blockers.
3. Nothing posted during testing. First real post happens on a live PR chosen
   by the user, after reading the rendered review.

## Out of scope (v1)

- Executing test cases anywhere (local or remote pod).
- Editing/updating previously posted reviews.
- Deep per-category rules for cci/jdbc/ha_repl/ha_shell/isolation/cdc_repl/
  unittest (generic checklist + flag only; references/ structure leaves room).
- Inline line-anchored PR comments (single review body in v1; findings cite
  file:line in text).
- CI orchestration or JIRA writes (review is read-only toward JIRA).
