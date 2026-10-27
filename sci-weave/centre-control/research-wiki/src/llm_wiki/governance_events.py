"""Governance event publisher for the Wiki management surface.

Symmetric to ``research_mapping.governance_events``: the domain services stay
queue-agnostic, ``WikiManagementService`` accepts an optional
``GovernanceEventPublisher`` port and publishes one event when a candidate is
submitted and one when a formal revision is published. Transport
(Kafka/Redpanda) is injected, never imported by the domain core; tests use
the in-memory ``RecordingGovernanceEventPublisher``.

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
    wiki_domain_id: str
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
    wiki_domain_id: str,
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
        wiki_domain_id=wiki_domain_id,
        occurred_at=utc_now(),
        dedupe_key=f"{wiki_domain_id}:{submission_id}:{candidate_head or ''}",
        target={"kind": "candidate", "id": submission_id},
        payload={
            "submission_id": submission_id,
            "proposal_id": proposal_id,
            "candidate_head": candidate_head,
            "domain": "wiki",
        },
    )


def formal_revision_event(
    *,
    wiki_domain_id: str,
    formal_wiki_revision_id: str,
    merge_request_id: str | None = None,
) -> GovernanceEvent:
    """Envelope for one published formal revision."""
    return GovernanceEvent(
        event_id=str(uuid.uuid4()),
        event_type="formal_revision_published",
        schema_version="1",
        wiki_domain_id=wiki_domain_id,
        occurred_at=utc_now(),
        dedupe_key=f"{wiki_domain_id}:{formal_wiki_revision_id}",
        target={"kind": "formal_revision", "id": formal_wiki_revision_id},
        payload={
            "formal_revision_id": formal_wiki_revision_id,
            "merge_request_id": merge_request_id,
            "domain": "wiki",
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
        # ai4-xncm: 连接惰性建立。kafka-python 的 KafkaProducer 构造期同步等
        # broker 元数据（默认 60 秒），broker 不可达时抛 KafkaTimeoutError，于是
        # 「配了队列但队列不通」会连带让 wiki 管理 MCP 起不来。第一次发布时才连，
        # 领域写入路径的 _publish_safely 会兜住异常。
        self._bootstrap_servers = bootstrap_servers
        self._producer_factory = producer_factory
        self._producer: Any | None = None
        self.topic = topic
        self._timeout = timeout_seconds

    def _producer_instance(self) -> Any:
        if self._producer is None:
            producer_factory = self._producer_factory
            if producer_factory is None:
                from kafka import KafkaProducer  # lazy import keeps domain tests broker-free

                producer_factory = KafkaProducer
            self._producer = producer_factory(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
            )
        return self._producer

    def publish(self, event: GovernanceEvent) -> None:
        envelope = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "schema_version": event.schema_version,
            "wiki_domain_id": event.wiki_domain_id,
            "occurred_at": event.occurred_at,
            "dedupe_key": event.dedupe_key,
            "target": event.target,
            "payload": event.payload,
        }
        self._producer_instance().send(
            self.topic, key=event.dedupe_key.encode("utf-8"), value=envelope
        ).get(timeout=self._timeout)

    def close(self) -> None:
        if self._producer is not None:
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

    Unset broker means "this deployment has no queue": the domain keeps
    working and Centre Agent falls back to snapshot scans. A configured broker
    must not silently degrade to no-op, otherwise wiki candidates and formal
    revisions never reach any consumer even though the operator configured one.
    """
    if not bootstrap_servers:
        return NoopGovernanceEventPublisher()
    return KafkaGovernanceEventPublisher(
        bootstrap_servers, topic=topic, producer_factory=producer_factory
    )