"""Cover the service-template subscriber run loop: acceptance guards, processing
and offset commit, without a broker (FakeQueue) and without a real draft box.

The messages here are built the way the producer actually builds them
(ai4-u9gj). `coordinator/src/coordinator/adapter_publisher.py:53-62` writes a
flat dict with no `message_id`, no `schema_version`, no `target` and no
`event_id`, and sets the Kafka key to `"{task_node_id}:{target_node_version_ref}"`.
The previous version of this file hand-wrote `{"target": {...}, "event_id": ...}`,
which is the one shape no producer emits — so the implementation and the test
agreed with each other and with nothing else.
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from work_agent_runtime import (
    FakeDraftBox,
    FakeQueue,
    QueueMessage,
    SqliteExecutionStore,
    WorkAgentRuntime,
)

_SUBSCRIBER_MAIN = Path(__file__).resolve().parents[2] / "service-template" / "gateway" / "subscriber" / "src" / "main.py"


def _load_main():
    spec = importlib.util.spec_from_file_location("subscriber_main", _SUBSCRIBER_MAIN)
    module = importlib.util.module_from_spec(spec)
    sys.modules["subscriber_main"] = module
    spec.loader.exec_module(module)
    return module


def producer_handoff(
    task_node_id: str = "node-1",
    version_ref: str = "cv-1",
    agent_id: str = "researcher-1",
    **overrides,
) -> tuple[dict, str]:
    """The exact envelope and key `adapter_publisher.py` publishes.

    Returns ``(envelope, kafka_key)``. `overrides` are applied to the envelope
    after the defaults so a test can delete or corrupt a single field.
    """
    envelope = {
        "message_type": "task_handoff_ready",
        "mapping_domain_id": "map-1",
        "task_node_id": task_node_id,
        "target_node_version_ref": version_ref,
        "target_agent_id": agent_id,
        "pending_handoff_id": f"pending-{version_ref}",
        "trigger_revision_id": f"rev-{version_ref}",
    }
    envelope.update(overrides)
    return envelope, f"{task_node_id}:{version_ref}"


class SubscriberRunLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main = _load_main()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _runtime(self) -> WorkAgentRuntime:
        """A runtime over a durable store: `ExecutionStore` is in-memory only.

        The in-memory store keys `_by_target` by target, so it *cannot* show two
        rows for one TaskNode — which is exactly what these tests need to look
        at. `SqliteExecutionStore` keeps every row.
        """
        runtime = WorkAgentRuntime()
        runtime.store = SqliteExecutionStore(os.path.join(self._tmp.name, "executions.sqlite3"))
        self.addCleanup(runtime.store.close)
        return runtime

    def _message(self, offset: int, envelope: dict, key: str | None = None) -> QueueMessage:
        return QueueMessage(topic="sciweave.task-handoff.researcher-1", partition=0, offset=offset, key=key, payload=envelope)

    def _run(self, queue, runtime, **kwargs):
        return self.main.run_loop(
            runtime,
            queue,
            ["sciweave.task-handoff.researcher-1"],
            max_messages=1,
            agent_id="researcher-1",
            **kwargs,
        )

    def test_accepts_the_real_producer_envelope(self) -> None:
        envelope, key = producer_handoff()
        queue = FakeQueue()
        queue.messages = [self._message(1, envelope, key=key)]
        runtime = self._runtime()
        processed = self._run(queue, runtime)
        self.assertEqual(processed, 1)
        self.assertTrue(queue.committed)
        execution = runtime.store.get_by_event(f"{key}")
        self.assertIsNotNone(execution)
        self.assertEqual(execution.status, "completed")

    def test_target_id_is_the_task_node_not_the_composite_key(self) -> None:
        """The regression this file exists for.

        `message.key` is `"{task_node_id}:{target_node_version_ref}"`. Falling
        back to it made `target_id` a compound string: two versions of one node
        took separate Worker Leases and ran concurrently, and the draft told the
        central buffer that `source_target_node_id` was `node-1:cv-1`.
        """
        envelope, key = producer_handoff(task_node_id="node-1", version_ref="cv-1")
        queue = FakeQueue()
        queue.messages = [self._message(1, envelope, key=key)]
        runtime = self._runtime()
        self._run(queue, runtime)
        pending = runtime.store.list_all()
        self.assertEqual([row["target_id"] for row in pending], ["node-1"])

    def test_two_versions_of_one_node_are_two_executions(self) -> None:
        runtime = self._runtime()
        queue = FakeQueue()
        for offset, version in enumerate(("cv-1", "cv-2"), start=1):
            envelope, key = producer_handoff(version_ref=version)
            queue.messages = [self._message(offset, envelope, key=key)]
            self.assertEqual(self._run(queue, runtime), 1)
        targets = sorted(row["target_id"] for row in runtime.store.list_all())
        self.assertEqual(targets, ["node-1", "node-1"], "both versions belong to the same task node")

    def test_rejects_a_handoff_for_another_agent(self) -> None:
        envelope, key = producer_handoff(agent_id="researcher-2")
        queue = FakeQueue()
        queue.messages = [self._message(1, envelope, key=key)]
        runtime = self._runtime()
        self.assertEqual(self._run(queue, runtime), 0)
        self.assertTrue(queue.committed)
        self.assertEqual(runtime.store.list_all(), [])

    def test_rejects_an_unsupported_integer_schema_version(self) -> None:
        envelope, key = producer_handoff(schema_version=2)
        queue = FakeQueue()
        queue.messages = [self._message(1, envelope, key=key)]
        runtime = self._runtime()
        self.assertEqual(self._run(queue, runtime), 0)
        self.assertTrue(queue.committed)
        self.assertEqual(runtime.store.list_all(), [])

    def test_accepts_a_supported_integer_schema_version(self) -> None:
        envelope, key = producer_handoff(schema_version=1)
        queue = FakeQueue()
        queue.messages = [self._message(1, envelope, key=key)]
        runtime = self._runtime()
        self.assertEqual(self._run(queue, runtime), 1)

    def test_a_missing_schema_version_is_accepted_and_reported(self) -> None:
        """Every message published today omits it, so rejecting would refuse all.

        The choice is to accept and say so once, rather than let the guard look
        like it is doing something (ai4-derq tracks making it required).
        """
        envelope, key = producer_handoff()
        self.assertNotIn("schema_version", envelope)
        queue = FakeQueue()
        queue.messages = [self._message(1, envelope, key=key)]
        runtime = self._runtime()
        with mock.patch("builtins.print") as printed:
            self.assertEqual(self._run(queue, runtime), 1)
        self.assertTrue(any("no schema_version" in str(call) for call in printed.call_args_list))

    def test_a_handoff_without_a_task_node_is_skipped_not_guessed(self) -> None:
        envelope, key = producer_handoff()
        del envelope["task_node_id"]
        queue = FakeQueue()
        queue.messages = [self._message(1, envelope, key=key)]
        runtime = self._runtime()
        with mock.patch("builtins.print") as printed:
            self.assertEqual(self._run(queue, runtime), 0)
        self.assertTrue(any("task_node_id is missing" in str(call) for call in printed.call_args_list))
        self.assertTrue(queue.committed, "a message that cannot be run must not stall the partition")
        self.assertEqual(runtime.store.list_all(), [])


class LayeredEnvelopeTests(unittest.TestCase):
    """The `message-envelope` layout must keep working if it is ever adopted.

    It has no caller today (ai4-derq), but reading by field name means it costs
    nothing to accept both, and a future producer switch should not silently
    break this consumer.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.main = _load_main()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_reads_task_node_and_message_id_from_the_layered_shape(self) -> None:
        envelope = {
            "message_id": "m-1",
            "message_type": "task_handoff_ready",
            "schema_version": 1,
            "dedupe_key": "d-1",
            "routing": {"partition_key": "task:node-1", "target_agent_id": "researcher-1"},
            "payload": {"mapping_domain_id": "map-1", "task_node_id": "node-1"},
        }
        queue = FakeQueue()
        queue.messages = [QueueMessage(topic="t", partition=0, offset=1, key="node-1:cv-1", payload=envelope)]
        runtime = WorkAgentRuntime()
        runtime.store = SqliteExecutionStore(os.path.join(self._tmp.name, "layered.sqlite3"))
        self.addCleanup(runtime.store.close)
        processed = self.main.run_loop(runtime, queue, ["t"], max_messages=1, agent_id="researcher-1")
        self.assertEqual(processed, 1)
        self.assertEqual([row["target_id"] for row in runtime.store.list_all()], ["node-1"])
        self.assertIsNotNone(runtime.store.get_by_event("m-1"))


class SubscriberDraftBoundaryTests(unittest.TestCase):
    """The subscriber never holds draft-box credentials (ai4-z3z4, ai4-4zjz).

    Drafts are written by the agent inside the worker through a draft-box MCP
    server. If the subscriber also assembled a writer, one execution would write
    two drafts, and the credential would sit in the wrong process.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.main = _load_main()

    def test_a_configured_draft_box_is_not_wired_into_the_subscriber(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"DRAFT_BUFFER_MCP_URL": "https://buffer.invalid/mcp", "DRAFT_BUFFER_MCP_TOKEN": "t"},
            clear=False,
        ):
            runtime = self.main.build_runtime()
        self.assertIsInstance(runtime.drafts, FakeDraftBox, "the subscriber must fall back to the fake draft box")

    def test_the_subscriber_module_does_not_import_the_draft_writer(self) -> None:
        source = _SUBSCRIBER_MAIN.read_text(encoding="utf-8")
        self.assertNotIn("BufferMCPDraftWriter", source)
        self.assertNotIn("DRAFT_BUFFER_MCP_TOKEN", source)


if __name__ == "__main__":
    unittest.main()
