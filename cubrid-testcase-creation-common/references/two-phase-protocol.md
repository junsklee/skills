# Two-phase creation protocol (shared contract)

Both creation skills follow this protocol. State lives in GitHub, not on
disk: the fork branch `cbrd_NNNNN_tc` is the single source of truth.

## Phase detection

Run `push_package.py status --upstream <repo> --fork-owner junsklee
--branch cbrd_NNNNN_tc`:

| branch_exists | empty_answers | pr | Phase |
|---|---|---|---|
| false | — | — | Phase 1 (fresh draft) |
| true | non-empty | null | Phase 2 (answers pending) |
| true | empty list | null | Phase 2, step 3 (ready for PR) |
| true | — | number | DONE — point the user at the PR; stop |

Footnotes: `empty_answers` and `package_files` are computed from the
branch-vs-base compare (package scope only). A `pr` with `pr_state`
closed/merged also means DONE — never open a duplicate PR. Phase detection
is advisory: sanity-check `package_files` against the expected package
before acting.

If the branch exists but the user asked for a fresh draft, offer:
resume (phase 2) / overwrite (`push --update`, only with explicit consent) /
abort. NEVER force-push or overwrite silently.

## Execution policy (host-conditional)

`CUBRID_TC_ALLOW_LOCAL_CTP=1` in the environment enables local answer
generation via `verify-procedure.md`. Flag absent → static-only: seeded
empty answers + printed verify handoff. On the QAHome development host the
flag must never be set (production CUBRID lives there); the deployment
machine sets it deliberately.

## Confirmation gates (both are hard gates)

1. **Push gate** — nothing is pushed to the fork until the user explicitly
   approves the rendered package in this conversation.
2. **PR gate** — no PR is opened until the user explicitly approves the
   rendered Korean PR body. `push_package.py` is dry-run by default; `--yes`
   only after the corresponding gate.

## Verify handoff (printed at end of phase 1 when answers are empty)

```
검증 필요 — 테스트 장비에서:
1. (없다면) CTP 설치 및 빌드 설치 — verify-procedure.md 참고
2. cubrid-sql-tc-verify 또는 cubrid-shell-tc-verify 스킬로
   <branch의 testcase 경로> 를 실행해 .answer 생성/검증
3. 생성된 .answer(.result) 파일을 가지고 동일 스킬을 다시 호출하면
   Phase 2(답지 검증 → 커밋 → PR)로 이어집니다.
```

## PR conventions (phase 2, step 3)

- Title: `[CBRD-NNNNN] <English description>`.
- Body: Korean; line 1 exactly `Refer to: http://jira.cubrid.org/browse/CBRD-NNNNN`;
  then scenario/coverage summary and the verification evidence the user
  supplied (build id, pass output).
- Base `develop`, head `junsklee:cbrd_NNNNN_tc`, upstream CUBRID repo.
