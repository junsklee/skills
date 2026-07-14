# Shell test-case rules (CTP)

Checkable conventions for `shell/` test cases in cubrid-testcases-private-ex.
Violations of MUST items are `NEEDS FIX`.

## Lifecycle contract (MUST)

Entry script `{name}/cases/{name}.sh` — directory name and filename MUST match.

1. Optional platform macro (`WINDOWS_NOT_SUPPORTED` / `LINUX_NOT_SUPPORTED` /
   `AIX_NOT_SUPPORTED`) BEFORE sourcing init.sh.
2. `. $init_path/init.sh` then `init test` — first real statements.
3. Every code path ends at exactly ONE of `write_ok` / `write_nok [evidence]`.
4. `finish` is the LAST call and every exit path (including early
   `write_nok` returns) must reach it — it stops services, reverts every conf
   change, and frees broker shared memory. A path that exits without `finish`
   leaks state into the next test: blocking.
5. Cleanup before `finish` on every path: `rm -f *.log csql.* <binaries>`,
   `cubrid server stop`/`deletedb` for DBs the test created.

## Helpers over raw commands (MUST)

| Required | Instead of | Why |
|---|---|---|
| `cubrid_createdb $db` | `cubrid createdb` | charset/locale compat across versions |
| `change_db_parameter "k=v"` / `change_broker_parameter "k=v"` | editing `.conf` | auto-reverted by `finish` |
| `xgcc -o bin src.c` | raw `gcc` | auto `-I/-L $CUBRID -lcascci -lpthread`, 32/64-bit + OS detection |
| `xkill <pattern>` | `kill -9` / `pkill` | user-scoped, cross-platform |
| `write_ok` / `write_nok` | echoing PASS/FAIL | CTP result tracking |
| `format_csql_output` / `format_query_plan` / `format_path_output` / `diff_ignore_lineno` | raw `diff` | strips exec time, volatile plan text, absolute paths |

## Writing rules

- SQL inline via single-quoted heredocs (`<<'EOF'`); no separate `.sql` files.
- Variables quoted (`"$db"`); no hardcoded paths (`/tmp`, `/home`, `/opt`) —
  use `$init_path`, `$CUBRID`, cwd, `$TMPDIR`.
- Bounded loops only: poll with a counter, never `while true`; sleeps >10s
  should be condition-based polling.
- Every background PID tracked (`cmd & pid=$!`) with matching `wait`/`xkill`.
- Error handling on fallible steps (`cubrid server start`, `csql`, compiles):
  `cmd || { write_nok "reason"; <cleanup>; finish; exit 0; }`.
  (Calibrated exemption for setup/DB-creation commands — do not flag missing
  fail-fast there; see `calibration-exclusions.md` entry 1.)
- Exit codes AND observable behavior both checked where appropriate;
  assertions specific enough to avoid matching unrelated log lines.
- No global service commands (`cubrid service stop` on shared instances)
  unless the issue itself requires them.

## Script conventions (MUST)

- Final statement is `finish`; NO trailing `exit 0` on the normal path.
  `exit 0` appears only on a premature/early-exit branch (after its `finish`).
- Header is a `:<< END … END` heredoc (unquoted `END`) with a one-line
  summary only — no step-by-step specifics. Inline comments 1–2 lines, only
  where useful; no comments on helper functions.
- DB name contains `db`, formatted `db<issue_num>` (e.g. `db26893`).

## House idioms (expected by reviewers)

- Default broker is `broker1` (not `query_editor`). Port:
  `` port=`cubrid broker status -b | grep broker1 | awk '{print $4}'` ``.
- CAS PID: `ps -f -u $USER | grep -v grep | grep broker1_cub_cas | awk '{print $2}'`.
- Crash/CAS-reuse repro: force single CAS (`MIN/MAX_NUM_APPL_SERVER=1` +
  `cubrid broker restart`), record `pid_before`.
- Coredump check = baseline → delta:
  `find "$CUBRID" ./ \( -name "core.*" -o -name "*coredump*" \) | wc -l`
  before vs after; pass = workload ok AND PID stable AND no new cores.
- Embedded CCI client: `.c` committed next to the `.sh`, compiled with `xgcc`,
  `#include "cas_cci.h"`.

## Directory conventions

- Bug fix: `shell/_06_issues/_{yy}_{1|2}h/{name}/cases/{name}.sh` where
  `{yy}{1|2}h` comes from the JIRA issue CREATION date — cross-check it.
- Feature: `shell/_{no}_{release_code}/{feature_group}/{name}/cases/{name}.sh`.
- Multiple tests per issue: `cbrd_xxxxx_1`, `cbrd_xxxxx_{keyword}` suffixes.
- Helper scripts live in the same `cases/` dir and own no lifecycle.

## Excluded-list changes

`shell/config/daily_regression_test_excluded_list_{linux,windows}.conf`:
each excluded path preceded by a `#CBRD-XXXXX (reason)` comment; the path must
exist in the tree; an exclusion without issue key + reason is NEEDS FIX.

## Expected-count answer updates

When a PR bumps hardcoded expected counts (daemon/thread/process counts,
etc.) to track an intentional engine change (answer-fix type), verify with
the engine PR what actually changed, then check the delta is applied to
EVERY assertion whose filter would include the changed entity — across all
files in the PR. Flag any sibling count that plausibly shares the delta but
was left unbumped (e.g. a filtered subtotal like `Tran_index is null` when
the new daemon would match that filter). Consistency across the whole
package is the finding; a single correct bump proves nothing about the
others.

## Failure classification vocabulary

When judging what a failing run would mean, classify as: product defect /
test defect / environment or tooling issue / flaky / inconclusive. Do not let
environment failures (lib paths, permissions, locale) masquerade as product
regressions.
