#!/bin/bash
# Vendored from tw-kang/skills@develop (0cb5ba2), cubrid-shell-tc-create/examples/utility_test.sh
# CBRD-99003: Verify backupdb and restoredb work correctly for a small database
# Creates a DB with data, performs backup, drops a table, restores,
# and verifies that the data is intact after restore.

. $init_path/init.sh
init test

dbname=backup_restore_db

# --- Setup ---
cubrid_createdb $dbname
cubrid server start $dbname
if [ $? -ne 0 ]; then
    write_nok "Failed to start server"
    cubrid deletedb $dbname
    finish
fi

# Insert test data
csql -udba "$dbname" <<'EOF'
CREATE TABLE t_backup (id INT, msg VARCHAR(200));
INSERT INTO t_backup VALUES (1, 'before_backup');
INSERT INTO t_backup VALUES (2, 'checkpoint_data');
EOF

# --- Test: backup ---
cubrid backupdb -S "$dbname" > backup.log 2>&1
if [ $? -ne 0 ]; then
    write_nok backup.log
    cubrid server stop $dbname
    cubrid deletedb $dbname
    rm -f backup.log
    finish
fi

# Modify data after backup (this should be lost after restore)
csql -udba "$dbname" -c "INSERT INTO t_backup VALUES (3, 'after_backup')"

# Stop server for restore
cubrid server stop $dbname

# --- Test: restore ---
cubrid restoredb "$dbname" > restore.log 2>&1
if [ $? -ne 0 ]; then
    write_nok restore.log
    cubrid deletedb $dbname
    rm -f backup.log restore.log
    finish
fi

# Restart and verify
cubrid server start $dbname
csql -udba "$dbname" -c "SELECT COUNT(*) FROM t_backup" > result.log 2>&1
format_csql_output result.log

# --- Verify: should have 2 rows (not 3, since row 3 was after backup) ---
row_count=$(grep -o '[0-9]\+' result.log | tail -1)
if [ "$row_count" = "2" ]; then
    write_ok
else
    write_nok result.log
fi

# --- Cleanup ---
cubrid server stop $dbname
cubrid deletedb $dbname
rm -f backup.log restore.log result.log
finish
