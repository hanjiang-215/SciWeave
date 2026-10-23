#!/usr/bin/env bash
set -euo pipefail

# Run when the harness opens. It only checks and starts missing user services;
# it never stops them when the harness closes.
for service in sciweave-task-agent-mcp.service sciweave-task-agent-subscriber.service; do
  if ! systemctl --user --quiet is-active "$service"; then
    systemctl --user start "$service"
  fi
done
