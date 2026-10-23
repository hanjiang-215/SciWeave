import threading
import unittest

from work_agent_runtime import (
    ExecutionStore,
    FakeDraftBox,
    FakeQueue,
    WorkAgentRuntime,
    WorkerLease,
    run_one,
)


class WorkAgentRuntimeTests(unittest.TestCase):
    def test_fake_handoff_writes_draft_and_completes(self) -> None:
        runtime = WorkAgentRuntime()
        queue = FakeQueue()
        queue.subscribe(runtime.handle_message)
        execution = queue.deliver("task-node", "handoff-1")
        self.assertEqual(execution.status, "completed")
        self.assertTrue(execution.draft_id)

    def test_duplicate_delivery_does_not_create_second_execution(self) -> None:
        runtime = WorkAgentRuntime()
        first = runtime.handle_message("task-node", "handoff-1", "card")
        duplicate = runtime.handle_message("task-node", "handoff-1", "card")
        self.assertEqual(first.execution_id, duplicate.execution_id)
        self.assertEqual(first.draft_id, duplicate.draft_id)

    def test_lease_rejects_same_target_while_running(self) -> None:
        lease = WorkerLease()
        barrier = threading.Barrier(2)
        outcomes: list[bool] = []

        def claim() -> None:
            barrier.wait()
            outcomes.append(lease.acquire("task-node"))

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(outcomes), [False, True])

    def test_configured_workflow_uses_one_platform_record_and_lease(self):
        from test_workflows import config
        runtime = WorkAgentRuntime()

        def agent(name, prompt, tools=None):
            return "specialist" if name == "entry" else f"{name}:{prompt}"

        execution = runtime.run_workflow("task-node", "workflow-1", config("Router"), agent, "main", "question")
        self.assertEqual(execution.status, "completed")
        self.assertTrue(execution.draft_id)
        self.assertEqual(execution.error_code, None)

        store, lease, drafts = ExecutionStore(), WorkerLease(), FakeDraftBox()
        first = run_one(store, lease, drafts, "task-node", "event-1", "card-a")
        second = run_one(store, lease, drafts, "task-node", "event-2", "card-b")
        self.assertEqual(first.status, second.status)
        self.assertNotEqual(first.execution_id, second.execution_id)


if __name__ == "__main__":
    unittest.main()
