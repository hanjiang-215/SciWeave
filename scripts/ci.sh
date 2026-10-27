#!/usr/bin/env bash
# Run the full regression matrix: every Python subproject's pytest, the web-ui
# vitest + build, a syntax compile, and a whitespace check.
#
# Project locations are discovered from the git index (every tests/test_*.py),
# so untracked local leftovers are never mistaken for CI targets.
#
# Usage:
#   scripts/ci.sh                 # unit matrix only
#   scripts/ci.sh --integration   # also run the TerminusDB-backed cases
#   scripts/ci.sh --skip-web
#   scripts/ci.sh --filter research-
#
# Exit code is non-zero when any stage fails.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

INTEGRATION=0
SKIP_WEB=0
FILTER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --integration) INTEGRATION=1 ;;
    --skip-web) SKIP_WEB=1 ;;
    --filter) shift; FILTER="${1:-}" ;;
    -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

if [[ $INTEGRATION -eq 1 ]]; then
  export SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1
else
  unset SCIWEAVE_RUN_TERMINUSDB_INTEGRATION
fi

stage() { printf '\n=== %s ===\n' "$1"; }

FAILED=()
TOTAL_PASSED=0
TOTAL_SKIPPED=0

count_of() {  # count_of "<pattern>" "<text>"
  printf '%s' "$2" | grep -o "$1" | head -1 | grep -o '[0-9]*' || true
}

projects="$(git ls-files '*tests/test_*.py' | sed 's|/tests/.*||' | grep -v '\.venv' | sort -u)"
if [[ -z "$projects" ]]; then
  echo "没有发现任何 tests/test_*.py，检查是否在仓库根目录。" >&2
  exit 2
fi
if [[ -n "$FILTER" ]]; then
  projects="$(printf '%s\n' "$projects" | grep -E "$FILTER" || true)"
fi

stage "Python 矩阵"
[[ $INTEGRATION -eq 0 ]] && echo "集成用例：跳过（用 --integration 或 SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1 执行）"

while IFS= read -r project; do
  [[ -z "$project" ]] && continue
  label="${project#sci-weave/}"
  started=$(date +%s)
  output="$(uv run --directory "$project" --with pytest --with pytest-asyncio \
              pytest tests -q -p no:cacheprovider 2>&1)"
  code=$?
  elapsed=$(( $(date +%s) - started ))
  passed=$(count_of '[0-9]* passed' "$output")
  failed=$(count_of '[0-9]* failed' "$output")
  skipped=$(count_of '[0-9]* skipped' "$output")
  passed=${passed:-0}; failed=${failed:-0}; skipped=${skipped:-0}
  TOTAL_PASSED=$((TOTAL_PASSED + passed))
  TOTAL_SKIPPED=$((TOTAL_SKIPPED + skipped))
  if [[ $code -eq 0 ]]; then
    printf '  %-52s PASS %4s passed %3s skipped %5ss\n' "$label" "$passed" "$skipped" "$elapsed"
  else
    printf '  %-52s FAIL %4s passed %3s failed  %5ss\n' "$label" "$passed" "$failed" "$elapsed"
    printf '%s\n' "$output" | tail -25
    FAILED+=("$project")
  fi
done <<< "$projects"

stage "语法检查（compileall）"
src_dirs=()
while IFS= read -r project; do
  [[ -z "$project" ]] && continue
  [[ -d "$project/src" ]] && src_dirs+=("$project/src")
done <<< "$projects"
if uv run --with pytest python -m compileall -q "${src_dirs[@]}" >/dev/null 2>&1; then
  echo "  PASS  ${#src_dirs[@]} 个 src 目录"
else
  echo "  FAIL"
  FAILED+=("compileall")
fi

if [[ $SKIP_WEB -eq 0 ]]; then
  stage "前端（web-ui）"
  WEB_DIR="sci-weave/centre-control/web-ui"
  if [[ ! -d "$WEB_DIR/node_modules" ]]; then
    echo "  node_modules 缺失，先 npm ci ..."
    ( cd "$WEB_DIR" && npm ci >/dev/null 2>&1 )
  fi
  for task in test build; do
    if ( cd "$WEB_DIR" && npm run "$task" >/tmp/ci-web-$task.log 2>&1 ); then
      printf '  npm run %-10s PASS\n' "$task"
    else
      printf '  npm run %-10s FAIL\n' "$task"
      tail -25 "/tmp/ci-web-$task.log"
      FAILED+=("web-ui:$task")
    fi
  done
fi

stage "git diff --check（空白与冲突标记）"
# 捕获而不是直接透传：Windows 上 git 会把「LF will be replaced by CRLF」写到
# stderr，透传会让 CI 日志充满可被误读为失败的噪声。
if whitespace_output=$(git diff --check 2>&1); then
  echo "  PASS"
else
  echo "  FAIL  存在行尾空白或冲突标记"
  printf '%s\n' "$whitespace_output"
  FAILED+=("git diff --check")
fi

stage "汇总"
echo "  pytest 用例 ${TOTAL_PASSED} 项通过"
echo "  已跳过 ${TOTAL_SKIPPED} 项（默认为依赖真实 TerminusDB / Kafka 的集成用例）"
if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo ""
  echo "  失败阶段："
  for name in "${FAILED[@]}"; do echo "    - $name"; done
  exit 1
fi
echo ""
echo "  全部通过。"
exit 0
