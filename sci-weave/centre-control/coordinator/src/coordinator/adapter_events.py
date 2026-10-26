"""Governance-event consumer for the handoff coordinator.

Subscribes to the central ``sciweave.governance-events`` topic (fixed
physical topic from the message-delivery-recovery contract) and translates
``formal_revision_published`` envelopes into ``on_formal_revision_published``
calls. Only published formal revisions trigger the coordinator: candidate
events are consumed by Centre Agent's prereview workflow, not here.

Replay safety mirrors the contract:

- the consumer group holds offsets across restarts,
- ``auto.offset.reset=earliest`` for new groups,
- ``on_formal_revision_published`` is idempotent per trigger revision (the
  store dedupes by pending-handoff keys), so at-least-once delivery does not
  double-dispatch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from .service import CoordinatorService

_GOVERNANCE_TOPIC = "sciweave.governance-events"
_FORMAL_REVISION_PUBLISHED = "formal_revision_published"
_TASK_COMPLETED = "task_completed"


class CoordinatorServiceLike(Protocol):
    def on_formal_revision_published(self, mapping_domain_id: str, formal_revision_id: str) -> None: ...

    def on_task_completed(self, mapping_domain_id: str, task_node_id: str, version_ref: str) -> None: ...


@dataclass(frozen=True)
class GovernanceEvent:
    event_type: str
    mapping_domain_id: str
    formal_revision_id: str
    dedupe_key: str


class GovernanceEventConsumer:
    """Poll one governance envelope at a time and route it to the service."""

    def __init__(self, service: CoordinatorServiceLike) -> None:
        self.service = service

    def handle(self, envelope: dict) -> GovernanceEvent | None:
        event_type = str(envelope.get("event_type") or "")
        payload = envelope.get("payload") or {}
        if event_type == _TASK_COMPLETED:
            return self._handle_task_completed(envelope, payload)
        if event_type != _FORMAL_REVISION_PUBLISHED:
            return None
        formal_revision_id = str(payload.get("formal_revision_id") or envelope.get("formal_revision_id") or "")
        mapping_domain_id = str(envelope.get("mapping_domain_id") or payload.get("mapping_domain_id") or "")
        if not formal_revision_id or not mapping_domain_id:
            return None
        event = GovernanceEvent(
            event_type=event_type,
            mapping_domain_id=mapping_domain_id,
            formal_revision_id=formal_revision_id,
            dedupe_key=str(envelope.get("dedupe_key") or f"{mapping_domain_id}:{formal_revision_id}"),
        )
        self.service.on_formal_revision_published(mapping_domain_id, formal_revision_id)
        return event

    def _handle_task_completed(self, envelope: dict, payload: dict) -> GovernanceEvent | None:
        """Route ``task_completed`` so a finished upstream node releases its downstream.

        Without this route the completion fact never reaches the coordinator in
        a real deployment: the only other trigger is another formal revision,
        so a downstream node would wait for an unrelated edit.
        """
        mapping_domain_id = str(envelope.get("mapping_domain_id") or payload.get("mapping_domain_id") or "")
        task_node_id = str(payload.get("task_node_id") or payload.get("task_node_logical_id") or "")
        version_ref = str(
            payload.get("node_version_ref")
            or payload.get("task_node_version_ref")
            or payload.get("target_node_version_ref")
            or ""
        )
        if not mapping_domain_id or not task_node_id or not version_ref:
            return None
        event = GovernanceEvent(
            event_type=_TASK_COMPLETED,
            mapping_domain_id=mapping_domain_id,
            formal_revision_id=str(payload.get("formal_revision_id") or ""),
            dedupe_key=str(
                envelope.get("dedupe_key")
                or f"{mapping_domain_id}:{task_node_id}:{version_ref}:task_completed"
            ),
        )
        self.service.on_task_completed(mapping_domain_id, task_node_id, version_ref)
        return event


class KafkaGovernanceEventConsumer:
    """kafka-python consumer for the central governance-events topic."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        *,
        topic: str = _GOVERNANCE_TOPIC,
        auto_offset_reset: str = "earliest",
        session_timeout_ms: int = 10_000,
    ) -> None:
        from kafka import KafkaConsumer  # lazily imported so tests run broker-free

        self.topic = topic
        self.consumer = KafkaConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            session_timeout_ms=session_timeout_ms,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
        self.consumer.subscribe([topic])

    def poll(self, timeout_ms: int = 1000) -> list[dict]:
        """Return decoded envelopes for the current poll batch."""
        batch: list[dict] = []
        for _consumer_record in self.consumer.poll(timeout_ms=timeout_ms).values():
            for record in _consumer_record:
                if isinstance(record.value, dict):
                    batch.append(record.value)
        return batch

    def commit(self) -> None:
        self.consumer.commit()

    def close(self) -> None:
        self.consumer.close()