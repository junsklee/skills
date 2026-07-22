# SQL verification calibration (manual, gated)

End-to-end proof of `verify_testcase.py --test-type sql` against an
already-merged SQL TC — ground-truth for the derivation path and the first
real `debug`-buildType SQL submission. Consumes builder capacity; run once
with user confirmation.

## Inputs
- An already-merged SQL TC whose answer actually CHANGED with a known engine
  fix, e.g. CBRD-26900 (engine PR CUBRID/cubrid#7269). Fetch the case `.sql`
  and its committed `answers/<name>.answer` from CUBRID/cubrid-testcases into
  a scratch dir (`fetch_context.py get`, both `cases/` and `answers/`).

## Steps
1. **Derivation ground-truth:** `verify_testcase.py derive-answer --test-type
   sql --script <scratch>/cases/<name>.sql --issue CBRD-26900` (dry-run, then
   `--yes`). The derived `answers/<name>.answer` must match the repo's
   committed answer (newline-level differences tolerated per the server's
   comparison rules; intra-line whitespace must match). A mismatch is a real
   finding — investigate before trusting derivation.
2. **Pre/post verify (debug build):** `verify_testcase.py run --test-type sql
   --script <scratch>/cases/<name>.sql --issue CBRD-26900` → expect
   **VERIFIED** (pre-fix answer mismatch/`fail`, post-fix `pass`). This is the
   first real `buildType=debug` SQL run — confirm it builds and reports
   normally. If the case's answer did NOT change with the fix it will be
   NOT-VERIFIED — pick a TC whose answer actually changed.

## Record
Capture the verdict block + report id. Validates SQL request assembly,
artifact-based derivation, and the shared verdict path against ground truth,
and confirms debug-buildType SQL works.
