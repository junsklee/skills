# Join Order File Map

Join Order spans two repos. Find the slice, then read the manual section it maps to.

## Authoritative reference
- `~/cubrid-testtools-internal/qaresult_enhance/doc/doc/join_order_benchmark_manual.md` — the code-derived contract (schema §30, writer lifecycle §40, `test_cubrid.sh` §50, taxonomy §60, config §90 + glossary). **Read before changing behavior; keep in sync after.**

## Writer side — `~/cubrid-perftools-internal/cptp`
- `app/src/com/cubrid/qa/application/join_order/JoinOrder.java` — the application class implementing the fw4qa lifecycle hooks (`onInit`/`onLoadStart`/`onTestInit`/`onTestStart`/`onTestStop`/`onStop`/`onCollect`). Owns: config parse, loaddb, FULLSCAN stats, launching `test_cubrid.sh`, parsing TSVs, median selection, result-type classification, plan-diff (`applyPlanDiff`/`findPlanDiffReferenceMainId`/`queryPlanDiffReference`), per-query timeout-cap generation (`writeQueryTimeoutMap`), JDBC inserts to all 5 tables, baseline resolution (`resolveBaselineBuild`). Runs locally or on the SUT; SSHes to the SUT for shell steps; connects to `qaresu` via JDBC (`getConnection`).
- `benchmark/join_order/test_cubrid.sh` — the on-SUT query driver. Per query: optional warmups, cold `;plan detail` pass, `queryruns` warm passes (median), `;trace on` pass. Emits raw TSVs: `query_catalog.tsv`, `answers.tsv`, `plan_pass.tsv`, `warm_runs.tsv`, `trace_pass.tsv`. Reads per-query caps from `query_timeouts.tsv`.
- `benchmark/join_order/test_queries/` — the 113 `*.sql` (+ `*.answer`) query files (alpha-suffixed: `1a`…`33c`).
- `benchmark/join_order/{joinorder_schema,joinorder_objects,joinorder_indexes}` — the IMDB dataset in CUBRID unloaddb format (~4.5 GB `objects`). On a SUT these are usually **symlinks** to the production unload (e.g. `~/performance/join-order-benchmark/cases/unloaddb/` on perf01).
- `conf/config.properties` — `[common]` (collect DB), `[cubrid]` (SUT cubrid.conf params), `[join_order]` (SUT creds, queryruns/warmup/timeout, baseline_build, skipclean). **Plaintext creds — never commit.**
- `run.sh join_order cubrid` — entrypoint (runs `build.sh` then `java … application.join_order.Main cubrid`).

## Viewer side — `~/cubrid-testtools-internal/qaresult_enhance`
- `src/java/com/nhncorp/qaresult/action/PerformanceManageAction.java` — `loadJoinorderBenchmarkData` (2 rows/run: baseline + previous), `classifyJoinorderRow` (±5%), `normalizeJoinorderCompareType` (default `previous`), `showJoinorderChart` / `showJoinorderFailedList` / `showJoinorderHistoryStatusList`, `getJoinorderQueryModalData`, `renderJoinorderPassFlagText` (NULL→"not reviewed"), memo/verified/pass-flag handlers, `compareJoinorderSqlIds` (alpha-suffix order).
- `src/sqlmap/com.nhncorp.qaresult.xml` — `selectJoinOrder*` statements: baseline-run lookup (keys off `#baselineBuild#`), comparison items (pct_change), history-status summary/rows, modal data. JOIN `join_order_sqls` for `sql_id_order`, JOIN `join_order_test` for `msg_id`; use `selected_sql_run_no` (not hardcoded `1`).
- `web/WEB-INF/jsp/perf/joinorder_query_chart.jsp` — the chart: baseline/previous compare, rightmost-build lock, 4-class filters, Plan+qmark+Trace modal, alpha-suffix grouping, dynamic `/113`. Query Selection is a flat 4-column grid.
- `web/WEB-INF/jsp/perf/joinorder_failed_list.jsp`, `…/joinorder_history_status_list.jsp` — drilldowns (history uses `selected_sql_run_no`).
- `web/WEB-INF/jsp/showPerformance.jsp` — the `joinorderres` Performance-tab table (two result rows per run: baseline + previous, rowspan); `<br>` whitespace before the JO heading. **Mixed CRLF/LF file — edit byte-precisely (see change-playbook).**
- `src/conf/xwork.xml` — `showJoinorderChart` / `showJoinorderFailedList` / `showJoinorderHistoryStatusList` routes.
- `doc/doc/db/join_order_schema.sql`, `doc/doc/db/join_order_schema_migration_tpch_style.sql` — DDL + migration/backfill.

## Collect DB
- `qaresu` (CUBRID 9.3): `csql -C -u dba qaresu@localhost`. Tables: `join_order_sqls`, `join_order_main`, `join_order_test`, `join_order_items`, `join_order_items_his` (+ `general_test_log` for config/csstat/optimizedb/runtime-env blobs). Note: PL/Java is not running on this DB (`cversion()` UDF unavailable → version compare is done in Java).
