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


class SubscriberDispatchTests(unittest.TestCase):
    """ai4-0fwc: the subscriber starts a worker process per handoff.

    Before this, `gateway/subscriber` ran the model inline under `run_one()`,
    which meant the resident process needed the model credentials and wrote a
    draft payload of `f"{agent_definition}:{event_id}"`. `service-template/worker`
    had the correct shape and no caller.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.main = _load_main()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = str(Path(self._tmp.name) / "kit.sqlite3")

    def _runtime(self, env: dict | None = None):
        with mock.patch.dict(
            os.environ, {"DATABASE_PATH": self.db, **(env or {})}, clear=False
        ):
            runtime = self.main.build_runtime()
        if runtime.inbox is not None:
            self.addCleanup(runtime.inbox.close)
        if getattr(runtime.lease, "durable", False):
            self.addCleanup(runtime.lease.close)
        return runtime

    def test_a_configured_database_wires_the_lease_and_the_dispatcher(self) -> None:
        runtime = self._runtime()
        self.assertTrue(runtime.lease.durable, "the lease must survive the process")
        self.assertIsNotNone(runtime.dispatcher)

    def test_the_lease_and_the_inbox_share_one_database_file(self) -> None:
        """Two files would let the lease and the inbox disagree about state."""
        runtime = self._runtime()
        self.assertEqual(runtime.lease.path, self.db)
        self.assertEqual(runtime.inbox.path, self.db)

    def test_without_a_database_the_subscriber_runs_inline_and_says_so(self) -> None:
        with mock.patch.dict(os.environ, {"DATABASE_PATH": ""}, clear=False), mock.patch(
            "builtins.print"
        ) as printed:
            runtime = self.main.build_runtime()
        self.assertIsNone(runtime.dispatcher)
        self.assertFalse(runtime.lease.durable)
        self.assertTrue(any("DATABASE_PATH is unset" in str(call) for call in printed.call_args_list))

    def test_dispatch_can_be_disabled_for_a_two_service_deployment(self) -> None:
        runtime = self._runtime({"SCIWEAVE_WORKER_DISPATCH": "0"})
        self.assertIsNotNone(runtime.inbox, "the inbox still records the handoff")
        self.assertIsNone(runtime.dispatcher, "but no worker is started")

    def test_a_real_handoff_through_the_subscriber_starts_the_worker(self) -> None:
        """The end-to-end shape: message -> inbox -> subprocess -> processed row.

        The worker runs with the passthrough runtime so no key or network is
        needed; what is asserted is that a *separate process* did the work and
        marked the row, not that a model answered.
        """
        env = {
            "DATABASE_PATH": self.db,
            "SCIWEAVE_AGENT_ID": "researcher-task-agent",
            "SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME": "1",
            "SCIWEAVE_FAST_AGENT_HOME": str(Path(self._tmp.name) / "home"),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            runtime = self.main.build_runtime()
            self.addCleanup(runtime.inbox.close)
            self.addCleanup(runtime.lease.close)
            queue = FakeQueue()
            queue.messages = [
                QueueMessage(
                    topic="t",
                    partition=0,
                    offset=1,
                    key="node-1:cv-1",
                    payload={
                        "message_type": "task_handoff_ready",
                        "task_node_id": "node-1",
                        "target_agent_id": "researcher-task-agent",
                    },
                )
            ]
            processed = self.main.run_loop(
                runtime, queue, ["t"], max_messages=1, agent_id="researcher-task-agent"
            )
            row = runtime.inbox.get("node-1:node-1:cv-1")
        self.assertEqual(processed, 1)
        self.assertEqual(row["status"], "processed", "the subprocess marked the row")
        self.assertIsNone(runtime.lease.holder("node-1"), "the lease was released")


if __name__ == "__main__":
    unittest.main()
