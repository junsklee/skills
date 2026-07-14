#!/bin/bash
# Vendored from tw-kang/skills@develop (0cb5ba2), cubrid-shell-tc-create/examples/output_comparison.sh
# CBRD-99004: Verify SHOW INDEX output format for composite index
# Creates a table with a composite index, captures SHOW INDEX output,
# normalizes it, and compares against expected output.

. $init_path/init.sh
init test

dbname=show_index_db

# --- Setup ---
cubrid_createdb $dbname
cubrid server start $dbname
if [ $? -ne 0 ]; then
    write_nok "Failed to start server"
    cubrid deletedb $dbname
    finish
fi

# Create table with composite index
csql -udba "$dbname" <<'EOF'
CREATE TABLE t_idx (
    id INT,
    name VARCHAR(100),
    score INT
);
CREATE INDEX idx_name_score ON t_idx (name, score);
EOF

# --- Test: capture index info ---
csql -udba "$dbname" -c "SHOW INDEX IN t_idx" > result.log 2>&1
format_csql_output result.log

# --- Verify: check key columns are present in index output ---
has_name=$(grep -c "name" result.log)
has_score=$(grep -c "score" result.log)
has_idx_name=$(grep -c "idx_name_score" result.log)

if [ "$has_name" -ge 1 ] && [ "$has_score" -ge 1 ] && [ "$has_idx_name" -ge 1 ]; then
    write_ok
else
    write_nok result.log
fi

# --- Cleanup ---
cubrid server stop $dbname
cubrid deletedb $dbname
rm -f result.log
finish
