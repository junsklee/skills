<!-- Vendored from tw-kang/skills@develop (0cb5ba2), cubrid-shell-tc-create/references/crash_cas_patterns.md. Refresh from upstream; do not fork content silently. -->
# Crash / CAS / Coredump Patterns

Recipes for testcases that must prove a server or CAS process did **not** crash — the hardest class to write correctly. Grounded in the CUBRID testcase corpus (260+ TCs extract the broker port this way, 208 do coredump detection, 75 force a single CAS) and in a real CAS-coredump regression (CBRD-26745).

## Broker and CAS naming

The default broker used by testcases is **`broker1`** — not `query_editor`. Everything derives from that name:

```bash
# Live broker port (column 4 of broker status). Resolve AFTER the broker is running.
port=`cubrid broker status -b | grep broker1 | awk '{print $4}'`

# CAS worker PID (one CAS when forced to a single server; otherwise broker1_cub_cas_N).
pid=`ps -f -u $USER | grep -v grep | grep broker1_cub_cas | awk '{print $2}' | head -1`
```

`grep broker1` matches the lowercased process/status name even though the conf section header is `[%BROKER1]`.

## Forcing a single CAS

A "one CAS reused across requests" bug only reproduces deterministically if exactly one CAS handles everything. The default broker pre-forks several (`MIN_NUM_APPL_SERVER=5`), which spreads connections and hides the bug. Force one, then restart the broker so it takes effect (`change_broker_parameter` is auto-reverted by `finish`):

```bash
change_broker_parameter "MIN_NUM_APPL_SERVER=1"
change_broker_parameter "MAX_NUM_APPL_SERVER=1"
cubrid broker restart
```

## Coredump detection (baseline → delta)

A crash leaves a core file under `$CUBRID` (CUBRID writes `*_cub_cas_*.coredump` under `$CUBRID/log/`) or in the cwd. Take a baseline count before the action and compare after — searching both `$CUBRID` and `./`:

```bash
core_before=$(find "$CUBRID" ./ \( -name "core.*" -o -name "*coredump*" \) 2>/dev/null | wc -l)
# ... run the workload ...
core_after=$(find "$CUBRID" ./ \( -name "core.*" -o -name "*coredump*" \) 2>/dev/null | wc -l)
core_new=$((core_after - core_before))
```

(The corpus also uses the simpler "clean first, then count": `find $CUBRID/ -name "core.*" | xargs rm -rf` before the test, `cnt=$(find ... | wc -l)` after. The baseline-delta form is safer when other cores may pre-exist.)

## CAS-PID stability

A CAS crash makes the broker respawn it with a new PID (or leave none). Capture the PID before and after; equal PID = survived:

```bash
pid_before=`ps -f -u $USER | grep -v grep | grep broker1_cub_cas | awk '{print $2}' | head -1`
# ... run the workload ...
pid_after=`ps -f -u $USER  | grep -v grep | grep broker1_cub_cas | awk '{print $2}' | head -1`
```

A robust pass condition combines all three signals: client/workload succeeded **and** `pid_before` == `pid_after` **and** `core_new` < 1.

## Embedded CCI C client

When the repro needs real driver behavior (connection pooling, session reuse) that `csql` can't model, embed a small CCI C client next to the `.sh` and compile it at run time with `xgcc` (it adds `-I/-L $CUBRID`, `-lcascci -lpthread`, and 32/64-bit + OS flags — never hand-roll those):

```bash
xgcc -o cci_client cci_client.c          # commit cci_client.c next to the .sh
port=`cubrid broker status -b | grep broker1 | awk '{print $4}'`
./cci_client localhost "$port" "$dbname" 200 > client.log 2>&1
client_rc=$?
```

The client's `#include` should be `"cas_cci.h"` (resolved via `-I$CUBRID/include`), not a source-tree path. See `@examples/cci_crash_repro.sh` and `@examples/cci_crash_repro.c` for a complete, compiling pattern.

## Putting it together

A crash/CAS-reuse testcase, in order: force single CAS → create DB(s) + schema/SP → start broker → resolve port + record `pid_before` → coredump baseline → compile + run the client/workload → recheck PID + cores → `write_ok` only if client ok **and** PID stable **and** no new cores, else `write_nok` with the evidence log. Clean up (`rm -f *.log csql.* cci_client`) on every exit path before `finish`.
