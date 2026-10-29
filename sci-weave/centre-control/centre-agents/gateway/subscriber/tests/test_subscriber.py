"""Behavior tests for the gateway/subscriber role.

These tests drive the subscriber through a fake queue and a deterministic
runtime; they never require a real broker, real model credentials, or fixed
ports.  They cover the message-queue contract items that live on the subscriber
side: persist a ``queued`` record on arrival, business-key deduplication, same
target serialization, draft-buffer write success/failure, and the offset commit
boundary.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
from gateway_subscriber.draft_writer import BufferMCPDraftWriter


class FakeDraftBufferHttp:
    """Minimal in-process /mcp stub that answers create_draft with a draft id."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def server(self) -> ThreadingHTTPServer:
        handler = self._handler
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.app = self  # type: ignore[attr-defined]
        return server

    class _handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            app = self.server.app  # type: ignore[attr-defined]
            method = payload.get("method")
            if method == "tools/call" and payload.get("params", {}).get("name") == "create_draft":
                arguments = payload["params"]["arguments"]
                app.calls.append(arguments)  # type: ignore[attr-defined]
                text = json.dumps({"draft_id": "draft-http-1", "status": "drafting"}, ensure_ascii=False)
                body = json.dumps(
                    {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"content": [{"type": "text", "text": text}]}}
                ).encode()
            else:
                body = json.dumps({"jsonrpc": "2.0", "id": payload.get("id"), "result": {}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            return


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

    def test_buffer_writer_posts_create_draft_and_returns_draft_id(self) -> None:
        buffer = FakeDraftBufferHttp()
        server = buffer.server
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            writer = BufferMCPDraftWriter(
                endpoint=f"http://127.0.0.1:{server.server_port}/mcp",
                token="test-token",
                namespace="mapping",
                submitter_id="agent-1",
            )
            self.enqueue(task_handoff("node-1", "event-1"))
            runner = SubscriberWorkerRunner(self.store, self.service, DeterministicRuntime(), writer)
            outcome = runner.run_once("node-1")
            self.assertEqual(outcome["status"], "completed")
            self.assertEqual(outcome["draft_id"], "draft-http-1")
            self.assertEqual(len(buffer.calls), 1)
            call = buffer.calls[0]
            self.assertEqual(call["namespace"], "mapping")
            self.assertEqual(call["source_execution_record_id"], outcome["execution_id"])
            self.assertEqual(call["source_task_node_id"], "node-1")
        finally:
            server.shutdown()
            server.server_close()

    def test_buffer_writer_unreachable_endpoint_fails_draft(self) -> None:
        writer = BufferMCPDraftWriter(
            endpoint="http://127.0.0.1:1/mcp",
            token="test-token",
            namespace="mapping",
            submitter_id="agent-1",
            timeout_seconds=1.0,
        )
        self.enqueue(task_handoff("node-1", "event-1"))
        runner = SubscriberWorkerRunner(self.store, self.service, DeterministicRuntime(), writer)
        outcome = runner.run_once("node-1")
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["error_summary"], "draft_submission_failed")


if __name__ == "__main__":
    unittest.main()

class PerRecordCommitTests(unittest.TestCase):
    """ai4-9k0m: commit the handled record, not the whole polled batch."""

    def test_fake_queue_records_the_committed_record(self) -> None:
        from gateway_subscriber.queue import FakeQueueClient

        queue = FakeQueueClient()
        first = queue.publish("sciweave.governance-events", "k1", {"a": 1})
        second = queue.publish("sciweave.governance-events", "k2", {"a": 2})

        queue.commit(first)
        queue.commit(second)

        self.assertEqual(
            queue.commits,
            [
                ("sciweave.governance-events", 0, first.offset),
                ("sciweave.governance-events", 0, second.offset),
            ],
        )

    def test_run_loop_commits_each_handled_record(self) -> None:
        from gateway_subscriber import cli
        from gateway_subscriber.queue import FakeQueueClient

        handled: list[Any] = []

        class _Service:
            def handle_message(self, message):
                handled.append(message.key)

            def queued_targets(self):
                return []

        class _Runner:
            def run_once(self, target):
                raise AssertionError("no queued target expected")

        queue = FakeQueueClient()
        queue.publish("sciweave.governance-events", "k1", {"a": 1})
        queue.publish("sciweave.governance-events", "k2", {"a": 2})

        processed = cli.run_loop(_Service(), _Runner(), queue, poll_timeout_ms=0, max_messages=2)

        self.assertEqual(processed, 2)
        self.assertEqual(handled, ["k1", "k2"])
        self.assertEqual([entry[2] for entry in queue.commits], [0, 1])

class RuntimeSelectionTests(unittest.TestCase):
    """ai4-c61f: the passthrough runtime must be an explicit choice."""

    def _settings(self, api_key: str = ""):
        from task_agent_worker.config import WorkerSettings

        return WorkerSettings(
            home=Path(tempfile.mkdtemp()),
            session_dir="sessions",
            connection_scope="local",
            base_url="https://api.example.invalid",
            model="deepseek-chat",
            api_key=api_key,
        )

    def test_missing_api_key_without_the_switch_fails_fast(self) -> None:
        import os

        from gateway_subscriber.cli import build_runtime

        previous = os.environ.pop("SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME", None)
        try:
            with self.assertRaises(SystemExit):
                build_runtime(self._settings())
        finally:
            if previous is not None:
                os.environ["SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME"] = previous

    def test_the_switch_enables_the_passthrough_runtime(self) -> None:
        import os

        from gateway_subscriber.cli import build_runtime
        from task_agent_worker.runtime import FastAgentPassthroughRuntime

        os.environ["SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME"] = "1"
        try:
            runtime = build_runtime(self._settings())
        finally:
            os.environ.pop("SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME", None)

        self.assertIsInstance(runtime, FastAgentPassthroughRuntime)

class CancelGuardTests(unittest.TestCase):
    """ai4-k6m2: a cancel that lands mid-run must survive the terminal write."""

    def setUp(self) -> None:
        from gateway_subscriber.queue import QueueMessage

        self.temp = tempfile.TemporaryDirectory()
        self.store = ExecutionStore(str(Path(self.temp.name) / "centre.sqlite3"))
        self.service = SubscriberService(self.store, agent_id="agent-1")
        self.runner = SubscriberWorkerRunner(self.store, self.service, DeterministicRuntime())
        self.message = QueueMessage(
            topic="sciweave.task-handoff.agent-1",
            partition=0,
            offset=0,
            key="event-1",
            payload=task_handoff("node-1", "event-1"),
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_cancelled_record_is_not_overwritten_by_completion(self) -> None:
        self.service.handle_message(self.message)
        claimed = self.runner._claim("node-1")
        self.assertIsNotNone(claimed)
        with self.store.transaction() as connection:
            connection.execute(
                "UPDATE execution_records SET status = 'cancelled' WHERE execution_id = ?",
                (claimed["execution_id"],),
            )

        result = self.runner._persist(claimed, "completed", result_summary="done")

        self.assertEqual(result["status"], "cancelled")
        stored = self.store.get_execution(claimed["execution_id"])
        self.assertEqual(stored["execution_status"], "cancelled")
        self.assertIsNone(stored["result_summary"])
        with self.store.transaction() as connection:
            leases = connection.execute("SELECT COUNT(*) FROM worker_leases").fetchone()[0]
        self.assertEqual(leases, 0)

class _RecordingCompletionPublisher:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        self.fail = False

    def publish(self, *, execution: dict[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("broker down")
        self.published.append(dict(execution))


class CompletionPublisherTests(unittest.TestCase):
    """B6: a completed execution must publish task_completed for downstream release."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = ExecutionStore(str(Path(self.temp.name) / "centre.sqlite3"))
        self.service = SubscriberService(self.store, agent_id="agent-1")
        self.queue = FakeQueueClient()
        self.queue.subscribe(["sciweave.task-handoff.agent-1"])

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def _enqueue(self) -> dict[str, Any]:
        message = task_handoff("node-1", "event-1", formal_revision_id="rev-9", target_version_ref="node-v7")
        queue_message = self.queue.publish("sciweave.task-handoff.agent-1", "event-1", message)
        return self.service.handle_message(queue_message)

    def test_completed_execution_publishes_task_completed(self) -> None:
        self._enqueue()
        publisher = _RecordingCompletionPublisher()
        runner = SubscriberWorkerRunner(
            self.store, self.service, DeterministicRuntime(), completion_publisher=publisher
        )
        outcome = runner.run_once("node-1")
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(len(publisher.published), 1)
        published = publisher.published[0]
        self.assertEqual(published["mapping_domain_id"], "iris")
        self.assertEqual(published["task_node_id"], "node-1")

    def test_failed_execution_does_not_publish_task_completed(self) -> None:
        self._enqueue()
        publisher = _RecordingCompletionPublisher()
        runner = SubscriberWorkerRunner(
            self.store, self.service, DeterministicRuntime(outcome="failed"),
            completion_publisher=publisher,
        )
        runner.run_once("node-1")
        self.assertEqual(publisher.published, [])


class KafkaCompletionEnvelopeTests(unittest.TestCase):
    """The published envelope matches the coordinator's task_completed router keys."""

    def test_build_envelope_carries_router_fields(self) -> None:
        from gateway_subscriber.completion_publisher import KafkaCompletionPublisher

        publisher = KafkaCompletionPublisher("127.0.0.1:1")
        execution = {
            "execution_id": "exec-1",
            "task_node_id": "node-1",
            "mapping_domain_id": "iris",
            "business_key": "node-1:node-v7:rev-9",
            "draft_id": "draft-1",
            "finished_at": "2026-10-29T00:00:00+00:00",
        }
        body, key = publisher.build_envelope(execution)
        envelope = json.loads(body)
        self.assertEqual(envelope["event_type"], "task_completed")
        self.assertEqual(envelope["mapping_domain_id"], "iris")
        payload = envelope["payload"]
        self.assertEqual(payload["mapping_domain_id"], "iris")
        self.assertEqual(payload["task_node_id"], "node-1")
        # the coordinator router reads node_version_ref OR completed_version_ref
        self.assertEqual(payload["node_version_ref"], "node-v7")
        self.assertEqual(payload["completed_version_ref"], "node-v7")
        self.assertEqual(payload["formal_revision_id"], "rev-9")
        self.assertEqual(key, "node-1:node-v7")


class CompletionOutboxTests(unittest.TestCase):
    """ai4-odwi: a crash between commit and publish must not lose task_completed."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = ExecutionStore(str(Path(self.temp.name) / "centre.sqlite3"))
        self.service = SubscriberService(self.store, agent_id="agent-1")
        self.queue = FakeQueueClient()
        self.queue.subscribe(["sciweave.task-handoff.agent-1"])

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def _enqueue(self) -> None:
        message = task_handoff("node-1", "event-1", formal_revision_id="rev-9", target_version_ref="node-v7")
        queue_message = self.queue.publish("sciweave.task-handoff.agent-1", "event-1", message)
        self.service.handle_message(queue_message)

    def test_event_is_staged_even_if_publish_fails_then_replayed(self) -> None:
        self._enqueue()
        publisher = _RecordingCompletionPublisher()
        publisher.fail = True  # broker down at completion time
        runner = SubscriberWorkerRunner(
            self.store, self.service, DeterministicRuntime(), completion_publisher=publisher
        )
        outcome = runner.run_once("node-1")
        self.assertEqual(outcome["status"], "completed")
        # The publish failed, so nothing was delivered -- but the event is staged.
        self.assertEqual(publisher.published, [])
        pending = self.store.pending_outbox_events()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["event_type"], "task_completed")

        # The broker recovers: the next drain replays the staged event exactly once.
        publisher.fail = False
        delivered = runner.drain_outbox()
        self.assertEqual(delivered, 1)
        self.assertEqual(len(publisher.published), 1)
        self.assertEqual(publisher.published[0]["task_node_id"], "node-1")
        self.assertEqual(publisher.published[0]["mapping_domain_id"], "iris")
        self.assertEqual(self.store.pending_outbox_events(), [])

    def test_event_is_staged_and_delivered_on_success(self) -> None:
        self._enqueue()
        publisher = _RecordingCompletionPublisher()
        runner = SubscriberWorkerRunner(
            self.store, self.service, DeterministicRuntime(), completion_publisher=publisher
        )
        runner.run_once("node-1")
        self.assertEqual(len(publisher.published), 1)
        self.assertEqual(self.store.pending_outbox_events(), [])


class RunLoopIsolationTests(unittest.TestCase):
    """ai4-onvr: one failing target must not skip the rest of the batch."""

    def test_a_failing_runner_does_not_stop_other_targets(self) -> None:
        from gateway_subscriber.cli import run_loop

        class _Service:
            def __init__(self) -> None:
                self.handled: list[Any] = []

            def handle_message(self, message) -> None:
                self.handled.append(message)

            def queued_targets(self):
                return ["bad", "good"]

        class _Runner:
            def __init__(self) -> None:
                self.ran: list[str] = []

            def run_once(self, target):
                self.ran.append(target)
                if target == "bad":
                    raise RuntimeError("worker exploded")
                return None

        class _Queue:
            def __init__(self) -> None:
                self.batch = [QueueMessage(topic="sciweave.task-handoff.agent-1", partition=0, offset=0, key=None, payload={})]
                self.committed: list[Any] = []

            def poll(self, timeout_ms):
                batch, self.batch = self.batch, []
                return batch

            def commit(self, message):
                self.committed.append(message)

        service, runner, queue = _Service(), _Runner(), _Queue()
        processed = run_loop(service, runner, queue, max_messages=1)

        self.assertEqual(processed, 1)
        self.assertEqual(runner.ran, ["bad", "good"])
        self.assertEqual(len(queue.committed), 1)
