from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from research_mapping.domain import FormalMappingRevision, SnapshotRead
from research_mapping.formalization import MappingFormalizationService
from research_mapping.sqlite_store import SqliteStore


class FakeTerminus:
    def __init__(self):
        self.snapshots = {"candidate": ({"@id": "TaskNode/one", "@type": "TaskNode", "title": "Ready"},)}
        self.calls = 0
        self.outcome = "confirmed"

    def current_branch_head(self, store_id, database, branch_id):
        return "candidate" if branch_id == "candidate-branch" else "base-commit"

    def create_formal_snapshot(self, store_id, database, branch_id, commit_hash, operation_id):
        self.calls += 1
        if self.outcome == "unknown":
            return SnapshotRead.unavailable("store_unavailable")
        return self.read_exact_snapshot(store_id, database, branch_id, commit_hash)

    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        docs = self.snapshots.get(commit_hash)
        if docs is None:
            return SnapshotRead.unavailable("unavailable")
        return SnapshotRead.confirmed(store_id=store_id, database=database, branch_id=branch_id,
                                      commit_hash=commit_hash, documents=docs)


class FormalizationTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sqlite = SqliteStore(os.path.join(self.tmp.name, "mapping.db"))
        self.sqlite.initialize()
        revision = FormalMappingRevision("base", "domain", "store", "formal", "base-commit", None,
                                         None, None, "owner", "now")
        self.sqlite.add_formal_revision(revision)
        self.sqlite.set_current_formal_revision("domain", "base", updated_at="now")
        with self.sqlite.connection() as db:
            db.execute("INSERT INTO mapping_submission VALUES (?,?,?,?,?,?,?,?,?)",
                       ("submission", "domain", "author", "base", "key", "digest", "proposal", "now", "candidate_created"))
            db.execute("INSERT INTO mapping_proposal VALUES (?,?,?,?,?,?,?,?)",
                       ("proposal", "domain", "base", "store", "candidate-branch", "candidate", "author", "now"))
            db.execute("INSERT INTO mapping_candidate_commit VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       ("candidate-id", "domain", "proposal", "store", "candidate-branch", "candidate", "base",
                        "digest", "snapshot", "author", "now"))
            db.execute("INSERT INTO mapping_review_preview VALUES (?,?,?,?,?,?,?,?,?)",
                       ("preview", "evidence", "proposal", "domain", "base", "candidate-id", "candidate",
                        '{"changes":[],"affected_objects":[],"route_impact":"unchanged"}', "now"))
            db.execute("INSERT INTO mapping_merge_request_buffer VALUES (?,?,?,?,?,?,?,?,?)",
                       ("buffer", "preview", "proposal", "domain", "base", "candidate-id", "candidate", "pending", "now"))
            db.execute("INSERT INTO mapping_review_event VALUES (?,?,?,?,?,?)",
                       ("approval", "buffer", "owner", "approved", "approve reviewed candidate", "now"))
            db.commit()
        self.terminus = FakeTerminus()
        self.service = MappingFormalizationService(
            self.sqlite, self.terminus, terminus_database="db", is_project_owner=lambda actor, domain: actor == "owner"
        )

    def test_owner_approval_activates_once_and_retry_is_idempotent(self):
        first = self.service.formalize("buffer", "operation")
        again = self.service.formalize("buffer", "operation")
        self.assertEqual(first.status, "succeeded")
        self.assertEqual(again, first)
        self.assertEqual(self.terminus.calls, 1)
        self.service.record_notification_result("operation", delivered=False, reason="mail unavailable")
        self.assertEqual(self.sqlite.get_current_formal_revision_id("domain"), first.formal_revision_id)
        with self.sqlite.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM formal_mapping_revision").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM mapping_formalization_result WHERE result_status='succeeded'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT status FROM mapping_merge_request_buffer WHERE buffer_id='buffer'").fetchone()[0], "merged")
            self.assertEqual(db.execute("SELECT status FROM mapping_notification").fetchone()[0], "failed")

    def test_unknown_formal_snapshot_is_not_activated_and_retry_is_tracked(self):
        self.terminus.outcome = "unknown"
        result = self.service.formalize("buffer", "operation")
        self.assertEqual(result.status, "reconciliation_required")
        self.assertEqual(self.sqlite.get_current_formal_revision_id("domain"), "base")
        self.terminus.outcome = "confirmed"
        retry = self.service.formalize("buffer", "operation")
        self.assertEqual(retry.status, "succeeded")
        self.assertEqual(retry.attempt_number, 2)
        self.assertEqual(self.terminus.calls, 2)

    def test_commit_persisted_then_raised_is_confirmed_from_durable_evidence(self):
        original_connection = self.sqlite.connection
        injected = False

        class CommitThenRaise:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def commit(self):
                nonlocal injected
                self.connection.commit()
                activation_persisted = self.connection.execute(
                    "SELECT COUNT(*) FROM mapping_formalization_result WHERE result_status='succeeded'"
                ).fetchone()[0] == 1
                if activation_persisted and not injected:
                    injected = True
                    raise sqlite3.OperationalError("client lost commit acknowledgement")

        @contextmanager
        def connection_with_lost_acknowledgement():
            with original_connection() as connection:
                yield CommitThenRaise(connection)

        with patch.object(self.sqlite, "connection", side_effect=connection_with_lost_acknowledgement):
            result = self.service.formalize("buffer", "operation")

        self.assertTrue(injected, "the test must exercise commit-success-then-error")
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(self.sqlite.get_current_formal_revision_id("domain"), result.formal_revision_id)
        with original_connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM formal_mapping_revision").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM mapping_formalization_result WHERE result_status='succeeded'").fetchone()[0], 1)
            attempt = db.execute("SELECT result_status FROM mapping_formalization_attempt").fetchone()
        self.assertEqual(attempt["result_status"], "succeeded")

    def test_activation_failure_rolls_back_revision_and_pointer(self):
        with self.sqlite.connection() as db:
            db.execute("""CREATE TRIGGER fail_formal_result BEFORE INSERT ON mapping_formalization_result
                         BEGIN SELECT RAISE(ABORT, 'injected activation failure'); END""")
            db.commit()
        result = self.service.formalize("buffer", "operation")
        self.assertEqual(result.status, "reconciliation_required")
        self.assertEqual(self.sqlite.get_current_formal_revision_id("domain"), "base")
        with self.sqlite.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM formal_mapping_revision").fetchone()[0], 1)
            attempt = db.execute("SELECT result_status FROM mapping_formalization_attempt").fetchone()
        self.assertEqual(attempt["result_status"], "reconciliation_required")

    def test_candidate_head_mismatch_fails_before_formal_write(self):
        self.terminus.current_branch_head = lambda *_: "newer-candidate"
        result = self.service.formalize("buffer", "operation")
        self.assertEqual(result.reason_code, "candidate_mismatch")
        self.assertEqual(self.terminus.calls, 0)
        self.assertEqual(self.sqlite.get_current_formal_revision_id("domain"), "base")

    def test_unavailable_candidate_head_requires_reconciliation(self):
        self.terminus.current_branch_head = lambda *_: None
        result = self.service.formalize("buffer", "operation")
        self.assertEqual(result.status, "reconciliation_required")
        self.assertEqual(self.terminus.calls, 0)
        with self.sqlite.connection() as db:
            self.assertEqual(db.execute("SELECT result_status FROM mapping_formalization_attempt").fetchone()[0],
                             "reconciliation_required")

    def test_missing_or_unauthorized_owner_approval_fails_without_activation(self):
        with self.sqlite.connection() as db:
            db.execute("DELETE FROM mapping_review_event WHERE event_id='approval'")
            db.commit()
        result = self.service.formalize("buffer", "operation")
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.sqlite.get_current_formal_revision_id("domain"), "base")

    def test_later_rejection_invalidates_an_earlier_owner_approval(self):
        with self.sqlite.connection() as db:
            db.execute("INSERT INTO mapping_review_event VALUES (?,?,?,?,?,?)",
                       ("rejection", "buffer", "owner", "rejected", "needs changes", "zzzz"))
            db.commit()
        result = self.service.formalize("buffer", "operation")
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.terminus.calls, 0)
        self.assertEqual(self.sqlite.get_current_formal_revision_id("domain"), "base")

    def test_non_owner_approval_fails_without_graph_write(self):
        with self.sqlite.connection() as db:
            db.execute("UPDATE mapping_review_event SET actor_id='not-owner' WHERE event_id='approval'")
            db.commit()
        result = self.service.formalize("buffer", "operation")
        self.assertEqual(result.reason_code, "owner_approval_required")
        self.assertEqual(self.terminus.calls, 0)
        self.assertEqual(self.sqlite.get_current_formal_revision_id("domain"), "base")

    def test_reconcile_resumes_same_operation_after_unknown_snapshot(self):
        self.terminus.outcome = "unknown"
        first = self.service.formalize("buffer", "operation")
        self.assertEqual(first.status, "reconciliation_required")
        self.terminus.outcome = "confirmed"
        resumed = self.service.reconcile("operation")
        self.assertEqual(resumed.status, "succeeded")
        self.assertEqual(resumed.attempt_number, 2)
        self.assertEqual(self.terminus.calls, 2)
        with self.sqlite.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM formal_mapping_revision").fetchone()[0], 2)

    def test_stale_base_fails_without_formal_snapshot(self):
        second = FormalMappingRevision("other", "domain", "store", "formal", "other-commit", "base",
                                       None, None, "owner", "now")
        self.sqlite.add_formal_revision(second)
        self.sqlite.set_current_formal_revision("domain", "other", updated_at="now")
        result = self.service.formalize("buffer", "operation")
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.sqlite.get_current_formal_revision_id("domain"), "other")


if __name__ == "__main__":
    unittest.main()
