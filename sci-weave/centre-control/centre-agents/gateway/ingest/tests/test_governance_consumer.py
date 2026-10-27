import tempfile
import unittest
from pathlib import Path

from gateway_ingest.domain_mcp import RecordingDomainMCPClient, ReviewableCandidate
from gateway_ingest.service import (
    CentreGovernanceConsumer,
    ConsumeOutcome,
    GovernanceEnvelopeError,
    MemoryProcessedKeyStore,
    SqliteProcessedKeyStore,
    make_event_body,
)


def candidate(candidate_id: str, head: str, base: str | None, status: str = "report_current") -> ReviewableCandidate:
    return ReviewableCandidate(
        candidate_id=candidate_id,
        candidate_head=head,
        base_formal_revision_id=base,
        prereview_status={"status": status, "candidate_id": candidate_id, "candidate_head": head},
    )


def fake_now(clock: list[str]):
    def _now() -> str:
        return clock[0]

    return _now


class CandidateConsumptionTests(unittest.TestCase):
    def test_continuous_head_updates_trigger_recompute_once(self) -> None:
        # Regression (ai4-a2ba #9): repeated head updates in a short window
        # coalesce into one full-snapshot recompute, not one per event.
        clock = ["2026-10-26T10:00:00"]
        mcp = RecordingDomainMCPClient(
            [candidate("sub-1", "head-1", "rev-1"), candidate("sub-2", "head-2", "rev-1")]
        )
        consumer = CentreGovernanceConsumer(mcp, MemoryProcessedKeyStore(), now=fake_now(clock))
        first = consumer.consume(make_event_body(event_type="candidate_head_updated", domain_id="map-1", dedupe_key="map-1:sub-1:head-a", payload={"candidate_id": "sub-1", "candidate_head": "head-a"}))
        second = consumer.consume(make_event_body(event_type="candidate_head_updated", domain_id="map-1", dedupe_key="map-1:sub-1:head-b", payload={"candidate_id": "sub-1", "candidate_head": "head-b"}))
        third = consumer.consume(make_event_body(event_type="candidate_created", domain_id="map-1", dedupe_key="map-1:sub-2:head-c", payload={"candidate_id": "sub-2", "candidate_head": "head-c"}))
        # One full-snapshot review per window; further events in the same window are debounced.
        self.assertEqual(first.recompute_triggered, 1)
        self.assertEqual(second.recompute_triggered, 0)
        self.assertEqual(third.recompute_triggered, 0)

    def test_new_window_triggers_recompute_again(self) -> None:
        clock = ["2026-10-26T10:00:00"]
        mcp = RecordingDomainMCPClient([candidate("sub-1", "head-1", "rev-1")])
        consumer = CentreGovernanceConsumer(mcp, MemoryProcessedKeyStore(), now=fake_now(clock))
        first = consumer.consume(make_event_body(event_type="candidate_head_updated", domain_id="map-1", dedupe_key="map-1:sub-1:head-a", payload={"candidate_id": "sub-1", "candidate_head": "head-a"}))
        self.assertEqual(first.recompute_triggered, 1)
        clock[0] = "2026-10-26T10:02:00"  # next debounce window
        second = consumer.consume(make_event_body(event_type="candidate_head_updated", domain_id="map-1", dedupe_key="map-1:sub-1:head-b", payload={"candidate_id": "sub-1", "candidate_head": "head-b"}))
        self.assertEqual(second.recompute_triggered, 1)

    def test_duplicate_delivery_is_blocked_by_dedupe_key(self) -> None:
        mcp = RecordingDomainMCPClient([candidate("sub-1", "head-1", "rev-1")])
        consumer = CentreGovernanceConsumer(mcp, MemoryProcessedKeyStore())
        body = make_event_body(event_type="candidate_created", domain_id="map-1", dedupe_key="map-1:sub-1:head-1", payload={"candidate_id": "sub-1", "candidate_head": "head-1"})
        first: ConsumeOutcome = consumer.consume(body)
        duplicate: ConsumeOutcome = consumer.consume(body)
        self.assertTrue(first.handled)
        self.assertTrue(duplicate.duplicate)
        self.assertFalse(duplicate.handled)


