from __future__ import annotations

import os
import tempfile
import unittest

from llm_wiki.formal_domain import WikiReferenceQualification, WikiSnapshotRead
from llm_wiki.canonical import sha256_json
from llm_wiki.formal_query import WikiFormalQueryService
from llm_wiki.sqlite_store import SqliteStore

DOMAIN = "wiki-domain-1"
REVISION = "revision-1"
STORE = "store-1"
DATABASE = "wiki-db"
BRANCH = "main"
COMMIT = "a" * 40
BODY = "# Formal content"


class FakeTerminusStore:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        self.calls.append((store_id, database, branch_id, commit_hash))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeResourceReviewService:
    def __init__(self, qualifications=None):
        self.qualifications = qualifications or {}
        self.calls = []

    def get_current_qualification(self, resource_version_id, requested_scope=None):
        self.calls.append((resource_version_id, requested_scope))
        return self.qualifications.get(
            (resource_version_id, requested_scope),
            WikiReferenceQualification(resource_version_id, "pending", "no_effective_decision"),
        )


class WikiFormalQueryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sqlite = SqliteStore(os.path.join(self.tmp.name, "wiki.db"))
        self.sqlite.initialize()
        self.sqlite.add_formal_revision(
            formal_revision_id=REVISION,
            wiki_domain_id=DOMAIN,
            terminus_store_id=STORE,
            formal_branch_id=BRANCH,
            formal_commit_hash=COMMIT,
            content_snapshot_digest=None,
        )
        self.sqlite.add_formalization_result(
            result_id="result-1",
            wiki_domain_id=DOMAIN,
            formal_wiki_revision_id=REVISION,
            terminus_store_id=STORE,
            formal_commit_hash=COMMIT,
            result_status="succeeded",
        )
        self.sqlite.set_current_formal_revision(DOMAIN, REVISION)
        self.revision_doc = {
            "@id": "WikiRevision/revision-1",
            "@type": "WikiRevision",
            "wiki_revision_id": REVISION,
            "document_id": "document-1",
            "title": "An approved page",
            "body_markdown": BODY,
        }
        self.reference = {
            "@id": "ResourceReference/ref-1",
            "@type": "ResourceReference",
            "reference_id": "ref-1",
            "source_revision_id": REVISION,
            "target_resource_version_id": "rv-exact-7",
            "reference_role": "evidence",
            "body_locator": "paragraph-2",
            "requested_scope": "reference",
        }
        self.snapshot = WikiSnapshotRead.confirmed(
            store_id=STORE, database=DATABASE, branch_id=BRANCH,
            commit_hash=COMMIT, documents=(self.revision_doc, self.reference),
            content_digest=sha256_json([self.revision_doc, self.reference]),
        )
        self.terminus = FakeTerminusStore(self.snapshot)
        self.reviews = FakeResourceReviewService()
        self.service = WikiFormalQueryService(
            sqlite_store=self.sqlite,
            terminus_store=self.terminus,
            terminus_database=DATABASE,
            resource_review_service=self.reviews,
        )

    def test_no_pointer_returns_no_revision_without_reading_store(self):
        self.sqlite.set_current_formal_revision("empty-domain", None)

        result = self.service.get_current("empty-domain")

        self.assertEqual(result.status, "no_formal_revision")
        self.assertEqual(result.reason_code, "no_current_pointer")
        self.assertIsNone(result.body_markdown)
        self.assertEqual(self.terminus.calls, [])

    def test_current_query_returns_exact_formal_body_and_qualified_reference(self):
        approved = WikiReferenceQualification(
            "rv-exact-7", "approved", "decision_recorded",
            review_id="review-1", use_scope=("reference",),
            limitations=("license_unknown",), unknown_facts=("license",),
        )
        self.reviews.qualifications[("rv-exact-7", "reference")] = approved

        result = self.service.get_current(DOMAIN)

        self.assertEqual(result.status, "available")
        self.assertEqual(result.body_markdown, BODY)
        self.assertEqual(result.references[0].target_resource_version_id, "rv-exact-7")
        self.assertEqual(result.references[0].qualification.status, "approved")
        self.assertEqual(result.references[0].qualification.limitations, ("license_unknown",))
        self.assertEqual(self.terminus.calls, [(STORE, DATABASE, BRANCH, COMMIT)])
        self.assertEqual(self.reviews.calls, [("rv-exact-7", "reference")])

    def test_unknown_qualification_is_pending_and_keeps_exact_target(self):
        result = self.service.get_current(DOMAIN)

        reference = result.references[0]
        self.assertEqual(reference.target_resource_version_id, "rv-exact-7")
        self.assertEqual(reference.qualification.status, "pending")
        self.assertNotEqual(reference.qualification.status, "approved")

    def test_unqualified_formalization_state_is_inconsistent_without_body(self):
        self.sqlite.set_formalization_status("result-1", "reconciliation_required")

        result = self.service.get_current(DOMAIN)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, "succeeded_result_missing")
        self.assertIsNone(result.body_markdown)

    def test_commit_identity_mismatch_fails_closed(self):
        self.terminus.outcome = WikiSnapshotRead(
            status="confirmed", store_id=STORE, database=DATABASE,
            branch_id=BRANCH, commit_hash="b" * 40,
            documents=self.snapshot.documents, content_digest=self.snapshot.content_digest,
        )

        result = self.service.get_current(DOMAIN)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, "snapshot_identity_mismatch")
        self.assertIsNone(result.body_markdown)

    def test_store_failure_does_not_expose_body(self):
        self.terminus.outcome = OSError("offline")

        result = self.service.get_current(DOMAIN)

        self.assertEqual(result.status, "unavailable")
        self.assertIsNone(result.body_markdown)

    def test_formal_revision_from_another_domain_is_inconsistent(self):
        self.sqlite.set_current_formal_revision("other-domain", REVISION)

        result = self.service.get_current("other-domain")

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, "pointer_domain_mismatch")
        self.assertIsNone(result.body_markdown)

    def test_snapshot_digest_mismatch_fails_closed(self):
        self.terminus.outcome = WikiSnapshotRead(
            status="confirmed", store_id=STORE, database=DATABASE,
            branch_id=BRANCH, commit_hash=COMMIT,
            documents=self.snapshot.documents, content_digest="wrong-digest",
        )

        result = self.service.get_current(DOMAIN)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, "snapshot_digest_mismatch")
        self.assertIsNone(result.body_markdown)

    def test_revoked_resource_keeps_reference_id_and_current_status(self):
        revoked = WikiReferenceQualification(
            "rv-exact-7", "revoked", "decision_recorded", review_id="revoke-2",
            limitations=("source_withdrawn",),
        )
        self.reviews.qualifications[("rv-exact-7", "reference")] = revoked

        result = self.service.get_current(DOMAIN)

        self.assertEqual(result.references[0].target_resource_version_id, "rv-exact-7")
        self.assertEqual(result.references[0].qualification.status, "revoked")
        self.assertEqual(result.references[0].qualification.limitations, ("source_withdrawn",))

    def test_wiki_revision_reference_keeps_exact_target_without_resource_review(self):
        wiki_reference = {
            "@id": "ResourceReference/ref-wiki", "@type": "ResourceReference",
            "reference_id": "ref-wiki", "source_revision_id": REVISION,
            "target_wiki_revision_id": "old-formal-revision", "reference_role": "related",
        }
        documents = (self.revision_doc, wiki_reference)
        self.terminus.outcome = WikiSnapshotRead.confirmed(
            store_id=STORE, database=DATABASE, branch_id=BRANCH, commit_hash=COMMIT,
            documents=documents, content_digest=sha256_json(list(documents)),
        )

        result = self.service.get_current(DOMAIN)

        self.assertEqual(result.references[0].target_wiki_revision_id, "old-formal-revision")
        self.assertIsNone(result.references[0].target_resource_version_id)
        self.assertEqual(self.reviews.calls, [])

    def test_candidate_only_documents_are_not_returned_as_formal_content(self):
        self.terminus.outcome = WikiSnapshotRead.confirmed(
            store_id=STORE, database=DATABASE, branch_id=BRANCH,
            commit_hash=COMMIT,
            documents=({"@type": "WikiRevision", "body_markdown": "candidate"},),
            content_digest=sha256_json([{"@type": "WikiRevision", "body_markdown": "candidate"}]),
        )

        result = self.service.get_current(DOMAIN)

        self.assertNotEqual(result.status, "available")
        self.assertIsNone(result.body_markdown)


if __name__ == "__main__":
    unittest.main()
