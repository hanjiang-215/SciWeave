#!/usr/bin/env sh
# Report whether the Centre Agent suite is installed and fit to run.
#
# Read-only: never starts, stops or installs. Exit 0 ready, 1 incomplete,
# 2 installed but not ready. "Not installed" and "installed but broken" get
# different advice, so they get different codes.
set -eu

SOURCE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
TARGET="${SCIWEAVE_CENTRE_SUITE_HOME:-$HOME/.sciweave/centre}"
SKILLS_HOME="${SCIWEAVE_CENTRE_SKILLS_HOME:-$HOME/.sciweave/centre-skills}"

missing=0
broken=0

need_file() {
  if [ ! -f "$2" ]; then
    echo "missing: $1 ($2)" >&2
    missing=$((missing + 1))
  fi
}

need_dir() {
  if [ ! -d "$2" ]; then
    echo "missing: $1 ($2)" >&2
    missing=$((missing + 1))
  fi
}

echo "suite:  $TARGET"
echo "skills: $SKILLS_HOME"

# 1. The suite's own payload.
need_dir "bin" "$TARGET/bin"
need_dir "systemd" "$TARGET/systemd"
need_file "start-ingest" "$TARGET/bin/start-ingest"
need_file "start-mcp" "$TARGET/bin/start-mcp"
need_file "prereview-sweep" "$TARGET/cron/prereview-sweep.sh"
need_file ".env" "$TARGET/.env"

# 2. The skills the operator's harness reads. Flat, one level, as fast-agent's
#    registry expects (it descends exactly one directory).
for skill in prereview-checks conflict-matrix merged-candidate invalidation \
             audit-candidate-branches; do
  need_file "skill $skill" "$SKILLS_HOME/$skill/SKILL.md"
done

if [ ! -f "$TARGET/.env" ]; then
  echo "incomplete: $missing item(s) missing; run ./install.sh" >&2
  exit 1
fi

# shellcheck disable=SC1090
. "$TARGET/.env"

# 3. The centre source, which the suite deliberately does not ship.
AGENTS_HOME="${SCIWEAVE_CENTRE_AGENTS_HOME:-}"
if [ -z "$AGENTS_HOME" ]; then
  echo "not configured: SCIWEAVE_CENTRE_AGENTS_HOME is empty in $TARGET/.env" >&2
  broken=$((broken + 1))
elif [ ! -f "$AGENTS_HOME/pyproject.toml" ]; then
  echo "not configured: $AGENTS_HOME has no pyproject.toml (not the centre-agents workspace)" >&2
  broken=$((broken + 1))
fi

# 4. Configuration a successful install cannot know.
for name in SCIWEAVE_DOMAIN_MCP_URL SCIWEAVE_DOMAIN_MCP_TOKEN \
            SCIWEAVE_GATEWAY_TOKEN SCIWEAVE_GATEWAY_DB \
            SCIWEAVE_QUEUE_GROUP_ID SCIWEAVE_SUBSCRIBER_TOPICS SCIWEAVE_INGEST_DB; do
  eval "value=\${$name:-}"
  if [ -z "$value" ]; then
    echo "not configured: $name is empty in $TARGET/.env" >&2
    broken=$((broken + 1))
  fi
done

# 5. A token still holding the example value passes every "is it non-empty"
#    check and fails on the first authenticated call. Catch the copy-the-example
#    mistake here instead of in a 401.
for name in SCIWEAVE_DOMAIN_MCP_TOKEN SCIWEAVE_GATEWAY_TOKEN; do
  eval "value=\${$name:-}"
  case "$value" in
    replace-with-*)
      echo "not configured: $name still holds the example value" >&2
      broken=$((broken + 1))
      ;;
  esac
done

# 6. A queue that silently fell back to FakeQueue is the single most deceptive
#    state this suite can be in: the service is active, and it consumes nothing.
if [ -z "${SCIWEAVE_QUEUE_BOOTSTRAP_SERVERS:-}" ]; then
  echo "not ready: SCIWEAVE_QUEUE_BOOTSTRAP_SERVERS is empty, so ingest runs FakeQueue" >&2
  echo "           (an ingest that consumes nothing still looks active to systemd)" >&2
  broken=$((broken + 1))
fi

# 7. Prereview rule sets. Without a resolvable <version>.json every
#    append_prereview_log answers rule_set_missing, so the suite can start and
#    still be unable to record a single report.
rules="${SCIWEAVE_MAPPING_PREREVIEW_RULES_DIR:-}"
if [ -z "$rules" ]; then
  echo "not configured: SCIWEAVE_MAPPING_PREREVIEW_RULES_DIR is empty (append_prereview_log will refuse)" >&2
  broken=$((broken + 1))
elif [ ! -d "$rules" ]; then
  echo "not ready: SCIWEAVE_MAPPING_PREREVIEW_RULES_DIR=$rules is not a directory" >&2
  broken=$((broken + 1))
elif ! ls "$rules"/*.json >/dev/null 2>&1; then
  echo "not ready: no <version>.json under $rules, so no prereview can be recorded" >&2
  broken=$((broken + 1))
fi

# 8. The two units. install.sh always writes them, so a missing unit is a broken
#    install rather than an uninstalled suite.
if command -v systemctl >/dev/null 2>&1; then
  for service in sciweave-centre-agent-ingest.service sciweave-centre-agent-mcp.service; do
    if ! systemctl --user --quiet is-enabled "$service" >/dev/null 2>&1; then
      echo "not enabled: $service (systemctl --user enable --now $service)" >&2
      broken=$((broken + 1))
    fi
  done
fi

# 9. The manifest still describes this tree.
if command -v python3 >/dev/null 2>&1; then
  if ! python3 -c "import suitecheck" >/dev/null 2>&1; then
    echo "note: suitecheck is not installed here, skipping the manifest re-check" >&2
  elif ! python3 -m suitecheck.cli check "$SOURCE" >/dev/null 2>&1; then
    echo "suitecheck dislikes this suite; run it by hand for the findings:" >&2
    echo "  python3 -m suitecheck.cli check $SOURCE" >&2
    broken=$((broken + 1))
  fi
fi

if [ "$broken" -gt 0 ]; then
  echo "installed but not ready: $broken problem(s)" >&2
  exit 2
fi
if [ "$missing" -gt 0 ]; then
  echo "incomplete: $missing item(s) missing; run ./install.sh" >&2
  exit 1
fi
echo "ready"
