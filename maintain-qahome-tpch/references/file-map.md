# TPCH File Map

## Core QAHome files

- `qaresult_enhance/src/java/com/nhncorp/qaresult/action/PerformanceManageAction.java`
  - main TPCH action logic
  - chart context resolution
  - compare/history/history-status row shaping
  - pass/fail, memo, and TPCH-specific display fields
  - version-compare chart resolution: canonical vs run-specific `main_id`, explicit/baseline windows (`references/version-compare-chart.md`)
- `qaresult_enhance/src/sqlmap/com.nhncorp.qaresult.xml`
  - TPCH iBatis SQL
  - `tpch_main`, `tpch_power_test`, `tpch_thput_test`, `tpch_items`, `tpch_items_his`
  - compare/history/modal/history-status queries
  - `selectTpchBuildListByScale` (one canonical row per build = MAX start_time), `selectTpchBaselineBuildsByScale`
- `qaresult_enhance/web/WEB-INF/jsp/showPerformance.jsp`
  - TPCH Power / Throughput tables in the Performance tab
  - column order, memo/pass-fail/verified cells, resource links
- `qaresult_enhance/web/WEB-INF/jsp/perf/tpch_query_chart.jsp`
  - TPCH chart UI
  - client-side query ordering, tooltip behavior, stream selection, same-build display
  - version comparison: `Current`/`Compared`, `Context` (Previous|Baseline) toggle, Major->Build cascade
  - editable x-axis "custom mode" (`builds=` param), rightmost-locked Current, hover affordance
  - standalone page: echarts only, NO jQuery (vanilla JS). See `references/version-compare-chart.md`
- `qaresult_enhance/web/WEB-INF/jsp/perf/tpch_failed_list.jsp`
  - compare-based failed-query list
- `qaresult_enhance/web/WEB-INF/jsp/perf/tpch_history_status_list.jsp`
  - raw-history failed/unknown drilldown
- `qaresult_enhance/src/conf/xwork.xml`
  - TPCH actions such as `showTpchChart`, `showTpchFailedList`, `showTpchHistoryStatusList`
- `qaresult_enhance/doc/tpch_schema.sql`
  - tracked TPCH schema and semantics comments

## Often-related files

- `qaresult_enhance/src/java/com/nhncorp/qaresult/dao/QaResultDAO.java`
- `qaresult_enhance/src/java/com/nhncorp/qaresult/dao/QaResultDAOImpl.java`
  - needed when TPCH persistence or memo/pass-fail update methods change
- `qaresult_enhance/web/common/js/echarts.min.js`
  - vendored chart dependency used by TPCH chart page

## Optional local context

These may exist only in some worktrees, but are important when present:

- `qaresult_enhance/AGENTS.md`
- `qaresult_enhance/doc/doc/features/tpch/README.md`
- `qaresult_enhance/doc/doc/db/sample_tpch_data_clean.sql`
- `qaresult_enhance/doc/doc/db/sample_tpch_data_clean copy.sql`

Read them before changing semantics if the task mentions them or if they exist locally.