class FormalRevisionTests(unittest.TestCase):
    def test_formal_revision_only_stales_dependents(self) -> None:
        # Regression (ai4-a2ba #9): publishing rev-2 only invalidates the
        # candidate based on rev-1; the candidate based on rev-2 is untouched.
        mcp = RecordingDomainMCPClient(
            [
                candidate("sub-old", "head-old", "rev-1"),
                candidate("sub-new", "head-new", "rev-2"),
                candidate("sub-current", "head-current", "rev-2", status="report_stale"),
            ]
        )
        consumer = CentreGovernanceConsumer(mcp, MemoryProcessedKeyStore())
        outcome = consumer.consume(
            make_event_body(
                event_type="formal_revision_published",
                domain_id="map-1",
                dedupe_key="map-1:rev-2",
                payload={"formal_revision_id": "rev-2"},
            )
        )
        self.assertEqual(outcome.stale_candidates, ["sub-old"])
        self.assertEqual(mcp.base_moved, [("map-1", "sub-old", "head-old")])
        # A new formal revision always deserves a fresh review.
        self.assertEqual(outcome.recompute_triggered, 1)

    def test_formal_revision_without_current_report_skips_append(self) -> None:
        mcp = RecordingDomainMCPClient(
            [
                candidate("sub-a", "head-a", "rev-1", status="missing_report"),
                candidate("sub-b", "head-b", "rev-1"),
            ]
        )
        consumer = CentreGovernanceConsumer(mcp, MemoryProcessedKeyStore())
        outcome = consumer.consume(
            make_event_body(
                event_type="formal_revision_published",
                domain_id="map-1",
                dedupe_key="map-1:rev-2",
                payload={"formal_revision_id": "rev-2"},
            )
        )
        self.assertEqual(set(outcome.stale_candidates), {"sub-a", "sub-b"})
        # Only the candidate with a currently valid report gets a base_moved append.
        self.assertEqual(mcp.base_moved, [("map-1", "sub-b", "head-b")])


class EnvelopeAndStoreTests(unittest.TestCase):
    def test_unsupported_event_type_is_observable_error(self) -> None:
        mcp = RecordingDomainMCPClient()
        consumer = CentreGovernanceConsumer(mcp, MemoryProcessedKeyStore())
        with self.assertRaises(GovernanceEnvelopeError):
            consumer.consume(make_event_body(event_type="unknown_kind", domain_id="map-1", dedupe_key="k", payload={}))

    def test_missing_domain_is_rejected(self) -> None:
        mcp = RecordingDomainMCPClient()
        consumer = CentreGovernanceConsumer(mcp, MemoryProcessedKeyStore())
        body = make_event_body(event_type="candidate_created", domain_id="map-1", dedupe_key="k", payload={"candidate_id": "s"})
        body.pop("mapping_domain_id")
        body["payload"].pop("mapping_domain_id", None)
        with self.assertRaises(GovernanceEnvelopeError):
            consumer.consume(body)

    def test_error_is_recorded_for_observability(self) -> None:
        mcp = RecordingDomainMCPClient()
        keys = MemoryProcessedKeyStore()
        consumer = CentreGovernanceConsumer(mcp, keys)
        with self.assertRaises(GovernanceEnvelopeError):
            consumer.consume({"event_type": "candidate_created"})
        # Permanent envelope errors are observable, never silently dropped.
        self.assertIn("error:candidate_created", keys._errors)

    def test_sqlite_store_dedupe_survives_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "keys.sqlite")
            store = SqliteProcessedKeyStore(path)
            self.assertFalse(store.already_processed("k1"))
            store.mark_processed("k1")
            self.assertTrue(store.already_processed("k1"))
            store.close()
            reopened = SqliteProcessedKeyStore(path)
            self.assertTrue(reopened.already_processed("k1"))
            reopened.close()


if __name__ == "__main__":
    unittest.main()

class IngestLoopTests(unittest.TestCase):
    """ai4-9k0m: one bad record must not stall the partition, and each offset commits alone."""

    def _consumer(self):
        mcp = RecordingDomainMCPClient([candidate("sub-1", "head-1", "rev-1")])
        return CentreGovernanceConsumer(mcp, MemoryProcessedKeyStore())

    def test_bad_envelope_is_committed_past_and_the_loop_continues(self) -> None:
        from gateway_ingest.cli import FakeQueue, _RawMessage, run_loop

        queue = FakeQueue()
        queue.messages = [
            _RawMessage(topic="sciweave.governance-events", partition=0, offset=10, key=None, payload={"event_type": "bogus"}),
            _RawMessage(
                topic="sciweave.governance-events",
                partition=0,
                offset=11,
                key=None,
                payload=make_event_body(
                    event_type="candidate_created",
                    domain_id="map-1",
                    dedupe_key="map-1:sub-1:head-1",
                    payload={"candidate_id": "sub-1", "candidate_head": "head-1"},
                ),
            ),
        ]

        consumed = run_loop(self._consumer(), queue, poll_timeout_ms=0, max_messages=2)

        self.assertEqual(consumed, 2)
        # Both records were committed individually: offset+1, per record.
        self.assertEqual(
            queue.commits,
            [
                ("sciweave.governance-events", 0, 10),
                ("sciweave.governance-events", 0, 11),
            ],
        )

    def test_commit_targets_the_record_not_the_batch(self) -> None:
        from gateway_ingest.cli import FakeQueue, _RawMessage, run_loop

        queue = FakeQueue()
        queue.messages = [
            _RawMessage(topic="t", partition=3, offset=99, key=None, payload={"event_type": "bogus"}),
        ]

        run_loop(self._consumer(), queue, poll_timeout_ms=0, max_messages=1)

        self.assertEqual(queue.commits, [("t", 3, 99)])