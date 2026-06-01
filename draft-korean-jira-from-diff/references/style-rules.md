# Style Rules

## Fixed sections

Always include:

- `Description`
- `Suggested Changes`
- `Acceptance Criteria`

Include `Repro` only when reproducible steps or a triggering path can be derived confidently.

Write all output section headers in bold JIRA wiki text:

- `*Description*`
- `*Repro*`
- `*Suggested Changes*`
- `*Acceptance Criteria*`

## Section behavior

- `Description`: current problem, mismatch, or impact only
- `Repro`: observable trigger path only
- `Suggested Changes`: change direction or implementation principle only
- `Acceptance Criteria`: verifiable result only

## Sentence style

- Prefer shortened endings such as `안 됨`, `필요`, `발생`, `불일치`, `적용`, `유지`, `노출`, `저장`
- Avoid long declarative endings such as `-다`, `-한다` when a shorter fragment works
- Avoid speculation such as `보임`, `추정`, `같음`
- Write in the order of 현상 -> 영향 -> 기대

## Bullet rules

- Each section starts with a 1-2 line summary
- Follow with flat bullets
- One bullet should carry one point only

## Identifier rules

- Wrap exact file paths, URLs, column names, screen names, labels, and other identifiers in backticks
- Keep raw sample values and ordering unchanged

## Output skeleton

```text
<제목>

*Description*
<1-2줄 요약>
- ...

*Repro*
<가능할 때만>
- ...

*Suggested Changes*
<1-2줄 요약>
- ...

*Acceptance Criteria*
<1-2줄 요약>
- ...
```
