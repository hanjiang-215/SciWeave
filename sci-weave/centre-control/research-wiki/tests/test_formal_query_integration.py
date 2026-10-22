from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from typing import Any

from llm_wiki.canonical import sha256_json
from llm_wiki.domain import ResourceVersionLocation
from llm_wiki.formal_query import WikiFormalQueryService
from llm_wiki.resource_review import ResourceReviewService
from llm_wiki.sqlite_store import SqliteStore
from llm_wiki.terminus_store import TerminusDBResourceStore

REQUIRED_VARIABLES = (
    "SCIWEAVE_WIKI_TERMINUSDB_URL",
    "SCIWEAVE_WIKI_TERMINUSDB_DATABASE",
    "SCIWEAVE_WIKI_TERMINUSDB_STORE",
)
DOMAIN = "wiki-query-integration-domain"
REVISION = "wiki-query-integration-revision"
BODY = "# Exact formal wiki page\n\nThis body is pinned to the captured commit."


class WikiFormalQueryIntegrationTestCase(unittest.TestCase):
    """Exercise the SQLite activation to exact TerminusDB commit query path."""

    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("SCIWEAVE_RUN_TERMINUSDB_INTEGRATION") != "1":
            raise unittest.SkipTest(
                "integration disabled; set SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1 "
                "and start the pinned TerminusDB service"
            )
        missing = [name for name in REQUIRED_VARIABLES if not os.environ.get(name)]
        if missing:
            raise AssertionError("integration configuration missing: " + ", ".join(missing))

        cls.base_url = os.environ["SCIWEAVE_WIKI_TERMINUSDB_URL"].rstrip("/")
        cls.store_id = os.environ["SCIWEAVE_WIKI_TERMINUSDB_STORE"]
        cls.database = _temporary_database_name(os.environ["SCIWEAVE_WIKI_TERMINUSDB_DATABASE"])
        cls.remote = os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_REMOTE", "local")
        cls.branch = os.environ.get("SCIWEAVE_WIKI_INTEGRATION_BRANCH", "main")
        cls.adapter = TerminusDBResourceStore(
            base_url=cls.base_url,
            token=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_TOKEN"),
            username=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_USERNAME"),
            password=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_PASSWORD"),
            remote=cls.remote,
        )

        status, _, body = _request(
            cls, "POST", f"/api/db/{cls.store_id}/{cls.database}",
            {"label": "SciWeave Wiki Formal Query Integration", "comment": "formal query"},
        )
        if status != 200:
            raise AssertionError(f"database creation failed: {status} {body[:400]}")
        cls.addClassCleanup(cls._delete_database)

        status, _, body = _request(
            cls, "POST", f"/api/document/{cls.store_id}/{cls.database}?graph_type=schema&author=it&message=define-wiki-schema",
            _schema(),
        )
        if status != 200:
            raise AssertionError(f"schema definition failed: {status} {body[:400]}")
        status, _, body = _request(
            cls, "POST", f"/api/document/{cls.store_id}/{cls.database}?author=it&message=seed-formal-wiki",
            _documents(),
        )
        if status != 200:
            raise AssertionError(f"formal wiki seed failed: {status} {body[:400]}")
        cls.commit_hash = cls._head_commit()

        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.sqlite = SqliteStore(os.path.join(cls.tmp.name, "formal-query.db"))
        cls.sqlite.initialize()
        cls.sqlite.add_formal_revision(
            formal_revision_id=REVISION, wiki_domain_id=DOMAIN,
            terminus_store_id=cls.store_id, formal_branch_id=cls.branch,
            formal_commit_hash=cls.commit_hash,
        )
        cls.sqlite.add_formalization_result(
            result_id="wiki-query-integration-result", wiki_domain_id=DOMAIN,
            formal_wiki_revision_id=REVISION, terminus_store_id=cls.store_id,
            formal_commit_hash=cls.commit_hash, result_status="succeeded",
        )
        cls.sqlite.set_current_formal_revision(DOMAIN, REVISION)

    @classmethod
    def _head_commit(cls) -> str:
        status, _, body = _request(
            cls, "GET", f"/api/log/{cls.store_id}/{cls.database}/{cls.remote}/branch/{cls.branch}?count=1",
        )
        if status != 200:
            raise AssertionError(f"log read failed: {status} {body[:400]}")
        entries = json.loads(body.decode("utf-8"))
        return str(entries[0]["identifier"])

    @classmethod
    def _delete_database(cls) -> None:
        _request(cls, "DELETE", f"/api/db/{cls.store_id}/{cls.database}")

    def test_current_query_reads_activated_exact_commit_body_and_reference(self) -> None:
        service = WikiFormalQueryService(
            sqlite_store=self.sqlite,
            terminus_store=self.adapter,
            terminus_database=self.database,
            resource_review_service=_NoResourceReviews(),
        )

        result = service.get_current(DOMAIN)

        self.assertEqual(result.status, "available", result.reason_code)
        self.assertEqual(result.formal_wiki_revision_id, REVISION)
        self.assertEqual(result.formal_commit_hash, self.commit_hash)
        self.assertEqual(result.body_markdown, BODY)
        self.assertEqual(len(result.references), 5)
        wiki_reference = next(
            reference for reference in result.references
            if reference.reference_id == "integration-reference"
        )
        self.assertEqual(wiki_reference.target_wiki_revision_id, "prior-formal-revision")

    def test_resource_references_use_real_review_service_and_keep_exact_targets(self) -> None:
        reviews = ResourceReviewService(
            sqlite_store=self.sqlite,
            terminus_store=self.adapter,
            location_source=_ExactVersionLocationSource(
                ResourceVersionLocation(
                    store_id=self.store_id,
                    database=self.database,
                    branch_id=self.branch,
                    commit_hash=self.commit_hash,
                )
            ),
            clock=lambda: "2026-10-22T00:00:00Z",
        )
        approved_decision = reviews.record_decision(
            "resource-approved", "resource-owner", "approved",
            reason="citation use verified", scope=("citation",),
        )
        self.assertTrue(approved_decision.recorded, approved_decision.reason_code)
        reviews.record_decision(
            "resource-revoked", "resource-owner", "approved",
            reason="initial approval", scope=("citation",),
        )
        reviews.record_decision(
            "resource-revoked", "resource-owner", "revoked",
            reason="source approval withdrawn",
        )
        service = WikiFormalQueryService(
            sqlite_store=self.sqlite,
            terminus_store=self.adapter,
            terminus_database=self.database,
            resource_review_service=reviews,
        )

        result = service.get_current(DOMAIN)

        self.assertEqual(result.status, "available", result.reason_code)
        self.assertEqual(
            [(reference.reference_id, reference.target_resource_version_id,
              reference.qualification.status if reference.qualification else None)
             for reference in result.references],
            [
                ("approved-citation", "resource-approved", "approved"),
                ("integration-reference", None, None),
                ("pending-citation", "resource-pending", "pending"),
                ("revoked-citation", "resource-revoked", "revoked"),
                ("scope-mismatch", "resource-approved", "pending"),
            ],
        )
        approved = result.references[0]
        self.assertEqual(approved.qualification.resource_version_id, "resource-approved")
        self.assertEqual(approved.qualification.use_scope, ("citation",))
        self.assertEqual(result.references[4].qualification.reason_code, "no_effective_decision")


