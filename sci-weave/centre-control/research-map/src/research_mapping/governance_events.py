"""Governance event publisher for the Mapping management surface.

The domain services stay queue-agnostic.  ``MappingManagementService`` accepts
an optional ``GovernanceEventPublisher`` port and publishes one event when a
candidate is submitted and one when a formal revision is published.  The
transport (Kafka/Redpanda) is injected, never imported by the domain core;
tests use the in-memory ``RecordingGovernanceEventPublisher``.

Events follow the message-queue contract envelope from ``ai4-te1v``: a stable
``event_id``, an ``event_type`` (``candidate_created`` /
``candidate_head_updated`` / ``formal_revision_published``), the exact version
references, and a ``dedupe_key`` so subscribers can block replays.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

GOVERNANCE_TOPIC = "sciweave.governance-events"


@dataclass(frozen=True)
class GovernanceEvent:
    event_id: str
    event_type: str
    schema_version: str
    mapping_domain_id: str
    occurred_at: str
    dedupe_key: str
    target: dict[str, str]
    payload: dict[str, Any]


class GovernanceEventPublisher(Protocol):
    """Port: publish one governance envelope to the central queue."""

    def publish(self, event: GovernanceEvent) -> None: ...
    def close(self) -> None: ...


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def candidate_event(
    *,
    mapping_domain_id: str,
    submission_id: str,
    proposal_id: str | None = None,
    candidate_head: str | None = None,
    event_type: str = "candidate_created",
) -> GovernanceEvent:
    """Envelope for a candidate creation or head update."""
    return GovernanceEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        schema_version="1",
        mapping_domain_id=mapping_domain_id,
        occurred_at=utc_now(),
        dedupe_key=f"{mapping_domain_id}:{submission_id}:{candidate_head or ''}",
        target={"kind": "candidate", "id": submission_id},
        payload={
            "submission_id": submission_id,
            "proposal_id": proposal_id,
            "candidate_head": candidate_head,
            "domain": "mapping",
        },
    )


def formal_revision_event(
    *,
    mapping_domain_id: str,
    formal_revision_id: str,
    merge_request_id: str | None = None,
) -> GovernanceEvent:
    """Envelope for one published formal revision."""
    return GovernanceEvent(
        event_id=str(uuid.uuid4()),
        event_type="formal_revision_published",
        schema_version="1",
        mapping_domain_id=mapping_domain_id,
        occurred_at=utc_now(),
        dedupe_key=f"{mapping_domain_id}:{formal_revision_id}",
        target={"kind": "formal_revision", "id": formal_revision_id},
        payload={
            "formal_revision_id": formal_revision_id,
            "merge_request_id": merge_request_id,
            "domain": "mapping",
        },
    )


class RecordingGovernanceEventPublisher:
    """In-memory publisher used by tests to assert what was emitted."""

    def __init__(self) -> None:
        self.events: list[GovernanceEvent] = []
        self.closed = False

    def publish(self, event: GovernanceEvent) -> None:
        self.events.append(event)

    def close(self) -> None:
        self.closed = True


class KafkaGovernanceEventPublisher:
    """kafka-python producer for the central Redpanda governance topic."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str = GOVERNANCE_TOPIC,
        *,
        timeout_seconds: float = 5.0,
        producer_factory: Callable[..., Any] | None = None,
    ) -> None:
        # The producer factory is injectable so the envelope shape can be
        # asserted without a broker; production leaves it as kafka-python.
        if producer_factory is None:
            from kafka import KafkaProducer  # lazy import keeps domain tests broker-free

            producer_factory = KafkaProducer
        self.topic = topic
        self._producer = producer_factory(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
        )
        self._timeout = timeout_seconds

    def publish(self, event: GovernanceEvent) -> None:
        envelope = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "schema_version": event.schema_version,
            "mapping_domain_id": event.mapping_domain_id,
            "occurred_at": event.occurred_at,
            "dedupe_key": event.dedupe_key,
            "target": event.target,
            "payload": event.payload,
        }
        self._producer.send(self.topic, key=event.dedupe_key.encode("utf-8"), value=envelope).get(timeout=self._timeout)

    def close(self) -> None:
        self._producer.close()


class NoopGovernanceEventPublisher:
    """Default publisher: publish nothing (queue is an optional integration)."""

    def publish(self, event: GovernanceEvent) -> None:
        return

    def close(self) -> None:
        return


def create_governance_publisher(
    bootstrap_servers: str | None,
    *,
    topic: str = GOVERNANCE_TOPIC,
    producer_factory: Callable[..., Any] | None = None,
) -> GovernanceEventPublisher:
    """Pick the publisher from configuration.

    An unset broker means "this deployment has no queue": the domain keeps
    working and Centre Agent falls back to snapshot scans.  A configured broker
    must not silently degrade to no-op, because the coordinator's whole trigger
    is the ``formal_revision_published`` event.
    """
    if not bootstrap_servers:
        return NoopGovernanceEventPublisher()
    return KafkaGovernanceEventPublisher(
        bootstrap_servers, topic=topic, producer_factory=producer_factory
    )