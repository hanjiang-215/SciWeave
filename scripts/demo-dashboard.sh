#!/usr/bin/env bash
# Bring up the SciWeave read-only dashboard against real data.
#
# Starts three processes and waits until each answers its health probe:
#   1. research-map dashboard source  (/api/dashboard/source/mapping)
#   2. dashboard-api                  (/api/dashboard/snapshot)
#   3. web-ui Vite dev server         (the page itself)
#
# Ports, hosts and the TerminusDB connection come from the environment. The seed
# step is idempotent; pass --reset-seed to rebuild the demo domain.
#
# Usage:
#   scripts/demo-dashboard.sh
#   scripts/demo-dashboard.sh --stop
#   scripts/demo-dashboard.sh --reset-seed
#
# NOTE: this shell variant mirrors scripts/demo-dashboard.ps1 but has only been
# exercised on the Windows host through the PowerShell version. Treat the first
# run on Linux/macOS as unverified until it is recorded in the ticket.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_PATH="$ROOT/scripts/.demo-dashboard.json"

MAP_DIR="$ROOT/sci-weave/centre-control/research-map"
DASH_DIR="$ROOT/sci-weave/centre-control/dashboard-api"
WEB_DIR="$ROOT/sci-weave/centre-control/web-ui"

setting() {
  local name="$1" fallback="$2"
  local value="${!name:-}"
  if [[ -z "${value// }" ]]; then printf '%s' "$fallback"; else printf '%s' "${value// /}"; fi
}

MAP_HOST="$(setting SCIWEAVE_MAPPING_DASHBOARD_HOST 127.0.0.1)"
MAP_PORT="$(setting SCIWEAVE_MAPPING_DASHBOARD_PORT 8701)"
DASH_HOST="$(setting SCIWEAVE_DASHBOARD_HOST 127.0.0.1)"
DASH_PORT="$(setting SCIWEAVE_DASHBOARD_PORT 8702)"
WEB_HOST="$(setting VITE_DEV_HOST 127.0.0.1)"
WEB_PORT="$(setting VITE_DEV_PORT 5173)"

export SCIWEAVE_MAPPING_TERMINUSDB_URL="$(setting SCIWEAVE_MAPPING_TERMINUSDB_URL http://127.0.0.1:6363)"
export SCIWEAVE_MAPPING_TERMINUSDB_STORE="$(setting SCIWEAVE_MAPPING_TERMINUSDB_STORE admin)"
export SCIWEAVE_MAPPING_TERMINUSDB_DATABASE="$(setting SCIWEAVE_MAPPING_TERMINUSDB_DATABASE sciweave_dashboard_demo)"
export SCIWEAVE_MAPPING_TERMINUSDB_USERNAME="$(setting SCIWEAVE_MAPPING_TERMINUSDB_USERNAME admin)"
export SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD="$(setting SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD root)"
export SCIWEAVE_MAPPING_DOMAIN_ID="$(setting SCIWEAVE_MAPPING_DOMAIN_ID iris-demo)"
export SCIWEAVE_MAPPING_SQLITE_PATH="$(setting SCIWEAVE_MAPPING_SQLITE_PATH "$MAP_DIR/data/dashboard.sqlite")"

stop_recorded() {
  if [[ ! -f "$STATE_PATH" ]]; then
    echo "没有找到 .demo-dashboard.json，没有需要停止的进程。"
    return 0
  fi
  while IFS=$'\t' read -r name pid; do
    [[ -z "${pid:-}" ]] && continue
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
      sleep 0.5
      kill -KILL "$pid" 2>/dev/null || true
      echo "已停止 $name (PID $pid)"
    else
      echo "$name (PID $pid) 已不在运行"
    fi
  done < <(python3 - "$STATE_PATH" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    state = json.load(handle)
for entry in state.get("processes", []):
    print(f"{entry.get('name','')}\t{entry.get('pid','')}")
PY
)
  rm -f "$STATE_PATH"
}

wait_for_probe() {
  local url="$1" label="$2" deadline=$((SECONDS + 40))
  while (( SECONDS < deadline )); do
    if curl -fsS -o /dev/null --max-time 2 "$url"; then return 0; fi
    sleep 0.4
  done
  echo "错误：$label 未在时限内就绪 ($url)" >&2
  return 1
}

case "${1:-}" in
  --stop) stop_recorded; exit 0 ;;
esac

