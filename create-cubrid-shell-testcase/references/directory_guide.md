<!-- Vendored from tw-kang/skills@develop (0cb5ba2), cubrid-shell-tc-create/references/directory_guide.md. Refresh from upstream; do not fork content silently. -->
# Shell Testcase Directory Structure Guide

## Base Path

All shell test cases live under:
```
cubrid-testcases-private-ex/shell/
```

## Directory Pattern

```
shell/{category}/{test_name}/cases/{test_name}.sh
```

The directory name and script filename must always match.

## Categories

### New Features

Path pattern:
```
shell/_{no}_{release_code}/{feature_group}/
```

Within the feature group, each test case follows:
```
{test_name}/cases/{test_name}.sh
```

Example:
```
shell/_35_cherry/issue_21506_online_index/cbrd_21506_backupdb/cases/cbrd_21506_backupdb.sh
```

### Bug Fixes (Issues)

Path pattern:
```
shell/_06_issues/_{yy}_{1|2}h/{test_name}/cases/{test_name}.sh
```

- `{yy}` = two-digit year (e.g., 19, 24, 26)
- `{1|2}h` = first half (1h) or second half (2h) of the year

Example:
```
shell/_06_issues/_19_2h/cbrd_22586/cases/cbrd_22586.sh
shell/_06_issues/_24_1h/cbrd_25301/cases/cbrd_25301.sh
shell/_06_issues/_26_1h/cbrd_27000/cases/cbrd_27000.sh
```

### Multiple Tests for Same Issue

Append a numeric suffix or descriptive keyword:
```
cbrd_xxxxx_1/cases/cbrd_xxxxx_1.sh
cbrd_xxxxx_2/cases/cbrd_xxxxx_2.sh
cbrd_xxxxx_{keyword}/cases/cbrd_xxxxx_{keyword}.sh
```

Example:
```
cbrd_25301_online_backup/cases/cbrd_25301_online_backup.sh
cbrd_25301_offline_backup/cases/cbrd_25301_offline_backup.sh
```

## Excluded Lists

Tests can be excluded from regression by adding them to:
```
shell/config/daily_regression_test_excluded_list_linux.conf
shell/config/daily_regression_test_excluded_list_windows.conf
```

Format:
```
#CBRD-XXXXX (reason for exclusion)
shell/_06_issues/_18_1h/bug_bts_12583
```

## Helper Scripts

Helper scripts can be placed alongside the entry script in the `cases/` directory:
```
test_name/cases/test_name.sh          # entry script
test_name/cases/helper_util.sh        # helper script
```

Helpers do NOT own the lifecycle — they are called by the entry script.
