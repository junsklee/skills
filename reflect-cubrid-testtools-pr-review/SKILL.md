---
name: reflect-cubrid-testtools-pr-review
description: Reflect GitHub PR review feedback for `~/cubrid-testtools-internal`. Use when Codex must read PR review comments, implement the requested fixes on the current branch, push the branch, and post Korean replies on the PR review threads. Especially useful for QAHome or qaresult_enhance follow-up work on PRs against CUBRID/cubrid-testtools-internal from the junsklee fork.
---

# Reflect CUBRID Testtools PR Review

## Overview

Use this skill when the task is not “create a new PR,” but “take existing GitHub PR review comments, apply the requested fixes, and reply on the PR.”

Target repo:
- `~/cubrid-testtools-internal`

Typical flow:
- read PR review comments
- map each comment to concrete source changes
- implement only the requested fixes
- validate locally as needed
- commit and push the branch
- post Korean replies on the PR review threads

## Workflow

1. Inspect the local branch first.
- Run `git status --short --branch`.
- Identify unrelated dirty files and keep them out of the commit.
- Review the latest commits so you know what has already been pushed.

2. Read the PR review comments from GitHub.
- Prefer GitHub API access with `GITHUB_TOKEN`.
- `gh` may not be installed on this host, so do not assume it exists.
- Read:
  - PR metadata
  - review summaries
  - inline review comments
  - issue comments only if they affect the requested follow-up

3. Reduce the review to actionable change items.
- Separate:
  - comments that require code changes
  - comments that are already addressed
  - comments that are informational only
- Do not broaden scope beyond the review unless a change is necessary to make the requested fix coherent.

4. Implement the fixes with minimal diff churn.
- Preserve existing URLs, DB tables, and response shapes unless the review explicitly requires changing them.
- Prefer local refactors over broad rewrites.
- If multiple review comments touch the same path, solve them together instead of stacking duplicate changes.

5. Validate locally for your own confidence.
- Run the smallest meaningful validation for the touched area.
- For `qaresult_enhance`, default to `ant dist` unless the user asks for a different runtime check.
- Validation is for implementation quality, not for PR reply prose.

6. Commit and push only the intended source changes.
- Stage only the files that belong to the review-response fix.
- Leave unrelated dirt uncommitted.
- Push to `origin HEAD:<current-branch>`.

7. Post PR replies after the push.
- Post one optional top-level summary comment when the review set is substantial.
- Reply inline on each actionable review thread.
- Replies should be concise Korean, factual, and mention the commit hash.

8. (Optional, off by default — only if the user asks) Reflect the follow-up on JIRA via the `cubrid-jira-ops` skill / `cubrid-jira` CLI.
- Derive `<KEY>` from the PR title `[CUBRIDQA-####]` or the branch name.
- Add a Korean progress comment: write the body to a temp file, preview with `cubrid-jira comment <KEY> --body-file <tmp>`, then add `--yes` after confirmation.
- If a status change is expected, list transitions with `cubrid-jira transition <KEY>`, then `cubrid-jira transition <KEY> --to "<STATUS>" --yes` after confirmation.
- Skip silently if `cubrid-jira` is not installed.

## GitHub API Usage

Use `bash -lc` when calling Python or curl helpers that depend on `GITHUB_TOKEN`, because this environment may have shell variables that are not exported to child processes by default.

Example pattern:

```bash
bash -lc 'export GITHUB_TOKEN; python3 - <<\"PY\"
import json, os, urllib.request
headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
    "User-Agent": "codex-pr-review-skill"
}
PY'
```

Useful endpoints:
- `GET /repos/CUBRID/cubrid-testtools-internal/pulls/<pr>`
- `GET /repos/CUBRID/cubrid-testtools-internal/pulls/<pr>/reviews`
- `GET /repos/CUBRID/cubrid-testtools-internal/pulls/<pr>/comments`
- `POST /repos/CUBRID/cubrid-testtools-internal/issues/<pr>/comments`
- `POST /repos/CUBRID/cubrid-testtools-internal/pulls/comments/<comment_id>/replies`

## Reply Style

Write PR replies in Korean.

Inline reply template:

```text
반영했습니다. <무엇을 어떻게 바꿨는지 한두 문장>. 커밋은 `<short_sha>` 입니다.
```

Top-level summary comment template:

```text
리뷰 반영했습니다. 커밋은 `<short_sha>` 입니다.

주요 반영 사항:
- ...
- ...
```

## Hard Rules

- Do not include build-verification lines in PR comments unless the user explicitly asks.
- Specifically avoid lines such as:
  - `검증은 ant dist로 확인했습니다.`
  - `빌드는 정상입니다.`
  - `테스트했습니다.`
- You may still tell the user separately what validation you ran.

- Do not claim a comment was addressed unless:
  - the code is changed,
  - the commit is created,
  - and the branch is pushed.

- Do not stage or commit unrelated dirty files.
- Do not overwrite the user’s local untracked files or generated artifacts.

- Do not comment on or transition the JIRA issue unless the corresponding fix is already committed and pushed. Always run the `cubrid-jira` write as a dry-run first and add `--yes` only after explicit user confirmation.

## CUBRID Repo Conventions

- Upstream repo: `CUBRID/cubrid-testtools-internal`
- Personal fork used here: `junsklee/cubrid-testtools-internal`
- Default branch for feature PRs: current feature branch, not `develop`
- Preserve Korean prose in replies, but keep class names, method names, paths, and identifiers in English.

## What to Report Back to the User

After finishing, report:
- commit hash
- whether the branch was pushed
- PR comment URLs if replies were posted
- any unrelated dirty files that were intentionally left out
