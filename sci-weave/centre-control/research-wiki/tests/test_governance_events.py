from __future__ import annotations

import json
import unittest

from llm_wiki.governance_events import (
    GOVERNANCE_TOPIC,
    GovernanceEvent,
    KafkaGovernanceEventPublisher,
    NoopGovernanceEventPublisher,
    RecordingGovernanceEventPublisher,
    candidate_event,
    formal_revision_event,
    utc_now,
)


class WikiGovernanceEventTests(unittest.TestCase):
    def test_candidate_event_envelope_has_stable_fields(self) -> None:
        event = candidate_event(
            wiki_domain_id="iris-wiki",
            submission_id="submission-1",
            proposal_id="proposal-1",
            candidate_head="head-a",
        )
        self.assertEqual(event.event_type, "candidate_created")
        self.assertEqual(event.schema_version, "1")
        self.assertEqual(event.wiki_domain_id, "iris-wiki")
        self.assertEqual(event.target, {"kind": "candidate", "id": "submission-1"})
        self.assertEqual(event.payload["proposal_id"], "proposal-1")
        self.assertEqual(event.payload["candidate_head"], "head-a")
        self.assertEqual(event.payload["domain"], "wiki")
        self.assertEqual(event.dedupe_key, "iris-wiki:submission-1:head-a")

    def test_head_update_reuses_same_dedupe_shape(self) -> None:
        event = candidate_event(
            wiki_domain_id="iris-wiki", submission_id="submission-1",
            proposal_id="proposal-1", candidate_head="head-b",
            event_type="candidate_head_updated",
        )
        self.assertEqual(event.event_type, "candidate_head_updated")
        self.assertEqual(event.dedupe_key, "iris-wiki:submission-1:head-b")

    def test_formal_revision_event_carries_exact_revision(self) -> None:
        event = formal_revision_event(
            wiki_domain_id="iris-wiki", formal_wiki_revision_id="rev-2", merge_request_id="buffer-1",
        )
        self.assertEqual(event.event_type, "formal_revision_published")
        self.assertEqual(event.dedupe_key, "iris-wiki:rev-2")
        self.assertEqual(event.payload["formal_revision_id"], "rev-2")
        self.assertEqual(event.payload["merge_request_id"], "buffer-1")
        self.assertEqual(event.payload["domain"], "wiki")

    def test_recording_publisher_collects_and_closes(self) -> None:
        publisher = RecordingGovernanceEventPublisher()
        publisher.publish(candidate_event(wiki_domain_id="iris-wiki", submission_id="s1"))
        publisher.publish(formal_revision_event(wiki_domain_id="iris-wiki", formal_wiki_revision_id="r1"))
        self.assertEqual(len(publisher.events), 2)
        publisher.close()
        self.assertTrue(publisher.closed)

    def test_noop_publisher_is_safe(self) -> None:
        publisher = NoopGovernanceEventPublisher()
        publisher.publish(candidate_event(wiki_domain_id="iris-wiki", submission_id="s1"))
        publisher.close()

    def test_kafka_publisher_serializes_envelope(self) -> None:
        event = candidate_event(wiki_domain_id="iris-wiki", submission_id="s1", candidate_head="h")
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
        serialized = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        self.assertTrue(serialized)
        self.assertIn(event.dedupe_key.encode("utf-8"), serialized)


if __name__ == "__main__":
    unittest.main()