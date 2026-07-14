#!/bin/bash
# Vendored from tw-kang/skills@develop (0cb5ba2), cubrid-shell-tc-create/examples/basic_entry.sh
# CBRD-99001: Verify INSERT ON DUPLICATE KEY UPDATE works correctly
# Creates a table with unique constraint, inserts duplicate key,
# and verifies that the existing row is updated instead of error.

. $init_path/init.sh
init test

dbname=dup_update_db

# --- Setup ---
cubrid_createdb $dbname
cubrid server start $dbname
if [ $? -ne 0 ]; then
    write_nok "Failed to start server"
    cubrid deletedb $dbname
    finish
fi

# --- Test: INSERT ON DUPLICATE KEY UPDATE ---
csql -udba "$dbname" <<'EOF'
CREATE TABLE t1 (
    id INT PRIMARY KEY,
    val VARCHAR(100),
    cnt INT DEFAULT 0
);

INSERT INTO t1 VALUES (1, 'initial', 0);
INSERT INTO t1 VALUES (1, 'updated', 1) ON DUPLICATE KEY UPDATE val='updated', cnt=cnt+1;
EOF

# Capture result
csql -udba "$dbname" -c "SELECT id, val, cnt FROM t1 WHERE id=1" > result.log 2>&1
format_csql_output result.log

# --- Verify ---
cnt_check=$(grep -c "updated" result.log)
if [ "$cnt_check" -ge 1 ]; then
    write_ok
else
    write_nok result.log
fi

# --- Cleanup ---
cubrid server stop $dbname
cubrid deletedb $dbname
rm -f result.log
finish
