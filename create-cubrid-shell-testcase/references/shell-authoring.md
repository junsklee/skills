# Shell test-case authoring doctrine (drafter-facing)

You are DRAFTING a new CTP shell test case. Follow every rule here; the
self-review gate checks them with the reviewer doctrine afterwards.
Companion references in this directory: `init_sh_helpers.md` (full helper
list), `crash_cas_patterns.md` (crash/CAS recipes), `directory_guide.md`
(placement rules) — consult them while drafting. Style anchors live in
`../examples/`. Rules below marked (n/42) are mined from the 42 most recent
house-authored test scripts; treat them as the production standard.

## Package shape

- Entry script `{test_name}/cases/{test_name}.sh` — directory name and
  script filename MUST match. Helper scripts / embedded `.c`/`.java`
  clients live in the same `cases/` dir (committed next to the `.sh`).
- Bug fix bucket: `shell/_06_issues/_{yy}_{1|2}h/…` from the JIRA creation
  date; feature: `shell/_{no}_{release_code}/{feature_group}/…`. Multiple
  tests per issue: `cbrd_XXXXX_1` / `cbrd_XXXXX_{keyword}` suffixes.

## Lifecycle skeleton (every entry script)

```bash
:<< END
This scenario verifies the following issue: CBRD-XXXXX
As-is: <one-line symptom>. To-be: <one-line expected behavior>.
END
#!/bin/bash
. $init_path/init.sh
init test

dbname=db12345

# --- Setup: fresh DB in its own subdir ---
cubrid deletedb $dbname > /dev/null 2>&1
rm -rf $dbname
mkdir $dbname
cd $dbname
cubrid_createdb --db-volume-size=20M --log-volume-size=20M $dbname
cd ..
cubrid server start $dbname
if [ $? -ne 0 ]; then
    write_nok "Failed to start server"
    cubrid deletedb $dbname; rm -rf $dbname
    finish
    exit 0
fi

# --- Test 1 ---
csql -u dba $dbname -c "select ...;" > test1.log 2>&1
format_csql_output test1.log
if [ <condition> ]; then
    write_ok  "Test 1: <what is verified> passed"
else
    write_nok "Test 1: <what is verified> failed"
    cat test1.log >> $result_file
fi

# --- Test 2 --- (the script CONTINUES after a NOK; every test always runs)
...

# --- Cleanup (reverse order) ---
cubrid server stop $dbname
cubrid deletedb $dbname
rm -f *.log listdrv csql.*
rm -rf $dbname
finish
```

- Header is a `:<< END … END` heredoc (unquoted `END`) placed BEFORE the
  `#!/bin/bash` shebang (40/40); first line
  `This scenario verifies the following issue: CBRD-XXXXX` (30/42), then
  1–3 summary lines (as-is → to-be). No step-by-step specifics. The shebang
  is decorative — CTP invokes the script with `sh`/`bash`. A
  `Verified: pre-fix <build> → NOK / post-fix <build> → OK` line is
  encouraged once runtime evidence exists.
- The script's final statement is `finish` — nothing after it, NEVER a
  trailing `exit 0` (0/67 corpus-wide). `exit 0` appears only inside a
  premature/early-exit branch, immediately after its `finish`.
- DB name is `db<issue_num>` (e.g. `db12345`); create it with
  `cubrid_createdb` in its own subdir guarded by `deletedb`/`rm -rf`
  (39/42). Volume flags `--db-volume-size=20M --log-volume-size=20M` (or
  `-r`) are the default; grow to 100M/128M only for bulk-data tests, and
  omit flags only when the test's math depends on default volumes.
- Start `cubrid server` only for client/server tests; standalone issues use
  `csql -S` with no server. Start the broker ONLY when a driver/CAS path is
  exercised (2/42).

## Verdicts and evidence (the core contract)

- **Each individual test has a 1:1 paired `if/else`: `write_ok` on the pass
  branch, `write_nok` on the fail branch** — exactly as in the skeleton.
  Never accumulate an `is_error`/fail flag across DIFFERENT test cases and
  branch once at the end (0/42). One narrow exception: a single
  repeated-reproduction loop (one logical test run N times) may count
  failures and emit its one paired verdict after the loop.
- **After a `write_nok` the script CONTINUES to the next test** — every
  case always runs. Never `set -e` (0/67). Early exit is reserved for
  setup/infra/precondition failures only (createdb, server start, compile),
  via `write_nok "<reason>"` → teardown → `finish` → `exit 0` — factor a
  `cleanup_and_exit()` helper when there are several guards.
