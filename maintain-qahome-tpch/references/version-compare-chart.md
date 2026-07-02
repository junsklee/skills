# TPCH Version-Comparison Chart

The Performance-tab "Query Execution Trend" chart (`showTpchChart.nhn`) compares TPC-H query
times across builds. Entry: `PerformanceManageAction.showTpchChart()` and
`getTpchQueryModalData()`; view: `web/WEB-INF/jsp/perf/tpch_query_chart.jsp` (standalone page).

## UI model

- `Current` = focus build, rightmost on the chart (x-axis is left=old / right=new).
- `Compared` = diff target. A separate `Context` toggle (`Previous` | `Baseline`, JS var
  `selectedCompareType`) picks the comparison axis. `Compared` is a Major (2-component, e.g. `11.5`)
  -> Build cascade; the auto-resolved build shows once with a `(baseline)`/`(previous)` tag and its
  plain duplicate is suppressed.
- `Baseline` context charts `Current` plus its most recent older baselines (default `Show last` = 2 ->
  diff column; up to 5). `Previous` context windows the last N builds ending at `Current`.
- Editable x-axis ("custom mode"): clicking a non-rightmost build label replaces that position. The
  explicit set rides in the `builds=` URL param (CSV of main_ids, positional). Custom mode shows a footer
  note + `(Custom)` title + `Reset builds`. The rightmost build is locked.

## Hard-won rules (these bit us repeatedly)

- **A `test_build` can have multiple FINISHED runs.** `selectTpchBuildListByScale` (-> `uniqueBuilds`)
  returns ONE row per build: the `MAX(start_time)` run = the **canonical** `main_id`. `mainBuildOptions`
  mirrors `uniqueBuilds`.
- **`baseline_build` is a per-run rolling pointer, not a per-major baseline.** A build line accumulates
  several baselines over time; "the baseline of 11.5" is not a well-posed question.
- **Window builders must add COPIES of `uniqueBuilds` rows, not references.**
  `applyTpchChartRunSelection` rewrites a window row's `main_id` to the run-specific id (Current's
  selected run, a baseline's first run). If the window holds references, that mutation corrupts
  `uniqueBuilds`/`mainBuildOptions`, so canonical ids go wrong and builds silently drop on reload.
  (`resolveChartWindowBuilds` was the offender.)
- **The explicit `builds=` resolver looks up by `main_id` against canonical `uniqueBuilds`.**
  Run-specific ids are not in `uniqueBuilds` and get dropped. So the client maps displayed builds to
  canonical ids (via `mainBuildOptions`) before navigating, and the server echoes CANONICAL ids captured
  BEFORE `applyTpchChartRunSelection` runs.
- **In custom mode force `Current` to appear exactly once as the rightmost (locked) build** — it is the
  classification reference (`loadTpchComparisonRows(current, ..., compare)`). Preserve non-Current order.
- **Reflected XSS:** the JSP emits request params raw (`${resultMap.x}` and `normalizeValue('${...}')`,
  no auto-escaping). Sanitize reflected ids/builds (`mainId`, `prevMainId`, `testBuild`, `scaleFactor`,
  `streamSelection`, `builds`) to safe charsets server-side before they reach the page.
- **`tpch_query_chart.jsp` loads only `echarts.min.js` — no jQuery.** The chained-dropdown plugin used on
  `showPerformance.jsp` is unavailable here; build cascades/menus in vanilla JS. The page navigates by
  full reload via `buildNavigationUrl`.
- **echarts axis interactivity:** the xAxis sets `triggerEvent: true`; hover/click arrive via
  `chart.on('mouseover'|'click', ...)` with `params.componentType === 'xAxis'`. The hover affordance is
  drawn through rich-text label styling re-rendered with `chart.setOption`.

## Verifying chart changes locally

- Build + deploy: `bash ~/.claude/skills/maintain-qaresult-enhance/scripts/deploy-local-qahome.sh
  --env-source ~/qaresult_en_<snap>` (rebuilds, restarts Tomcat). App context is `/qaresult`; the page
  requires login (the local `qauser` table holds dev creds; query it, do not hardcode).
- JSP JS sanity without a browser: extract the last `<script>` block, replace `${...}` EL with a literal,
  run `node --check`. IDE "',' expected" diagnostics on `var x = ${resultMap.x}` lines are EL false
  positives, not real errors.
- For x-axis edit logic, drive an end-to-end harness that replicates the client edit (compute the `builds=`
  it would send) and asserts the server's resulting window — catches drop/shift/order regressions across
  multi-run builds, baseline/previous modes, and build counts.
