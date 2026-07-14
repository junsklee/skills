#!/bin/bash
# Vendored from tw-kang/skills@develop (0cb5ba2), cubrid-shell-tc-create/examples/cci_crash_repro.sh
# Example: prove a CAS process does NOT crash under repeated session reuse.
# Pattern (see references/crash_cas_patterns.md): force a single CAS, drive it
# with an embedded CCI client compiled by xgcc, then assert the client
# succeeded, the CAS PID is unchanged, and no new coredump appeared.

. $init_path/init.sh
init test

broker=broker1
dbname=db_repro
client=cci_crash_repro
iter=200

# --- Setup: force one CAS so the same process handles every cycle ---
change_broker_parameter "MIN_NUM_APPL_SERVER=1"
change_broker_parameter "MAX_NUM_APPL_SERVER=1"

cubrid_createdb $dbname
cubrid server start $dbname
if [ $? -ne 0 ]; then
    write_nok "failed to start server"
    cubrid deletedb $dbname 2>/dev/null
    rm -f *.log csql.* $client
    finish
    exit 0
fi

# Restart the broker so the single-CAS setting takes effect.
cubrid broker restart > /dev/null 2>&1

# --- Resolve port, record CAS PID, compile the client, baseline cores ---
port=`cubrid broker status -b | grep $broker | awk '{print $4}'`
pid_before=`ps -f -u $USER | grep -v grep | grep ${broker}_cub_cas | awk '{print $2}' | head -1`

xgcc -o $client ${client}.c
if [ $? -ne 0 ]; then
    write_nok "failed to compile $client"
    cubrid server stop $dbname 2>/dev/null
    cubrid deletedb $dbname 2>/dev/null
    rm -f *.log csql.* $client
    finish
    exit 0
fi

core_before=$(find "$CUBRID" ./ \( -name "core.*" -o -name "*coredump*" \) 2>/dev/null | wc -l)

# --- Test: drive the reused CAS ---
./$client localhost "$port" "$dbname" "$iter" > client.log 2>&1
client_rc=$?

# --- Verify: client ok AND CAS PID unchanged AND no new coredump ---
pid_after=`ps -f -u $USER | grep -v grep | grep ${broker}_cub_cas | awk '{print $2}' | head -1`
core_after=$(find "$CUBRID" ./ \( -name "core.*" -o -name "*coredump*" \) 2>/dev/null | wc -l)
core_new=$((core_after - core_before))

is_error=0
if [ "$client_rc" -ne 0 ]; then
    echo "FAILED: client exited $client_rc" >> result.log; cat client.log >> result.log; is_error=1
fi
if [ "$pid_before" != "$pid_after" ]; then
    echo "FAILED: CAS crashed/restarted (before=$pid_before after=$pid_after)" >> result.log; is_error=1
fi
if [ "$core_new" -ge 1 ]; then
    echo "FAILED: $core_new new coredump(s) under \$CUBRID" >> result.log; is_error=1
fi

if [ "$is_error" -eq 0 ]; then write_ok; else write_nok result.log; fi

# --- Cleanup (reverse order) ---
cubrid server stop $dbname
cubrid deletedb $dbname
rm -f *.log csql.* $client
finish
