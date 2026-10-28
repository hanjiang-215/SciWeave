#!/usr/bin/env sh
# Report whether the Project Owner suite is installed and usable.
#
# Read-only. Exit 0 ready, 1 incomplete, 2 installed but not usable. There are
# no services here, so "usable" means: the skills are where the harness loads
# them from, the cards are present, and every token the cards need is set.
set -eu

SOURCE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SKILLS_HOME="${SCIWEAVE_OWNER_SKILLS_HOME:-$HOME/.sciweave/owner-skills}"
CONFIG_HOME="${SCIWEAVE_OWNER_CONFIG_HOME:-$HOME/.sciweave/owner}"

missing=0
broken=0

need_file() {
  if [ ! -f "$2" ]; then
    echo "missing: $1 ($2)" >&2
    missing=$((missing + 1))
  fi
}

echo "skills: $SKILLS_HOME"
echo "config: $CONFIG_HOME"

# 1. Skills, flat. A nested layout loads zero skills in fast-agent's registry,
#    and the harness reports nothing when it happens.
for skill in decide-candidate request-revision dispatch-root-task \
             handle-merge-candidate impact-preview notification-status; do
  need_file "skill $skill" "$SKILLS_HOME/$skill/SKILL.md"
done

# 2. Cards. One mcp.json per server.
for service in research-mapping research-wiki coordinator registry email-service; do
  need_file "card $service" "$CONFIG_HOME/mcp/$service/mcp.json"
done

if [ ! -f "$CONFIG_HOME/.env" ]; then
  echo "incomplete: $CONFIG_HOME/.env is absent; run ./install.sh" >&2
  exit 1
fi

# shellcheck disable=SC1090
. "$CONFIG_HOME/.env"

# 3. Every variable the five cards name. A card whose url_env is empty is a
#    server the harness cannot start, and a missing token is a 401 on the first
#    call — both surface later as "the tool did not work".
for name in RESEARCH_MAPPING_MCP_URL RESEARCH_MAPPING_MCP_TOKEN \
            LLM_WIKI_MCP_URL LLM_WIKI_MCP_TOKEN \
            SCIWEAVE_COORDINATOR_MCP_URL SCIWEAVE_COORDINATOR_MCP_TOKEN \
            SCIWEAVE_REGISTRY_URL SCIWEAVE_REGISTRY_TOKEN \
            EMAIL_MCP_URL EMAIL_MCP_TOKEN; do
  eval "value=\${$name:-}"
  if [ -z "$value" ]; then
    echo "not configured: $name is empty in $CONFIG_HOME/.env" >&2
    broken=$((broken + 1))
  fi
done

# 4. A token that still says "replace-with-" is installed but not configured.
#    Checking the prefix catches the copy-paste-the-example mistake, which
#    otherwise looks identical to a working setup until the first 401.
for name in RESEARCH_MAPPING_MCP_TOKEN LLM_WIKI_MCP_TOKEN \
            SCIWEAVE_COORDINATOR_MCP_TOKEN SCIWEAVE_REGISTRY_TOKEN EMAIL_MCP_TOKEN; do
  eval "value=\${$name:-}"
  case "$value" in
    replace-with-*)
      echo "not configured: $name still holds the example value" >&2
      broken=$((broken + 1))
      ;;
  esac
done

# 5. The manifest still describes this tree.
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
  echo "installed but not usable: $broken problem(s)" >&2
  exit 2
fi
if [ "$missing" -gt 0 ]; then
  echo "incomplete: $missing item(s) missing; run ./install.sh" >&2
  exit 1
fi
echo "ready"
