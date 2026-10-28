import tempfile
import unittest
from pathlib import Path

from work_agent_runtime import (
    ExecutionStore,
    FakeDraftBox,
    InboxError,
    InboxStore,
    WorkAgentRuntime,
    WorkerLease,
)


class InboxStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.db = str(Path(self.dir.name) / "inbox.sqlite")
        self._stores: list[InboxStore] = []

    def tearDown(self) -> None:
        for store in self._stores:
            store.close()
        self.dir.cleanup()

    def _store(self) -> InboxStore:
        store = InboxStore(self.db)
        self._stores.append(store)
        return store

    def test_missing_binding_stays_awaiting_and_runs_nothing(self) -> None:
        inbox = self._store()
        runtime = WorkAgentRuntime(inbox=inbox, binding_resolver=lambda _target: False)
        record = runtime.handle_inbound("task-node", "handoff-1")
        self.assertEqual(record.status, "awaiting_workflow_binding")
        status, created = inbox.enqueue("task-node:handoff-1", "task-node", "handoff-1", binding_present=False)
        self.assertEqual(status, "awaiting_workflow_binding")
        self.assertFalse(created)

    def test_bind_transitions_awaiting_to_queued_and_executes(self) -> None:
        inbox = self._store()
        runtime = WorkAgentRuntime(inbox=inbox, binding_resolver=lambda _target: False)
        pending = runtime.handle_inbound("task-node", "handoff-1", "card")
        self.assertEqual(pending.status, "awaiting_workflow_binding")
        record = runtime.bind("task-node:handoff-1")
        self.assertIsNotNone(record)
        self.assertEqual(record.status, "completed")
        self.assertTrue(record.draft_id)
        self.assertEqual(inbox.get("task-node:handoff-1")["status"], "processed")

    def test_duplicate_delivery_executes_once(self) -> None:
        inbox = self._store()
        runtime = WorkAgentRuntime(inbox=inbox)
        first = runtime.handle_inbound("task-node", "handoff-1", "card")
        duplicate = runtime.handle_inbound("task-node", "handoff-1", "card")
        self.assertEqual(first.status, "completed")
        self.assertEqual(first.execution_id, duplicate.execution_id)
        self.assertEqual(inbox.get("task-node:handoff-1")["status"], "processed")

    def test_restart_recovers_queued_rows_and_skips_processed(self) -> None:
        first_db = self._store()
        # Simulate a crash after the message was recorded as queued but before it ran.
        status, created = first_db.enqueue("task-node:handoff-1", "task-node", "handoff-1", "card", binding_present=True)
        self.assertTrue(created)
        self.assertEqual(status, "queued")
        first_db.enqueue("task-node:done-1", "task-node", "done-1", "card", binding_present=True)
        first_db.mark_processed("task-node:done-1")
        first_db.close()

        second_db = self._store()
        runtime = WorkAgentRuntime(inbox=second_db)
        results = runtime.drain_queued()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "completed")
        self.assertEqual(second_db.get("task-node:handoff-1")["status"], "processed")
        self.assertEqual(second_db.get("task-node:done-1")["status"], "processed")

    def test_drain_does_not_rerun_processed_rows(self) -> None:
        inbox = self._store()
        runtime = WorkAgentRuntime(inbox=inbox)
        runtime.handle_inbound("task-node", "handoff-1", "card")
        results = runtime.drain_queued()
        self.assertEqual(results, [])

    def test_bind_on_missing_or_processed_row_raises(self) -> None:
        inbox = self._store()
        inbox.enqueue("task-node:handoff-1", "task-node", "handoff-1", binding_present=False)
        with self.assertRaises(InboxError):
            inbox.bind("task-node:missing")
        inbox.bind("task-node:handoff-1")
        inbox.mark_processed("task-node:handoff-1")
        with self.assertRaises(InboxError):
            inbox.bind("task-node:handoff-1")


class TaskTextTests(unittest.TestCase):
    """ai4-1e9e: the handoff's instruction is stored, not dropped."""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.db = str(Path(self.dir.name) / "inbox.sqlite")

    def test_a_task_text_round_trips_through_the_inbox(self) -> None:
        inbox = InboxStore(self.db)
        self.addCleanup(inbox.close)
        runtime = WorkAgentRuntime(inbox=inbox)
        runtime.handle_inbound("node-1", "evt-1", task_text="Summarise the graph papers.")
        self.assertEqual(inbox.get("node-1:evt-1")["command_text"], "Summarise the graph papers.")

    def test_an_empty_task_text_is_recorded_as_empty_not_as_the_node_id(self) -> None:
        """Empty is a fact the worker has to see; overwriting it hides the defect."""
        inbox = InboxStore(self.db)
        self.addCleanup(inbox.close)
        WorkAgentRuntime(inbox=inbox).handle_inbound("node-1", "evt-1")
        self.assertEqual(inbox.get("node-1:evt-1")["command_text"], "")

    def test_the_task_text_survives_a_restart(self) -> None:
        first = InboxStore(self.db)
        first.enqueue("node-1:evt-1", "node-1", "evt-1", binding_present=True, command_text="do the thing")
        first.close()
        second = InboxStore(self.db)
        self.addCleanup(second.close)
        self.assertEqual(second.get("node-1:evt-1")["command_text"], "do the thing")

    def test_bind_and_drain_carry_the_task_text_instead_of_losing_it(self) -> None:
        """The booking path re-reads the row; the text must come back with it."""
        inbox = InboxStore(self.db)
        self.addCleanup(inbox.close)
        runtime = WorkAgentRuntime(inbox=inbox, binding_resolver=lambda _target: False)
        runtime.handle_inbound("node-1", "evt-1", task_text="bind then run")
        runtime.bind("node-1:evt-1")
        self.assertEqual(inbox.get("node-1:evt-1")["command_text"], "bind then run")


