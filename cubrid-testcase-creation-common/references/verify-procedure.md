<!-- Distilled from tw-kang/skills@develop (0cb5ba2) cubrid-sql-tc-verify/SKILL.md + cubrid-shell-tc-verify/SKILL.md. -->
# Verify procedure — answer generation and pass/fail on a CTP host

Dual use: (a) the runbook the skills execute locally when
`CUBRID_TC_ALLOW_LOCAL_CTP=1`; (b) the handoff instructions printed for a
test machine otherwise. NEVER run any of this on the QAHome development
host.

## Preconditions

- CTP at `$CTP_HOME` (env → `~/CTP` → `~/cubrid-testtools/CTP`). Sanity:
  `ls $CTP_HOME/bin/ctp.sh` (sql) / `ls $CTP_HOME/shell/init_path/init.sh` (shell).
  Missing → `git clone https://github.com/CUBRID/cubrid-testtools.git && cp -rf cubrid-testtools/CTP ~/`.
- A CUBRID build URL for the binary under test.
- Work from a scratch dir: `work=$(mktemp -d)`.

## Install the build (both categories)

```bash
sh "$CTP_HOME/common/script/run_cubrid_install" <build_url> 2>&1 | tee "$work/install.log"
grep '\[ERROR\]' "$work/install.log"        # any hit -> stop, show lines
source ~/.cubrid.sh && cubrid_rel            # must print a version
```
`run_cubrid_install` can return 0 on failure and wipes `$HOME/CUBRID` first —
trust the binary, not the exit code.

## SQL cases

1. Locale lib (DB startup fails without it) and a real JDK (CTP compiles
   Java SP classes; `which java` may be a JRE):
   ```bash
   export JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java))))
   [ -x "$JAVA_HOME/bin/javac" ] || JAVA_HOME=$(dirname "$JAVA_HOME")
   [ ! -f $CUBRID/lib/libcubrid_all_locales.so ] && sh $CUBRID/bin/make_locale.sh -t 64bit
   ```
2. Category → conf → run command: `sql` → `sql.conf` → `run`; path contains
   `/medium/` → `medium_dev.conf` → `run`; `sql_by_cci` → `sql_by_cci.conf`
   → `run_cci`.
3. Structure: the `.sql` must sit in `cases/` with a sibling `answers/`.
   **Seed an empty `answers/<name>.answer` first** — interactive `run`
   silently SKIPS a case with no answer file (`Total:1 / Success:0 / Fail:0`).
4. Execute (DB setup takes 1–3 min):
   ```bash
   printf "%s %s\nquit\n" "run" "$SQL_FILE" | \
     timeout 600 "$CTP_HOME/bin/ctp.sh" sql -c "$CTP_HOME/conf/sql.conf" --interactive 2>&1 | tee "$work/run.log"
   ```
5. Verdict: `RESULT_DIR=$(grep "^Result Root Dir" "$work/run.log" | head -1 | awk -F': ' '{print $2}' | tr -d ' ')`;
   `cat "$RESULT_DIR/main.info"` — `Fail: 0` = PASS.
6. **Answer generation loop**: first run diffs against the empty answer
   (Fail:1) and writes real output to `$RESULT_DIR/.../<name>.result`.
   Promote it: copy over `answers/<name>.answer`, re-run, expect `Success:1`.
   Read the final `.answer` and confirm it matches intent (row counts,
   `Error:-NNN` codes, `===` statement separators).

## Shell cases

1. Locate `{name}/cases/{name}.sh`; read it first (platform guards, services).
2. Execute from the `cases/` dir with a timeout:
   ```bash
   export init_path="$CTP_HOME/shell/init_path"
   cd <case dir> && timeout 300 sh <name>.sh 2>&1 | tee "$work/run.log"; echo "exit=$?"
   ```
3. Verdict: `cat <case dir>/<name>.result` — `OK` = pass, `NOK` = fail
   (exit 124 = timeout = fail). On NOK: check `$work/run.log`,
   `$CUBRID/log/server/*.err`, core files.
4. Afterwards check leftovers (`cubrid server status`, `ps -ef | grep cub_`)
   and clean up.

## Classify a failure before touching the answer

- **answer-fix**: format/identifier-only diff (hash suffixes, XASL ids,
  plan text, byte counters) — regenerate the baseline.
- **bug-report**: crash/core, wrong result, lock change — file it with
  evidence; do NOT bake it into the `.answer`.

## Pitfalls

- "No Results!!" → wrong `.sql` path / not in a `cases/` dir.
- "Failed to connect to database server" → missing locale lib, port
  conflict, or disk full. "Cannot connect to a broker" → broker down/port
  33120 busy.
- "socket path is too long (>108)" → CUBRID installed too deep; use a short
  path like `~/CUBRID`.
- `javac not found` → JAVA_HOME points at a JRE (fix per SQL step 1).
- Answer file missing → the case is skipped, not run (SQL step 3).
