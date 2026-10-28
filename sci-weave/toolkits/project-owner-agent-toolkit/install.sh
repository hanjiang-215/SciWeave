#!/usr/bin/env sh
# Install the Project Owner suite into the owner's own harness.
#
# A "human" suite has no services and no worker: the owner drives it from their
# own Codex / Cursor / WorkBuddy session. So all this installs is
#
#   * the skills, flat, at <skills-home>/<skill>/SKILL.md;
#   * the MCP cards, as a config fragment the harness can point at;
#   * the agent definition under fast-sci-agent/, for a fast-agent-style harness.
#
# It never installs a service, never starts anything and never writes a token.
set -eu

SOURCE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SKILLS_HOME="${SCIWEAVE_OWNER_SKILLS_HOME:-$HOME/.sciweave/owner-skills}"
CONFIG_HOME="${SCIWEAVE_OWNER_CONFIG_HOME:-$HOME/.sciweave/owner}"

SKILLS="decide-candidate request-revision dispatch-root-task handle-merge-candidate impact-preview notification-status"

for skill in $SKILLS; do
  if [ ! -f "$SOURCE/$skill/SKILL.md" ]; then
    echo "missing $skill/SKILL.md: this zip is incomplete" >&2
    exit 65
  fi
done

mkdir -p "$SKILLS_HOME"
for skill in $SKILLS; do
  rm -rf "${SKILLS_HOME:?}/$skill"
  cp -R "$SOURCE/$skill" "$SKILLS_HOME/$skill"
done

# The cards are what a harness's MCP client needs. They are copied rather than
# referenced so the installed tree is self-contained: a harness may run in a
# different checkout, and a card pointing back into a repo that moved is a
# card that silently stops working.
mkdir -p "$CONFIG_HOME/mcp" "$CONFIG_HOME/fast-sci-agent"
for card in "$SOURCE"/mcp/*/mcp.json; do
  service="$(basename "$(dirname "$card")")"
  mkdir -p "$CONFIG_HOME/mcp/$service"
  cp "$card" "$CONFIG_HOME/mcp/$service/mcp.json"
done

if [ -d "$SOURCE/fast-sci-agent" ]; then
  cp -R "$SOURCE/fast-sci-agent/." "$CONFIG_HOME/fast-sci-agent/"
fi

if [ ! -f "$CONFIG_HOME/.env" ]; then
  cp "$SOURCE/.env.example" "$CONFIG_HOME/.env"
  echo "wrote $CONFIG_HOME/.env from .env.example; fill in the tokens" >&2
else
  echo "kept existing $CONFIG_HOME/.env"
fi

cat <<EOF

owner skills at  $SKILLS_HOME
mcp cards at     $CONFIG_HOME/mcp
agent defs at    $CONFIG_HOME/fast-sci-agent
env example at   $CONFIG_HOME/.env

next:
  1. fill $CONFIG_HOME/.env — the five MCP tokens plus their URLs
  2. point your harness at the skills directory:
       $SKILLS_HOME
     Note: the harness loads ONE level, so do not point it at the suite zip root;
     the skills must sit directly under the directory you configure.
  3. register the five MCP servers from $CONFIG_HOME/mcp/*/mcp.json
  4. ./check.sh
EOF
