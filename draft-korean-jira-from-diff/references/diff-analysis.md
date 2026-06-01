# Diff Analysis

## Read order

1. `git status --short`
2. `git diff --stat`
3. `git diff --name-only`
4. relevant file diffs
5. if needed, touched file context around the changed code

If the working tree diff is empty, use:

1. `git show --stat --name-only HEAD`
2. `git show HEAD -- <relevant files>`

## What to infer

- affected screen, endpoint, or workflow
- current mismatch or failure mode
- impact on user flow, data flow, or rendering
- expected post-change behavior
- exact identifiers worth preserving in the issue text

## What not to invent

- hidden root cause not proven by the diff
- reproduction steps not visible in code, tests, logs, or user input
- implementation details that do not belong in `Description`
- validation data reordered or cleaned up for readability

## Title guidance

- Use one concise Korean line
- Mention the affected area and the symptom or change theme
- Keep it factual and compact

Examples:

- `Verify Test Case 재진입 시 Reason 표시값 불일치 수정`
- `Fail Result 그룹별 페이지네이션 적용`
- `Function 탭 Build Memo 저장/표시 경로 추가`

## Repro decision

Include `Repro` when at least one of these exists:

- explicit trigger path in the diff
- failing URL or screen flow
- test or plan text with reproducible steps
- log or error condition with a clear entry path

Otherwise omit it.
