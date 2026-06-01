# Repo Map

## Core paths

- Source repo: `~/cubrid-testtools-internal/qaresult_enhance`
- Runtime tree: `~/qaresult_en`
- Env overlay candidates live under `~/qaresult_en_*`
- Local Tomcat: `~/apache-tomcat-8.5.4`

## Entry wiring and config

- `src/conf/xwork.xml`: main WebWork action mapping and result wiring
- `src/conf/applicationContext-bo.xml`: BO/action bean wiring
- `src/conf/constant.properties`: runtime flags, paging caps, URLs, and legacy constants
- `src/conf/datasource/sql-map-qaresult.xml`: sql-map registration
- `build.xml`, `build.properties`: local Ant flow

## Function and summary flow

- `src/java/com/nhncorp/qaresult/action/ShowFunctionalReportAction.java`
- `src/java/com/nhncorp/qaresult/action/ShowFunctionSummaryReportAction.java`
- `src/java/com/nhncorp/qaresult/action/SummaryReportbyNowAction.java`
- `web/WEB-INF/jsp/showres/showFunctionSummary.jsp`
- `web/WEB-INF/jsp/showFunctionReport.jsp`
- `web/WEB-INF/jsp/showSummaryReport.jsp`
- `web/WEB-INF/jsp/statShow.jsp`

Use this route for Function tab, summary report, build memo, and related AJAX handlers.

## Performance flow

- `src/java/com/nhncorp/qaresult/action/PerformanceManageAction.java`
- `src/java/com/nhncorp/qaresult/dao/QaResultDAO.java`
- `src/java/com/nhncorp/qaresult/dao/QaResultDAOImpl.java`
- `src/sqlmap/com.nhncorp.qaresult.xml`
- `src/java/com/nhncorp/qaresult/bean/TpcwResult.java`
- `src/java/com/nhncorp/qaresult/bean/DblinkResult.java`
- `web/WEB-INF/jsp/showPerformance.jsp`

Use this route for performance tables, compare rows, memo fields, verified state, and section-specific save handlers.

## Verify Status and fail-result flow

- `src/java/com/nhncorp/qaresult/action/verifyFailcase/ShowFailResultAction.java`
- `src/java/com/nhncorp/qaresult/action/verifyFailcase/ReportNewIssueAction.java`
- `src/java/com/nhncorp/qaresult/action/verifyFailcase/ReportAsCommentAction.java`
- `src/java/com/nhncorp/qaresult/dao/VerifyItemDAO.java`
- `src/java/com/nhncorp/qaresult/dao/VerifyItemDAOImpl.java`
- `web/WEB-INF/jsp/verify_fail_case/showFailCaseResult.jsp`
- `web/WEB-INF/jsp/verify_fail_case/showCaseResultItem.jsp`
- `web/WEB-INF/jsp/verify_fail_case/showSelectedOne.jsp`
- `web/WEB-INF/jsp/verify_fail_case/verifierForm.jsp`
- `web/WEB-INF/jsp/verify_fail_case/reportNewIssue.jsp`
- `web/WEB-INF/jsp/verify_fail_case/reportAsComment.jsp`

Use this route for paging, filters, verifier form behavior, JIRA/reporting flows, and partial reload fragments.

## Result handlers and background ingestion

- `src/java/com/nhncorp/qaresult/bo/impl/FunctionResultHandleImpl.java`
- `src/java/com/nhncorp/qaresult/bo/impl/CCIForSQLHandleImpl.java`
- `src/java/com/nhncorp/qaresult/bo/impl/MemoryleakResultHandleImpl.java`
- `src/java/com/nhncorp/qaresult/bo/impl/DotsResultHandleImpl.java`

Use this route for auto-refresh, filesystem ingestion, retry loops, and handler-side guardrails.

## Data layer shortcuts

- Most page work eventually lands in `src/sqlmap/com.nhncorp.qaresult.xml`
- Verify/fail-result work may also use `VerifyItemDAO*`
- Runtime datasource config lives in `src/conf/datasource/`

## Runtime-only files restored after deploy

- `build.xml`
- `src/conf/constant.properties`
- `src/conf/datasource/sql-map-qaresult.properties`
- `src/conf/log4j.xml`
- `src/conf/mask_keywords.txt`