RESET_ARG=""
if [[ "${1:-}" == "--reset-seed" ]]; then RESET_ARG="--reset"; fi

for required in "$MAP_DIR/.venv/bin/python" "$DASH_DIR/.venv/bin/python" "$WEB_DIR/node_modules/vite/bin/vite.js"; do
  [[ -e "$required" ]] || { echo "缺少依赖：$required。先在各子项目执行 uv sync / npm install。" >&2; exit 1; }
done

if ! curl -fsS -o /dev/null --max-time 3 "$SCIWEAVE_MAPPING_TERMINUSDB_URL/api/ok"; then
  echo "错误：TerminusDB 不可达：$SCIWEAVE_MAPPING_TERMINUSDB_URL" >&2
  exit 1
fi

stop_recorded
mkdir -p "$(dirname "$SCIWEAVE_MAPPING_SQLITE_PATH")"

echo "--- 播种演示域 ---"
"$MAP_DIR/.venv/bin/python" "$ROOT/scripts/seed_dashboard_demo.py" $RESET_ARG

PIDS=()

export SCIWEAVE_MAPPING_DASHBOARD_MODE=1
export SCIWEAVE_MAPPING_DASHBOARD_HOST="$MAP_HOST"
export SCIWEAVE_MAPPING_DASHBOARD_PORT="$MAP_PORT"
export SCIWEAVE_MAPPING_DASHBOARD_TOKEN="$(setting SCIWEAVE_MAPPING_DASHBOARD_TOKEN '')"
(
  cd "$MAP_DIR"
  PYTHONPATH="$MAP_DIR/src" exec .venv/bin/python src/main.py
) &
MAP_PID=$!
PIDS+=("mapping-dashboard-source	$MAP_PID")
wait_for_probe "http://$MAP_HOST:$MAP_PORT/health" "mapping dashboard source"

export SCIWEAVE_DASHBOARD_HOST="$DASH_HOST"
export SCIWEAVE_DASHBOARD_PORT="$DASH_PORT"
export SCIWEAVE_DASHBOARD_CORS_ORIGIN="http://$WEB_HOST:$WEB_PORT"
export SCIWEAVE_DASHBOARD_SOURCE_MAPPING_URL="http://$MAP_HOST:$MAP_PORT/api/dashboard/source/mapping"
(
  cd "$DASH_DIR"
  PYTHONPATH="$DASH_DIR/src" exec .venv/bin/python src/main.py
) &
DASH_PID=$!
PIDS+=("dashboard-api	$DASH_PID")
wait_for_probe "http://$DASH_HOST:$DASH_PORT/health" "dashboard-api"

export VITE_DASHBOARD_API_URL="http://$DASH_HOST:$DASH_PORT/"
export VITE_DEV_HOST="$WEB_HOST"
export VITE_DEV_PORT="$WEB_PORT"
(
  cd "$WEB_DIR"
  exec node node_modules/vite/bin/vite.js --host "$WEB_HOST" --port "$WEB_PORT" --strictPort
) &
WEB_PID=$!
PIDS+=("web-ui	$WEB_PID")

{
  echo "{"
  echo '  "processes": ['
  first=1
  for entry in "${PIDS[@]}"; do
    name="${entry%%	*}"
    pid="${entry##*	}"
    [[ $first -eq 0 ]] && echo ","
    printf '    {"name": "%s", "pid": %s}' "$name" "$pid"
    first=0
  done
  echo ''
  echo "  ]"
  echo "}"
} > "$STATE_PATH"

wait_for_probe "http://$WEB_HOST:$WEB_PORT/" "web-ui"

SNAPSHOT="$(curl -fsS --max-time 8 "http://$DASH_HOST:$DASH_PORT/api/dashboard/snapshot")"
python3 - "$SNAPSHOT" <<'PY'
import json, sys
payload = json.loads(sys.argv[1])
mapping = next((s for s in payload.get("sources", []) if s.get("id") == "mapping"), {})
print()
print(f"模式      : {payload.get('mode')}")
print(f"mapping   : {mapping.get('status')}")
print(f"项目/任务 : {len(payload.get('projects', []))} / {len(payload.get('tasks', []))}")
print(f"部分来源  : {payload.get('partial')}")
PY

echo ""
echo "看板地址  : http://$WEB_HOST:$WEB_PORT"
echo "停止      : scripts/demo-dashboard.sh --stop"
