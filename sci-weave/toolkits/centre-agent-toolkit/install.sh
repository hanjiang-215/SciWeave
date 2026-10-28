#!/usr/bin/env sh
# Install the Centre Agent suite on the central server.
#
# What this does and does not install, in that order:
#
#   * it does NOT copy the centre source. The server already has a checkout of
#     `sci-weave/centre-control/centre-agents`, and ADR-0002 keeps the Task Agent
#     and Centre Agent codebases apart instead of shipping one runtime to both.
#     Copying a second tree here would create two versions of the same service.
#   * it DOES install the suite's own configuration, start scripts, systemd
#     units and skills — the parts that do not live in the service repository.
#
# Idempotent: re-running replaces code and units, and leaves an existing `.env`,
# the ingest SQLite and the gateway SQLite untouched.
set -eu

SOURCE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
TARGET="${SCIWEAVE_CENTRE_SUITE_HOME:-$HOME/.sciweave/centre}"
SKILLS_HOME="${SCIWEAVE_CENTRE_SKILLS_HOME:-$HOME/.sciweave/centre-skills}"

for program in uv systemctl; do
  if ! command -v "$program" >/dev/null 2>&1; then
    echo "$program is required: the two centre roles run as user services" >&2
    exit 69
  fi
done

mkdir -p "$TARGET"
for item in bin cron systemd README.md; do
  if [ ! -e "$SOURCE/$item" ]; then
    echo "missing $item/: this zip is incomplete" >&2
    exit 65
  fi
  rm -rf "${TARGET:?}/$item"
  cp -R "$SOURCE/$item" "$TARGET/$item"
done

if [ ! -f "$TARGET/.env" ]; then
  cp "$SOURCE/.env.example" "$TARGET/.env"
  echo "wrote $TARGET/.env from .env.example; fill in the tokens before starting" >&2
else
  echo "kept existing $TARGET/.env"
fi

# The start scripts read SCIWEAVE_CENTRE_AGENTS_HOME out of .env. Checking it
# here rather than at first start turns "systemd restarts every 5s forever" into
# one clear message at install time.
# shellcheck disable=SC1090
. "$TARGET/.env"
AGENTS_HOME="${SCIWEAVE_CENTRE_AGENTS_HOME:-}"
if [ -z "$AGENTS_HOME" ]; then
  echo "SCIWEAVE_CENTRE_AGENTS_HOME is empty in $TARGET/.env" >&2
  echo "point it at the centre-agents checkout before enabling the services" >&2
elif [ ! -f "$AGENTS_HOME/pyproject.toml" ]; then
  echo "SCIWEAVE_CENTRE_AGENTS_HOME=$AGENTS_HOME has no pyproject.toml" >&2
  echo "it must be the sci-weave/centre-control/centre-agents workspace root" >&2
else
  # Resolving the workspace once means the services do not pay for it on every
  # restart. Failure is not fatal here: the operator may be installing before
  # the checkout is ready, and `check.sh` will report it.
  (cd "$AGENTS_HOME" && uv sync --quiet) || echo "warning: uv sync failed in $AGENTS_HOME" >&2
fi

chmod +x "$TARGET"/bin/start-ingest "$TARGET"/bin/start-mcp "$TARGET"/cron/prereview-sweep.sh

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
for unit in sciweave-centre-agent-ingest.service sciweave-centre-agent-mcp.service; do
  sed "s#%h/.sciweave/centre#$TARGET#g" "$TARGET/systemd/$unit" > "$UNIT_DIR/$unit"
done
systemctl --user daemon-reload

# Skills go to their own home, flat: <skills-home>/<skill>/SKILL.md. They are
# for the *operator's* harness (and for a human reading them), not for a worker
# loop — the centre worker runs no skills, and putting these under the suite
# directory would invite exactly that.
mkdir -p "$SKILLS_HOME"
for skill in prereview-checks conflict-matrix merged-candidate invalidation \
             audit-candidate-branches; do
  if [ ! -f "$SOURCE/$skill/SKILL.md" ]; then
    echo "missing $skill/SKILL.md: this zip is incomplete" >&2
    exit 65
  fi
  rm -rf "${SKILLS_HOME:?}/$skill"
  cp -R "$SOURCE/$skill" "$SKILLS_HOME/$skill"
done

cat <<EOF

suite installed at    $TARGET
centre source at      ${AGENTS_HOME:-<not configured>}
centre skills at      $SKILLS_HOME

next:
  1. fill $TARGET/.env — at minimum SCIWEAVE_DOMAIN_MCP_URL/_TOKEN,
     SCIWEAVE_GATEWAY_TOKEN, SCIWEAVE_QUEUE_GROUP_ID and
     SCIWEAVE_SUBSCRIBER_TOPICS
  2. run one ingest per domain (Mapping and Wiki) with distinct consumer groups
  3. systemctl --user enable --now sciweave-centre-agent-ingest.service
     systemctl --user enable --now sciweave-centre-agent-mcp.service
  4. install the sweeper if you want a stall alarm (it is read-only):
       crontab -e
       */10 * * * * $TARGET/cron/prereview-sweep.sh
  5. ./check.sh to confirm
EOF
