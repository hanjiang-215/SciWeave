#!/usr/bin/env sh
# Report whether the researcher suite is installed and usable.
#
# Read-only: it never starts, stops or installs anything. Exit 0 when the suite
# is complete, 1 when something is missing, 2 when it is installed but not fit
# to run. The distinction matters because "not installed" and "installed but
# broken" get different advice.
set -eu

SOURCE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
KIT_HOME="${SCIWEAVE_TASK_AGENT_HOME:-$HOME/.sciweave/task-agent}"
SKILLS_HOME="${SCIWEAVE_RESEARCHER_SKILLS_HOME:-$HOME/.sciweave/researcher-skills}"

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

echo "kit:    $KIT_HOME"
echo "skills: $SKILLS_HOME"

# 1. The kit's own payload.
need_dir "runtime" "$KIT_HOME/runtime"
need_dir "service-template" "$KIT_HOME/service-template"
need_dir "agent-definitions" "$KIT_HOME/agent-definitions"
need_dir "libs" "$KIT_HOME/libs"
need_file "start-mcp" "$KIT_HOME/bin/start-mcp"
need_file "start-subscriber" "$KIT_HOME/bin/start-subscriber"
need_file ".env" "$KIT_HOME/.env"

# 2. The skills the personal Agent reads. Flat, one level, as the loader expects.
for skill in install-suite upgrade-suite register-instance audit-buffer \
             use-research-map use-research-wiki promote-draft push-task-agent-to-rework; do
  need_file "skill $skill" "$SKILLS_HOME/$skill/SKILL.md"
done

# 3. Configuration that a successful install still cannot know.
if [ -f "$KIT_HOME/.env" ]; then
  # shellcheck disable=SC1090
  . "$KIT_HOME/.env"
  for name in SCIWEAVE_AGENT_ID SCIWEAVE_SUBSCRIBER_TOPICS DRAFT_BUFFER_MCP_URL \
              RESEARCH_MAPPING_MCP_URL LLM_WIKI_MCP_URL DISPOSITION_MCP_TOKEN; do
    eval "value=\${$name:-}"
    if [ -z "$value" ]; then
      echo "not configured: $name is empty in $KIT_HOME/.env" >&2
      broken=$((broken + 1))
    fi
  done
fi

# 4. The two services. Not being registered with systemd is a broken install,
#    not a missing one: install.sh always writes the units.
if command -v systemctl >/dev/null 2>&1; then
  for service in sciweave-task-agent-mcp.service sciweave-task-agent-subscriber.service; do
    if ! systemctl --user --quiet is-enabled "$service" >/dev/null 2>&1; then
      echo "not enabled: $service (systemctl --user enable --now $service)" >&2
      broken=$((broken + 1))
    fi
  done
fi

# 5. The suite manifest still describes this tree.
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
