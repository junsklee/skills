# Calibration exclusions

Findings that calibration runs judged to be **noise** — the reviewer must NOT
raise them. This file is the single source of truth for calibration policy
(hand-maintained, versioned with the skill). It is loaded on EVERY review —
including baseline/degraded mode when the mined rubric is unavailable — and
any candidate finding matching an entry is dropped before the review is
finalized (hard gate). Respect each entry's scope column: an exclusion never
extends past its stated scope.

| # | Excluded finding | Scope | Why it's not a defect | Source |
|---|---|---|---|---|
| 1 | Missing fail-fast / return-code check on setup / DB-creation commands (`cubrid_createdb`, `createdb`) | shell | A setup failure still surfaces per-case as `write_nok` with the `.log` preserved — no state leak, no false pass. Does NOT apply to comparison/verification steps, where fail-fast (`compare_... \|\| exit 1`) is still valid. | PR #3626 / CBRD-26563 (`~/pr-review-mining/review_runs/pr3626-CBRD-26563/`) |

## How this list grows

Add an entry only when a calibration run rejects a **recurring, rule-level**
finding-type — a pattern the doctrine or mined rubric will keep producing.
A one-off false positive killed by ground truth (e.g. "already resolved in
this PR's review thread", "deferred to another JIRA") is NOT an exclusion;
those are handled by the self-skeptic pass in review-core.md's Do-not-flag
section. (Precedent: the PR #2988 calibration run added no entry for exactly
this reason.)
