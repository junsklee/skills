-- Vendored from tw-kang/skills@develop (0cb5ba2), cubrid-sql-tc-create/examples/feature_query_plan.sql
/**
 * This test case verifies CBRD-25975: Malformed query hint handling with recompile
 *
 * Coverage:
 * 1 - Valid hint with recompile - query runs and plan is captured
 * 2 - Malformed hint is ignored gracefully, no crash
 * 3 - Unknown hint is silently ignored
 */

-- Note: cbrd_25975.queryPlan (empty file) must exist alongside this file
-- to enable query plan capture in the answer.

DROP TABLE IF EXISTS tbl_a;
CREATE TABLE tbl_a (col_a INT);
INSERT INTO tbl_a VALUES (1);

evaluate 'Case 1: Valid recompile hint captures query plan';
SELECT /*+ recompile use_hash(tbl_a, tbl_a) */ * FROM tbl_a;

evaluate 'Case 2: Malformed hint is ignored, query executes normally';
SELECT /*+ recompile use_hash( ) */ * FROM tbl_a;

evaluate 'Case 3: Unknown hint is silently ignored';
SELECT /*+ recompile unknown_hint */ * FROM tbl_a;

DROP TABLE IF EXISTS tbl_a;