- `write_nok` always carries a diagnostic: a message naming the failed
  expectation (expected vs actual), or the offending logfile as its
  argument (`write_nok test1.log`). A standalone `write_ok` is acceptable,
  but a short pass message is preferred. Message template:
  `"Test [Case] N: <what> passed"` / `"Test [Case] N: <what> failed"`.
- Optionally preserve evidence in the fail branch by appending the test's
  log to the CTP result sink: `cat test1.log >> $result_file`
  (`$result_file` is provided by `init.sh`). Not required — passing the
  logfile to `write_nok`, or embedding the deciding values in the message,
  is equally acceptable.
- **Answer-file delegation is a first-class alternative** (20/42): redirect
  the case output to a log, normalize with `format_csql_output`, then
  `compare_result_between_files <log> <checked-in .answer>` — it emits the
  OK/NOK itself. Use it for deterministic full-output cases; use paired
  `if/else` greps for counts/markers.
- A skipped/inapplicable environment (e.g. `nproc` too small, wrong build
  type) reports `write_ok` (+ reason) then `finish; exit 0` — never NOK.

## Helpers over raw commands (review-blocking if violated)

`cubrid_createdb` (not `cubrid createdb`), `change_db_parameter` /
`change_broker_parameter` / `change_db_section_parameter` (not conf edits —
auto-reverted by `finish`), `xgcc` (not raw gcc), `xkill` (not
kill -9/pkill), `write_ok`/`write_nok`/`compare_result_between_files` (not
echoed PASS/FAIL), `format_csql_output`/`format_query_plan`/
`format_path_output`/`diff_ignore_lineno` before any diff. Full list:
`init_sh_helpers.md`.

## Writing rules

- SQL via `csql -c "…"` or a `csql … <<EOF` heredoc — both house-standard;
  never separate `.sql` files except multi-session concurrency scripts.
  Spaced `-u dba` (not `-udba`); redirect each test's output to its own
  `<name>.log 2>&1`.
- Guard compilation of embedded clients (`xgcc`/`javac`): check `$?` and
  early-exit with `write_nok "compile failed"` — an env failure must not
  masquerade as a product regression.
- Bounded poll-with-timeout for every state transition (server up/down,
  process appear/exit, marker line in a log) — a counter loop with a short
  sleep, never `while true`, never a blind fixed `sleep` for state. Track
  every background PID (`cmd & pid=$!`) with a matching `wait`/`xkill`.
- Layer an error-log gate on top of value checks where output could hide a
  failure: `grep -qi "ERROR" <log>` fails the case even when the value
  matched.
- Quote variables (`"$db"`); no hardcoded paths (`/tmp`, `/home`) — use
  `$init_path`, `$CUBRID`, cwd. Assertions specific enough not to match
  unrelated log lines. Never destructive cleanup (`rm -rf`) on paths you
  did not create; no global service commands unless the issue requires
  them.
- Inline comments 1–2 lines, only where they add value; NO comments on
  helper functions. Optional `set -x` for tracing goes immediately after
  `init test` (13/42 use it).
- Teardown order before `finish`: [broker stop] → `cubrid server stop` →
  `cubrid deletedb` → `rm -f *.log *diff listdrv csql.*` (+`*.err` for
  compiled clients) → `rm -rf $db*`.

## Crash / CAS tests

Default broker is `broker1`. Single-CAS forcing, coredump baseline→delta
counting (`find "$CUBRID" ./ \( -name "core.*" -o -name "*coredump*" \)`
before vs after the risky op), CAS-PID stability, and the embedded CCI `.c`
client pattern: follow `crash_cas_patterns.md` exactly — pass condition
combines workload ok AND PID stable AND no new cores.

## Faithfulness and minimality

- Reproduce the exact JIRA repro (mode matters: SA vs CS, csql vs broker
  client). If the issue is csql-only, drive csql; if it needs a driver,
  embed the CCI client. Add a precondition/control assertion first when a
  NOK must be attributable to the feature, not the data.
- Only what exercises the issue; no padding — but never trim the issue's
  OWN variant matrix (broader coverage is the single most-requested review
  change). For a function/operator bug: exact repro, opposite-sign control,
  explicit optional-argument paths, typed variant, boundary neighbours —
  each asserting an exact expected value, not just an error-absence
  invariant.
- Environment failures (lib/permission/locale) must not be reportable as
  product regressions — guard and classify.
