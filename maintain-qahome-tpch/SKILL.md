---
name: maintain-qahome-tpch
description: Maintain TPCH-related QAHome code under `~/cubrid-testtools-internal/qaresult_enhance`. Use when Codex needs to fix or extend TPCH Performance-tab behavior, TPCH schema/docs alignment, TPCH chart or failed/history drilldown logic, TPCH SQL map queries, TPCH pass/fail or elapsed semantics, or production issue triage involving `tpch_*` tables, `tpch_items`, `tpch_items_his`, or TPCH-specific CUBRID SQL logs.
---

# Maintain QAHome TPCH

## Overview

Use this skill for QAHome TPCH reader/viewer work in the legacy WebWork + iBatis stack. It covers the TPCH-specific file hotspots, current schema/runtime split, common change patterns, and production triage points that repeatedly caused regressions in this repo.

## Quick Start

1. Work in `~/cubrid-testtools-internal/qaresult_enhance`.
2. Before changing TPCH semantics, read `references/runtime-model.md` and `references/file-map.md`.
3. If the work touches charts, compare rows, history drilldowns, or pass/fail columns, also read `references/change-playbook.md`.
4. If the task comes from a production SQL log or DB-only symptom, read `references/triage.md` first.
5. If the request involves CPTP resource/config integration, read `references/cptp-integration.md`.

## Working Rules

- Treat TPCH as a specialized slice of QAHome, not a generic performance table.
- Prefer minimal diffs against `develop`; TPCH merge conflicts cluster in `PerformanceManageAction`, `com.nhncorp.qaresult.xml`, and `showPerformance.jsp`.
- Do not assume Power and Throughput share the same persistence or viewer semantics; verify the current runtime model first.
- If local TPCH docs exist in the worktree, such as `qaresult_enhance/AGENTS.md` or `qaresult_enhance/doc/doc/features/tpch/README.md`, read them before changing behavior. Those files may be untracked but still authoritative for the current branch.
- For production issues, distinguish between:
  - a query emitted by QAHome source in this repo
  - a manual/ad hoc SQL statement found in CUBRID logs
  - a CPTP writer-side data problem

## Default Workflow

1. Identify the entrypoint and affected slice from `references/file-map.md`.
2. Confirm the runtime semantics in `references/runtime-model.md`.
3. Choose the smallest change set that fixes the bug or aligns the docs.
4. Update source and docs together when behavior or schema meaning changes.
5. Validate with:
   - `git diff --check`
   - `ant -f ~/cubrid-testtools-internal/qaresult_enhance/build.xml compile resource`
6. For production triage, keep read-only verification queries separate from source changes.

## References

- `references/file-map.md`: TPCH hotspot files and what each one owns.
- `references/runtime-model.md`: current TPCH canonical/history model, Power vs Throughput distinctions, and naming gotchas.
- `references/change-playbook.md`: common change patterns for tables, charts, history drilldowns, docs, and minimal-diff strategy.
- `references/triage.md`: production issue workflow, SQL-log interpretation, and known TPCH failure patterns.
- `references/cptp-integration.md`: QAHome <-> CPTP integration points for monitor resources, `msg_id`, and `general_test_log`.
