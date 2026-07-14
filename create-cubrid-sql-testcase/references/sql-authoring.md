# SQL test-case authoring doctrine (drafter-facing)

You are DRAFTING a new CTP SQL test case. Follow every rule here; the
self-review gate checks them with the reviewer doctrine afterwards.

## Package shape

- `cases/<name>.sql` + seeded EMPTY `answers/<name>.answer` sharing the
  basename. NEVER write answer content by hand — CTP generates it.
- Optimizer/plan test → also an EMPTY `cases/<name>.queryPlan` sidecar
  (case-sensitive extension).
- Bug fix: `sql/_13_issues/_{yy}_{1|2}h/cases/…`; release-targeted issue:
  `sql/_{no}_{release_code}/cbrd_XXXXX/cases/…` — match where sibling
  issues of the same release actually landed (release targeting beats JIRA
  creation date). Multiple files per issue share ONE `cases/`+`answers/`
  pair with suffixes (`cbrd_XXXXX_select.sql`) — never one subdir per file.
- Supplementing existing tests for the same CBRD → keep their naming scheme.

## File structure

- Header block first:
  `/** This test case verifies CBRD-XXXXX: <title> */` plus a numbered
  `Coverage:` list that matches what the file actually tests.
- `evaluate 'Case N: description';` before each scenario, numbered
  sequentially, captions truthful. 3–10 scenarios per file is the norm.
- Setup at top, cleanup at bottom. `DROP TABLE IF EXISTS t;` before every
  `CREATE TABLE` (drop children before parents when FKs exist).
- **The suite shares ONE database.** Undo everything at the end: drop every
  table/view/serial/trigger/procedure, `deallocate prepare` every
  `prepare`, `drop variable` every session variable, restore every
  `SET SYSTEM PARAMETERS` to its original value.
- Comments always on their OWN line above a statement — a trailing
  same-line comment can break the CTP runner.

## Determinism by construction

- Every SELECT that can return >1 row gets a full, discriminating
  `ORDER BY` (add tie-breakers until total). Single-row/scalar/aggregate
  SELECTs get NO ORDER BY.
- Never let volatile values reach the answer: no bare
  timestamps/OIDs/UUID raw values/Java object hashes — assert derived
  values instead (`count(*)`, `bit_length(...)`, `typeof(...)`, substrings).
- Simple, distinct data values (`1,2,3` / `'a','b'`) so answer diffs read
  cleanly; explicit column lists on INSERT when it aids readability.
- Plan tests: pin the plan — hints (`NO_ELIMINATE_JOIN`, `ORDERED`,
  `MATERIALIZE`, `/*+ recompile */`) where needed; `UPDATE STATISTICS ON
  <tables>` scoped to the tables under test, never `all classes`.

## Error cases

- Assert the `-NNN` code alone (the corpus norm). `--+ server-message
  on`/`off` (always paired) ONLY for PL/CSQL `DBMS_OUTPUT` or when the
  exact message text is the point.
- Mark intentional error cases in the caption ("expects Error:-NNN").
- An unexpected error/result may be a product bug: do not design the case
  to bake it in — flag it for a CBRD issue instead.

## Faithfulness and minimality

- Reproduce the EXACT issue conditions from JIRA/engine PR: same syntax
  form, same predicate/expression shape, required `SET SYSTEM PARAMETERS`.
  A look-alike scenario that misses the code path is worthless.
- Only what exercises the target issue — no unrelated setup, hints, or
  padding cases. But minimality never trims the issue's OWN variant
  matrix; reviewers ask for broader coverage more than anything else:
  - guard/limit fixes: boundary cases straddling the limit (N-1, N, N+1),
    plus one case per shared-path variant (BEFORE/AFTER timing,
    INSERT/UPDATE/DELETE event, statement type).
  - function/operator fixes: the exact repro, an opposite-sign/positive
    control, explicit optional-argument paths (e.g. round(x,0),
    round(x,scale)), the typed variant (NUMERIC cast vs literal), and
    boundary neighbours around the trigger value — each with an exact
    expected value.
  - always: main success path, main failure/exclusion path, empty/no-match,
    NULL when relevant.
- Proofread adapted/copied SQL for copy-paste artifacts: wrong
  object/user/variable names, stale JIRA numbers, unmatched parentheses,
  wrong argument counts.
- Record known gaps/limitations as `-- todo:` comments with rationale.
