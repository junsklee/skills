# CPTP Integration Notes

Use this only when the TPCH task crosses into `~/cubrid-perftools-internal/cptp` or the QAHome resource/config detail page.

## QAHome expects two separate inputs

For TPCH `detail -> view` resource/config display, QAHome needs:

- monitor files under `web/monitor`
- config text rows in `general_test_log`

It does not derive those automatically from `tpch_items` or `tpch_items_his`.

## Key identifiers

- `key=tpch`
- `mainId=tpch_<main_id>_<test_build>`
- `msgId=<tpch_power_test.msg_id or tpch_thput_test.msg_id>`
- `general_test_log.src_id = msgId`

## Important QAHome files

- `showPerformance.jsp`
- `PerformanceManageAction.java`
- `ShowResourceMonitorDataAction.java`
- `showResourceUtilizationAndTestConfigurationAction.java`

## CPTP side expectation

The CPTP developer usually does not need a brand-new framework path. Reuse the existing benchmark pattern for:

- `msg_id` persistence
- `general_test_log` inserts
- monitor start/stop/data/graph/upload flow

The TPCH-specific parts are mostly:

- TPCH table names
- monitor folder prefix `tpch`
- `tpch_<main_id>_<test_build>` run folder naming
- TPCH result inserts into `tpch_*` tables

## Existing handoff artifact

A session-created guide exists locally at:

- `qaresult_enhance/doc/tpch_cptp_qahome_resource_integration_guide.md`

That file may be untracked. Use it only when present and relevant.
