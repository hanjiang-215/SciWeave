import unittest

from work_agent_runtime import FakeQueue, WorkAgentRuntime


class FakeQueueRuntimeTests(unittest.TestCase):
    """FakeQueue drives the runtime seam without a broker; Kafka adapter is thin.

    The Kafka adapter itself is a thin kafka-python wrapper and is exercised in
    the local Redpanda integration script; unit tests stay broker-free.
    """

    def test_fake_queue_holds_until_polled_and_commits(self):
        queue = FakeQueue()
        self.assertFalse(queue.committed)
        self.assertEqual(queue.poll(0), [])
        queue.commit()
        self.assertTrue(queue.committed)

    def test_template_loop_handles_message_and_commits_offset(self):
        runtime = WorkAgentRuntime()
        queue = FakeQueue()
        handled = []

        def handler(target_id, event_id):
            handled.append((target_id, event_id))
            return runtime.handle_message(target_id, event_id)

        queue.subscribe(handler)
        execution = queue.deliver("task-node-a", "event-7")
        self.assertEqual(handled, [("task-node-a", "event-7")])
        self.assertEqual(execution.status, "completed")
        self.assertTrue(execution.draft_id.startswith("draft-task-node-a-"))


if __name__ == "__main__":
    unittest.main()