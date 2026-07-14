-- Vendored from tw-kang/skills@develop (0cb5ba2), cubrid-sql-tc-create/examples/bug_fix_select.sql
/**
 * This test case verifies CBRD-26058: Fix error in CASE expression with logical type
 *
 * Coverage:
 * 1 - CASE with mixed integer THEN and NULL ELSE branches
 * 2 - CASE where THEN returns boolean literals
 * 3 - CASE in WHERE clause with subquery
 */

DROP TABLE IF EXISTS tbl1;
CREATE TABLE tbl1 (col1 INT, col2 VARCHAR(20));
INSERT INTO tbl1 VALUES (1, 'apple'), (2, 'banana'), (3, NULL);

evaluate 'Case 1: CASE with integer THEN and NULL ELSE';
SELECT col1,
    CASE
        WHEN col1 = 1 THEN 100
        WHEN col1 = 2 THEN 200
        ELSE NULL
    END AS result
FROM tbl1
ORDER BY col1;

evaluate 'Case 2: CASE THEN TRUE / FALSE';
SELECT col1,
    CASE
        WHEN col1 > 1 THEN TRUE
        ELSE FALSE
    END AS is_big
FROM tbl1
ORDER BY col1;

evaluate 'Case 3: CASE in WHERE filters correctly';
SELECT col1, col2
FROM tbl1
WHERE
    CASE
        WHEN col1 IN (SELECT 1 FROM db_root) THEN TRUE
        ELSE FALSE
    END = TRUE;

DROP TABLE IF EXISTS tbl1;
