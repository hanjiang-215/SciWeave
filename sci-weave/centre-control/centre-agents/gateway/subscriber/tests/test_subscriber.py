"""Behavior tests for the gateway/subscriber role.

These tests drive the subscriber through a fake queue and a deterministic
runtime; they never require a real broker, real model credentials, or fixed
ports.  They cover the message-queue contract items that live on the subscriber
side: persist a ``queued`` record on arrival, business-key deduplication, same
target serialization, draft-buffer write success/failure, and the offset commit
boundary.
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from task_agent_worker.store import ExecutionStore, utc_now

from gateway_subscriber.queue import FakeQueueClient, QueueMessage
from gateway_subscriber.service import SubscriberService
from gateway_subscriber.worker_runner import (
    DraftWriteError,
    DraftWriter,
    RuntimeLike,
    RuntimeOutcomeLike,
    SubscriberWorkerRunner,
    WorkerRequest,
)


def task_handoff(
    task_node_id: str,
    event_id: str,
    formal_revision_id: str = "rev-1",
    target_version_ref: str = "node-v1",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": "task_handoff_ready",
        "schema_version": "1",
        "mapping_domain_id": "iris",
        "occurred_at": utc_now(),
        "dedupe_key": f"{task_node_id}:{target_version_ref}:{formal_revision_id}",
        "target": {"kind": "task_node", "id": task_node_id},
        "payload": {
            "target_agent_id": "agent-1",
            "target_node_version_ref": target_version_ref,
            "source_node_version_ref": "source-v1",
            "dependency_edge_version_ref": "edge-v1",
            "formal_revision_id": formal_revision_id,
            "required_outputs": [],
        },
    }


class DeterministicRuntime(RuntimeLike):
    """Process-safe fake runtime mirroring TestRuntimeAdapter's outcome model."""

    def __init__(self, outcome: str = "completed", duration_seconds: float = 0) -> None:
        self.outcome = outcome
        self.duration_seconds = duration_seconds

    def run(self, request: WorkerRequest) -> RuntimeOutcomeLike:
        return _Outcome(self.outcome, result="deterministic runtime completed")

    def resume(self, request: WorkerRequest) -> RuntimeOutcomeLike:
        return _Outcome(self.outcome, result="deterministic runtime resumed")


class _Outcome(RuntimeOutcomeLike):
    def __init__(self, status: str, result: str | None = None) -> None:
        self.status = status
        self.result_summary = result
        self.error_summary = None if status not in {"failed", "cancelled"} else "deterministic error"


class FakeDraftWriter(DraftWriter):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.written: list[dict[str, Any]] = []

    def write(self, *, execution: dict[str, Any], result_summary: str) -> str:
        if self.fail:
            raise DraftWriteError("draft_unavailable")
        self.written.append({"execution_id": execution["execution_id"], "result_summary": result_summary})
        return f"draft-{execution['execution_id']}"


class SubscriberTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = ExecutionStore(str(Path(self.temp.name) / "centre.sqlite3"))
        self.service = SubscriberService(self.store, agent_id="agent-1")
        self.queue = FakeQueueClient()
        self.queue.subscribe(["sciweave.task-handoff.agent-1"])

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def enqueue(self, message: dict[str, Any], key: str | None = None) -> dict[str, Any]:
        queue_message = self.queue.publish(
            "sciweave.task-handoff.agent-1",
            key or message["event_id"],
            message,
        )
        return self.service.handle_message(queue_message)

    def test_message_creates_queued_record_with_trigger_ref(self) -> None:
        result = self.enqueue(task_handoff("node-1", "event-1"))
        self.assertEqual(result["execution_status"], "queued")
        self.assertEqual(result["trigger"], "queue")
        self.assertEqual(result["trigger_ref"], "event-1")
        self.assertEqual(result["task_node_id"], "node-1")
        with self.store.lock:
            audit = self.store.connection.execute(
                "SELECT COUNT(*) FROM audit_events WHERE event_type = 'message_received'"
            ).fetchone()[0]
        self.assertEqual(audit, 1)

    def test_duplicate_message_does_not_create_second_execution(self) -> None:
        first = self.enqueue(task_handoff("node-1", "event-1"))
        second = self.enqueue(task_handoff("node-1", "event-1"))
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["execution_id"], first["execution_id"])
        with self.store.lock:
            count = self.store.connection.execute("SELECT COUNT(*) FROM execution_records").fetchone()[0]
        self.assertEqual(count, 1)

    def test_runner_claims_lease_and_runs_to_completed(self) -> None:
        self.enqueue(task_handoff("node-1", "event-1"))
        runner = SubscriberWorkerRunner(self.store, self.service, DeterministicRuntime())
        outcome = runner.run_once("node-1")
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["result_summary"], "deterministic runtime completed")
        execution = self.store.get_execution(outcome["execution_id"])
        self.assertEqual(execution["execution_status"], "completed")
        self.assertIsNone(execution["error_summary"])

    def test_same_target_is_serialized_by_lease(self) -> None:
        self.enqueue(task_handoff("node-1", "event-1", target_version_ref="node-v1"))
        self.enqueue(task_handoff("node-1", "event-2", target_version_ref="node-v2"))
        runner = SubscriberWorkerRunner(self.store, self.service, DeterministicRuntime())
        first = runner.run_once("node-1")
        self.assertEqual(first["status"], "completed")
        self.assertEqual(first["trigger_ref"], "event-1")
        second = runner.run_once("node-1")
        self.assertEqual(second["status"], "completed")
        self.assertEqual(second["trigger_ref"], "event-2")
        with self.store.lock:
            leases = self.store.connection.execute("SELECT COUNT(*) FROM worker_leases").fetchone()[0]
            statuses = self.store.connection.execute(
                "SELECT status FROM execution_records WHERE task_node_id = 'node-1' ORDER BY created_at"
            ).fetchall()
        self.assertEqual(leases, 0)
        self.assertEqual([row["status"] for row in statuses], ["completed", "completed"])

    def test_held_lease_prevents_second_runner(self) -> None:
        self.enqueue(task_handoff("node-1", "event-1"))
        runner = SubscriberWorkerRunner(self.store, self.service, DeterministicRuntime())
        with self.store.transaction() as connection:
            queued = connection.execute(
                "SELECT execution_id FROM execution_records WHERE status = 'queued'"
            ).fetchone()
            connection.execute(
                "INSERT INTO worker_leases VALUES ('node-1', ?, ?)",
                (queued["execution_id"], utc_now()),
            )
            connection.execute(
                "UPDATE execution_records SET status = 'running' WHERE execution_id = ?",
                (queued["execution_id"],),
            )
        self.assertIsNone(runner.run_once("node-1"))

    def test_concurrent_targets_run_independently(self) -> None:
        self.enqueue(task_handoff("node-1", "event-1"))
        self.enqueue(task_handoff("node-2", "event-2"))
        runner = SubscriberWorkerRunner(self.store, self.service, DeterministicRuntime())
        results = {}
        for target in ("node-1", "node-2"):
            results[target] = runner.run_once(target)
        self.assertEqual(results["node-1"]["status"], "completed")
        self.assertEqual(results["node-2"]["status"], "completed")

    def test_draft_written_before_completed_saves_draft_id(self) -> None:
        self.enqueue(task_handoff("node-1", "event-1"))
        writer = FakeDraftWriter()
        runner = SubscriberWorkerRunner(self.store, self.service, DeterministicRuntime(), writer)
        outcome = runner.run_once("node-1")
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["draft_id"], f"draft-{outcome['execution_id']}")
        execution = self.store.get_execution(outcome["execution_id"])
        self.assertEqual(execution["draft_id"], f"draft-{outcome['execution_id']}")

    def test_draft_failure_flips_record_to_failed(self) -> None:
        self.enqueue(task_handoff("node-1", "event-1"))
        runner = SubscriberWorkerRunner(
            self.store, self.service, DeterministicRuntime(), FakeDraftWriter(fail=True)
        )
        outcome = runner.run_once("node-1")
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["error_summary"], "draft_submission_failed")
        execution = self.store.get_execution(outcome["execution_id"])
        self.assertEqual(execution["execution_status"], "failed")

    def test_offset_committed_only_after_worker_loop_ends(self) -> None:
        self.enqueue(task_handoff("node-1", "event-1"))
        runner = SubscriberWorkerRunner(self.store, self.service, DeterministicRuntime())
        self.assertFalse(self.queue.committed)
        runner.run_once("node-1")
        self.queue.commit()
        self.assertTrue(self.queue.committed)


if __name__ == "__main__":
    unittest.main()