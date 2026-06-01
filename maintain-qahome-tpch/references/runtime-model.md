# TPCH Runtime Model

## First rule

Do not assume TPCH schema/viewer semantics from memory. They changed repeatedly across branches. Re-read `doc/tpch_schema.sql` and any local TPCH docs in the worktree before changing behavior.

## Current recurring model from recent sessions

- `tpch_main`
  - run-level header row
  - contains `test_build`, `baseline_build`, `power_size`, `throughput_size`, `qphh_size`
- `tpch_power_test`
  - Power run-level row
  - holds Power elapsed and pass/fail flags
- `tpch_thput_test`
  - Throughput run-level row
  - holds Throughput elapsed, sum/max metrics, and pass/fail flags
- `tpch_items`
  - canonical TPCH query table used by the viewer for Power-style rows
  - may not represent a single physical warm run row
- `tpch_items_his`
  - per-run history rows
  - stores `sql_run_no`, `sql_exe_type`, `sql_id`, warm elapsed, warm result

## Power vs Throughput

Power and Throughput often diverge in reader semantics.

Check the current branch before changing anything, but recent patterns were:

- Power viewer paths commonly read canonical `tpch_items`
- Throughput viewer paths often read `tpch_items_his` directly
- Throughput charts and drilldowns may use history rows even when table summaries use run-level metrics from `tpch_thput_test`

Never blindly apply a Power fix to Throughput or the reverse.

## SQL ID set and ordering

Current TPCH ID set for viewer work is:

- `q1` .. `q22`
- refresh function rows `r1`, `r2`

Current accepted viewer behavior:

- TPCH SQL paths may use plain lexical `ORDER BY sql_id`
- that gives `q1, q10, ... q2` style ordering
- this is currently accepted by spec and may later be replaced by a dedicated `sql_no` column

Guidance:

- avoid introducing cast-based ordering unless the task explicitly requires numeric ordering
- if later ordering must become stable/numeric, prefer a dedicated order column such as `sql_no`

## Current sorting helpers in repo

- server-side helper in `PerformanceManageAction.java`: `compareTpchSqlIds(...)`
- client-side helper in `tpch_query_chart.jsp`: `compareQueryIds(...)`

These are relevant when a screen or tooltip performs code-side sorting, but they are no longer the preferred long-term ordering source if a dedicated `sql_no` column is introduced later.

## Run-level metrics and elapsed semantics

These semantics changed during the session and should be re-verified on each branch:

- visible `Elapse Time (Sec)` can mean wall-clock `start_time/end_time` delta, not SQL sum
- Power also has `SQL Elapse Time (Sec)` using `pt_ela_time_sec`
- Throughput may keep `Sum (Sec)` as the SQL-total metric instead of adding another column

Read the current table columns and docs before changing labels.
