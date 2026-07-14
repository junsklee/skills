# Shell test-case authoring doctrine (drafter-facing)

You are DRAFTING a new CTP shell test case. Follow every rule here; the
self-review gate checks them with the reviewer doctrine afterwards.
Companion references in this directory: `init_sh_helpers.md` (full helper
list), `crash_cas_patterns.md` (crash/CAS recipes), `directory_guide.md`
(placement rules) — consult them while drafting. Style anchors live in
`../examples/`.

## Package shape

- Entry script `{test_name}/cases/{test_name}.sh` — directory name and
  script filename MUST match. Helper scripts / embedded `.c` clients live
  in the same `cases/` dir (committed next to the `.sh`).
- Bug fix bucket: `shell/_06_issues/_{yy}_{1|2}h/…` from the JIRA creation
  date; feature: `shell/_{no}_{release_code}/{feature_group}/…`. Multiple
  tests per issue: `cbrd_XXXXX_1` / `cbrd_XXXXX_{keyword}` suffixes.

## Lifecycle skeleton (every entry script)

```bash
#!/bin/bash
# CBRD-XXXXX: one-line statement of what this verifies.
# Setup -> action -> expected outcome, in 1-2 lines.
# (platform macro BEFORE init.sh when needed: WINDOWS_NOT_SUPPORTED)

. $init_path/init.sh
init test

dbname=db_xxxxx

# --- Setup ---
cubrid_createdb $dbname
cubrid server start $dbname || { write_nok "server start failed"; cubrid deletedb $dbname; finish; exit 0; }

# --- Test --- (SQL inline via single-quoted heredocs; capture to logs)
csql -udba "$dbname" > result.log 2>&1 <<'EOF'
CREATE TABLE t1 (id INT PRIMARY KEY);
EOF

# --- Verify ---
if [ <condition> ]; then write_ok; else write_nok result.log; fi

# --- Cleanup (reverse order, on EVERY exit path) ---
cubrid server stop $dbname
cubrid deletedb $dbname
rm -f *.log csql.*
finish
```

- Every code path ends at exactly ONE of `write_ok`/`write_nok`, then
  reaches `finish` LAST — including early-exit error branches.
- Multi-scenario tests satisfy this per scenario: factor a
  `run_case "name" "sql" "expected"` helper that runs csql, extracts and
  whitespace-normalizes the value line, compares exact strings
  (`[ "$result" = "$expected" ]`), and emits ONE `write_ok`/`write_nok`
  per scenario — better failure granularity than a single aggregate flag.
- Keep DB volume files out of the shared cwd: `mkdir "$dbname"; cd
  "$dbname"; cubrid_createdb …` then `cd ..` and remove the dir in
  cleanup. The repo also commonly heads scripts with a
  `:<<'DESCRIPTION' … DESCRIPTION` block instead of `#` comments — either
  is fine.
- `finish` reverts conf changes, stops services, frees broker shared
  memory; a path that skips it poisons the next test.

## Helpers over raw commands (review-blocking if violated)

`cubrid_createdb` (not `cubrid createdb`), `change_db_parameter` /
`change_broker_parameter` (not conf edits — auto-reverted by `finish`),
`xgcc` (not raw gcc), `xkill` (not kill -9/pkill), `write_ok`/`write_nok`
(not echoed PASS/FAIL), `format_csql_output`/`format_query_plan`/
`format_path_output`/`diff_ignore_lineno` before any diff. Full list:
`init_sh_helpers.md`.

## Writing rules

- SQL inline via single-quoted heredocs (`<<'EOF'`); never separate `.sql`
  files. Quote variables (`"$db"`). No hardcoded paths (`/tmp`, `/home`) —
  use `$init_path`, `$CUBRID`, cwd, `$TMPDIR`.
- Bounded loops only (poll with a counter, never `while true`); sleeps
  >10s become condition-based polling. Track every background PID
  (`cmd & pid=$!`) with a matching `wait`/`xkill`.
- Error handling on fallible steps:
  `cmd || { write_nok "reason"; <cleanup>; finish; exit 0; }`.
- Assertions specific enough not to match unrelated log lines; check exit
  codes AND observable behavior. Never destructive cleanup like
  `rm -rf $db` on paths you did not create; no global service commands
  unless the issue requires them.
- Timing: `\time -f "%e"` if you must time something (bare `time` is not
  everywhere); prefer condition polling over timing at all.

## Crash / CAS tests

Default broker is `broker1`. Single-CAS forcing, coredump baseline→delta
counting, CAS-PID stability, and the embedded CCI `.c` client pattern:
follow `crash_cas_patterns.md` exactly — pass condition combines workload
ok AND PID stable AND no new cores.

## Faithfulness and minimality

- Reproduce the exact JIRA repro (mode matters: SA vs CS, csql vs broker
  client). If the issue is csql-only, drive csql; if it needs a driver,
  embed the CCI client.
- Only what exercises the issue; no padding — but never trim the issue's
  OWN variant matrix (broader coverage is the single most-requested review
  change). For a function/operator bug: exact repro, opposite-sign control,
  explicit optional-argument paths, typed variant, boundary neighbours —
  each asserting an exact expected value, not just an error-absence
  invariant. Answer/inline-expected comparisons must normalize volatile
  output first (`format_*` helpers).
- Environment failures (lib/permission/locale) must not be reportable as
  product regressions — guard and classify.
