from __future__ import annotations

import json
import unittest

from research_mapping.governance_events import (
    GOVERNANCE_TOPIC,
    GovernanceEvent,
    KafkaGovernanceEventPublisher,
    NoopGovernanceEventPublisher,
    RecordingGovernanceEventPublisher,
    candidate_event,
    create_governance_publisher,
    formal_revision_event,
    utc_now,
)


class GovernanceEventTests(unittest.TestCase):
    def test_candidate_event_envelope_has_stable_fields(self) -> None:
        event = candidate_event(
            mapping_domain_id="iris",
            submission_id="submission-1",
            proposal_id="proposal-1",
            candidate_head="head-a",
        )
        self.assertEqual(event.event_type, "candidate_created")
        self.assertEqual(event.schema_version, "1")
        self.assertEqual(event.mapping_domain_id, "iris")
        self.assertEqual(event.target, {"kind": "candidate", "id": "submission-1"})
        self.assertEqual(event.payload["proposal_id"], "proposal-1")
        self.assertEqual(event.payload["candidate_head"], "head-a")
        self.assertEqual(event.dedupe_key, "iris:submission-1:head-a")

    def test_head_update_reuses_same_dedupe_shape(self) -> None:
        event = candidate_event(
            mapping_domain_id="iris", submission_id="submission-1",
            proposal_id="proposal-1", candidate_head="head-b",
            event_type="candidate_head_updated",
        )
        self.assertEqual(event.event_type, "candidate_head_updated")
        self.assertEqual(event.dedupe_key, "iris:submission-1:head-b")

    def test_formal_revision_event_carries_exact_revision(self) -> None:
        event = formal_revision_event(
            mapping_domain_id="iris", formal_revision_id="rev-2", merge_request_id="buffer-1",
        )
        self.assertEqual(event.event_type, "formal_revision_published")
        self.assertEqual(event.dedupe_key, "iris:rev-2")
        self.assertEqual(event.payload["merge_request_id"], "buffer-1")

    def test_recording_publisher_collects_and_closes(self) -> None:
        publisher = RecordingGovernanceEventPublisher()
        publisher.publish(candidate_event(mapping_domain_id="iris", submission_id="s1"))
        publisher.publish(formal_revision_event(mapping_domain_id="iris", formal_revision_id="r1"))
        self.assertEqual(len(publisher.events), 2)
        publisher.close()
        self.assertTrue(publisher.closed)

    def test_noop_publisher_is_safe(self) -> None:
        publisher = NoopGovernanceEventPublisher()
        publisher.publish(candidate_event(mapping_domain_id="iris", submission_id="s1"))
        publisher.close()

    def test_kafka_publisher_serializes_envelope(self) -> None:
        # Drive the real publisher through an injected producer. The previous
        # version rebuilt the envelope by hand and asserted on its own literal,
        # so it would have passed even if publish() sent nothing.
        sent: list[tuple] = []

        class _Future:
            def get(self, timeout=None):
                return None

        class _Producer:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def send(self, topic, key=None, value=None):
                sent.append((topic, key, value))
                return _Future()

            def close(self) -> None:
                sent.append(("closed", b"", {}))

        publisher = KafkaGovernanceEventPublisher("broker:9092", producer_factory=_Producer)
        event = candidate_event(mapping_domain_id="iris", submission_id="s1", candidate_head="h")
        publisher.publish(event)
        publisher.close()

        topic, key, value = sent[0]
        self.assertEqual(topic, GOVERNANCE_TOPIC)
        self.assertEqual(key, event.dedupe_key.encode("utf-8"))
        self.assertEqual(value["event_type"], "candidate_created")
        self.assertEqual(value["dedupe_key"], event.dedupe_key)
        self.assertEqual(sent[-1][0], "closed")

    def test_publisher_factory_degrades_only_without_a_broker(self) -> None:
        # ai4-te1v: an unset broker is a deliberate "no queue" deployment; a
        # configured broker must not silently become the no-op publisher, or
        # every downstream consumer goes deaf without a trace.
        self.assertIsInstance(create_governance_publisher(None), NoopGovernanceEventPublisher)
        self.assertIsInstance(create_governance_publisher(""), NoopGovernanceEventPublisher)
        self.assertIsInstance(
            create_governance_publisher("broker:9092", producer_factory=lambda **_: _NullProducer()),
            KafkaGovernanceEventPublisher,
        )


class _NullProducer:
    def send(self, topic, key=None, value=None):
        class _Future:
            def get(self, timeout=None):
                return None

        return _Future()

    def close(self) -> None:
        return None


if __name__ == "__main__":
    unittest.main()