class InboxMigrationTests(unittest.TestCase):
    """An installed kit already has a database; the new column must appear."""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.db = str(Path(self.dir.name) / "old.sqlite")

    def _make_old_database(self) -> None:
        """The schema exactly as it shipped before ai4-1e9e, with a row in it."""
        import sqlite3

        connection = sqlite3.connect(self.db)
        connection.executescript(
            """
            CREATE TABLE inbox_messages (
                dedupe_key TEXT PRIMARY KEY,
                target_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                agent_definition TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('awaiting_workflow_binding', 'queued', 'processed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO inbox_messages VALUES ('node-1:evt-1', 'node-1', 'evt-1', '', 'queued', "
            "'2026-10-27T00:00:00+00:00', '2026-10-27T00:00:00+00:00')"
        )
        connection.commit()
        connection.close()

    def test_an_old_database_gains_the_column_and_keeps_its_rows(self) -> None:
        self._make_old_database()
        inbox = InboxStore(self.db)
        self.addCleanup(inbox.close)
        row = inbox.get("node-1:evt-1")
        self.assertIsNotNone(row, "the migration must not drop rows")
        self.assertEqual(row["command_text"], "", "old rows have no task text, not a guess")
        self.assertEqual(row["status"], "queued")

    def test_the_migration_is_repeatable(self) -> None:
        """Every start runs it; a second run must not fail or duplicate a column."""
        self._make_old_database()
        InboxStore(self.db).close()
        inbox = InboxStore(self.db)
        self.addCleanup(inbox.close)
        self.assertEqual(inbox.get("node-1:evt-1")["command_text"], "")

    def test_a_new_column_can_be_written_after_a_migration(self) -> None:
        self._make_old_database()
        inbox = InboxStore(self.db)
        self.addCleanup(inbox.close)
        inbox.mark_processed("node-1:evt-1")
        inbox.enqueue("node-2:evt-2", "node-2", "evt-2", binding_present=True, command_text="new text")
        self.assertEqual(inbox.get("node-2:evt-2")["command_text"], "new text")


class InboxCompatTests(unittest.TestCase):
    def test_inbox_defaults_keep_in_memory_path(self) -> None:
        runtime = WorkAgentRuntime()
        execution = runtime.handle_message("task-node", "handoff-1", "card")
        self.assertEqual(execution.status, "completed")

    def test_execution_store_get_by_event(self) -> None:
        store = ExecutionStore()
        first = store.enqueue("task-node", "handoff-1")
        self.assertEqual(store.get_by_event("handoff-1").execution_id, first.execution_id)
        self.assertIsNone(store.get_by_event("other-event"))

    def test_runtime_components_exist(self) -> None:
        self.assertTrue(WorkerLease() is not None)
        self.assertTrue(FakeDraftBox() is not None)
        self.assertIsInstance(WorkAgentRuntime().store, ExecutionStore)


if __name__ == "__main__":
    unittest.main()

class DraftBoxFailureTests(unittest.TestCase):
    """ai4-58d0: a failed run must stay replayable, and one draft shape only."""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.db = str(Path(self.dir.name) / "inbox.sqlite")

    def tearDown(self) -> None:
        self.dir.cleanup()

    def test_failed_draft_write_keeps_the_row_queued(self) -> None:
        class _BrokenDraftBox:
            def write(self, *, target_id, payload):
                raise RuntimeError("draft box down")

        inbox = InboxStore(self.db)
        try:
            runtime = WorkAgentRuntime(inbox=inbox, drafts=_BrokenDraftBox())
            with self.assertRaises(RuntimeError):
                runtime.handle_inbound("task-node", "handoff-1")
            row = inbox.get("task-node:handoff-1")
            self.assertEqual(row["status"], "queued")
        finally:
            inbox.close()

    def test_replay_after_a_restart_completes_the_row(self) -> None:
        class _BrokenDraftBox:
            def write(self, *, target_id, payload):
                raise RuntimeError("draft box down")

        inbox = InboxStore(self.db)
        try:
            with self.assertRaises(RuntimeError):
                WorkAgentRuntime(inbox=inbox, drafts=_BrokenDraftBox()).handle_inbound(
                    "task-node", "handoff-1"
                )
            self.assertEqual(inbox.get("task-node:handoff-1")["status"], "queued")

            # A restarted process has a fresh in-memory execution store, so the
            # queued row is the only surviving fact and must still be runnable.
            restarted = WorkAgentRuntime(inbox=inbox, drafts=FakeDraftBox())
            records = restarted.drain_queued()

            self.assertEqual([record.status for record in records], ["completed"])
            self.assertEqual(inbox.get("task-node:handoff-1")["status"], "processed")
        finally:
            inbox.close()

    def test_runtime_and_real_writer_share_one_draft_shape(self) -> None:
        from work_agent_runtime.draft_writer import BufferMCPDraftWriter

        self.assertTrue(callable(getattr(BufferMCPDraftWriter, "write", None)))
        self.assertFalse(hasattr(BufferMCPDraftWriter, "create_draft"))
        self.assertTrue(callable(getattr(FakeDraftBox, "write", None)))
        self.assertFalse(hasattr(FakeDraftBox, "create_draft"))