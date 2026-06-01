# Examples

## Example 1: verifier form state bug

Title:
`Verify Test Case 재진입 시 Reason 표시값 불일치 수정`

*Description*
`Verify Test Case` 재진입 시 저장된 Reason 값과 화면 선택 상태 불일치 발생.
- 저장값이 `revise required`여도 `Test Case`가 선택된 상태로 노출
- 재검토 시 잘못된 상태 인지 가능

*Suggested Changes*
Reason 렌더링 조건을 저장값 기준으로 정리 필요.
- 단일 케이스 폼의 radio checked 조건 정합성 맞춤
- 기본 선택값은 미설정 상태에서만 적용

*Acceptance Criteria*
저장된 Reason 값과 재진입 화면 선택 상태 일치.
- `verify_reason_kind=1` 재진입 시 `revise required` 정상 선택
- 미설정 항목은 기존 기본값 흐름 유지

## Example 2: fail-result pagination

Title:
`Verify Status 그룹별 페이지네이션 적용`

*Description*
`showFailResult.nhn`에서 전역 LIMIT 적용으로 일부 카테고리 미노출 발생.
- 상위 row만 조회되어 뒤쪽 그룹 누락
- 대량 결과에서 카테고리별 후속 페이지 접근 불가

*Suggested Changes*
그룹 목록 조회와 그룹별 페이지 조회 경로 분리 필요.
- 그룹 키 목록을 먼저 조회
- 그룹별 `limit/offset`으로 부분 렌더링 적용

*Acceptance Criteria*
카테고리 누락 없이 그룹별 페이지 이동 가능.
- 모든 예상 그룹 노출
- 각 그룹의 페이지 이동이 다른 그룹 상태에 영향 없음

## Example 3: memo feature split style

Title:
`Performance 탭 메모 저장 경로 및 Compare 렌더링 연동`

*Description*
성능 섹션 메모가 조회, 저장, compare 렌더링 경로에서 일관되게 연결되지 않음.
- 섹션별 메모 필드 전달 경로 누락 가능
- compare row에서 memo 셀 정렬 불일치 가능

*Suggested Changes*
메모 필드 전달과 compare 렌더링 경로를 같은 기준으로 정리 필요.
- action, DAO, sqlmap, JSP의 메모 필드 경로 일치
- compare row와 ratio row의 컬럼 수 정합성 유지

*Acceptance Criteria*
메모 저장과 compare 렌더링 경로 일관성 확보.
- 섹션별 메모 저장 정상
- compare row 추가 후 컬럼 밀림 없음
