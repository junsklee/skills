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

Let `$SKILL` = this skill's directory and `$work` = a fresh scratchpad dir.

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
acceptance criteria, repro, linked engine PR (`github.com/CUBRID/cubrid/pull/N`).
- `jira_key` null → continue; the missing `Refer to:` line is itself a finding.
- CLI missing or issue restricted → continue; the review must open with a
  "JIRA 컨텍스트 없이 리뷰됨 — 정확도 제한" note.

### 3. Engine-PR enrichment (optional)

If an engine PR is linked, fetch its title + description + changed-file list (REST API,
same `bash -lc` pattern) into `$work/engine_pr.md` — it tells the reviewer
what engine code changed, to judge whether the TC exercises it.

### 4. Assemble doctrine by category

From `bundle.json` `categories`:
- always include `$SKILL/references/review-core.md`
- `sql` → add `$SKILL/references/sql-rules.md`
- `shell` or `excluded_list` → add `$SKILL/references/shell-rules.md`
- `other` → add `$SKILL/references/generic-rules.md`

### 5. Spawn the reviewer subagent

Count distinct test-case directories among changed files (a test-case dir =
the parent of `cases/`, e.g. `shell/_06_issues/_26_1h/cbrd_27000`; for
`sql/.../cases/x.sql` layouts use the parent of `cases/`).

- **≤ 4 dirs** → ONE `general-purpose` subagent.
- **> 4 dirs** → one subagent per test-case dir in parallel, then synthesize:
  merge findings, drop duplicates, overall verdict = worst individual verdict.

Each subagent prompt must contain, in order: the full text of the selected
reference files; the paths `$work/bundle/bundle.json`, `$work/bundle/files/`,
`$work/bundle/pr.diff`, `$work/jira.md`, `$work/engine_pr.md` (when present);
and the instruction: *"Read the bundle, apply the doctrine, and return ONLY
the final review markdown in Korean per the Output contract — no preamble."*

Save the result to `$work/review.md`.

### 6. Render locally and confirm

Show `$work/review.md` verbatim in the session. Then ask the user explicitly
whether to post. Do NOT post without a clear yes in this conversation.

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
