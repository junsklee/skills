# SQL test-case authoring doctrine (drafter-facing)

You are DRAFTING a new CTP SQL test case. Follow every rule here; the
self-review gate checks them with the reviewer doctrine afterwards.

## Package shape

- `cases/<name>.sql` + seeded EMPTY `answers/<name>.answer` sharing the
  basename. NEVER write answer content by hand — CTP generates it.
- Optimizer/plan test → also an EMPTY `cases/<name>.queryPlan` sidecar
  (case-sensitive extension).
- Bug fix: `sql/_13_issues/_{yy}_{1|2}h/cases/cbrd_XXXXX[_n|_keyword].sql`
  (shared `cases/`+`answers/` for the bucket; simple repros are a single
  `cbrd_XXXXX.sql`). Release feature: `sql/_{no}_{release_code}/cbrd_XXXXX/
  cases/<NN_feature-description>.sql` — its own per-issue folder with
  descriptive, numbered file names (the current `_36_guava` convention for
  issues needing several independent test angles). Match where sibling issues
  of the same release actually landed (release targeting beats JIRA creation
  date). Generic regression-suite dirs legitimately use plain descriptive
  names with no CBRD number.
- Supplementing existing tests for the same CBRD → keep their naming scheme.

## File structure

- Header block first (current-suite convention, confirmed 2026-07 in every
  recent `_36_guava` feature case): a `/** … */` block opening
  `This test case verifies CBRD-XXXXX: <title>` plus a numbered `Coverage:`
  list that matches what the file actually tests. Legacy `_13_issues` cases
  often have no header — for NEW work always include one. A `-- ==== CBRD-…`
  banner is an accepted alternative.
- Label each scenario with `evaluate '<label>';` before it, numbered
  sequentially, captions truthful (they land in the `.answer` for
  traceability). The label wording is not standardized — recent cases use
  `[TEST N] <desc>` or `[N] <desc>` as often as `Case N:`; any consistent,
  descriptive scheme is fine. 3–10 scenarios per file is the norm.
- Setup at top, cleanup at bottom. `DROP TABLE IF EXISTS t;` before every
  `CREATE TABLE` (drop children before parents when FKs exist).
- **The suite shares ONE database.** Undo everything at the end: drop every
  table/view/serial/trigger/procedure, `deallocate prepare` every `prepare`,
  `drop variable` every session variable, restore every `SET SYSTEM
  PARAMETERS` to its original value. `DROP ... IF EXISTS` is required at CREATE
  time (re-run safety); end-of-file cleanup DROPs need NOT be `IF EXISTS` (bare
  `DROP TABLE t;` is the dominant real pattern). A fully-symmetric IF-EXISTS
  teardown is optional best practice for suites likely to be re-run after a
  mid-file failure.
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
- Plan tests: create an EMPTY `cases/<name>.queryPlan` sidecar (case-sensitive
  extension) to make CTP emit the query plan into the result — this is the
  house convention; do NOT use the inline `--@queryplan` directive for new
  drafts. Pin the plan with hints (`NO_ELIMINATE_JOIN`, `ORDERED`,
  `MATERIALIZE`, `/*+ recompile */`) where needed; scope `UPDATE STATISTICS ON
  <tables>` to the tables under test, never `all classes`. Note: a
  `.queryPlan` case cannot be verified via remote Builder-Tester (no sidecar
  channel — see builder-tester-verification.md); generate/verify its answer on
  a local CTP host.

## Error cases

- Assert the `-NNN` code alone (the corpus norm). `--+ server-message
  on`/`off` (always paired) ONLY for PL/CSQL `DBMS_OUTPUT` or when the
  exact message text is the point.
- Mark intentional error cases in the caption ("expects Error:-NNN").
- An unexpected error/result may be a product bug: do not design the case
  to bake it in — flag it for a CBRD issue instead.
- Answer variants are opt-in, created only on a real divergence and kept in
  sync thereafter: `answers/<name>.answer_cci` (CCI output differs — rare,
  seen mainly in older plan/trace cases) and `.answer_WIN` (Windows differs —
  effectively unused in recent cases). Do not add them speculatively.
- For files with several negative cases, a recommended enhancement (seen in
  recent `_36_guava` cases) is a defensive `SELECT COUNT(*)` catalog/state
  sanity-check after each error, using a distinct object name per negative
  case, so a masked failure can't pass silently.

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
