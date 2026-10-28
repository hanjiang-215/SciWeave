#!/usr/bin/env sh
# Prereview sweeper.
#
# Why this exists at all: the ingest consumer is pull-driven. Every trigger in
# the Centre Agent's world arrives as a queue message, so when the consumer
# stops (crash, revoked offset, topic renamed in .env) *nothing else notices*.
# Candidates keep piling up with `missing_report` or `report_stale` and the
# Project Owner sees a queue of candidates that look like nobody is working on
# them. The one thing that cannot detect its own absence is the consumer, so a
# dumb periodic check is the honest answer.
#
# Read-only by design. It never appends a report, never appends an invalidation
# and never starts a consumer: a sweeper that could write would become a second,
# unaudited path into the governance log.
#
# Exit codes: 0 healthy, 1 stalled or unreachable, 2 misconfigured.
set -eu

DB="${SCIWEAVE_INGEST_DB:-}"
MAX_AGE="${SCIWEAVE_PREREVIEW_SWEEP_MAX_AGE_SECONDS:-1800}"

# Which domain MCP health endpoints to probe. A deployment either names them
# explicitly (`SCIWEAVE_PREREVIEW_SWEEP_MCP_URLS`, comma separated) or leaves the
# two per-domain variables the cards already use. The older single-domain
# `SCIWEAVE_DOMAIN_MCP_URL` is still honoured because a host that runs one ingest
# per domain has no reason to repeat itself here.
URLS="${SCIWEAVE_PREREVIEW_SWEEP_MCP_URLS:-}"
if [ -z "$URLS" ]; then
  URLS="${RESEARCH_MAPPING_MCP_URL:-},${LLM_WIKI_MCP_URL:-}"
fi
# POSIX sh has no `${VAR//,/}`; strip the separators instead.
if [ -z "$(printf '%s' "$URLS" | tr -d ',')" ] && [ -n "${SCIWEAVE_DOMAIN_MCP_URL:-}" ]; then
  URLS="$SCIWEAVE_DOMAIN_MCP_URL"
fi

if [ -z "$DB" ]; then
  echo "SCIWEAVE_INGEST_DB is unset: cannot tell whether ingest is alive" >&2
  exit 2
fi
if [ ! -f "$DB" ]; then
  # Exit 2, not 1: a missing file means either a wrong path or an ingest that
  # never started, and both are fixed by looking at configuration rather than
  # at a stalled process. Reporting "stalled" here would send the operator to
  # restart something that was never running.
  echo "ingest database $DB does not exist: check SCIWEAVE_INGEST_DB, or the consumer never started" >&2
  exit 2
fi

# 1. Is the consumer still committing? processed_events.handled_at is written in
#    the same transaction as the dedupe row, so its newest value is the last
#    message the consumer actually finished.
if command -v python3 >/dev/null 2>&1; then
  python3 - "$DB" "$MAX_AGE" <<'PY' || exit 1
import sqlite3, sys
from datetime import datetime, timezone

path, max_age = sys.argv[1], float(sys.argv[2])
try:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    row = connection.execute(
        "SELECT handled_at, status FROM processed_events ORDER BY handled_at DESC LIMIT 1"
    ).fetchone()
except sqlite3.Error as error:
    print(f"cannot read {path}: {error}", file=sys.stderr)
    raise SystemExit(1)

if row is None:
    # An empty table is not a stall: a fresh install that has not received a
    # governance event yet looks exactly like this.
    print("sweep: no governance events handled yet (consumer not yet exercised)")
    raise SystemExit(0)

handled_at, status = row
try:
    newest = datetime.fromisoformat(handled_at.replace("Z", "+00:00"))
except ValueError:
    print(f"sweep: unreadable handled_at {handled_at!r}", file=sys.stderr)
    raise SystemExit(1)
age = (datetime.now(timezone.utc) - newest).total_seconds()
if age > max_age:
    print(
        f"sweep: ingest looks stalled — last handled at {handled_at} "
        f"({int(age)}s ago, limit {int(max_age)}s, last status {status})",
        file=sys.stderr,
    )
    raise SystemExit(1)
print(f"sweep: ingest alive, last handled {int(age)}s ago (last status {status})")
PY
else
  echo "python3 is required to read the ingest database" >&2
  exit 2
fi

# 2. Is each domain MCP the consumer writes through actually answering? Liveness
#    of the consumer is worthless if its only write target is down: it would
#    commit offsets past events it could not record. Mapping and Wiki are
#    separate services, so both get probed — one domain answering says nothing
#    about the other.
#
#    /health is the unauthenticated probe both domain MCPs serve, which is also
#    why it says nothing about capability: this checks reachability, not rights.
for url in $(printf '%s' "$URLS" | tr ',' ' '); do
  [ -n "$url" ] || continue
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required to probe $url" >&2
    exit 2
  fi
  health_url="${url%/}/health"
  case "$url" in
    */mcp) health_url="${url%/mcp}/health" ;;
  esac
  if ! curl --silent --show-error --fail --max-time 5 "$health_url" >/dev/null; then
    echo "sweep: domain MCP health probe failed at $health_url" >&2
    exit 1
  fi
  echo "sweep: domain MCP reachable at $health_url"
done

exit 0
