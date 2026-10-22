"""audit_trail 共享包回归测试。"""

import sqlite3
import unittest

import audit_trail
from audit_trail import (
    AuditEvent,
    AuditValidationError,
    TransactionRequiredError,
    init_audit_table,
    query_audit_events,
    write_audit_event,
)


def make_event(**overrides) -> AuditEvent:
    base = {
        "actor_id": "researcher-1",
        "actor_type": "human",
        "operation": "draft.status_changed",
        "target_object_type": "draft",
        "target_object_id": "draft-42",
        "result": "accepted",
    }
    base.update(overrides)
    return AuditEvent(**base)


class AuditTrailTest(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        init_audit_table(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_write_within_transaction_persists_event(self) -> None:
        self.conn.execute("BEGIN")
        event_id = write_audit_event(
            self.conn, make_event(proposal_id="proposal-1", task_id="task-7")
        )
        self.conn.commit()
        rows = query_audit_events(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_id"], event_id)
        self.assertEqual(rows[0]["proposal_id"], "proposal-1")
        self.assertEqual(rows[0]["task_id"], "task-7")

    def test_write_outside_transaction_is_rejected(self) -> None:
        with self.assertRaises(TransactionRequiredError):
            write_audit_event(self.conn, make_event())

    def test_write_requires_sqlite_connection(self) -> None:
        with self.assertRaises(TypeError):
            write_audit_event(None, make_event())  # type: ignore[arg-type]

    def test_missing_required_field_rejected(self) -> None:
        self.conn.execute("BEGIN")
        with self.assertRaises(AuditValidationError):
            write_audit_event(self.conn, AuditEvent(actor_id="", actor_type="human", operation="draft.status_changed", target_object_type="draft", target_object_id="d", result="ok"))
        self.conn.rollback()

    def test_invalid_actor_type_rejected(self) -> None:
        self.conn.execute("BEGIN")
        with self.assertRaises(AuditValidationError):
            write_audit_event(self.conn, make_event(actor_type="robot"))
        self.conn.rollback()

    def test_invalid_operation_rejected(self) -> None:
        self.conn.execute("BEGIN")
        with self.assertRaises(AuditValidationError):
            write_audit_event(self.conn, make_event(operation="mapping.magic"))
        self.conn.rollback()

    def test_no_update_or_delete_api(self) -> None:
        self.assertFalse(hasattr(audit_trail, "update_audit_event"))
        self.assertFalse(hasattr(audit_trail, "delete_audit_event"))

    def test_query_filters_by_task_proposal_formal_revision(self) -> None:
        self.conn.execute("BEGIN")
        write_audit_event(self.conn, make_event(task_id="task-a", proposal_id="p-1", formal_revision_id="fr-1"))
        write_audit_event(self.conn, make_event(task_id="task-b", proposal_id="p-2", formal_revision_id="fr-2"))
        write_audit_event(self.conn, make_event(operation="mapping.formal_revision_promoted", task_id="task-a", proposal_id="p-3", formal_revision_id="fr-3"))
        self.conn.commit()

        self.assertEqual(len(query_audit_events(self.conn, task_id="task-a")), 2)
        self.assertEqual(len(query_audit_events(self.conn, proposal_id="p-2")), 1)
        self.assertEqual(len(query_audit_events(self.conn, formal_revision_id="fr-1")), 1)
        self.assertEqual(len(query_audit_events(self.conn, task_id="task-missing")), 0)

    def test_query_filters_by_time_range(self) -> None:
        self.conn.execute("BEGIN")
        first = write_audit_event(self.conn, make_event())
        # 时间按倒序：后写的事件在前。
        second = write_audit_event(self.conn, make_event(operation="wiki.formal_revision_promoted"))
        self.conn.commit()

        all_rows = query_audit_events(self.conn)
        self.assertEqual(len(all_rows), 2)
        self.assertEqual(all_rows[0]["event_id"], second)
        self.assertEqual(all_rows[1]["event_id"], first)

        before = query_audit_events(self.conn, occurred_before="2000-01-01T00:00:00+00:00")
        self.assertEqual(len(before), 0)
        after = query_audit_events(self.conn, occurred_after="2000-01-01T00:00:00+00:00")
        self.assertEqual(len(after), 2)

    def test_refs_json_roundtrip(self) -> None:
        self.conn.execute("BEGIN")
        write_audit_event(self.conn, make_event(refs={"nested": {"zh": "中文"}}))
        self.conn.commit()
        rows = query_audit_events(self.conn)
        self.assertEqual(rows[0]["refs"], {"nested": {"zh": "中文"}})

    def test_all_operations_accepted(self) -> None:
        operations = [
            "draft.status_changed",
            "mapping.prereview_log_appended",
            "mapping.formal_revision_promoted",
            "wiki.prereview_log_appended",
            "wiki.formal_revision_promoted",
        ]
        self.conn.execute("BEGIN")
        for op in operations:
            write_audit_event(self.conn, make_event(operation=op))
        self.conn.commit()
        self.assertEqual(len(query_audit_events(self.conn)), len(operations))


if __name__ == "__main__":
    unittest.main()
