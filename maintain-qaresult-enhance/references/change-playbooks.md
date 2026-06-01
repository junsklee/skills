# Change Playbooks

## Verify Status and fail-result

Key files:
- `src/java/com/nhncorp/qaresult/action/verifyFailcase/ShowFailResultAction.java`
- `src/java/com/nhncorp/qaresult/dao/VerifyItemDAO.java`
- `src/java/com/nhncorp/qaresult/dao/VerifyItemDAOImpl.java`
- `src/sqlmap/com.nhncorp.qaresult.xml`
- `web/WEB-INF/jsp/verify_fail_case/showFailCaseResult.jsp`
- `web/WEB-INF/jsp/verify_fail_case/showCaseResultItem.jsp`
- `web/WEB-INF/jsp/verify_fail_case/showSelectedOne.jsp`
- `web/WEB-INF/jsp/verify_fail_case/_verifyStatusGroup.jsp`

Watch for:
- global limit or offset applied before grouping
- paging state lost during AJAX reload
- sort handlers breaking after fragment replacement
- query-size or show-all changes that can regress OOM guardrails

Recent anchors:
- `05a9a517`: fail-result paging, OOM safety, grouped fragment updates
- `db963eb0`: verifier form behavior regression fix

## Function tab and summary pages

Key files:
- `src/java/com/nhncorp/qaresult/action/ShowFunctionalReportAction.java`
- `src/java/com/nhncorp/qaresult/action/ShowFunctionSummaryReportAction.java`
- `src/java/com/nhncorp/qaresult/action/SummaryReportbyNowAction.java`
- `web/WEB-INF/jsp/showres/showFunctionSummary.jsp`
- `web/WEB-INF/jsp/showFunctionReport.jsp`
- `web/WEB-INF/jsp/main/left_main.jsp`

Watch for:
- build-level data that must stay independent from performance rows
- AJAX handler and tooltip flows that need stale-request protection
- summary or JSP runtime failures caused by missing bundle keys or tag mistakes

Recent anchors:
- `f7e86a9c`: build memo and left-tree hover memo flow

## Performance tab and compare rows

Key files:
- `src/java/com/nhncorp/qaresult/action/PerformanceManageAction.java`
- `src/java/com/nhncorp/qaresult/dao/QaResultDAO.java`
- `src/java/com/nhncorp/qaresult/dao/QaResultDAOImpl.java`
- `src/sqlmap/com.nhncorp.qaresult.xml`
- `web/WEB-INF/jsp/showPerformance.jsp`

Watch for:
- memo field propagation across select, compare, and update paths
- column-count drift between base rows, compare rows, and ratio rows
- numeric ID parsing problems on larger row IDs
- section-specific differences between `id` and `main_id`

Recent anchors:
- `f7e86a9c`: memo/verified UI, compare alignment, new YCSB coverage

## JIRA/reporting and verifier form

Key files:
- `src/java/com/nhncorp/qaresult/action/verifyFailcase/ReportNewIssueAction.java`
- `src/java/com/nhncorp/qaresult/action/verifyFailcase/ReportAsCommentAction.java`
- `web/WEB-INF/jsp/verify_fail_case/reportNewIssue.jsp`
- `web/WEB-INF/jsp/verify_fail_case/reportAsComment.jsp`
- `web/WEB-INF/jsp/verify_fail_case/verifierForm.jsp`

Watch for:
- required-field enforcement and default assignee behavior
- existing issue vs new issue flow divergence
- commit-list loading and selected-commit formatting
- browser-history or radio-button state regressions in verifier form

Recent anchors:
- `ad2311ae`: commit-aware JIRA/reporting automation
- `db963eb0`: reason radio-button selection fix

## Auto-refresh and result handlers

Key files:
- `src/java/com/nhncorp/qaresult/bo/impl/FunctionResultHandleImpl.java`
- `src/java/com/nhncorp/qaresult/bo/impl/CCIForSQLHandleImpl.java`
- `src/java/com/nhncorp/qaresult/bo/impl/MemoryleakResultHandleImpl.java`

Watch for:
- retry loops on missing files or empty directory listings
- downstream processing continuing after failed inserts
- noisy logs inside tight retry paths

Recent anchors:
- `ab1611ad`: function and sql_by_cci auto-refresh hardening
- `f2d9afbf`: coverage auto-refresh heap growth fix
