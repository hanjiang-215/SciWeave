"""Durable execution state (ai4-58d0).

A disposition surface runs in a different process from the one that executes, so
the state it acts on has to survive a restart; the in-memory store cannot.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from work_agent_runtime import (
    ExecutionNotFound,
    FakeDraftBox,
    InvalidTransition,
    SqliteExecutionStore,
    WorkAgentRuntime,
)


class DurableStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "executions.sqlite3")
        self.store = SqliteExecutionStore(self.path)
        self.addCleanup(self.store.close)

    def _queued(self, event_id: str = "event-1") -> str:
        return self.store.enqueue("node-1", event_id).execution_id


class RuntimeBoundaryTests(DurableStoreTestCase):
    def test_enqueue_is_idempotent_per_event(self) -> None:
        first = self.store.enqueue("node-1", "event-1")
        second = self.store.enqueue("node-1", "event-1")

        self.assertEqual(first.execution_id, second.execution_id)
        self.assertEqual(len(self.store.list_all()), 1)

    def test_start_only_moves_a_queued_execution(self) -> None:
        record = self.store.enqueue("node-1", "event-1")

        self.assertTrue(self.store.start(record))
        self.assertFalse(self.store.start(record))
        self.assertEqual(self.store.get(record.execution_id).status, "running")

    def test_complete_records_the_draft(self) -> None:
        record = self.store.enqueue("node-1", "event-1")
        self.store.start(record)

        completed = self.store.complete(record, "draft-1")

        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.draft_id, "draft-1")

    def test_fail_records_the_code_and_the_agent(self) -> None:
        record = self.store.enqueue("node-1", "event-1")
        self.store.start(record)

        failed = self.store.fail(record, "agent_error", "planner")

        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error_code, "agent_error")
        self.assertEqual(failed.failed_agent, "planner")

    def test_a_cancel_is_not_overwritten_by_a_later_completion(self) -> None:
        record = self.store.enqueue("node-1", "event-1")
        self.store.start(record)
        self.store.cancel(record.execution_id)

        after = self.store.complete(record, "draft-1")

        self.assertEqual(after.status, "cancelled")
        self.assertIsNone(after.draft_id)

    def test_state_survives_a_reopen(self) -> None:
        record = self.store.enqueue("node-1", "event-1")
        self.store.start(record)
        self.store.close()

        reopened = SqliteExecutionStore(self.path)
        self.addCleanup(reopened.close)

        self.assertEqual(reopened.get(record.execution_id).status, "running")
        self.assertEqual(reopened.get_by_event("event-1").execution_id, record.execution_id)

    def test_the_runtime_runs_against_the_durable_store(self) -> None:
        runtime = WorkAgentRuntime(drafts=FakeDraftBox())
        runtime.store = self.store

        record = runtime.handle_message("node-1", "event-1", "researcher")

        self.assertEqual(record.status, "completed")
        self.assertEqual(self.store.get(record.execution_id).status, "completed")


class DispositionTests(DurableStoreTestCase):
    def test_pending_lists_only_unfinished_work(self) -> None:
        queued = self._queued("event-1")
        running = self.store.enqueue("node-2", "event-2")
        self.store.start(running)
        done = self.store.enqueue("node-3", "event-3")
        self.store.start(done)
        self.store.complete(done, "draft-3")

        pending = {row["execution_id"] for row in self.store.list_pending()}

        self.assertEqual(pending, {queued, running.execution_id})

    def test_cancel_refuses_a_finished_execution(self) -> None:
        record = self.store.enqueue("node-1", "event-1")
        self.store.start(record)
        self.store.complete(record, "draft-1")

        with self.assertRaises(InvalidTransition):
            self.store.cancel(record.execution_id)

    def test_cancel_rejects_an_unknown_execution(self) -> None:
        with self.assertRaises(ExecutionNotFound):
            self.store.cancel("nope")

    def test_a_question_parks_the_execution_until_it_is_answered(self) -> None:
        record = self.store.enqueue("node-1", "event-1")
        self.store.start(record)

        question = self.store.ask(record.execution_id, "which dataset version?")

        self.assertEqual(question["status"], "waiting")
        self.assertEqual(self.store.get(record.execution_id).status, "waiting")
        self.assertEqual(len(self.store.pending_questions()), 1)

        answer = self.store.answer(question["question_id"], "v3")

        self.assertEqual(answer["status"], "queued")
        self.assertEqual(self.store.get(record.execution_id).status, "queued")
        self.assertEqual(self.store.pending_questions(), [])

    def test_a_question_cannot_be_asked_on_a_finished_execution(self) -> None:
        record = self.store.enqueue("node-1", "event-1")
        self.store.start(record)
        self.store.fail(record, "agent_error")

        with self.assertRaises(InvalidTransition):
            self.store.ask(record.execution_id, "why?")

    def test_an_empty_question_or_answer_is_refused(self) -> None:
        record = self.store.enqueue("node-1", "event-1")
        with self.assertRaises(ValueError):
            self.store.ask(record.execution_id, "   ")

        question = self.store.ask(record.execution_id, "which dataset?")
        with self.assertRaises(ValueError):
            self.store.answer(question["question_id"], " ")

    def test_a_question_cannot_be_answered_twice(self) -> None:
        record = self.store.enqueue("node-1", "event-1")
        question = self.store.ask(record.execution_id, "which dataset?")
        self.store.answer(question["question_id"], "v3")

        with self.assertRaises(InvalidTransition):
            self.store.answer(question["question_id"], "v4")

    def test_review_only_applies_to_a_finished_execution(self) -> None:
        record = self.store.enqueue("node-1", "event-1")

        with self.assertRaises(InvalidTransition):
            self.store.review(record.execution_id, "accepted", "looks right")

    def test_a_review_is_append_only(self) -> None:
        record = self.store.enqueue("node-1", "event-1")
        self.store.start(record)
        self.store.complete(record, "draft-1")

        first = self.store.review(record.execution_id, "rejected", "wrong dataset")
        second = self.store.review(record.execution_id, "accepted", "fixed")

        reviews = self.store.reviews(record.execution_id)
        self.assertEqual([review["decision"] for review in reviews], ["rejected", "accepted"])
        self.assertNotEqual(first["review_id"], second["review_id"])

    def test_a_review_needs_a_known_decision_and_a_reason(self) -> None:
        record = self.store.enqueue("node-1", "event-1")
        self.store.start(record)
        self.store.complete(record, "draft-1")

        with self.assertRaises(ValueError):
            self.store.review(record.execution_id, "maybe", "unsure")
        with self.assertRaises(ValueError):
            self.store.review(record.execution_id, "accepted", "  ")


if __name__ == "__main__":
    unittest.main()
