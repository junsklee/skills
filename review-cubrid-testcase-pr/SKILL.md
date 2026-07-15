---
name: review-cubrid-testcase-pr
description: Review a GitHub pull request that adds or modifies CUBRID CTP test cases (SQL or shell) against its CBRD JIRA issue, render a Korean review locally, and post it to the PR only after explicit user confirmation. Use when asked to review a test-case PR in CUBRID/cubrid-testcases, cubrid-testcases-private, or cubrid-testcases-private-ex — "review this TC PR", "TC PR 리뷰해줘", "테스트케이스 PR 검토해줘", or a testcase-repo PR URL plus the word review. NOT for creating test cases, running/verifying test cases on a build, or PRs in cubrid-testtools-internal (use create-cubrid-testtools-pr / reflect-cubrid-testtools-pr-review).
---

# Review CUBRID Test-Case PR

Fetch a test-case PR and its JIRA context, review it with category doctrine
via a subagent, render the Korean review locally, and post only after the
user explicitly confirms.

## Hard safety rule

NEVER execute test cases, CTP, or `run_cubrid_install` on this host. This
machine runs the production QAHome CUBRID (`~/CUBRID`, `qaresu` DB); CTP runs
wipe `$HOME/CUBRID` and stop CUBRID services. Review is static analysis only;
runtime proof is delegated to a test machine via the verification footer.

## Prerequisites

- `GITHUB_TOKEN` set (unexported) in `~/.bash_profile`. Wrap every script
  call in `bash -lc 'export GITHUB_TOKEN; …'`.
- `cubrid-jira` CLI — optional enrichment; skip with a visible note if absent.
- Mined reviewer rubric (optional empirical layer): dir
  `$CUBRID_REVIEW_RUBRIC_DIR`, default `~/pr-review-mining/reviewer_rubric`.
  If missing, note "mined rubric not found — baseline doctrine only" and
  continue; the skill works standalone.

Let `$SKILL` = this skill's directory and `$work` = a fresh scratchpad dir.

- `$COMMON` = `$SKILL/../cubrid-testcase-creation-common` — shared scripts
  (`fetch_context.py`, `verify_testcase.py`). Present only when the creation
  suite is installed; the optional verification step below needs it.

## Steps

### 1. Fetch the PR bundle

```bash
bash -lc "export GITHUB_TOKEN; python3 $SKILL/scripts/fetch_pr.py '<PR_URL>' --out $work/bundle"
```

Read `$work/bundle/bundle.json`. If `truncated` is non-empty, tell the user
which files were capped BEFORE reviewing. If the repo is not one of the
three testcase repos, confirm intent with the user before continuing.

### 2. JIRA context (optional enrichment)

If `jira_key` is set and `cubrid-jira` exists:
`cubrid-jira search <KEY> > $work/jira.md`. Extract: expected behavior,
acceptance criteria, repro.

The engine PR is NOT in `jira.md` — `cubrid-jira search` does not render the
JIRA "development / N pull requests" panel. Resolve it separately (auth is
~/.netrc, machine jira.cubrid.org):
  bash -lc "python3 $SKILL/scripts/get_engine_pr.py <KEY> > $work/engine_pr_links.txt"
The engine PR = the `[engine]`-tagged line (URL under github.com/CUBRID/cubrid/
AND title carries <KEY>). Ignore `[other-repo-pr]` lines (e.g. CUBVEC-* CI
merges) and the testcase PR itself. Exit 2 = no engine PR linked; note it and
continue (reduced-evidence, not a defect against the author).
- `jira_key` null → continue; the missing `Refer to:` line is itself a finding.
- CLI missing or issue restricted → continue; the review must open with a
  "JIRA 컨텍스트 없이 리뷰됨 — 정확도 제한" note.

### 3. Engine-PR enrichment (optional)

If an engine PR is linked, fetch its title + description + changed-file list (REST API,
same `bash -lc` pattern) into `$work/engine_pr.md` — it tells the reviewer
what engine code changed, to judge whether the TC exercises it.

### 4. Assemble doctrine by category

Normative layer, from `bundle.json` `categories`:
- always include `$SKILL/references/review-core.md` and
  `$SKILL/references/calibration-exclusions.md` (hard drop list — loaded
  even when the rubric below is unavailable)
- `sql` → add `$SKILL/references/sql-rules.md`
- `shell` or `excluded_list` → add `$SKILL/references/shell-rules.md`
- `other` → add `$SKILL/references/generic-rules.md`

Empirical layer (mined rubric). Let `$RUBRIC` = `$CUBRID_REVIEW_RUBRIC_DIR`,
default `~/pr-review-mining/reviewer_rubric`. If the dir does not exist,
tell the user "mined rubric not found — baseline doctrine only" and skip
this block:
- always add `$RUBRIC/mined-rubric-overview.md` and
  `$RUBRIC/mined-general-rules.md` (its Tier-1 rules are cross-category)
