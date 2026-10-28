#!/usr/bin/env sh
# Install the kit into ~/.sciweave/task-agent and register the two user services.
#
# Idempotent: re-running upgrades the code in place and leaves `.env`,
# `WORKER_HOME` and the SQLite files alone. It never touches credentials.
set -eu

TARGET="${SCIWEAVE_TASK_AGENT_HOME:-$HOME/.sciweave/task-agent}"
SOURCE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 69
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl is required: the two gateway roles run as user services" >&2
  exit 69
fi

mkdir -p "$TARGET"
# Copy the kit next to .env rather than into a versioned subdirectory: the
# systemd units and the start scripts all derive paths from the kit root.
for item in runtime service-template agent-definitions libs custom-mcp deploy-task-agent-skills hooks bin systemd README.md; do
  if [ -e "$SOURCE/$item" ]; then
    rm -rf "${TARGET:?}/$item"
    cp -R "$SOURCE/$item" "$TARGET/$item"
  fi
done

if [ ! -f "$TARGET/.env" ]; then
  cp "$SOURCE/.env.example" "$TARGET/.env"
  echo "wrote $TARGET/.env from .env.example; fill in the credentials before starting" >&2
else
  echo "kept existing $TARGET/.env"
fi

chmod +x "$TARGET"/bin/start-mcp "$TARGET"/bin/start-subscriber

# The runtime is the only project with dependencies; installing it here means
# the start scripts do not pay for a resolve on every service restart.
(cd "$TARGET/runtime" && uv sync --quiet)

# The checked-in units use %h/.sciweave/task-agent. Substitute the real target so
# SCIWEAVE_TASK_AGENT_HOME keeps working; %h stays the fallback for the default.
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
for unit in sciweave-task-agent-mcp.service sciweave-task-agent-subscriber.service; do
  sed "s#%h/.sciweave/task-agent#$TARGET#g" "$TARGET/systemd/$unit" > "$UNIT_DIR/$unit"
done
systemctl --user daemon-reload

echo "installed at $TARGET"
echo "next: fill $TARGET/.env, then 'systemctl --user enable --now sciweave-task-agent-subscriber.service'"
