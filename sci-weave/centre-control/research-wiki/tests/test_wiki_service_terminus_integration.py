from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from llm_wiki.candidate_submission import WikiCandidateService
from llm_wiki.domain import ResourceVersionLocation
from llm_wiki.formal_query import WikiFormalQueryService
from llm_wiki.formalization import WikiFormalizationService
from llm_wiki.resource_review import ResourceReviewService
from llm_wiki.review import WikiReviewService
from llm_wiki.sqlite_store import SqliteStore
from llm_wiki.terminus_store import TerminusDBResourceStore, TerminusDBWikiCandidateStore

from test_formal_query_integration import (
    _documents,
    _request,
    _schema,
    _temporary_database_name,
    REVISION as SEEDED_FORMAL_REVISION_ID,
)


class WikiServiceTerminusIntegrationTestCase(unittest.TestCase):
    """Exercise candidate governance, activation, and exact formal query with real TerminusDB."""

    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("SCIWEAVE_RUN_TERMINUSDB_INTEGRATION") != "1":
            raise unittest.SkipTest(
                "integration disabled; set SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1"
            )
        required = (
            "SCIWEAVE_WIKI_TERMINUSDB_URL",
            "SCIWEAVE_WIKI_TERMINUSDB_DATABASE",
            "SCIWEAVE_WIKI_TERMINUSDB_STORE",
        )
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise AssertionError("integration configuration missing: " + ", ".join(missing))

        cls.base_url = os.environ["SCIWEAVE_WIKI_TERMINUSDB_URL"].rstrip("/")
        cls.store_id = os.environ["SCIWEAVE_WIKI_TERMINUSDB_STORE"]
        cls.database = _temporary_database_name(os.environ["SCIWEAVE_WIKI_TERMINUSDB_DATABASE"])
        cls.remote = os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_REMOTE", "local")
        cls.store = TerminusDBWikiCandidateStore(
            base_url=cls.base_url,
            store_id=cls.store_id,
            database=cls.database,
            remote=cls.remote,
            token=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_TOKEN"),
            username=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_USERNAME"),
            password=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_PASSWORD"),
        )
        status, _, body = _request(
            cls, "POST", f"/api/db/{cls.store_id}/{cls.database}",
            {"label": "SciWeave Wiki Service Integration", "comment": "governed candidate flow"},
        )
        if status != 200:
            raise AssertionError(f"database creation failed: {status} {body[:400]}")
        cls.addClassCleanup(cls._delete_database)
        schema = _schema()
        for definition in schema:
            if definition.get("@id") == "WikiRevision":
                definition.update({
                    "category": "xsd:string", "created_by": "xsd:string", "created_at": "xsd:string",
                    "wiki_domain_id": "xsd:string", "proposal_id": "xsd:string",
                    "base_formal_revision_id": "xsd:string", "lifecycle_state": "xsd:string",
                })
            elif definition.get("@id") == "ResourceReference":
                definition.update({"requested_scope": "xsd:string", "wiki_domain_id": "xsd:string"})
        status, _, body = _request(
            cls, "POST", f"/api/document/{cls.store_id}/{cls.database}?graph_type=schema&author=it&message=define-wiki-schema",
            schema,
        )
        if status != 200:
            raise AssertionError(f"schema definition failed: {status} {body[:400]}")
        seeded_documents = [document for document in _documents() if document.get("@type") != "ResourceReference"]
        for document in seeded_documents:
            if document.get("@type") == "WikiRevision":
                document.update({
                    "category": "source", "created_by": "integration", "created_at": "2026-10-22T00:00:00Z",
                    "wiki_domain_id": "seed-domain", "proposal_id": "seed-proposal",
                    "base_formal_revision_id": "seed-base", "lifecycle_state": "formal",
                })
            elif document.get("@type") == "ResourceReference":
                document.update({"requested_scope": "", "wiki_domain_id": "seed-domain"})
        status, _, body = _request(
            cls, "POST", f"/api/document/{cls.store_id}/{cls.database}?author=it&message=seed-formal-wiki",
            seeded_documents,
        )
        if status != 200:
            raise AssertionError(f"formal wiki seed failed: {status} {body[:400]}")
        cls.base_commit = cls._head_commit()

    @classmethod
    def _head_commit(cls) -> str:
        status, _, body = _request(
            cls, "GET", f"/api/log/{cls.store_id}/{cls.database}/{cls.remote}/branch/main?count=1",
        )
        if status != 200:
            raise AssertionError(f"log read failed: {status} {body[:400]}")
        import json
        return str(json.loads(body.decode("utf-8"))[0]["identifier"])

    @classmethod
    def _delete_database(cls) -> None:
        _request(cls, "DELETE", f"/api/db/{cls.store_id}/{cls.database}")

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sqlite = SqliteStore(str(Path(self.temp.name) / "wiki-service-integration.sqlite"))
        self.sqlite.initialize()
        self.sqlite.add_formal_revision(
            formal_revision_id=SEEDED_FORMAL_REVISION_ID, wiki_domain_id="wiki-domain",
            terminus_store_id=self.store_id, formal_branch_id="main",
            formal_commit_hash=self.base_commit,
        )
        self.sqlite.set_current_formal_revision("wiki-domain", SEEDED_FORMAL_REVISION_ID)
        seeded = self.store.read_exact_snapshot(
            self.store_id, self.database, "main", self.base_commit,
        )
        if seeded.status != "confirmed":
            raise AssertionError(f"seeded formal snapshot unavailable: {seeded.reason_code}")
        self.sqlite.add_formalization_result(
            result_id="seed-formalization-result", wiki_domain_id="wiki-domain",
            formal_wiki_revision_id=SEEDED_FORMAL_REVISION_ID, terminus_store_id=self.store_id,
            formal_commit_hash=self.base_commit, result_status="succeeded",
        )
        self.resource_reviews = ResourceReviewService(
            sqlite_store=self.sqlite,
            terminus_store=TerminusDBResourceStore(
                base_url=self.base_url,
                token=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_TOKEN"),
                username=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_USERNAME"),
                password=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_PASSWORD"),
                remote=self.remote,
            ),
            location_source=_ExactLocation(self.store_id, self.database, "main", self.base_commit),
            clock=lambda: "2026-10-22T00:00:00Z",
        )
        self.owner_verifier = _OwnerVerifier()
        self.candidate_service = WikiCandidateService(
            sqlite_store=self.sqlite, terminus_store=self.store,
            resource_review_service=self.resource_reviews, terminus_database=self.database,
        )

    def test_candidate_review_owner_formalization_and_current_query_use_real_services(self):
        self._approve_resource()
        candidate = self.candidate_service.submit(_submission("candidate-success"), "key-success")
        self.assertEqual(candidate.status, "confirmed", candidate.reason_code)
        self.assertEqual(candidate.references[0].qualification.status, "approved")

        review = WikiReviewService(
            sqlite_store=self.sqlite, terminus_store=self.store, terminus_database=self.database,
            resource_review_service=self.resource_reviews, owner_authorization_verifier=self.owner_verifier,
        )
        merge_request = review.create_merge_request(candidate.proposal_id, "mr-success", "curator")
        self.assertEqual(merge_request.status, "ready_for_owner", merge_request.reason_code)
        decision = review.decide(
            "mr-success", actor_id="wiki-owner", decision="approved", reason="verified candidate",
            selected_solution_id=candidate.candidate_commit_id,
        )
        self.assertEqual(decision.status, "approved", decision.reason_code)

        formalizer = WikiFormalizationService(
            sqlite_store=self.sqlite, terminus_store=self.store, terminus_database=self.database,
            resource_review_service=self.resource_reviews, owner_authorization_verifier=self.owner_verifier,
        )
        result = formalizer.formalize("mr-success", "formal-op-success")
        self.assertEqual(result.status, "succeeded", result.reason_code)

        query = WikiFormalQueryService(
            sqlite_store=self.sqlite, terminus_store=self.store, terminus_database=self.database,
            resource_review_service=self.resource_reviews,
        )
        current = query.get_current("wiki-domain")
        self.assertEqual(current.status, "available", current.reason_code)
        self.assertEqual(current.formal_wiki_revision_id, result.formal_wiki_revision_id)
        self.assertEqual(current.body_markdown, "A newly governed candidate page.")
        reference = next(item for item in current.references if item.reference_id == "candidate-resource-reference")
        self.assertEqual(reference.qualification.status, "approved")
        self.assertEqual(self.sqlite.get_current_formal_revision_id("wiki-domain"), result.formal_wiki_revision_id)

    def test_resource_revocation_after_owner_approval_blocks_activation(self):
        self._approve_resource()
        candidate = self.candidate_service.submit(_submission("candidate-revoked"), "key-revoked")
        self.assertEqual(candidate.status, "confirmed", candidate.reason_code)
        review = WikiReviewService(
            sqlite_store=self.sqlite, terminus_store=self.store, terminus_database=self.database,
            resource_review_service=self.resource_reviews, owner_authorization_verifier=self.owner_verifier,
        )
        self.assertEqual(review.create_merge_request(candidate.proposal_id, "mr-revoked", "curator").status, "ready_for_owner")
        decision = review.decide(
            "mr-revoked", actor_id="wiki-owner", decision="approved", reason="verified candidate",
            selected_solution_id=candidate.candidate_commit_id,
        )
        self.assertEqual(decision.status, "approved", decision.reason_code)
        revoked = self.resource_reviews.record_decision(
            "resource-approved", "resource-owner", "revoked", reason="approval withdrawn",
        )
        self.assertTrue(revoked.recorded, revoked.reason_code)

        formalizer = WikiFormalizationService(
            sqlite_store=self.sqlite, terminus_store=self.store, terminus_database=self.database,
            resource_review_service=self.resource_reviews, owner_authorization_verifier=self.owner_verifier,
        )
        result = formalizer.formalize("mr-revoked", "formal-op-revoked")

        self.assertEqual((result.status, result.reason_code), ("failed", "resource_qualification_required"))
        self.assertEqual(self.sqlite.get_current_formal_revision_id("wiki-domain"), SEEDED_FORMAL_REVISION_ID)
        query = WikiFormalQueryService(
            sqlite_store=self.sqlite, terminus_store=self.store, terminus_database=self.database,
            resource_review_service=self.resource_reviews,
        )
        current = query.get_current("wiki-domain")
        self.assertEqual(current.status, "available", current.reason_code)
        self.assertEqual(current.formal_wiki_revision_id, SEEDED_FORMAL_REVISION_ID)
        self.assertNotEqual(current.body_markdown, "A newly governed candidate page.")

    def _approve_resource(self) -> None:
        result = self.resource_reviews.record_decision(
            "resource-approved", "resource-owner", "approved", reason="citation verified",
            scope=("evidence",),
        )
        self.assertTrue(result.recorded, result.reason_code)


