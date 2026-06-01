---
name: draft-korean-jira-from-diff
description: Draft Korean JIRA issue titles and bodies from the current code change in `~/cubrid-testtools-internal`, then prepare or submit a CUBRIDQA Task through the JIRA API after explicit user confirmation. Use for QAHome or qaresult_enhance changes that should become JIRA issues. Produce one Korean title plus fixed sections with bold JIRA headers such as `*Description*`, optional `*Repro*`, `*Suggested Changes*`, and `*Acceptance Criteria*`, preserving exact identifiers.
---

# Draft Korean JIRA From Diff

## Overview

Use the current git diff in `~/cubrid-testtools-internal` as the primary evidence source, then draft a Korean JIRA title and body without pretending the fix is already known. For QAHome issues, prepare a `CUBRIDQA` Task payload and submit it to `http://jira.cubrid.org/` only after the user explicitly confirms the preview.

## Workflow

1. Gather evidence first: `git status --short`, `git diff --stat`, `git diff --name-only`, then read the touched file diffs.
2. If the working tree diff is empty, fall back to `git show --stat --name-only HEAD` and read the latest commit diff.
3. Infer only what the diff proves: current problem, impact, expected outcome, affected identifiers, and whether a reproducible path is visible.
4. If the diff contains clearly unrelated change clusters, ask before splitting into multiple issues. Otherwise default to one issue draft.
5. Write one Korean title plus the fixed JIRA body sections.
6. Build and show a dry-run JIRA payload with `scripts/create_jira_issue.py`.
7. Submit the issue only after explicit user confirmation. If `JIRA_USER` or `JIRA_PASSWORD` is missing, stop and ask the user to set them.

## Output Contract

- Always produce `*Description*`, `*Suggested Changes*`, and `*Acceptance Criteria*`.
- Include `*Repro*` only when the steps or trigger can be derived confidently from diff, logs, tests, or user input.
- Write section headers exactly as bold JIRA wiki text: `*Description*`, `*Repro*`, `*Suggested Changes*`, `*Acceptance Criteria*`.
- Give each section a 1-2 line summary followed by flat bullets.
- Keep one bullet to one point. Do not mix current problem, cause, and fix in the same bullet.
- Wrap exact file paths, URLs, labels, columns, screen names, and other identifiers in backticks.

## JIRA API Contract

- Use `scripts/create_jira_issue.py` for dry-runs and submissions.
- Fixed fields:
  - Project: `CUBRIDQA`
  - Issue Type: `Task`
  - Summary: `[QAHome] <Korean title>`
  - Description: every drafted output section except the title
  - Assignee: omit the field so JIRA automatic assignment applies
- Credentials come only from `JIRA_USER` and `JIRA_PASSWORD`. Do not hardcode, print, or write credentials into skill files.
- To preview a payload, pass the title with `--title` and the body through `--description`, `--description-file`, or stdin. The script defaults to dry-run mode and prints the JSON payload.
- To create the issue after confirmation, run the same command with `--submit --confirmed`. Report the returned issue key and browse URL.

Example dry-run:

```bash
python ~/skills/draft-korean-jira-from-diff/scripts/create_jira_issue.py \
  --title "검증 실패 메모 저장 오류 수정 필요" \
  --description-file /tmp/qahome-jira-description.md
```

Example confirmed submit:

```bash
JIRA_USER="$JIRA_USER" JIRA_PASSWORD="$JIRA_PASSWORD" \
python ~/skills/draft-korean-jira-from-diff/scripts/create_jira_issue.py \
  --title "검증 실패 메모 저장 오류 수정 필요" \
  --description-file /tmp/qahome-jira-description.md \
  --submit --confirmed
```

## Writing Rules

- Prefer fragment endings such as `안 됨`, `필요`, `발생`, `불일치`, `적용`, `유지`, `노출`, `저장`.
- Avoid speculative phrases such as `보임`, `추정`, `같음`.
- Keep `*Description*` limited to current problem or mismatch.
- Keep `*Suggested Changes*` limited to change direction or implementation principle.
- Keep `*Acceptance Criteria*` limited to verifiable end states such as `정상`, `일치`, `적용`, `유지`.
- Preserve provided sample data, sort order, and path lists exactly as given. Do not normalize or summarize them.

## When Information Is Missing

- If the diff shows code movement but not user-visible behavior, say only what is proven and ask one concise follow-up before drafting.
- If `*Repro*` is not supported by evidence, omit the section entirely instead of guessing.

## References

- `references/style-rules.md`: exact section and sentence rules.
- `references/diff-analysis.md`: how to read a diff and turn it into issue content.
- `references/examples.md`: repo-specific examples that match this style.
