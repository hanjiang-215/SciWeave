from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from llm_wiki.candidate_submission import WikiCandidateService
from llm_wiki.formal_domain import WikiSnapshotRead
from llm_wiki.sqlite_store import SqliteStore


class FakeCandidateStore:
    def __init__(self, outcome="confirmed"):
        self.outcome = outcome
        self.calls = []

    def create_candidate_snapshot(self, domain_id, base_commit_ref, canonical_snapshot, idempotency_key):
        self.calls.append((domain_id, base_commit_ref, canonical_snapshot, idempotency_key))
        if self.outcome == "unknown":
            return {"status": "unknown", "reason_code": "store_result_unknown"}
        if self.outcome == "failed":
            return {"status": "failed", "reason_code": "store_rejected"}
        return {
            "status": "confirmed", "store_id": "wiki-store", "branch_id": "candidate-branch",
            "commit_hash": "candidate-commit",
        }

    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        import json
        docs = __import__("json").loads(self.calls[-1][2])
        return WikiSnapshotRead.confirmed(
            store_id=store_id, database=database, branch_id=branch_id,
            commit_hash=commit_hash, documents=docs,
            content_digest=__import__("llm_wiki.canonical", fromlist=["sha256_json"]).sha256_json(docs),
        )


class FakeQualification:
    def __init__(self, status="pending"):
        self.status = status
        self.reason_code = "no_effective_decision"
        self.review_id = None
        self.use_scope = ()
        self.limitations = ()
        self.unknown_facts = ()


class FakeReviews:
    def __init__(self, status="pending"):
        self.status = status
        self.calls = []

    def get_current_qualification(self, resource_version_id, requested_scope=None):
        self.calls.append((resource_version_id, requested_scope))
        return FakeQualification(self.status)


class WikiCandidateSubmissionTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sqlite = SqliteStore(str(Path(self.temp.name) / "wiki.sqlite"))
        self.sqlite.initialize()
        self.sqlite.add_formal_revision(
            formal_revision_id="base-rev", wiki_domain_id="domain-1",
            terminus_store_id="wiki-store", formal_branch_id="main",
            formal_commit_hash="base-commit", content_snapshot_digest="base-digest",
        )
        self.sqlite.set_current_formal_revision("domain-1", "base-rev")
        self.terminus = FakeCandidateStore()
        self.reviews = FakeReviews()
        self.service = WikiCandidateService(
            sqlite_store=self.sqlite, terminus_store=self.terminus,
            resource_review_service=self.reviews, terminus_database="wiki-db",
        )
        self.change = {
            "submission_id": "submission-1", "proposal_id": "proposal-1",
            "wiki_domain_id": "domain-1", "submitter_id": "researcher-1",
            "base_formal_revision_id": "base-rev",
            "document": {
                "@type": "WikiRevision", "wiki_revision_id": "revision-candidate-1",
                "document_id": "document-1", "category": "concept", "title": "Test",
                "body_markdown": "Full body", "created_by": "researcher-1",
                "created_at": "2026-10-22T00:00:00Z",
            },
            "references": [{
                "@type": "ResourceReference", "reference_id": "reference-1",
                "source_revision_id": "revision-candidate-1",
                "target_resource_version_id": "resource-version-1",
                "reference_role": "evidence", "body_locator": "paragraph 1",
                "wiki_domain_id": "domain-1",
            }],
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_accepts_complete_document_and_pending_reference_as_isolated_candidate(self):
        result = self.service.submit(self.change, "key-1")
        self.assertEqual(result.status, "confirmed")
        self.assertEqual(result.proposal_id, "proposal-1")
        self.assertEqual(result.references[0].qualification.status, "pending")
        self.assertFalse(result.owner_review_eligible)
        self.assertEqual(len(self.terminus.calls), 1)
        self.assertEqual(self.sqlite.list_candidate_submissions("domain-1")[0].submission_id, "submission-1")

    def test_same_key_returns_same_candidate_and_different_content_conflicts(self):
        first = self.service.submit(self.change, "key-1")
        second = self.service.submit(self.change, "key-1")
        self.assertEqual(second.candidate_commit_id, first.candidate_commit_id)
        self.assertEqual(len(self.terminus.calls), 1)
        changed = {**self.change, "document": {**self.change["document"], "body_markdown": "changed"}}
        self.assertEqual(self.service.submit(changed, "key-1").reason_code, "idempotency_conflict")

    def test_unknown_store_result_is_retained_for_same_identity_reconciliation(self):
        self.terminus.outcome = "unknown"
        first = self.service.submit(self.change, "key-1")
        self.assertEqual(first.status, "result_unknown")
        self.terminus.outcome = "confirmed"
        retry = self.service.submit(self.change, "key-1")
        self.assertEqual(retry.status, "confirmed")
        self.assertEqual(len(self.terminus.calls), 2)

    def test_stale_base_is_rejected_before_candidate_write(self):
        self.sqlite.set_current_formal_revision("domain-1", None)
        result = self.service.submit(self.change, "key-1")
        self.assertEqual(result.reason_code, "stale_base")
        self.assertEqual(self.terminus.calls, [])

    def test_rejects_invalid_exact_reference_target(self):
        self.change["references"][0]["target_resource_version_id"] = ""
        result = self.service.submit(self.change, "key-1")
        self.assertEqual(result.status, "rejected")
        self.assertEqual(self.terminus.calls, [])


if __name__ == "__main__":
    unittest.main()
