# Join Order SUTs & Running the Benchmark

## SUTs (System Under Test)
- **func45 — `192.168.2.154`** (user `latest`, app user `qahome`): the **fast dev SUT** (16-core). ~5× faster than perf01. Low-contention; good for development/baseline. cptp typically runs **locally** (on the qahome box) and SSHes here.
- **perf01 — `192.168.1.136`** (user `plcsql`): the **slow, production-class SUT** (32-core, RHEL 8). Runs the long-standing production single-shot Join Order benchmark via an ActiveMQ queue (`QUEUE_CUBRID_QA_JOINORDER_LINUX`, controller `192.168.1.90` / `ycsb_ctrl`). **Shared** — confirm it is idle and not running another benchmark before using; the production daily run lands ~22:00–03:00. Both production and cptp use `~/CUBRID` + ports 2323/41000/43092, so never overlap.
  - The legacy production benchmark lives in `~/performance/join-order-benchmark/cases/` (`join_order_benchmark.sh` — a 1-run, no-warmup, single-measurement, compare-vs-fixed-CSV regression test; the IMDB dataset is in `cases/unloaddb/`).

## Collect DB
- `qaresu` on `192.168.1.15:33080` (`collectserver` in `[common]`), reachable as `csql -C -u dba qaresu@localhost` from the qahome box. The writer connects via JDBC regardless of which SUT ran.

## Key `[join_order]` config (`cptp/conf/config.properties`)
- `serverip`/`clientip`/`appip` + `serverusr`/`appusr` + `serverpw` = the SUT target/creds. `serverhosts` = hostname label.
- `queryruns` (measured runs/query, median stored; default 5), `querywarmupruns` (discarded warmups; default 1), `querytimeout` (fallback per-query cap seconds, 0=disabled).
- `baseline_build` (e.g. `11.5.0.2245-71387b9`) — comparison baseline + source of per-query timeout caps.
- `skipclean` — `false` = clean-install build + recreate DB + reload; `true` = reuse the existing `~/CUBRID` install/DB (fast). **Switching builds requires `skipclean=false`.** Stale `cubrid.conf` from a previous build persists under `skipclean=true`.
- `[cubrid]` section (shared with TPCH) writes the SUT `cubrid.conf`: `data_buffer_size=10g`, `parallelism=32`, `sort_buffer_size=8M`, `double_write_buffer_size=default`; DB created `en_US.utf8`, `dbpagesz=16K`. **Build gotcha:** builds ≥ 11.5.0.2245 removed `parallel_heap_scan_threads`/`max_parallel_workers` (use `parallelism`); a stale config with the old keys makes csql fail "Unrecognized keyword" at load.
- `buildurl` = `http://192.168.1.91:8080/REPO_ROOT/store_01/<build>/drop/CUBRID-<build>-Linux.x86_64.sh`.

## Dataset (IMDB / JOB, ~4.5 GB)
`benchmark/join_order/{joinorder_schema,joinorder_objects,joinorder_indexes}` (CUBRID unloaddb format). It is NOT in git. On a SUT, symlink it from the production unload, e.g. on perf01: `ln -s ~/performance/join-order-benchmark/cases/unloaddb/joinorder_objects …/benchmark/join_order/joinorder_objects` (and schema/indexes). `JoinOrder.onLoadStart` also accepts `imdb_schema`/`imdb_objects`/`imdb_indexes` names.

## Running
- Entry: `cd cptp && JAVA_HOME=… sh run.sh join_order cubrid`. A full install run is ~3 h on perf01 (~45 min on func45). `skipclean=true` reuse runs are NOT much faster — the 113-query phase dominates.
- Background-launch on a SUT cleanly: `setsid bash -c "sh run.sh join_order cubrid > ~/run.log 2>&1" </dev/null >/dev/null 2>&1 &` (plain `nohup … &` over ssh tends to hang the ssh channel on exit, though the run still launches).
- Verify a run wrote correctly: `join_order_items`=113, `join_order_items_his`=113×queryruns, `baseline_build` populated, `jo_status=FINISHED`. Key log markers: `query-timeout: wrote per-query caps for N queries (ref=…)`, `plan-diff: reference=…`, `Inserted join_order_items_his=… items=…`, `update done`.

## SSH / transfer gotchas (perf01)
- Plain `ssh host 'cmd'` works; **scp and `ssh 'cat>dst' <src` both HANG** against perf01 (OpenSSH-8 SFTP backend / pipe issue). Transfer files via **base64 over a plain ssh command**: `B64=$(base64 -w0 local); ssh host "printf %s '$B64' | base64 -d > remote"` (base64 alphabet is single-quote-safe; ~120 KB args are fine).
- Use an `expect` wrapper for password auth (passwords in `[join_order]`/`[common]`; **mask in output**). `pgrep -f` self-matches the ssh command string — use the bracket trick `pgrep -f "[a]pplication.join_order.Main"`.
- Leftover state: after a run, stop the server to free the 10 GB buffer — `cubrid server stop join_order` (needs `LD_LIBRARY_PATH=$CUBRID/lib`, else rc 127 "libcubridsa.so not found"). Clean orphan `START` rows in `qaresu` (incomplete runs).

## Multi-run / partial-run helpers (built this session, reusable patterns)
- A multi-build × N-run script: loop builds, run 1 install (`skipclean=false`) + N−1 reuse (`skipclean=true`), tag each run's memo with the machine via `UPDATE join_order_test SET join_order_memo=…`. Write logs per run; a master log; a background "waiter" that polls the SUT `Main` pgrep and dumps results on exit.
- Partial timeout test: reduce `test_queries/` to a control + one query, hand-write `query_timeouts.tsv` with a tight cap, run `test_cubrid.sh` standalone (server up) → expect `warm_runs.tsv` row `rc=124, elapsed=cap`. Restore `test_queries/` after.
- Memo helper pattern: `fill_jo_memo.sh "<label>" "<WHERE on join_order_test t>"` builds a rich memo (build/baseline/config/timing/result-type breakdowns) via correlated subqueries.

## Heavy-query crash note
Heavy queries (notably `8c`, ~130 s on perf01) can crash the CUBRID server cold ("transaction aborted … server failure") — independent of the timeout. Warmed/normal full runs (queryruns=5/warmup=1) have completed `8c` successfully; cold single runs are riskier. If the server dies mid-run, restart with `cubrid server start join_order` (recovers the loaded DB).
