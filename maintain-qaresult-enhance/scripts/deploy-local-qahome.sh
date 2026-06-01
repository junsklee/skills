#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  deploy-local-qahome.sh --env-source /abs/path/to/qaresult_en_* [--dry-run]

Behavior:
  1. Copy ~/cubrid-testtools-internal/qaresult_enhance/* into ~/qaresult_en/
  2. Restore env-specific config/build files from the selected env snapshot
  3. Run Tomcat shutdown
  4. Run ant inside ~/qaresult_en
  5. Run Tomcat startup
EOF
}

ENV_SOURCE=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-source)
      [[ $# -ge 2 ]] || { echo "Missing value for --env-source" >&2; usage >&2; exit 1; }
      ENV_SOURCE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

[[ -n "$ENV_SOURCE" ]] || { echo "--env-source is required" >&2; usage >&2; exit 1; }

SOURCE_REPO="${HOME}/cubrid-testtools-internal/qaresult_enhance"
RUNTIME_TREE="${HOME}/qaresult_en"
TOMCAT_DIR="${HOME}/apache-tomcat-8.5.4"

require_dir() {
  local dir="$1"
  [[ -d "$dir" ]] || { echo "Required directory not found: $dir" >&2; exit 1; }
}

require_file() {
  local file="$1"
  [[ -f "$file" ]] || { echo "Required file not found: $file" >&2; exit 1; }
}

run_cmd() {
  if (( DRY_RUN )); then
    printf '+ '
    printf '%q ' "$@"
    printf '\n'
  else
    "$@"
  fi
}

run_in_dir() {
  local dir="$1"
  shift
  if (( DRY_RUN )); then
    printf '+ (cd %q && ' "$dir"
    printf '%q ' "$@"
    printf ')\n'
  else
    (
      cd "$dir"
      "$@"
    )
  fi
}

require_dir "$SOURCE_REPO"
require_dir "$RUNTIME_TREE"
require_dir "$ENV_SOURCE"
require_dir "$TOMCAT_DIR"
require_file "${TOMCAT_DIR}/bin/shutdown.sh"
require_file "${TOMCAT_DIR}/bin/startup.sh"
require_file "${ENV_SOURCE}/build.xml"
require_file "${ENV_SOURCE}/src/conf/constant.properties"
require_file "${ENV_SOURCE}/src/conf/datasource/sql-map-qaresult.properties"
require_file "${ENV_SOURCE}/src/conf/log4j.xml"
require_file "${ENV_SOURCE}/src/conf/mask_keywords.txt"

shopt -s dotglob nullglob
SOURCE_ITEMS=("${SOURCE_REPO}"/*)
shopt -u dotglob

(( ${#SOURCE_ITEMS[@]} > 0 )) || { echo "No files found under ${SOURCE_REPO}" >&2; exit 1; }

run_cmd cp -r "${SOURCE_ITEMS[@]}" "${RUNTIME_TREE}/"
run_cmd cp "${ENV_SOURCE}/src/conf/constant.properties" "${RUNTIME_TREE}/src/conf/constant.properties"
run_cmd cp "${ENV_SOURCE}/src/conf/datasource/sql-map-qaresult.properties" "${RUNTIME_TREE}/src/conf/datasource/sql-map-qaresult.properties"
run_cmd cp "${ENV_SOURCE}/src/conf/log4j.xml" "${RUNTIME_TREE}/src/conf/log4j.xml"
run_cmd cp "${ENV_SOURCE}/src/conf/mask_keywords.txt" "${RUNTIME_TREE}/src/conf/mask_keywords.txt"
run_cmd cp "${ENV_SOURCE}/build.xml" "${RUNTIME_TREE}/build.xml"
run_cmd "${TOMCAT_DIR}/bin/shutdown.sh"
run_in_dir "${RUNTIME_TREE}" ant
run_cmd "${TOMCAT_DIR}/bin/startup.sh"
