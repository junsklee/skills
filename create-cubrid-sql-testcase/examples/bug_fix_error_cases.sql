-- Vendored from tw-kang/skills@develop (0cb5ba2), cubrid-sql-tc-create/examples/bug_fix_error_cases.sql
/**
 * This test case verifies CBRD-26252: Procedure Call Policy Modification
 *
 * Coverage:
 * 1 - Valid CALL statement succeeds
 * 2 - CALL with INTO clause raises error
 * 3 - Procedure in SELECT raises error
 */

--+ server-message on

CREATE OR REPLACE PROCEDURE proc_test(arg1 INT) AS
BEGIN
    DBMS_OUTPUT.put_line('executed: ' || arg1);
END;

DROP TABLE IF EXISTS tbl1;
CREATE TABLE tbl1 (col1 INT, col2 VARCHAR(10));
INSERT INTO tbl1 VALUES (1, 'test');

evaluate 'Case 1: CALL procedure with IN parameter';
CALL proc_test(10);

evaluate 'Case 2: CALL with INTO clause should fail';
CALL proc_test(10) INTO :v;

evaluate 'Case 3: Procedure in SELECT list should fail';
SELECT col1, proc_test(col1) FROM tbl1;

DROP PROCEDURE proc_test;
DROP TABLE IF EXISTS tbl1;

--+ server-message off
