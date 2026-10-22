from __future__ import annotations

import json
import os
import tempfile
import unittest

from research_mapping.candidate_domain import CandidateSnapshotResult
from research_mapping.domain import FormalMappingRevision, SnapshotRead
from research_mapping.review import MappingReviewService
from research_mapping.sqlite_store import SqliteStore

DOMAIN, BASE = "domain", "formal-1"
BASE_DOCS = ({"@id": "TaskNode/n1", "@type": "TaskNode", "title": "Old", "lifecycle_state": "formal"},)
CANDIDATE_DOCS = ({"@id": "TaskNode/n1", "@type": "TaskNode", "title": "New", "lifecycle_state": "candidate"},)


class FakeTerminus:
    def __init__(self):
        self.snapshots = {"base-commit": BASE_DOCS, "candidate-commit": CANDIDATE_DOCS}
        self.calls = []
        self.branch_head = "candidate-commit"

    def current_branch_head(self, store_id, database, branch_id):
        return self.branch_head if branch_id == "candidate-key" else "base-commit"

    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        self.calls.append((store_id, database, branch_id, commit_hash))
        docs = self.snapshots.get(commit_hash)
        if docs is None:
            return SnapshotRead.unavailable("unavailable")
        return SnapshotRead.confirmed(store_id=store_id, database=database, branch_id=branch_id,
                                      commit_hash=commit_hash, documents=docs)


class MappingReviewTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sqlite = SqliteStore(os.path.join(self.tmp.name, "mapping.db"))
        self.sqlite.initialize()
        revision = FormalMappingRevision(
            formal_revision_id=BASE, mapping_domain_id=DOMAIN, terminus_store_id="store",
            formal_branch_id="formal", formal_commit_hash="base-commit",
            base_formal_revision_id=None, source_proposal_id=None, approval_audit_event_id=None,
            published_by="owner", published_at="2026-10-22T00:00:00Z")
        self.sqlite.add_formal_revision(revision)
        self.sqlite.set_current_formal_revision(DOMAIN, BASE, updated_at="2026-10-22T00:00:00Z")
        with self.sqlite.connection() as db:
            db.execute("INSERT INTO mapping_submission VALUES (?,?,?,?,?,?,?,?,?)",
                ("submission", DOMAIN, "author", BASE, "key", "digest", "proposal", "now", "candidate_created"))
            db.execute("INSERT INTO mapping_proposal VALUES (?,?,?,?,?,?,?,?)",
                ("proposal", DOMAIN, BASE, "store", "candidate-key", "candidate", "author", "now"))
            db.execute("INSERT INTO mapping_candidate_commit VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("candidate-id", DOMAIN, "proposal", "store", "candidate-key", "candidate-commit", BASE,
                 "change-digest", "snapshot-digest", "author", "now"))
            db.execute("INSERT INTO mapping_audit_event VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("candidate-audit", DOMAIN, "author", "candidate_created", "MappingProposal", "proposal",
                 "confirmed", "now", "submission", "proposal", "candidate-id"))
            db.commit()
        self.terminus = FakeTerminus()
        self.service = MappingReviewService(self.sqlite, self.terminus, terminus_database="db")

    def test_malformed_snapshot_is_rejected_and_audited(self):
        self.terminus.snapshots["candidate-commit"] = ({"@type": "TaskNode", "title": "Missing ID"},)
        result = self.service.preview("proposal", BASE, "candidate-commit")
        self.assertEqual(result.reason_code, "preview_unavailable")
        with self.sqlite.connection() as db:
            attempt = db.execute("SELECT result_code FROM mapping_review_attempt").fetchone()
            previews = db.execute("SELECT COUNT(*) FROM mapping_review_preview").fetchone()[0]
        self.assertEqual(attempt["result_code"], "preview_unavailable")
        self.assertEqual(previews, 0)

    def test_preview_handles_no_change_and_head_mismatch(self):
        self.terminus.snapshots["candidate-commit"] = BASE_DOCS
        unchanged = self.service.preview("proposal", BASE, "candidate-commit")
        self.assertEqual(unchanged.changes, ())
        self.assertEqual(unchanged.route_impact, "unchanged")

        self.terminus.branch_head = "later-head"
        stale_head = self.service.preview("proposal", BASE, "candidate-commit")
        self.assertEqual(stale_head.reason_code, "candidate_mismatch")

    def test_buffer_rechecks_candidate_head(self):
        preview = self.service.preview("proposal", BASE, "candidate-commit")
        self.terminus.branch_head = "later-head"
        with self.assertRaisesRegex(ValueError, "candidate_mismatch"):
            self.service.create_buffer(preview.preview_id)
        with self.sqlite.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM mapping_merge_request_buffer").fetchone()[0], 0)

    def test_preview_is_stable_and_contains_field_diff_and_impact(self):
        first = self.service.preview("proposal", BASE, "candidate-commit")
        second = self.service.preview("proposal", BASE, "candidate-commit")
        self.assertEqual(first.status, "available")
        self.assertEqual(first.preview_id, second.preview_id)
        self.assertEqual(first.evidence_id, second.evidence_id)
        self.assertEqual(first.changes, ({"object_type": "TaskNode", "object_id": "TaskNode/n1",
                                          "field": "title", "before": "Old", "after": "New"},))
        self.assertEqual(first.affected_objects, ("TaskNode/n1",))
        self.assertEqual(first.route_impact, "changed")

    def test_preview_refuses_stale_formal_base(self):
        alternate = FormalMappingRevision(
            formal_revision_id="another", mapping_domain_id=DOMAIN, terminus_store_id="store",
            formal_branch_id="formal", formal_commit_hash="other-commit",
            base_formal_revision_id=BASE, source_proposal_id=None, approval_audit_event_id=None,
            published_by="owner", published_at="2026-10-22T00:00:00Z")
        self.sqlite.add_formal_revision(alternate)
        self.sqlite.set_current_formal_revision(DOMAIN, "another", updated_at="now")
        result = self.service.preview("proposal", BASE, "candidate-commit")
        self.assertEqual(result.reason_code, "stale_base")

    def test_buffer_head_read_exception_is_audited_and_creates_no_buffer(self):
        preview = self.service.preview("proposal", BASE, "candidate-commit")

        def unavailable(*_):
            raise TimeoutError("TerminusDB request timed out")

        self.terminus.current_branch_head = unavailable
        with self.assertRaisesRegex(ValueError, "candidate_unavailable"):
            self.service.create_buffer(preview.preview_id)
        with self.sqlite.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM mapping_merge_request_buffer").fetchone()[0], 0)
            attempt = db.execute(
                "SELECT result_code FROM mapping_review_attempt ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            approvals = db.execute(
                "SELECT COUNT(*) FROM mapping_review_event WHERE decision='approved'"
            ).fetchone()[0]
        self.assertEqual(attempt["result_code"], "candidate_unavailable")
        self.assertEqual(approvals, 0)

    def test_buffer_locks_candidate_and_audits_review(self):
        preview = self.service.preview("proposal", BASE, "candidate-commit")
        buffer = self.service.create_buffer(preview.preview_id)
        decision = self.service.record_review(buffer.buffer_id, "reviewer", "returned", "clarify route")
        self.assertEqual(buffer.candidate_commit_hash, "candidate-commit")
        self.assertEqual(decision.actor_id, "reviewer")
        self.assertEqual(decision.decision, "returned")
        with self.sqlite.connection() as db:
            saved = db.execute("SELECT * FROM mapping_merge_request_buffer WHERE buffer_id=?", (buffer.buffer_id,)).fetchone()
            event = db.execute("SELECT * FROM mapping_review_event WHERE buffer_id=?", (buffer.buffer_id,)).fetchone()
        self.assertEqual(saved["candidate_head_commit_hash"], "candidate-commit")
        self.assertEqual(event["reason"], "clarify route")
        with self.sqlite.connection() as db:
            persisted = json.dumps([dict(row) for row in db.execute("SELECT * FROM mapping_review_preview")])
        self.assertNotIn("Old", persisted)
        self.assertNotIn("New", persisted)

    def test_branch_head_read_exception_is_audited_as_unavailable(self):
        def unavailable(*_):
            raise TimeoutError("TerminusDB request timed out")

        self.terminus.current_branch_head = unavailable
        result = self.service.preview("proposal", BASE, "candidate-commit")
        self.assertEqual(result.reason_code, "candidate_unavailable")
        with self.sqlite.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM mapping_review_preview").fetchone()[0], 0)
            attempt = db.execute("SELECT result_code FROM mapping_review_attempt ORDER BY rowid DESC LIMIT 1").fetchone()
        self.assertEqual(attempt[0], "candidate_unavailable")

    def test_unreadable_candidate_does_not_create_preview_or_buffer(self):
        self.terminus.snapshots.pop("candidate-commit")
        result = self.service.preview("proposal", BASE, "candidate-commit")
        self.assertEqual(result.reason_code, "candidate_unavailable")
        with self.sqlite.connection() as db:
            count = db.execute("SELECT COUNT(*) FROM mapping_merge_request_buffer").fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
