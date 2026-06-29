# Join Order Runtime Model

## First rule
Re-read `join_order_benchmark_manual.md` (and the live DDL) before changing semantics. The contract below is current as of the `joinorder-tpch-style` work but the manual is authoritative.

## 5-table schema (single category `sql_exe_type='JO00'`)
- `join_order_sqls` — fixed query catalog. `sql_id VARCHAR(10) PK`, `sql_stmt`, `sql_desc`, **`sql_id_order`** (the ONLY place display order lives). 113 rows.
- `join_order_main` — run header. `main_id VARCHAR(20) PK` (`"M"+yyyyMMddHHmmssSSS`), `test_build`, `baseline_build`, `start/end_time`, `join_order_status` (START→FINISHED), `succ_flag`, `db_charset`, memo, `is_verified`. No aggregate counts (derived at read time). **No `msg_id` here.**
- `join_order_test` — per-run test summary. `main_id PK`, `jo_status`, `jo_ela_time_sec` (wall), `jo_sum_time_sec` (Σ canonical warm), `jo_succ_flag` (machine), **`pass_flag`** (human verdict, NULL=not reviewed), **`msg_id`**, `err_flag`, memo, `is_verified`.
- `join_order_items` — canonical (median) row per query. `(main_id,sql_exe_type,sql_id)` PK, **`selected_sql_run_no`**, `sql_w_ela_time_sec`/`sql_w_result_type` (warm), `sql_p_ela_time_sec`/`sql_p_result_type` (plan), `sql_trace_desc`, `sql_plan_desc`. (No `sql_id_order`; no `sql_plan_qmark` column in live DB — qmark normalization is done in Java at diff time.)
- `join_order_items_his` — every warm run. `(main_id,sql_run_no,sql_exe_type,sql_id)` PK, warm elapsed/result.

## Writer = SSH → TSV → JDBC (no stored procedures)
The fw4qa framework owns lifecycle sequencing + generic CUBRID install/clean/createdb (`com.cubrid.qa.dbms.cubrid.Cubrid`) + SSH/collect plumbing. `JoinOrder.java` fills each hook:
- `onInit` — read `[join_order]`/`[common]` config (queryruns, warmup, querytimeout, baseline_build, collect params).
- `onLoadStart` — SSH `loaddb` (`joinorder_schema`/`joinorder_objects`) + create indexes (`joinorder_indexes`).
- `onTestInit` — **`UPDATE STATISTICS ON ALL CLASSES WITH FULLSCAN`** via csql against the running server (exact stats; defensive `server start` first). Log archived as `join_order_optimizedb_log`; markers `JOIN_ORDER_OPTIMIZEDB_OK/FAIL`.
- `onTestStart` — snapshot server/broker config; write **`query_timeouts.tsv`** (per-query caps, see below); export `JOIN_ORDER_RUNS`/`_WARMUP_RUNS`/`_QUERY_TIMEOUT`; run `test_cubrid.sh`.
- `onTestStop` — `cat` the 5 TSVs back; gate: if `query_catalog.tsv`/`warm_runs.tsv` missing/empty OR `itemCount < expected` → set `hasFatalError` (run finalized FAIL, never silent-empty PASS); `processJoinOrderResults` parses, picks median over successful warm runs, classifies, JDBC-inserts items/his; `applyPlanDiff` flags `INVALID_QUERY_PLAN`.
- `onStop` — JDBC final status (`FINISHED`, `succ_flag`/`jo_succ_flag`). `updateDB` rethrows SQLException (no silent swallow); persistence failure → fatal.

The SUT never reads `qaresu`; it only runs shell and writes TSVs. All `qaresu` reads/writes are tester-side Java/JDBC.

## Result taxonomy
- Warm (`sql_w_result_type`): `SUCCESS`, `INVALID_RESULT` (answer diff), `ERROR` (rc≠0,≠124), `TIME_OUT` (rc 124). Canonical falls back by priority `TIME_OUT > INVALID_RESULT > ERROR` when the success quorum (`(queryRuns+1)/2`) is missed. Anything ≠`SUCCESS` ⇒ viewer-classified `failed`.
- Plan (`sql_p_result_type`): `SUCCESS`, `NO_QUERY_PLAN` (empty plan body), `ERROR`, `INVALID_QUERY_PLAN` (post-insert plan-diff: normalized plan structure differs from the baseline reference). Plan type does NOT feed slower/normal/faster.

## Baseline & plan-diff (current rules)
- `resolveBaselineBuild`: configured `baseline_build` > last FINISHED run's baseline > NULL.
- Reference run (`findPlanDiffReferenceMainId` → `queryPlanDiffReference`): the **OLDEST** (`start_time ASC`) FINISHED run of the configured baseline build that carries gen-2 plan data (`sql_p_result_type` non-null). **No fallback** to other builds. Resolved once at `onTestStart` (stored in `baselineRefMainId`), reused at `onTestStop`. Oldest, not most-recent, so adding newer baseline-build runs never shifts existing comparisons.
- `applyPlanDiff`: for each current `SUCCESS`-plan query, `normalizePlan` (strip cost/cardinality numbers) both sides; if structures differ → `INVALID_QUERY_PLAN`. No reference ⇒ nothing flagged.

## Per-query timeout cap (safety-net, not a regression gate)
- Derived per-query from the pinned baseline run: **`cap = max(ceil(3 × baseline_query_time), 60)` seconds**, written to `query_timeouts.tsv` (`sql_id \t cap_sec`) in `onTestStart`. The 60 s floor governs all sub-20 s queries (so high-variance short queries are not falsely timed out); 3× only engages for large queries.
- `test_cubrid.sh` wraps that query's csql in `timeout -k 10s ${cap}s`. On rc 124 it records **`elapsed_sec = cap`** (JOB-style penalty/censored value, not wall-time, not NULL). `processJoinOrderResults` stores that cap as `sql_w_ela_time_sec` for an all-timeout query.
- Static `querytimeout` config is now only the **fallback** when no baseline reference exists (`0` = disabled). Regression magnitude is judged by the viewer's ±5% classification from recorded/capped times — the timeout is purely a runaway safety net.

## Viewer classification
`classifyJoinorderRow` (clone of TPCH ±5%): `failed` (current ≠ SUCCESS) > `slower` (>+5%) > `faster` (<−5%) > `normal` (±5% or no compare). Compare modes: `previous` (default; nearest lower build) and `baseline` (run's `baseline_build`). Performance tab shows BOTH (two rows/run). `pass_flag` NULL → "not reviewed".