class _ExactVersionLocationSource:
    def __init__(self, location: ResourceVersionLocation):
        self.location = location

    def locate(self, resource_version_id: str) -> ResourceVersionLocation:
        return self.location


class _NoResourceReviews:
    def get_current_qualification(self, resource_version_id: str, requested_scope: str | None = None):
        raise AssertionError("wiki revision references must not trigger resource review")


def _temporary_database_name(configured: str) -> str:
    prefix = "".join(c if c.isalnum() else "_" for c in configured.lower()).strip("_")
    return f"{prefix or 'sciweave_wiki'}_formal_it_{uuid.uuid4().hex[:8]}"


def _request(cls: type, method: str, path: str, payload: Any | None = None):
    import base64
    import urllib.error
    import urllib.request

    headers = {"Accept": "application/json"}
    token = os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_TOKEN")
    username = os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_USERNAME")
    password = os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_PASSWORD")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif username and password:
        credentials = f"{username}:{password}".encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(credentials).decode("ascii")
    elif username or password:
        raise AssertionError("integration credentials need both username and password")
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(cls.base_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), error.read()


def _schema() -> list[dict[str, Any]]:
    return [
        {"@type": "Class", "@id": "WikiRevision", "@key": {"@type": "Lexical", "@fields": ["wiki_revision_id"]},
         "wiki_revision_id": "xsd:string", "document_id": "xsd:string", "title": "xsd:string",
         "description": "xsd:string", "body_markdown": "xsd:string"},
        {"@type": "Class", "@id": "ResourceReference", "@key": {"@type": "Lexical", "@fields": ["reference_id"]},
         "reference_id": "xsd:string", "source_revision_id": "xsd:string",
         "target_wiki_revision_id": "xsd:string", "target_resource_version_id": "xsd:string",
         "requested_scope": "xsd:string", "reference_role": "xsd:string", "body_locator": "xsd:string"},
        {"@type": "Class", "@id": "Resource", "@key": {"@type": "Lexical", "@fields": ["name"]},
         "name": "xsd:string", "owner_id": "xsd:string"},
        {"@type": "Class", "@id": "ResourceVersion", "@key": {"@type": "Lexical", "@fields": ["resource_version_id"]},
         "resource_version_id": "xsd:string", "resource_id": "xsd:string",
         "content_checksum_algorithm": "xsd:string", "content_checksum_value": "xsd:string",
         "license": "xsd:string", "attribution": "xsd:string", "source_locator": "xsd:string",
         "external_version_id": "xsd:string", "current_access_locator": "xsd:string",
         "availability_status": "xsd:string", "availability_checked_at": "xsd:string",
         "generated_at": "xsd:string", "generated_by": "xsd:string",
         "generated_by_task_id": "xsd:string", "handling_mode": "xsd:string"},
    ]


