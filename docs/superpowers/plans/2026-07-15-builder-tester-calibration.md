# CBRD-26893 calibration run (manual, gated)

End-to-end proof of `verify_testcase.py` against a known real fix. Consumes
builder/tester capacity — run once, with user confirmation.

## Inputs
- Draft: the CBRD-26893 v3 shell TC (SIGSEGV on `IS NOT NULL` folding over
  db_class). Stage it so the entry script and its helpers sit together in a
  `cases/` dir; point `--script` at `cbrd_26893.sh`.
- Engine PR: the CUBRID/cubrid PR that fixed CBRD-26893 (or `--issue CBRD-26893`).

## Steps
1. `bash -lc 'export GITHUB_TOKEN; python3 $COMMON/scripts/verify_testcase.py \
   run --script <path>/cbrd_26893.sh --issue CBRD-26893'`  (dry-run — inspect
   the elided payload and the echoed pre/post pair with subjects)
2. Re-run with `--yes` after confirming the pair.
3. Expected verdict: **VERIFIED** — pre-fix build crashes (Test 1 exit ≠ 0 /
   Test 2 new coredump → NOK), post-fix build passes all three tests.
4. If FLAKY: the crash may not reproduce deterministically in Docker → re-run
   with `--special-case core-dump` and record the caveat.

## Record
Capture the verdict block (incl. the direct log URLs and the `Verified:` line)
and the report id. This both validates the tool and discharges the outstanding
runtime verification of the CBRD-26893 TC.
