# Generic rules for categories without loaded doctrine

Used when the PR touches CTP categories other than sql/medium/shell. The
review still runs the core process (review-core.md), but the review MUST
include an explicit flag immediately after the verdict line, in Korean, e.g.:

```
⚠️ 이 PR 은 전용 리뷰 규칙이 없는 카테고리(<dirs>)를 포함합니다.
   일반 체크리스트만 적용했으므로 카테고리 관례 위반은 놓칠 수 있습니다.
```

## Category identification hints

| Tree / extension | Category | Notes |
|---|---|---|
| `.ctl` files | isolation | multi-client isolation-level scenarios |
| JUnit 4 `@Test` Java | jdbc | JUnit conventions apply |
| `.c` with CCI calls + driver script | cci | compiled client tests |
| `.sql` with `--test:` / `--check:` markers | ha_repl / cdc_repl | master/slave semantics |
| `make_ha.sh`-based `.sh` | ha_shell | HA lifecycle differs from plain shell |
| C/C++ sources under a unittest tree | unittest | engine-level unit tests |

## Generic checklist (applies to every category)

- Changed files form a complete, internally consistent package (scripts,
  inputs, answers, helpers all referenced and name-matched).
- Setup creates what it needs; cleanup removes exactly what was created and
  restores settings; safe after partial failure.
- Output is deterministic (ordering, timestamps, ids, paths normalized).
- Expected results semantically match the JIRA intent; error codes exact.
- The test can distinguish patched from unpatched behavior.
- No effect on unrelated tests or global services.

Anything category-specific that looks suspicious should be reported as a
QUESTION rather than a definitive finding, citing the lack of loaded rules.