- `sql` → add `$RUBRIC/mined-sql-rules.md`; `shell` or `excluded_list` →
  add `$RUBRIC/mined-shell-rules.md`; a PR spanning categories loads every
  matching mined doc (mirror the normative selection)
- Token cap: from each mined category doc inject only the `## Tier 1` and
  `## Tier 2` sections (cut at the `## Tier 3` heading) — Tier 3 is
  watchlist-only; pass the full file PATH so the reviewer can consult it
  on demand.

### 5. Spawn the reviewer subagent

Count distinct test-case directories among changed files (a test-case dir =
the parent of `cases/`, e.g. `shell/_06_issues/_26_1h/cbrd_27000`; for
`sql/.../cases/x.sql` layouts use the parent of `cases/`).

- **≤ 4 dirs** → ONE `general-purpose` subagent.
- **> 4 dirs** → one subagent per test-case dir in parallel, then synthesize:
  merge findings, drop duplicates, overall verdict = worst individual verdict.

Each subagent prompt must contain, in order: the full text of the selected
reference files (calibration-exclusions.md included); the mined-rubric
sections per Step 4 (when available); the paths `$work/bundle/bundle.json`,
`$work/bundle/files/`, `$work/bundle/pr.diff`, `$work/jira.md`,
`$work/engine_pr.md` (when present); and the instruction: *"Read the bundle,
apply the doctrine, and return ONLY the final review markdown in Korean per
the Output contract — no preamble."*

When the rubric is loaded, the prompt must also instruct the reviewer to:
- treat the mined **Tier-1 themes as the must-check list** for the detected
  category — one pass per applicable theme over the changed files; a
  confirmed violation is a `NEEDS FIX` candidate. Tier 2 → non-blocking
  suggestion only, never gates the verdict alone. Tier 3 → mention only when
  the diff directly triggers it; never hunt for it.
- **cite the mined theme** on every rubric-grounded finding and, where
  useful, mirror the team's phrasing from the precedent quotes; use per-theme
  PR/reviewer counts for prioritisation and tone, never as proof of a defect.
- apply the **calibration drop (hard gate)**: before finalizing, delete any
  candidate finding matching a `calibration-exclusions.md` entry, respecting
  each entry's scope.
- run the **self-skeptic pass** per review-core.md's Do-not-flag section:
  default to NOT flagging under doubt.
- **complement, don't duplicate, the live AI reviewers**: greptile already
  covers plan/answer-regression and `.answer_cci` variant sync on these
  repos; the bundle's existing reviews/comments show what it and humans
  already raised — do not re-post those.

Save the result to `$work/review.md`.

### 6. Render locally and confirm

Show `$work/review.md` verbatim in the session. Then ask the user explicitly
whether to post. Do NOT post without a clear yes in this conversation.

### Optional: runtime verification of a shell TC PR (ask first)

For a shell test-case PR only, offer — never run unprompted — a remote
Builder-Tester check. It spends shared cluster capacity, so ask the user
first, and skip silently if `$COMMON` is absent or the gateway is unreachable.
On agreement, read `$COMMON/references/builder-tester-verification.md`, fetch
the PR's shell package into a scratch dir with
`python3 $COMMON/scripts/fetch_context.py get <owner/repo> <case-dir paths> --out $scratch --ref <pr-head-sha>`,
then run against the PR head's entry script and the issue's engine PR:

`python3 $COMMON/scripts/verify_testcase.py run --script <fetched entry.sh>
--engine-pr <engine ref>` (dry-run first, `--yes` after the user confirms).

The script travels in the custom-script request, so a fork branch is fine.
Fold the verdict block into the review as supporting evidence: VERIFIED
strengthens an approval; NOT-VERIFIED/FLAKY is a `NEEDS FIX` with the run as
proof; INCONCLUSIVE is a builder/env issue, reported as such — not a finding
against the PR. Never block a review on the gateway being reachable.

### 7. Post

```bash
bash -lc "export GITHUB_TOKEN; python3 $SKILL/scripts/post_review.py '<PR_URL>' --body-file $work/review.md --yes"
```

Default event is `COMMENT`; add `--request-changes` only when the user asks
for a blocking review. On HTTP failure the script preserves the payload and
prints a curl fallback — relay both to the user.

## Failure conditions

- `GITHUB_TOKEN` missing → stop and tell the user.
- Reviewer subagent returns empty/no verdict line → do not post; rerun or
  report.
- Re-running on the same PR posts a NEW review (v1 never edits old ones);
  the bundle includes existing reviews so the subagent avoids repeating them.
