"""Centre-side disposition on the durable execution store.

The gateway advertised ``answer_question`` and ``review_execution`` while
answering ``unimplemented`` for both; these cases pin the store behaviour the
handlers now call.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from task_agent_worker.store import DispositionError, ExecutionStore


class DispositionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = ExecutionStore(Path(self._tmp.name) / "worker.sqlite3")
        self.store.initialize()
        self.addCleanup(self.store.close)

    def _execution(self, status: str = "running", execution_id: str = "exec-1") -> str:
        with self.store.transaction() as connection:
            connection.execute(
                """INSERT INTO execution_records
                   (execution_id, task_node_id, session_id, status, created_at, updated_at)
                   VALUES (?, 'node-1', 'session-1', ?, '2026-10-27T00:00:00Z',
                           '2026-10-27T00:00:00Z')""",
                (execution_id, status),
            )
        return execution_id

    def _status(self, execution_id: str) -> str:
        return self.store.get_execution(execution_id)["execution_status"]


class AskQuestionTests(DispositionTestCase):
    def test_a_running_execution_is_parked_with_the_question(self) -> None:
        execution_id = self._execution()

        result = self.store.ask_question(execution_id, "which dataset version?")

        self.assertEqual(result["status"], "waiting")
        row = self.store.get_execution(execution_id)
        self.assertEqual(row["execution_status"], "waiting")
        self.assertEqual(row["pending_question"], "which dataset version?")

    def test_an_empty_question_is_refused(self) -> None:
        execution_id = self._execution()

        with self.assertRaises(DispositionError) as caught:
            self.store.ask_question(execution_id, "   ")

        self.assertEqual(caught.exception.code, "invalid_state")

    def test_a_finished_execution_cannot_be_asked(self) -> None:
        execution_id = self._execution(status="completed")

        with self.assertRaises(DispositionError) as caught:
            self.store.ask_question(execution_id, "why?")

        self.assertEqual(caught.exception.code, "invalid_state")

    def test_an_unknown_execution_is_not_found(self) -> None:
        with self.assertRaises(DispositionError) as caught:
            self.store.ask_question("nope", "why?")

        self.assertEqual(caught.exception.code, "not_found")


class AnswerQuestionTests(DispositionTestCase):
    def test_an_answer_queues_a_resumed_execution_and_finishes_the_original(self) -> None:
        execution_id = self._execution()
        self.store.ask_question(execution_id, "which dataset version?")

        result = self.store.answer_question(execution_id, "v3", idempotency_key="answer-1")

        self.assertEqual(result["status"], "queued")
        resumed_id = result["execution_id"]
        self.assertNotEqual(resumed_id, execution_id)
        resumed = self.store.get_execution(resumed_id)
        self.assertEqual(resumed["execution_status"], "queued")
        self.assertEqual(resumed["resume_of"], execution_id)
        self.assertEqual(resumed["task_node_id"], "node-1")
        self.assertEqual(resumed["session_id"], "session-1")
        self.assertEqual(self._status(execution_id), "completed")
        self.assertIsNone(self.store.get_execution(execution_id)["pending_question"])

    def test_the_same_idempotency_key_does_not_queue_twice(self) -> None:
        execution_id = self._execution()
        self.store.ask_question(execution_id, "which dataset version?")
        first = self.store.answer_question(execution_id, "v3", idempotency_key="answer-1")

        second = self.store.answer_question(execution_id, "v3", idempotency_key="answer-1")

        self.assertEqual(second["execution_id"], first["execution_id"])
        self.assertTrue(second["idempotent"])

    def test_answering_an_execution_that_is_not_waiting_is_refused(self) -> None:
        execution_id = self._execution()

        with self.assertRaises(DispositionError) as caught:
            self.store.answer_question(execution_id, "v3", idempotency_key="answer-2")

        self.assertEqual(caught.exception.code, "invalid_state")

    def test_an_empty_answer_is_refused(self) -> None:
        execution_id = self._execution()
        self.store.ask_question(execution_id, "which dataset version?")

        with self.assertRaises(DispositionError):
            self.store.answer_question(execution_id, "  ", idempotency_key="answer-3")


class RecordReviewTests(DispositionTestCase):
    def test_each_decision_maps_to_its_resulting_status(self) -> None:
        for decision, expected in (
            ("request_revision", "needs_revision"),
            ("reject", "rejected"),
            ("request_human_takeover", "human_takeover"),
        ):
            execution_id = self._execution(status="completed", execution_id=f"exec-{decision}")

            result = self.store.record_review(
                execution_id, decision, "checked", idempotency_key=f"key-{decision}"
            )

            self.assertEqual(result["status"], expected)
            self.assertEqual(self._status(execution_id), expected)

    def test_an_unknown_decision_is_refused(self) -> None:
        execution_id = self._execution(status="completed")

        with self.assertRaises(DispositionError):
            self.store.record_review(execution_id, "accept", "ok", idempotency_key="key-1")

    def test_a_review_needs_a_reason(self) -> None:
        execution_id = self._execution(status="completed")

        with self.assertRaises(DispositionError):
            self.store.record_review(execution_id, "reject", "  ", idempotency_key="key-2")

    def test_a_running_execution_cannot_be_reviewed(self) -> None:
        execution_id = self._execution()

        with self.assertRaises(DispositionError) as caught:
            self.store.record_review(execution_id, "reject", "no", idempotency_key="key-3")

        self.assertEqual(caught.exception.code, "invalid_state")

    def test_the_same_idempotency_key_does_not_decide_twice(self) -> None:
        execution_id = self._execution(status="completed")
        self.store.record_review(execution_id, "reject", "no", idempotency_key="key-4")

        second = self.store.record_review(
            execution_id, "request_revision", "revise", idempotency_key="key-4"
        )

        self.assertTrue(second["idempotent"])
        self.assertEqual(self._status(execution_id), "rejected")

    def test_a_review_is_audited(self) -> None:
        execution_id = self._execution(status="completed")

        self.store.record_review(execution_id, "reject", "no", idempotency_key="key-5")

        events = [row["event_type"] for row in self.store.list_recent_audit_events()]
        self.assertIn("execution_reviewed", events)


if __name__ == "__main__":
    unittest.main()