def _documents() -> list[dict[str, Any]]:
    return [
        {"@type": "WikiRevision", "@id": f"WikiRevision/{REVISION}",
         "wiki_revision_id": REVISION, "document_id": "integration-document",
         "title": "Integration formal page", "description": "Exact commit query",
         "body_markdown": BODY},
        {"@type": "ResourceReference", "@id": "ResourceReference/integration-reference",
         "reference_id": "integration-reference", "source_revision_id": REVISION,
         "target_wiki_revision_id": "prior-formal-revision", "target_resource_version_id": "",
         "requested_scope": "", "reference_role": "related",
         "body_locator": "paragraph-1"},
        _resource_document("source-resource-approved"),
        _resource_document("source-resource-pending"),
        _resource_document("source-resource-revoked"),
        _resource_version_document("resource-approved"),
        _resource_version_document("resource-pending"),
        _resource_version_document("resource-revoked"),
        _resource_reference("approved-citation", "resource-approved", "citation"),
        _resource_reference("pending-citation", "resource-pending", "citation"),
        _resource_reference("revoked-citation", "resource-revoked", "citation"),
        _resource_reference("scope-mismatch", "resource-approved", "redistribution"),
    ]


def _resource_document(resource_name: str) -> dict[str, Any]:
    return {
        "@type": "Resource", "@id": f"Resource/{resource_name}",
        "name": resource_name, "owner_id": "resource-owner",
    }


def _resource_version_document(version_id: str) -> dict[str, Any]:
    resource_name = f"source-{version_id}"
    return {
        "@type": "ResourceVersion", "@id": f"ResourceVersion/{version_id}",
        "resource_version_id": version_id, "resource_id": f"Resource/{resource_name}",
        "content_checksum_algorithm": "sha256", "content_checksum_value": "a" * 64,
        "license": "CC-BY-4.0", "attribution": "Integration Lab",
        "source_locator": f"doi:10.0000/{version_id}", "external_version_id": "upstream-v1",
        "current_access_locator": "https://example.org/resource", "availability_status": "available",
        "availability_checked_at": "2026-10-22T00:00:00Z", "generated_at": "2026-10-21T00:00:00Z",
        "generated_by": "integration-agent", "generated_by_task_id": "integration-task",
        "handling_mode": "direct_query",
    }


def _resource_reference(reference_id: str, version_id: str, scope: str) -> dict[str, Any]:
    return {
        "@type": "ResourceReference", "@id": f"ResourceReference/{reference_id}",
        "reference_id": reference_id, "source_revision_id": REVISION,
        "target_resource_version_id": version_id, "target_wiki_revision_id": "",
        "requested_scope": scope,
        "reference_role": "evidence", "body_locator": "paragraph-2",
    }


if __name__ == "__main__":
    unittest.main()
