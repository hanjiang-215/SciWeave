from __future__ import annotations

import json
import os
import tempfile
import unittest

from research_mapping.candidate_submission import MappingCandidateService
from research_mapping.domain import FormalMappingRevision, SnapshotRead
from research_mapping.formal_query import FormalQueryService
from research_mapping.formalization import MappingFormalizationService
from research_mapping.review import MappingReviewService
from research_mapping.sqlite_store import SqliteStore

DOMAIN, BASE = "domain-flow", "formal-base"
CANDIDATE_BRANCH, CANDIDATE_COMMIT = "candidate/submission-flow", "candidate-commit-flow"


def candidate_node():
    return {
        "@type": "TaskNode", "@id": "TaskNode/task-flow-v1", "mapping_domain_id": DOMAIN,
        "logical_id": "task-flow", "version_id": "task-flow-v1", "title": "Candidate task",
        "objective": "Complete the task", "scope": "Project scope", "acceptance_criteria": ["verified"],
        "expected_outputs": ["result"], "required_evidence": ["evidence"], "task_owner_id": "owner",
        "lifecycle_state": "candidate", "proposal_id": "proposal-flow",
        "base_formal_revision_id": BASE, "created_by": "hanjiang", "created_at": "2026-10-22T00:00:00Z",
    }


class FlowTerminus:
    def __init__(self):
        self.snapshots = {"base-commit": ({"@id": "TaskNode/base", "@type": "TaskNode", "title": "Base"},)}
        self.head = None

    def create_candidate_snapshot(self, domain_id, base_commit_ref, canonical_snapshot, idempotency_key):
        documents = tuple(json.loads(canonical_snapshot))
        self.snapshots[CANDIDATE_COMMIT] = documents
        self.head = CANDIDATE_COMMIT
        return {"status": "confirmed", "store_id": "store", "branch_id": CANDIDATE_BRANCH,
                "commit_hash": CANDIDATE_COMMIT}

    def current_branch_head(self, store_id, database, branch_id):
        return self.head if branch_id == CANDIDATE_BRANCH else "base-commit"

    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        documents = self.snapshots.get(commit_hash)
        if documents is None:
            return SnapshotRead.unavailable("snapshot_unavailable")
        return SnapshotRead.confirmed(store_id=store_id, database=database, branch_id=branch_id,
                                      commit_hash=commit_hash, documents=documents)

    def create_formal_snapshot(self, store_id, database, branch_id, commit_hash, operation_id):
        return self.read_exact_snapshot(store_id, database, branch_id, commit_hash)


class CandidateReviewFormalizationFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sqlite = SqliteStore(os.path.join(self.tmp.name, "mapping.db"))
        self.sqlite.initialize()
        self.sqlite.add_formal_revision(FormalMappingRevision(
            formal_revision_id=BASE, mapping_domain_id=DOMAIN, terminus_store_id="store",
            formal_branch_id="formal", formal_commit_hash="base-commit", base_formal_revision_id=None,
            source_proposal_id=None, approval_audit_event_id=None, published_by="owner",
            published_at="2026-10-22T00:00:00Z"))
        self.sqlite.set_current_formal_revision(DOMAIN, BASE, updated_at="2026-10-22T00:00:00Z")
        self.terminus = FlowTerminus()
        self.candidates = MappingCandidateService(self.sqlite, self.terminus, terminus_database="db")
        self.reviews = MappingReviewService(self.sqlite, self.terminus, terminus_database="db")
        self.formalizer = MappingFormalizationService(
            self.sqlite, self.terminus, terminus_database="db",
            is_project_owner=lambda actor, domain: actor == "project-owner" and domain == DOMAIN)
        self.queries = FormalQueryService(sqlite_store=self.sqlite, terminus_store=self.terminus,
                                          terminus_database="db")

    def test_candidate_submission_review_owner_approval_formalizes_and_is_queryable(self):
        submitted = self.candidates.submit({
            "mapping_domain_id": DOMAIN, "submitter_id": "hanjiang", "submission_id": "submission-flow",
            "proposal_id": "proposal-flow", "base_formal_revision_id": BASE,
            "nodes": [candidate_node()], "edges": [],
        }, "idempotency-flow")
        self.assertEqual(submitted.status, "confirmed")

        preview = self.reviews.preview("proposal-flow", BASE, submitted.commit_hash)
        self.assertEqual(preview.status, "available")
        buffer = self.reviews.create_buffer(preview.preview_id)
        self.assertEqual(buffer.candidate_commit_hash, submitted.commit_hash)
        self.reviews.record_review(buffer.buffer_id, "project-owner", "approved", "Candidate verified")

        formalized = self.formalizer.formalize(buffer.buffer_id, "formalization-flow")
        self.assertEqual(formalized.status, "succeeded")
        current = self.queries.get_current(DOMAIN)
        self.assertEqual(current.status, "available")
        self.assertEqual(current.formal_revision_id, formalized.formal_revision_id)
        self.assertEqual(current.commit_hash, submitted.commit_hash)
        self.assertEqual(current.nodes[0]["title"], "Candidate task")


if __name__ == "__main__":
    unittest.main()
