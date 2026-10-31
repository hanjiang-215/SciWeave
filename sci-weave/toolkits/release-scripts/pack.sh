#!/usr/bin/env sh
# Pack the two Agent suites into release zips.
#
# Each zip is a self-contained suite directory: `install.sh` / `check.sh` and
# `suite.yaml` at the top, skills and MCP cards below. A user unpacks it and
# runs `./install.sh`; nothing else is expected.
#
# What must NOT go into the zip, and why:
#   * .venv / __pycache__ / .pytest_cache — build+cache artifacts. The researcher
#     kit's runtime is synced on the user's machine by install.sh (`uv sync`), so
#     shipping a 200MB venv is pure waste and breaks on a different OS/Python.
#   * .env — never ship real credentials; the suite's own .env.example travels.
#   * .git — a zip archive has no repository context; upgrades are "install the
#     next tag's zip", not `git pull`.
#
# Usage:
#   ./pack.sh                 # version from suite.yaml (both suites share it)
#   ./pack.sh v0.2.0          # override the version used in file names
#   OUT_DIR=/tmp/out ./pack.sh
#
# Output: ${OUT_DIR}/sciweave-po-toolkit-<ver>.zip and
#         ${OUT_DIR}/sciweave-researcher-toolkit-<ver>.zip, plus SHA256SUMS.
set -eu

TOOLKITS_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$TOOLKITS_DIR/release-scripts/dist}"

# Version: prefer an explicit argument, else read suite.yaml (identical in both
# suites — publish.sh refuses to release if they disagree).
if [ "${1:-}" != "" ]; then
  VER="$1"
else
  VER="$(sed -n 's/^version: *//p' "$TOOLKITS_DIR/researcher-agent-toolkit/suite.yaml" | head -1)"
fi
[ -n "$VER" ] || { echo "cannot determine version (suite.yaml has no version)" >&2; exit 65; }
VER="${VER#v}"   # tolerate v-prefixed input; file names use the bare version

if ! command -v zip >/dev/null 2>&1; then
  echo "zip is required to build release archives" >&2
  exit 69
fi

mkdir -p "$OUT_DIR"
cd "$TOOLKITS_DIR"

PACKAGES="project-owner-agent-toolkit:po researcher-agent-toolkit:researcher"
SUM_FILE="$OUT_DIR/SHA256SUMS"
: > "$SUM_FILE"

for spec in $PACKAGES; do
  src="${spec%%:*}"
  short="${spec##*:}"
  [ -f "$src/suite.yaml" ] || { echo "missing $src/suite.yaml" >&2; exit 65; }
  [ -f "$src/install.sh" ] || { echo "missing $src/install.sh" >&2; exit 65; }

  zipname="sciweave-${short}-toolkit-${VER}.zip"
  rm -f "$OUT_DIR/$zipname"

  # -r recurse, -X drop extra file attrs, -q quiet. Exclusions via -x patterns.
  # The patterns are anchored so `*/mcp/*` cards are kept; only build junk drops.
  ( cd "$TOOLKITS_DIR" && zip -rqX "$OUT_DIR/$zipname" "$src" \
      -x "*/${src}/.venv/*" \
      -x "*/.venv/*" \
      -x "*/__pycache__/*" \
      -x "*/.pytest_cache/*" \
      -x "*.pyc" \
      -x "*/${src}/.env" )

  ( cd "$OUT_DIR" && sha256sum "$zipname" >> "$SUM_FILE" )
  printf '%s  %s\n' "$zipname" "$(du -h "$OUT_DIR/$zipname" | cut -f1)"
done

echo
echo "version: $VER"
echo "packed into: $OUT_DIR"
cat "$SUM_FILE"
