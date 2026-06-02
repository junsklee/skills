---
name: create-cubrid-testtools-pr
description: Prepare and create GitHub pull requests for `~/cubrid-testtools-internal`. Use when Codex is asked to push a local feature branch to the junsklee fork and open a PR against CUBRID/cubrid-testtools-internal, especially after creating a CUBRIDQA JIRA issue. Builds PR titles with the JIRA key in square brackets and Korean PR bodies that start with the JIRA issue link.
---

# Create CUBRID Testtools PR

## Overview

Create GitHub PRs from `~/cubrid-testtools-internal` to upstream `CUBRID/cubrid-testtools-internal`. Always preview first, then push and create the PR only after explicit confirmation.

## Workflow

1. Inspect local state: current branch, `git status --short --branch`, recent commits, and the JIRA key from user context, branch name, or commit messages.
2. Do not create a PR from `develop`, `master`, `main`, or `release/*` unless the user explicitly overrides this safety check.
3. Draft PR title as `[CUBRIDQA-####] <actual title>`. The title must always be in English. Preserve `[QAHome]` only when it is part of the real feature title.
4. Draft PR body in Korean with the JIRA link as the first line: `http://jira.cubrid.org/browse/CUBRIDQA-####`.
5. Preview with `scripts/create_github_pr.py` in dry-run mode and show the branch, push target, PR head/base, title, and body.
6. After explicit user confirmation, run the same helper with `--submit --confirmed`.

## PR Format

- Base repo: `CUBRID/cubrid-testtools-internal`
- Head repo: `junsklee/cubrid-testtools-internal`
- Base branch: `develop` by default
- Push target: `origin HEAD:<current-branch>`
- Title must always be in English
- Body style from recent repo history:
  - start with the JIRA URL
  - write the summary paragraph and bullets in Korean
  - keep structural headers in English, such as `Changes` or `## Changes`
  - use `Changes` or `## Changes` with flat Korean bullets for substantial QAHome changes
  - Avoid non-code-related sections like `Validation` or `Testing`.
  - keep bullets factual and implementation-specific
- English identifiers, class names, paths, labels, and quoted commit/JIRA names may stay as-is, but explanatory prose should be Korean.
- Prefer providing `--body-file` with a reviewed Korean PR body instead of relying on the helper's commit-subject fallback.

## Script Usage

Dry-run preview:

```bash
python ~/skills/create-cubrid-testtools-pr/scripts/create_github_pr.py \
  --jira-key CUBRIDQA-1370 \
  --title "Stabilize legacy shell last-pass writer flow and pass full success log" \
  --body-file /tmp/pr-body.md
```

Confirmed creation:

```bash
GITHUB_TOKEN="$GITHUB_TOKEN" \
python ~/skills/create-cubrid-testtools-pr/scripts/create_github_pr.py \
  --jira-key CUBRIDQA-1370 \
  --title "Stabilize legacy shell last-pass writer flow and pass full success log" \
  --body-file /tmp/pr-body.md \
  --submit --confirmed
```

## Safety Rules

- `GITHUB_TOKEN` is required only for submit mode. Do not read, print, or rely on credentials embedded in git remote URLs.
- If the working tree is dirty, tell the user that uncommitted changes are not included in pushed commits.
- Submit mode refuses a PR body with no Korean text unless explicitly overridden for an exceptional identifier-only change.
- In submit mode, push the branch first. If a matching open PR already exists for `junsklee:<branch>` to `develop`, report that PR instead of creating another one.
- If no JIRA key can be found, ask for it before previewing or submitting.
