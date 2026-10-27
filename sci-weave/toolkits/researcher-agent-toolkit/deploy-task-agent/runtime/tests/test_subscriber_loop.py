"""Cover the service-template subscriber run loop: acceptance guards, processing
and offset commit, without a broker (FakeQueue) and without a real draft box.
"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from work_agent_runtime import FakeDraftBox, FakeQueue, QueueMessage, WorkAgentRuntime

_SUBSCRIBER_MAIN = Path(__file__).resolve().parents[2] / "service-template" / "gateway" / "subscriber" / "src" / "main.py"


def _load_main():
    spec = importlib.util.spec_from_file_location("subscriber_main", _SUBSCRIBER_MAIN)
    module = importlib.util.module_from_spec(spec)
    sys.modules["subscriber_main"] = module
    spec.loader.exec_module(module)
    return module


class SubscriberRunLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main = _load_main()

    def _message(self, offset: int, payload: dict, key: str | None = None) -> QueueMessage:
        return QueueMessage(topic="sciweave.task-handoff.researcher-1", partition=0, offset=offset, key=key, payload=payload)

    def test_accepts_matching_agent_message_and_commits(self) -> None:
        queue = FakeQueue()
        queue.messages = [
            self._message(1, {"target": {"id": "node-1", "agent_id": "researcher-1"}, "event_id": "handoff-1"}),
        ]
        runtime = WorkAgentRuntime()
        processed = self.main.run_loop(runtime, queue, ["sciweave.task-handoff.researcher-1"], max_messages=1, agent_id="researcher-1")
        self.assertEqual(processed, 1)
        self.assertTrue(queue.committed)
        execution = runtime.store.get_by_event("handoff-1")
        self.assertIsNotNone(execution)
        self.assertEqual(execution.status, "completed")

    def test_rejects_other_agent_message_without_processing(self) -> None:
        queue = FakeQueue()
        queue.messages = [
            self._message(1, {"target": {"id": "node-1", "agent_id": "researcher-2"}, "event_id": "handoff-1"}),
        ]
        runtime = WorkAgentRuntime()
        processed = self.main.run_loop(runtime, queue, ["sciweave.task-handoff.researcher-1"], max_messages=1, agent_id="researcher-1")
        self.assertEqual(processed, 0)
        self.assertTrue(queue.committed)
        self.assertIsNone(runtime.store.get_by_event("handoff-1"))

    def test_rejects_unsupported_schema_version_without_processing(self) -> None:
        queue = FakeQueue()
        queue.messages = [
            self._message(1, {"target": {"id": "node-1"}, "event_id": "handoff-1", "schema_version": "2"}),
        ]
        runtime = WorkAgentRuntime()
        processed = self.main.run_loop(runtime, queue, ["sciweave.task-handoff.researcher-1"], max_messages=1, agent_id="researcher-1")
        self.assertEqual(processed, 0)
        self.assertTrue(queue.committed)
        self.assertIsNone(runtime.store.get_by_event("handoff-1"))

    def test_accepts_message_without_optional_guard_fields(self) -> None:
        queue = FakeQueue()
        queue.messages = [
            self._message(1, {"target": {"id": "node-1"}, "event_id": "handoff-1"}),
        ]
        runtime = WorkAgentRuntime()
        processed = self.main.run_loop(runtime, queue, ["sciweave.task-handoff.researcher-1"], max_messages=1, agent_id="researcher-1")
        self.assertEqual(processed, 1)
        self.assertTrue(queue.committed)


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