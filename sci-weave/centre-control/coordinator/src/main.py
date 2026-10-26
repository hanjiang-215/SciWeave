from __future__ import annotations

import logging
import os
import sqlite3
import time

# Absolute imports: this file is the process entry point (`uv run python
# src/main.py`), not part of the installed `coordinator` package, so relative
# imports would make it unrunnable.
from coordinator.adapter_email import EmailMcpNotificationPublisher
from coordinator.adapter_events import GovernanceEventConsumer, KafkaGovernanceEventConsumer
from coordinator.adapter_publisher import KafkaHandoffPublisher
from coordinator.adapter_registry import RegistryMcpAvailabilityPort
from coordinator.adapter_snapshot import ResearchMapMcpSnapshotPort
from coordinator.config import CoordinatorConfig
from coordinator.ports import NotificationTransportUnavailable
from coordinator.service import CoordinatorService
from coordinator.store import CoordinatorStore

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
    governance_group = os.environ.get("SCIWEAVE_COORDINATOR_KAFKA_GROUP_ID", "coordinator").strip()
    events = KafkaGovernanceEventConsumer(
        kafka_bootstrap,
        governance_group,
    )
    service = CoordinatorService(store, snapshot, publisher, notifications, registry)
    return CoordinatorRuntime(
        service=service,
        publisher=publisher,
        connection=connection,
        poll_seconds=config.dispatch_poll_seconds,
        events=events,
        event_router=GovernanceEventConsumer(service),
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
        events: KafkaGovernanceEventConsumer,
        event_router: GovernanceEventConsumer,
    ) -> None:
        self.service = service
        self.publisher = publisher
        self.connection = connection
        self.poll_seconds = poll_seconds
        self.events = events
        self.event_router = event_router
        self._running = False

    def start(self) -> None:
        self.service.startup_scan()
        self._running = True
        logger.info("coordinator adapter wiring ready; polling every %.1fs", self.poll_seconds)

    def stop(self) -> None:
        self._running = False
        self.events.close()
        self.publisher.close()
        self.connection.close()

    def on_event_batch(self) -> int:
        """Consume one governance-events batch and trigger recomputations.

        Returns the number of events routed. The batch position is committed
        once the batch has been walked, even if an event could not be handled:
        a poison event must not pin the partition and stall every later event,
        and the trace left behind is what an operator acts on.
        """
        envelopes = self.events.poll(timeout_ms=100)
        if not envelopes:
            return 0
        handled = 0
        try:
            for envelope in envelopes:
                try:
                    if self.event_router.handle(envelope) is not None:
                        handled += 1
                except Exception:
                    logger.exception("governance event could not be handled; continuing with the batch")
        finally:
            self.events.commit()
        return handled

    def on_formal_revision_published(self, mapping_domain_id: str, formal_revision_id: str) -> None:
        self.service.on_formal_revision_published(mapping_domain_id, formal_revision_id)

    def poll_once(self) -> None:
        self.on_event_batch()
        self.service.retry_pending_dispatches()

    def serve_forever(self) -> None:
        """Blocking loop: startup scan, then consume governance events and
        retry non-terminal dispatches on an interval."""
        self.start()
        try:
            while self._running:
                self.poll_once()
                time.sleep(self.poll_seconds)
        finally:
            self.stop()


class _NoopNotificationPublisher:
    """Degraded notification path: record the fact, deliver nothing.

    Used when email-service MCP is not configured. It raises instead of
    returning quietly: a silent return would let the coordinator mark the
    dispatch ``published`` and the owner would never be told, not even after
    the endpoint is configured and the process restarts.
    """

    def publish(self, intent) -> None:  # type: ignore[no-untyped-def]
        raise NotificationTransportUnavailable(
            f"email MCP not configured; {intent.notification_kind} intent for "
            f"{intent.related.get('task_node_id')} was not sent"
        )


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