class _ExactLocation:
    def __init__(self, store_id: str, database: str, branch: str, commit: str):
        self.location = ResourceVersionLocation(store_id, database, branch, commit)

    def locate(self, resource_version_id: str) -> ResourceVersionLocation:
        return self.location


class _OwnerVerifier:
    def verify_owner(self, actor_id: str, wiki_domain_id: str) -> bool:
        return actor_id == "wiki-owner" and wiki_domain_id == "wiki-domain"


def _submission(suffix: str) -> dict:
    revision = f"wiki-{suffix}"
    return {
        "submission_id": f"submission-{suffix}", "proposal_id": f"proposal-{suffix}",
        "wiki_domain_id": "wiki-domain", "submitter_id": "researcher",
        "base_formal_revision_id": SEEDED_FORMAL_REVISION_ID,
        "document": {
            "@type": "WikiRevision", "@id": f"WikiRevision/{revision}", "wiki_revision_id": revision,
            "document_id": "integration-candidate-document", "category": "concept",
            "title": "Governed candidate", "description": "Integration test candidate",
            "body_markdown": "A newly governed candidate page.",
            "created_by": "researcher", "created_at": "2026-10-22T00:00:00Z",
            "lifecycle_state": "candidate", "wiki_domain_id": "wiki-domain",
            "proposal_id": f"proposal-{suffix}", "base_formal_revision_id": SEEDED_FORMAL_REVISION_ID,
        },
        "references": [{
            "@type": "ResourceReference", "@id": "ResourceReference/candidate-resource-reference",
            "reference_id": "candidate-resource-reference",
            "source_revision_id": revision, "target_resource_version_id": "resource-approved",
            "target_wiki_revision_id": "", "requested_scope": "evidence", "reference_role": "evidence",
            "body_locator": "paragraph-1", "wiki_domain_id": "wiki-domain",
        }],
    }


if __name__ == "__main__":
    unittest.main()
