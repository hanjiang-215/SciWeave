from __future__ import annotations

import logging
import sqlite3

from .config import CoordinatorConfig
from .store import CoordinatorStore

logger = logging.getLogger("coordinator")


def main() -> None:
    """Entry point for the coordinator subproject.

    The 2026-10-25 core (ai4-1y6q) delivers the store and recompute/dispatch
    logic behind fake ports. Real adapters (research-map MCP snapshot, Redpanda
    publisher, email-service notifications, Registry availability) are wired
    after ai4-te1v message semantics settle; until then this entry loads the
    configuration and opens the coordinator state store, which is the only
    startup side effect that does not depend on an adapter.
    """
    config = CoordinatorConfig.from_environment()
    connection = sqlite3.connect(config.sqlite_path)
    store = CoordinatorStore(connection)
    logger.info("coordinator store ready at %s", config.sqlite_path)
    logger.info("adapter wiring awaits ai4-te1v; core is verified via fake-port tests")
    connection.close()


if __name__ == "__main__":
    main()
