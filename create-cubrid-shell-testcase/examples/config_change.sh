#!/bin/bash
# Vendored from tw-kang/skills@develop (0cb5ba2), cubrid-shell-tc-create/examples/config_change.sh
# CBRD-99002: Verify java_stored_procedure parameter enables JSP execution
# Changes java_stored_procedure to yes, restarts server, and verifies
# that a Java stored procedure can be loaded and called.

. $init_path/init.sh
init test

dbname=jsp_test_db

# --- Setup: change parameter before DB creation ---
change_db_parameter "java_stored_procedure=yes"

cubrid_createdb $dbname
cubrid server start $dbname
if [ $? -ne 0 ]; then
    write_nok "Failed to start server with JSP enabled"
    cubrid deletedb $dbname
    finish
fi

# --- Test: verify JSP is enabled ---
csql -udba "$dbname" -c "SHOW SYSTEM PARAMETERS LIKE 'java_stored_procedure'" > result.log 2>&1
format_csql_output result.log

# --- Verify ---
if grep -q "yes" result.log; then
    write_ok
else
    write_nok result.log
fi

# --- Cleanup ---
cubrid server stop $dbname
cubrid deletedb $dbname
rm -f result.log
finish
