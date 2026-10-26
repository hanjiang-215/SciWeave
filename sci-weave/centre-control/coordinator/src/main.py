from __future__ import annotations

import logging
import os
import sqlite3
import time

from .adapter_email import EmailMcpNotificationPublisher
from .adapter_publisher import KafkaHandoffPublisher
from .adapter_registry import RegistryMcpAvailabilityPort
from .adapter_snapshot import ResearchMapMcpSnapshotPort
from .config import CoordinatorConfig
from .service import CoordinatorService
from .store import CoordinatorStore

logger = logging.getLogger("coordinator")

_EMAIL_MCP_ENDPOINT = "SCIWEAVE_EMAIL_MCP_ENDPOINT"
_EMAIL_MCP_TOKEN = "SCIWEAVE_EMAIL_MCP_TOKEN"


def build(config: CoordinatorConfig) -> "CoordinatorRuntime":
    """Assemble the coordinator with real central adapters.

    Snapshot, registry and Redpanda publishers are required; email routing is
    optional and degrades to keeping waiting facts when unconfigured. All
    endpoints/tokens come from environment variables; the coordinator never
    opens domain stores.
    """
    mapping_mcp_endpoint = os.environ.get("SCIWEAVE_MAPPING_MCP_ENDPOINT")
    mapping_mcp_token = os.environ.get("SCIWEAVE_MAPPING_MCP_TOKEN")
    registry_mcp_endpoint = os.environ.get("SCIWEAVE_REGISTRY_MCP_ENDPOINT")
    registry_mcp_token = os.environ.get("SCIWEAVE_REGISTRY_MCP_TOKEN")
    kafka_bootstrap = os.environ.get("SCIWEAVE_COORDINATOR_KAFKA_BOOTSTRAP")
    missing = [
        name
        for name, value in {
            "SCIWEAVE_MAPPING_MCP_ENDPOINT": mapping_mcp_endpoint,
            "SCIWEAVE_MAPPING_MCP_TOKEN": mapping_mcp_token,
            "SCIWEAVE_REGISTRY_MCP_ENDPOINT": registry_mcp_endpoint,
            "SCIWEAVE_REGISTRY_MCP_TOKEN": registry_mcp_token,
            "SCIWEAVE_COORDINATOR_KAFKA_BOOTSTRAP": kafka_bootstrap,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"missing required coordinator adapter configuration: {', '.join(missing)}")

    snapshot = ResearchMapMcpSnapshotPort(
        endpoint=mapping_mcp_endpoint,
        token=mapping_mcp_token,
    )
    registry = RegistryMcpAvailabilityPort(
        endpoint=registry_mcp_endpoint,
        token=registry_mcp_token,
    )
    publisher = KafkaHandoffPublisher(kafka_bootstrap)
    email_endpoint = os.environ.get(_EMAIL_MCP_ENDPOINT)
    email_token = os.environ.get(_EMAIL_MCP_TOKEN)
    notifications = (
        EmailMcpNotificationPublisher(endpoint=email_endpoint, token=email_token)
        if email_endpoint and email_token
        else _NoopNotificationPublisher()
    )
    connection = sqlite3.connect(config.sqlite_path)
    store = CoordinatorStore(connection)
    return CoordinatorRuntime(
        service=CoordinatorService(store, snapshot, publisher, notifications, registry),
        publisher=publisher,
        connection=connection,
        poll_seconds=config.dispatch_poll_seconds,
    )


class CoordinatorRuntime:
    """Wraps the core service with adapter lifecycle and a dispatch poll loop."""

    def __init__(
        self,
        *,
        service: CoordinatorService,
        publisher: KafkaHandoffPublisher,
        connection: sqlite3.Connection,
        poll_seconds: float,
    ) -> None:
        self.service = service
        self.publisher = publisher
        self.connection = connection
        self.poll_seconds = poll_seconds
        self._running = False

    def start(self) -> None:
        self.service.startup_scan()
        self._running = True
        logger.info("coordinator adapter wiring ready; polling every %.1fs", self.poll_seconds)

    def stop(self) -> None:
        self._running = False
        self.publisher.close()
        self.connection.close()

    def on_formal_revision_published(self, mapping_domain_id: str, formal_revision_id: str) -> None:
        self.service.on_formal_revision_published(mapping_domain_id, formal_revision_id)

    def poll_once(self) -> None:
        for dispatch in self.service.store.list_dispatches(
            statuses=("result_unknown", "failed")
        ):
            self.service._retry_dispatch(dispatch.dispatch_id)  # noqa: SLF001 - visibility deliberately fine

    def serve_forever(self) -> None:
        """Minimal blocking loop; runs startup scan then retries non-terminal
        dispatches on an interval. Consumption of formal_revision_published
        events remains an integration decision (queue subscriber yet to be
        wired in centre-control deployment)."""
        self.start()
        try:
            while self._running:
                self.poll_once()
                time.sleep(self.poll_seconds)
        finally:
            self.stop()


class _NoopNotificationPublisher:
    """Degraded notification path: keep waiting facts, publish nothing.

    Used when email-service MCP is not configured. Human notification intents
    stay observable through the PendingHandoff waiting state; configuring the
    email endpoint switches to real delivery without code changes.
    """

    def publish(self, intent) -> None:  # type: ignore[no-untyped-def]
        logger.info("notification intent suppressed (email MCP not configured): %s", intent.notification_kind)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = CoordinatorConfig.from_environment()
    runtime = build(config)
    try:
        runtime.serve_forever()
    except KeyboardInterrupt:
        runtime.stop()
        logger.info("coordinator stopped")


if __name__ == "__main__":
    main()