"""Researcher-side disposition MCP: the six tools of the work-agent flow.

Serves ``health``, ``query_execution``, ``list_pending``, ``cancel_execution``,
``answer_question`` and ``review_execution`` over ``POST /mcp`` against the
durable execution store written by ``gateway/subscriber``. The role runs in its
own process, which is why the store is SQLite rather than in-memory.

Configuration comes entirely from the environment; a missing store path or
token fails fast instead of serving an empty surface.
"""

from __future__ import annotations

import logging
import os

from work_agent_runtime import SqliteExecutionStore
from work_agent_runtime.disposition_mcp import create_disposition_server


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value or not value.strip():
        raise SystemExit(f"{name} must be configured through the environment")
    return value.strip()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    store = SqliteExecutionStore(required("DATABASE_PATH"))
    server = create_disposition_server(
        os.environ.get("DISPOSITION_MCP_HOST", "127.0.0.1").strip() or "127.0.0.1",
        int(os.environ.get("DISPOSITION_MCP_PORT", "8790")),
        store,
        required("DISPOSITION_MCP_TOKEN"),
    )
    uplink = bool(
        os.environ.get("CONFIRM_UPLINK_URL", "").strip()
        and os.environ.get("CONFIRM_UPLINK_TOKEN", "").strip()
    )
    logging.info(
        "disposition MCP listening on %s:%s (centre confirm uplink: %s)",
        server.server_address[0],
        server.server_address[1],
        "enabled" if uplink else "local-only",
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("disposition MCP stopped")
    finally:
        server.server_close()
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
