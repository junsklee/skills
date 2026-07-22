#!/bin/bash
# Read-only Builder-Tester check. Submits NOTHING. Exercises the four §10
# read paths: /health, /api/builder/health, /api/reports, one attempt-log.
set -u
here=$(cd "$(dirname "$0")/.." && pwd)
echo "== health =="
python3 "$here/verify_testcase.py" health || exit 1
echo "== reports + one attempt log =="
python3 - "$here" <<'PY'
import sys, os
sys.path.insert(0, sys.argv[1])
import btlib
data = btlib.bt_request("/api/reports?pageSize=25")
assert "items" in data, data
print("reports OK: totalItems=%s" % data.get("totalItems"))
for item in data.get("items", []):
    for r in item.get("results", []):
        meta = r.get("attemptLogMetadata") or []
        if meta and meta[0].get("logFileName"):
            fn = meta[0]["logFileName"]
            txt = btlib.bt_get_text("/api/log/%s/tests/%s" % (item["id"], fn))
            assert txt, "empty log"
            print("attempt-log OK: %s/%s (%d bytes)" % (item["id"], fn, len(txt)))
            sys.exit(0)
print("no attempt log available to sample (reports have no results yet)")
PY
echo "== sql report + artifact (read-only) =="
python3 - "$here" <<'PY'
import sys, os
sys.path.insert(0, sys.argv[1])
import btlib
data = btlib.bt_request("/api/reports?pageSize=50")
sqlrep = next((it for it in data.get("items", []) if it.get("testType") == "sql"), None)
if not sqlrep:
    print("no SQL report available to sample yet (ok)"); sys.exit(0)
print("sql report:", sqlrep["id"])
for r in sqlrep.get("results", []):
    for a in r.get("attemptLogMetadata", []):
        if a.get("artifactType") and a.get("logFileName"):   # artifact, not a plain log
            txt = btlib.bt_get_text("/api/log/%s/tests/%s" % (sqlrep["id"], a["logFileName"]))
            assert txt is not None, "empty artifact"
            print("sql artifact OK: %s %s (%d bytes)"
                  % (a["artifactType"], a["logFileName"], len(txt)))
            sys.exit(0)
print("SQL report has no artifact to sample (ok)")
PY
