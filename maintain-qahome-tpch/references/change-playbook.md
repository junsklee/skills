# TPCH Change Playbook

## 1. Table column or display changes

When a request touches the TPCH tables in Performance:

- start with `showPerformance.jsp`
- trace the source fields back into `PerformanceManageAction.java`
- then verify the SQL columns in `com.nhncorp.qaresult.xml`
- update `doc/tpch_schema.sql` if the meaning or label changed

Typical examples:

- pass/fail column
- elapsed-time semantics
- SQL pass-rate summary
- title-case column labels
- build/scale-factor column order

## 2. Chart or query modal changes

When the request mentions `showTpchChart`, the chart tooltip, query order, or query modal:

- start with `tpch_query_chart.jsp`
- then inspect:
  - `showTpchChart()` in `PerformanceManageAction.java`
  - `getTpchQueryModalData()`
  - the SQL map queries that feed `tpchHistoryJson`, `tpchComparisonJson`, or modal rows

Recent fragile areas:

- same-build baseline display
- stream selection for Throughput
- axis label vs tooltip behavior
- chart x-axis using build labels while compare logic uses `main_id`
- query ordering for `q*` plus `rf*`

## 3. History / failed drilldown changes

When the request is about failed or unknown SQL rows:

- compare-based list: `tpch_failed_list.jsp`
- raw-history list: `tpch_history_status_list.jsp`
- action logic lives in `PerformanceManageAction.java`
- history source query lives in `com.nhncorp.qaresult.xml`

Decide first which model the user wants:

- compare result classification from current vs compare run
- raw history status from `tpch_items_his`

Do not overload one page with the other semantics unless explicitly requested.

## 4. Schema/doc alignment work

When schema changed first and code/docs lag behind:

- treat `doc/tpch_schema.sql` as the tracked source of truth in this repo
- if local docs such as `AGENTS.md` or TPCH README exist, use them as required context too
- keep doc updates surgical and specific to the current branch semantics

## 5. Minimal-diff strategy

TPCH work tends to conflict in shared hotspot files. Prefer this order of options:

1. change one SQL map query if that fully resolves the bug
2. change one action method if SQL cannot express the behavior safely
3. touch JSP only when the issue is truly presentation-only
4. avoid broad cross-layer changes unless the request explicitly needs end-to-end behavior change

This matters for hotfixes and PRs against `develop`.
