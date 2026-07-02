---
name: maintain-qahome-joinorder
description: Maintain the CUBRID Join Order Benchmark end-to-end — the SUT-side writer (`~/cubrid-perftools-internal/cptp`, `JoinOrder.java` + `benchmark/join_order/test_cubrid.sh`) and the QAHome viewer (`~/cubrid-testtools-internal/qaresult_enhance`). Use when fixing or extending Join Order behavior: the `join_order_*` 5-table schema, the SSH→TSV→JDBC writer, per-query timeout caps, baseline/plan-diff (`INVALID_QUERY_PLAN`), result taxonomy, the Performance-tab `joinorderres` rows, the `joinorder_query_chart` / `joinorder_failed_list` / `joinorder_history_status_list` JSPs, pass/fail (`pass_flag`) and elapsed semantics, running the benchmark on a SUT, or triaging `qaresu` Join Order data. The IMDB/Join-Order-Benchmark workload is 113 alpha-suffixed queries (`1a`…`33c`), single category `JO00`, no scale-factor/throughput.
---

# Maintain QAHome Join Order

## Overview

The Join Order benchmark is CUBRID QA's plan-stability regression benchmark on the IMDB / Join-Order-Benchmark dataset (113 queries). Unlike TPCH it is **cross-repo**: a **writer** (cptp framework + `JoinOrder.java`, runs on/against the SUT) produces raw TSV artifacts and persists them to the `qaresu` collect DB over JDBC, and a **viewer** (qaresult_enhance, WebWork + iBatis) renders them. It mirrors the TPCH gen-2 contract (baseline/previous compare, ±5% slower/normal/faster/failed, failed-list, history-status) but with Join-Order traits: single category `JO00`, alpha-suffixed query ids, no scale factor, no throughput.

## Quick Start

1. **Read the manual first.** `~/cubrid-testtools-internal/qaresult_enhance/doc/doc/join_order_benchmark_manual.md` is the authoritative, code-derived reference (schema, lifecycle, taxonomy, config, glossary). Do not reconstruct semantics from memory.
2. Identify whether the work is **writer-side** (cptp), **viewer-side** (qaresult_enhance), or **both** — see `references/file-map.md`.
3. For schema/lifecycle/taxonomy/baseline/timeout semantics, read `references/runtime-model.md`.
4. To change code, follow `references/change-playbook.md` (build/deploy, CRLF gotcha, minimal-diff strategy).
5. To run the benchmark on a SUT (or set up one), read `references/sut-and-runs.md` (SUTs, config, dataset, SSH/transfer gotchas, multi-run scripts).
6. For a DB-only symptom or `qaresu` triage, read `references/triage.md`.
7. For "is the test stable / why did plans change" questions, read `references/stability-and-findings.md`.

## Working Rules

- **Writer = SSH→TSV→JDBC, no stored procedures.** `JoinOrder.java` runs shell on the SUT (install/load/stats/queries via `test_cubrid.sh`), reads raw TSVs, and does ALL parsing/median/classification/persistence in Java over JDBC. This is a deliberate divergence from TPCH's Java-UDF writer — do not "port" UDFs in.
- **Statistics must be exact.** The writer gathers stats with `UPDATE STATISTICS ON ALL CLASSES WITH FULLSCAN` (csql, in `onTestInit`), NOT `cubrid optimizedb`. Sampled stats jitter cardinalities run-to-run and flip plans on cost-boundary queries. Keep FULLSCAN.
- **Baseline reference = the OLDEST valid run of the configured baseline build, and only that build (no fallback).** Used for both plan-diff and per-query timeout caps. Oldest (not most-recent) keeps comparisons stable as new baseline-build runs are added.
- **`pass_flag` is the human review verdict** (NULL = "not reviewed"); `jo_succ_flag`/`succ_flag` is the machine verdict. The writer never sets `pass_flag`; the viewer renders NULL as "not reviewed", not "fail".
- **Ordering lives on `join_order_sqls.sql_id_order` only** (not on items/items_his). Every read needing display order JOINs `join_order_sqls` and sorts by `sqls.sql_id_order` — sorting by the `sql_id` string is wrong (`6` must precede `10`).
- **The collect DB is `qaresu`**: `csql -C -u dba qaresu@localhost`. Keep production triage read-only and separate from source changes.
- **Do not commit `cptp/conf/config.properties`** — it holds plaintext SSH/DB passwords and transient per-run state (buildurl/baseline/skipclean). Mask passwords in any output.
- Minimal diffs; Join Order shares `PerformanceManageAction.java`, `com.nhncorp.qaresult.xml`, and `showPerformance.jsp` with TPCH — conflicts cluster there. Active feature branch this work lives on: `joinorder-tpch-style`.

## Default Workflow

1. Locate the entrypoint/slice in `references/file-map.md`; confirm semantics in `references/runtime-model.md` and the manual.
2. Choose the smallest change set; update the manual when behavior/schema meaning changes (keep `join_order_benchmark_manual.md` in sync — it is the contract).
3. Build:
   - viewer: `cd ~/cubrid-testtools-internal/qaresult_enhance && ant dist` (deploy to `~/qaresult_en` + restart Tomcat for runtime checks — see `maintain-qaresult-enhance`).
   - writer: `cd ~/cubrid-perftools-internal/cptp && sh build.sh`; `bash -n benchmark/join_order/test_cubrid.sh`.
4. Validate with `qaresu` read-only queries and (for writer changes) a SUT run or partial run (`references/sut-and-runs.md`).
5. Keep writer-side `JoinOrder.java`/`test_cubrid.sh` and viewer-side semantics consistent; the manual must reflect both.

## References

- `references/file-map.md`: writer (cptp) and viewer (qaresult_enhance) hotspots and what each owns.
- `references/runtime-model.md`: 5-table schema, writer lifecycle, SSH→TSV→JDBC contract, result taxonomy, baseline/timeout/plan-diff/pass_flag semantics.
- `references/change-playbook.md`: build/deploy, common change patterns, CRLF gotcha, minimal-diff strategy.
- `references/sut-and-runs.md`: SUTs (func45 fast, perf01 slow), config keys, dataset, running/partial runs, SSH + base64-transfer gotchas, multi-run scripts.
- `references/stability-and-findings.md`: stability characterization, noisy-query tail, sampled-vs-FULLSCAN plan sensitivity, the 2248→2251 optimizer regression.
- `references/triage.md`: `qaresu` queries, common symptoms, known failure/crash patterns.
