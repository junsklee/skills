# TPCH Production Triage

## Key distinction

A SQL statement found in the CUBRID log is the SQL text that was actually sent to the engine. CUBRID does not invent expressions like `CAST(SUBSTR(sql_id, 2) AS INTEGER)` by itself.

If the raw SQL in a log does not exist in the current repo, consider:

- a manual `csql` query
- a script outside this repo
- an older deployed artifact
- another application path

## Useful checks

### 1. Confirm current TPCH SQL IDs in DB

```sql
SELECT sql_id, COUNT(*) AS cnt
FROM tpch_items_his
WHERE main_id >= 'H20260518132950'
GROUP BY sql_id
ORDER BY sql_id;
```

### 2. Check refresh-function rows

```sql
SELECT main_id, scale_factor_type, sql_run_no, sql_exe_type, sql_id
FROM tpch_items_his
WHERE main_id >= 'H20260518132950'
  AND LOWER(sql_id) LIKE 'r%'
ORDER BY main_id, scale_factor_type, sql_run_no, sql_exe_type, sql_id;
```

### 3. Verify pass-flag column shape

This repo saw production mismatches between code and DB when `pt_act_flag/tt_act_flag` were renamed to `pt_pass_flag/tt_pass_flag`.

Use targeted schema checks before blaming application code.

## Historical failure pattern from this session

Problematic shape:

```sql
SELECT *
FROM tpch_items_his
WHERE main_id >= 'H20260527160203'
ORDER BY CAST(substr(sql_id, 2) AS integer);
```

Why it fails:

- `q1` -> `SUBSTR(..., 2)` = `1` -> valid cast
- `rf1` -> `SUBSTR(..., 2)` = `f1` -> invalid cast -> `-181`

That exact failure applies only to branches or data sets that still use `rf1`, `rf2`.

## Current naming and ordering assumption

Current working assumption:

- `q1 .. q22`
- `r1`, `r2`

Current accepted viewer SQL ordering:

```sql
ORDER BY sql_id
```

This is lexical, not numeric. It may produce `q1, q10, ..., q2`, but that is currently acceptable until a future `sql_no` column is introduced.

## Preferred response pattern

1. Confirm whether the logged SQL exists in repo source.
2. Confirm actual `sql_id` values in the database.
3. Decide whether the issue is:
   - source bug in QAHome SQL map
   - manual/ad hoc SQL outside repo
   - naming/data problem from the writer side
4. If current data uses `q1..q22,r1,r2`, avoid adding cast-based ordering unless numeric ordering is explicitly required.
5. If numeric ordering becomes a real requirement, prefer adding a dedicated `sql_no` column over more string parsing.
6. Otherwise choose the smallest fix that matches the real source of the SQL.

## Validation after fixes

For source changes:

- `git diff --check`
- `ant -f ~/cubrid-testtools-internal/qaresult_enhance/build.xml compile resource`

For DB-only investigation:

- keep verification queries read-only unless the user explicitly asks for migration SQL
