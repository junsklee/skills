# Join Order Change Playbook

## Build / compile
- Writer (cptp): `cd ~/cubrid-perftools-internal/cptp && export JAVA_HOME=/usr/lib/jvm/java-1.8.0-openjdk && sh build.sh` (builds `framework` then `app`). Shell check: `bash -n benchmark/join_order/test_cubrid.sh`.
- Viewer (qaresult_enhance): `cd ~/cubrid-testtools-internal/qaresult_enhance && ant dist`. For runtime verification, deploy to `~/qaresult_en` + restart Tomcat — use the `maintain-qaresult-enhance` skill / `scripts/deploy-local-qahome.sh`. Tomcat 8.5.4 on :8080, context `/qaresult`, JDK 1.8.

## Deploying writer changes to a SUT
- If running cptp **on the SUT**: deploy the changed `JoinOrder.java` AND `test_cubrid.sh` there and rebuild on the SUT.
- If running cptp **locally targeting the SUT**: only `test_cubrid.sh` must be on the SUT (`benchmarkhome`); `JoinOrder.java` runs locally. `run.sh` rebuilds from local source each run.
- **scp/sftp to the slow SUT (perf01) hangs** (OpenSSH-8 SFTP backend); plain ssh works. Transfer via base64-over-ssh: `B64=$(base64 -w0 local); ssh host "printf %s '$B64' | base64 -d > remote"`. See `references/sut-and-runs.md`.

## Editing `showPerformance.jsp` (CRLF gotcha)
`web/WEB-INF/jsp/showPerformance.jsp` is a **mixed CRLF/LF** file. The Edit tool normalizes line endings and blows up the diff. Edit it **byte-precisely with Python** (read bytes, replace exact byte slice, write bytes) to keep the diff minimal. Other JSPs are normal LF.

## Common change patterns
- **Schema change** → update `doc/doc/db/join_order_schema.sql` + the migration file, the writer inserts in `JoinOrder.java`, the sqlmap selects, AND the manual. Mirror `tpch_schema.sql` DDL style (`ALTER TABLE ADD CONSTRAINT pk_…`, `CREATE INDEX idx_…`, `NUMERIC(30,6)`, `VARCHAR(1073741823)` blobs).
- **New read/query** → add to `com.nhncorp.qaresult.xml`; JOIN `join_order_sqls` and `ORDER BY sqls.sql_id_order`; JOIN `join_order_test` for `msg_id`; use `curr.selected_sql_run_no as sql_run_no` (not literal `1`). Baseline lookups key off `#baselineBuild#`.
- **Classification/compare** → reuse `classifyJoinorderRow` / `normalizeJoinorderCompareType` (clones of the TPCH ±5% / default-`previous` logic). Don't invent new buckets.
- **Chart/JSP** → preserve alpha-suffix grouping (`/^(\d+)([a-z])$/i`), dynamic `/<count>` (not hardcoded `/113`), secure-clipboard copy, rightmost-build lock, the Plan+qmark+Trace modal (pass `prevMainId`), and the flat 4-column Query Selection grid.
- **pass_flag** → it is human-only. Writer must NOT set it (`getTestEndSql` sets only `jo_succ_flag`). Viewer renders NULL as "not reviewed". `renderJoinorderPassFlagText` returns pass/fail/"not reviewed".
- **Timeout/stats/baseline** → see `runtime-model.md`; keep FULLSCAN, oldest-run reference, no-fallback, `max(ceil(3×base),60)` caps with cap-as-penalty.

## Minimal-diff strategy
Join Order shares `PerformanceManageAction.java`, `com.nhncorp.qaresult.xml`, `showPerformance.jsp`, `xwork.xml` with TPCH. Keep JO hunks isolated; don't reformat shared files. Where JO intentionally diverges from TPCH (e.g. `pass_flag` human-only, `selected_sql_run_no` in history, JDBC instead of UDFs), that divergence is deliberate — don't "fix" it back toward TPCH.

## After behavior changes
Update `join_order_benchmark_manual.md` in the same change (it is the contract; a parallel agent can do the doc sweep). Keep writer + viewer + manual consistent.

## Git
- Feature branch: `joinorder-tpch-style` (both repos). Fork `junsklee/` → `CUBRID/`.
- Commit messages in English; PR bodies / JIRA in Korean (`create-cubrid-testtools-pr`, `draft-korean-jira-from-diff`). **No `Co-Authored-By` lines.**
- Never stage `cptp/conf/config.properties` (plaintext creds + transient run state). Restore unintentionally-deleted tracked jars (`lib/build/*.jar`) rather than committing their deletion. A GitHub PAT was exposed in remote URLs this project — rotate before pushing.
