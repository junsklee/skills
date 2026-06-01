---
name: maintain-qaresult-enhance
description: Maintain and deploy `~/cubrid-testtools-internal/qaresult_enhance` for the local QAHome stack. Use when Codex needs to fix or add QAHome result features, especially WebWork actions, iBatis SQL maps, DAO changes, JSP/AJAX fragments, Verify Status or fail-result flows, Function or Performance tab behavior, memo or pagination features, JSP error investigations, auto-refresh result-handler hardening, or local sync/build/restart work for `~/qaresult_en`.
---

# Maintain QAResult Enhance

## Overview

Work in `~/cubrid-testtools-internal/qaresult_enhance`, but treat `~/qaresult_en` as the local runtime tree. Use this skill for source edits, local deploy sync, and regression checks in the legacy QAHome stack.

## Quick Routing

- Function tab or summary pages: open `references/repo-map.md`, then the Function sections in `references/change-playbooks.md`.
- Performance tab, compare rows, memo, or verified state: open `references/change-playbooks.md`.
- Verify Status, fail-result, verifier form, or JIRA/reporting: open both `references/repo-map.md` and `references/change-playbooks.md`.
- Auto-refresh or result-ingestion handlers: open `references/change-playbooks.md`.
- Local deploy or restart work: open `references/deployment.md` and use `scripts/deploy-local-qahome.sh`.
- Validation or regression planning: open `references/validation.md`.

## Working Model

- Edit source under `~/cubrid-testtools-internal/qaresult_enhance`.
- Do not hand-edit `~/qaresult_en` except through the deploy workflow.
- The running local server uses `~/qaresult_en` plus env-specific overlays copied from a selected `qaresult_en_*` snapshot.
- If the user does not name the env snapshot directory and several candidates exist, inspect the local `qaresult_en_*` directories and ask before deploying. Do not guess.

## Change Workflow

1. Inspect the entrypoint and the full path from WebWork mapping to action, DAO/sqlmap, and JSP.
2. Keep changes aligned with the existing legacy stack: WebWork/XWork actions, iBatis SQL maps, Lucy `DataMap`, server-rendered JSP fragments, and jQuery-based reloads.
3. Prefer minimal cross-layer changes that keep existing URLs, parameter names, and table shapes stable.
4. For compare rows and AJAX fragments, verify both the initial page render and the reload/update path.
5. For memory or large-result changes, preserve guardrails that cap query   ze, page size, or repeated retries.

## Deploy Workflow

- Use `scripts/deploy-local-qahome.sh --env-source /abs/path/to/qaresult_en_*` for the normal local deploy path.
- Use `--dry-run` first when the env snapshot is unclear or when you only need to confirm the command sequence.
- The script copies the repo tree into `~/qaresult_en`, restores the env-specific config/build files, runs `ant` inside the runtime tree, and restarts `~/apache-tomcat-8.5.4`.

## Validation

- Use `ant dist` in the repo tree for fast compile feedback when useful.
- Treat the real verification path as: deploy into `~/qaresult_en`, build there, restart Tomcat, and load the affected screen or endpoint.
- After restart or runtime errors, inspect `~/apache-tomcat-8.5.4/logs/`.

## References

- `references/repo-map.md`: file routing and subsystem map.
- `references/change-playbooks.md`: common change patterns and recent commit anchors.
- `references/deployment.md`: runtime tree, env overlay, exact copy order, and deploy script usage.
- `references/validation.md`: compile, regression, and runtime-check guidance.
