# Join Order Triage

Read-only first. Keep verification queries separate from source changes. Distinguish: a query emitted by QAHome source, a writer-side data problem, an ad-hoc SQL in a CUBRID log, and an environmental SUT issue.

## qaresu quick queries (`csql -C -u dba qaresu@localhost`)
```sql
-- runs of a build (status, baseline, timing)
SELECT main_id, join_order_status, TO_CHAR(start_time,'YYYY-MM-DD HH24:MI') st, baseline_build
FROM join_order_main WHERE test_build='11.5.0.XXXX-yyyy' ORDER BY start_time;

-- a run's row counts + summary
SELECT (SELECT COUNT(*) FROM join_order_items WHERE main_id='M…') items,        -- expect 113
       (SELECT COUNT(*) FROM join_order_items_his WHERE main_id='M…') his,       -- expect 113×queryruns
       (SELECT jo_succ_flag FROM join_order_test WHERE main_id='M…') succ,
       (SELECT NVL(pass_flag,'(NULL)') FROM join_order_test WHERE main_id='M…') pass;

-- warm / plan result-type breakdown
SELECT sql_w_result_type, COUNT(*) FROM join_order_items WHERE main_id='M…' GROUP BY sql_w_result_type;
SELECT NVL(sql_p_result_type,'(null)'), COUNT(*) FROM join_order_items WHERE main_id='M…' GROUP BY sql_p_result_type;

-- per-query compare vs a baseline run (±5%)
SELECT c.sql_id, b.sql_w_ela_time_sec base, c.sql_w_ela_time_sec cur,
  ROUND((c.sql_w_ela_time_sec-b.sql_w_ela_time_sec)/b.sql_w_ela_time_sec*100,1) pct
FROM join_order_items c JOIN join_order_items b ON b.sql_id=c.sql_id AND b.main_id='<baseline M>'
WHERE c.main_id='<cur M>' AND b.sql_w_ela_time_sec>0 ORDER BY ABS(pct) DESC;
```
Always JOIN `join_order_sqls` and `ORDER BY sqls.sql_id_order` for display order; `msg_id` lives on `join_order_test`.

## Known symptoms & causes
- **All queries 0 / chart shows nothing for a run**: items=0. The writer's artifact gate now marks such runs FAIL (`hasFatalError`) instead of silent PASS; check the run log for `query_catalog.tsv`/`warm_runs.tsv missing or empty`.
- **`pass_flag` shows "fail" for old runs**: NULL renders as "not reviewed" now; if it shows "fail" the migrated value is an explicit FAIL or the viewer is stale. 124 migrated rows are NULL = not reviewed.
- **Lots of `INVALID_QUERY_PLAN`**: usually sampled-vs-FULLSCAN contamination or a cross-machine/wrong baseline reference, NOT an engine bug. See `stability-and-findings.md`. Real plan changes are FULLSCAN-vs-FULLSCAN against the pinned oldest baseline run.
- **`TIME_OUT` with a time (not NULL)**: by design — the cap is recorded as `sql_w_ela_time_sec` (penalty/censored). Only reachable when a per-query cap applied (`query_timeouts.tsv`) or the static `querytimeout` fallback > 0.
- **Big timing swing, unchanged plan**: likely the cache/I-O noisy tail (23a/b, 6d/f, 7c, 8d, 15d, 13d) — not a real regression. Confirm with median-of-N.
- **Run aborts mid-way / many ERRORs after one query**: a heavy query (e.g. `8c`) crashed the SUT server cold ("transaction aborted … server failure"). Restart `cubrid server start <db>`; prefer warmup>0 / avoid cold heavy single runs.
- **"Unrecognized keyword … Could not load system parameter" at load**: stale `cubrid.conf` has `parallel_heap_scan_threads`/`max_parallel_workers` removed in the installed build; do a `skipclean=false` reinstall (regenerates conf with `parallelism`).
- **csql `command not found` / `libcubridsa.so not found` (rc 127) in non-interactive SSH**: missing CUBRID env — set `CUBRID=$HOME/CUBRID; PATH=$CUBRID/bin:$PATH; LD_LIBRARY_PATH=$CUBRID/lib:$LD_LIBRARY_PATH` (the writer uses `addRemoteCubridEnv` for this).
- **Orphan `START` rows** in `join_order_main`: an aborted/killed run that never reached FINISHED. Safe to delete the orphan `main_id` from main/test/items/items_his after confirming it's incomplete.

## Cross-checks
- Production single-shot CSVs on perf01 (`~/performance/join-order-benchmark/cases/job_sql*_<build>.csv`) are a real-SUT cross-reference (per-query times per build) — useful to sanity-check cptp results against the long-running production history, but they are single-shot (no warmup/median) so noisier.
