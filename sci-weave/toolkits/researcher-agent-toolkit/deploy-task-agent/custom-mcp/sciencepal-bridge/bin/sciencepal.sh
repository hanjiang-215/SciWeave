#!/usr/bin/env sh
set -eu
DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$DIR"
exec uv run --project "$DIR" --env-file "$DIR/.env" sciencepal "$@"
