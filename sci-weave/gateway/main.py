"""Run the SciWeave Gateway MVP."""

from __future__ import annotations

import os

from .app import create_app, serve


if __name__ == "__main__":
    database = os.environ.get("SCIWEAVE_GATEWAY_DB", "sci-weave-gateway.sqlite3")
    token = os.environ.get("SCIWEAVE_GATEWAY_TOKEN")
    if not token:
        raise SystemExit("SCIWEAVE_GATEWAY_TOKEN must be configured")
    serve(create_app(database, token), os.environ.get("SCIWEAVE_GATEWAY_HOST", "127.0.0.1"), int(os.environ.get("SCIWEAVE_GATEWAY_PORT", "8080")))
