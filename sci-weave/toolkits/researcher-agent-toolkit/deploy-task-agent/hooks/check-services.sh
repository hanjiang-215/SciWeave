#!/usr/bin/env bash
set -euo pipefail

# Run when the harness opens. It only checks and starts missing user services;
# it never stops them when the harness closes.
#
# A machine where the kit was never installed (or one without a systemd user
# bus, e.g. inside a container) is not a failure: this hook is a convenience,
# not a deployment step. Exiting non-zero here would break every harness start
# on a developer machine that does not run the two services.
for service in sciweave-task-agent-mcp.service sciweave-task-agent-subscriber.service; do
  if ! systemctl --user --quiet is-enabled "$service" >/dev/null 2>&1; then
    echo "skip $service: not installed (run ./install.sh first)" >&2
    continue
  fi
  if ! systemctl --user --quiet is-active "$service"; then
    systemctl --user start "$service" || echo "could not start $service" >&2
  fi
done

exit 0
