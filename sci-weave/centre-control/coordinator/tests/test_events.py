"""Governance-event consumer tests for the handoff coordinator."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from coordinator.adapter_events import (
    GovernanceEventConsumer,
    KafkaGovernanceEventConsumer,
)


class RecordingCoordinator:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def on_formal_revision_published(self, mapping_domain_id: str, formal_revision_id: str) -> None:
        self.events.append((mapping_domain_id, formal_revision_id))


def test_formal_revision_published_routes_to_service() -> None:
    coordinator = RecordingCoordinator()
    consumer = GovernanceEventConsumer(coordinator)
    envelope = {
        "event_id": "event-1",
        "event_type": "formal_revision_published",
        "schema_version": "1",
        "mapping_domain_id": "iris-demo",
        "dedupe_key": "iris-demo:rev-2",
        "target": {"kind": "formal_revision", "id": "rev-2"},
        "payload": {"formal_revision_id": "rev-2", "domain": "mapping"},
    }
    event = consumer.handle(envelope)
    assert event is not None
    assert event.formal_revision_id == "rev-2"
    assert event.mapping_domain_id == "iris-demo"
    assert coordinator.events == [("iris-demo", "rev-2")]


def test_candidate_events_are_ignored() -> None:
    coordinator = RecordingCoordinator()
    consumer = GovernanceEventConsumer(coordinator)
    for event_type in ("candidate_created", "candidate_head_updated"):
        envelope = {
            "event_id": "event-x",
            "event_type": event_type,
            "mapping_domain_id": "iris-demo",
            "target": {"kind": "candidate", "id": "submission-1"},
            "payload": {},
        }
        assert consumer.handle(envelope) is None
    assert coordinator.events == []


def test_malformed_envelope_is_ignored() -> None:
    coordinator = RecordingCoordinator()
    consumer = GovernanceEventConsumer(coordinator)
    assert consumer.handle({}) is None
    assert consumer.handle({"event_type": "formal_revision_published"}) is None
    assert consumer.handle({"event_type": "formal_revision_published", "mapping_domain_id": "d", "payload": {}}) is None
    assert coordinator.events == []


def test_kafka_consumer_wraps_kafka_consumer_with_group() -> None:
    """KafkaGovernanceEventConsumer instantiates a kafka-python consumer with
    the coordinator group id and subscribes to the governance topic. The
    dependency is imported lazily so broker-free tests use a mock."""
    with patch("kafka.KafkaConsumer") as fake:
        consumer = KafkaGovernanceEventConsumer("127.0.0.1:9092", "coordinator-group")
        fake.assert_called_once()
        fake.return_value.subscribe.assert_called_once_with(["sciweave.governance-events"])
        consumer.close()