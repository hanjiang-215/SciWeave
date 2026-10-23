import threading
import unittest

from work_agent_libs import ExecutionStore, FakeDraftBox, FakeQueue, WorkerLease, run_one


class WorkAgentRuntimeTests(unittest.TestCase):
    def test_fake_handoff_writes_draft_and_completes(self) -> None:
        store, lease, drafts = ExecutionStore(), WorkerLease(), FakeDraftBox()
        queue = FakeQueue()
        queue.subscribe(lambda target, event: run_one(store, lease, drafts, target, event, "card"))
        execution = queue.deliver("task-node", "handoff-1")
        self.assertEqual(execution.status, "completed")
        self.assertTrue(execution.draft_id)

    def test_duplicate_delivery_does_not_create_second_execution(self) -> None:
        store, lease, drafts = ExecutionStore(), WorkerLease(), FakeDraftBox()
        handler = lambda target, event: run_one(store, lease, drafts, target, event, "card")
        first = handler("task-node", "handoff-1")
        duplicate = handler("task-node", "handoff-1")
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

    def test_agent_definition_is_only_runtime_input(self) -> None:
        store, lease, drafts = ExecutionStore(), WorkerLease(), FakeDraftBox()
        first = run_one(store, lease, drafts, "task-node", "event-1", "card-a")
        second = run_one(store, lease, drafts, "task-node", "event-2", "card-b")
        self.assertEqual(first.status, second.status)
        self.assertNotEqual(first.execution_id, second.execution_id)


if __name__ == "__main__":
    unittest.main()
