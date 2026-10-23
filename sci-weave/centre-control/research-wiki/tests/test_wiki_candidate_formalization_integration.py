from __future__ import annotations

import json
import os
import unittest
import uuid

from llm_wiki.canonical import sha256_json
from llm_wiki.terminus_store import TerminusDBWikiCandidateStore

from test_terminus_integration import (
    _authorization_from_environment,
    _temporary_database_name,
)


class WikiCandidateFormalizationTerminusIntegrationTestCase(unittest.TestCase):
    """Exercise Wiki candidate write/readback and formal exact-Commit writes."""

    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("SCIWEAVE_RUN_TERMINUSDB_INTEGRATION") != "1":
            raise unittest.SkipTest(
                "integration disabled; set SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1"
            )
        missing = [name for name in (
            "SCIWEAVE_WIKI_TERMINUSDB_URL",
            "SCIWEAVE_WIKI_TERMINUSDB_DATABASE",
            "SCIWEAVE_WIKI_TERMINUSDB_STORE",
        ) if not os.environ.get(name)]
        if missing:
            raise AssertionError("integration configuration missing: " + ", ".join(missing))

        cls.base_url = os.environ["SCIWEAVE_WIKI_TERMINUSDB_URL"].rstrip("/")
        cls.store_id = os.environ["SCIWEAVE_WIKI_TERMINUSDB_STORE"]
        cls.database = _temporary_database_name(os.environ["SCIWEAVE_WIKI_TERMINUSDB_DATABASE"])
        cls.remote = os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_REMOTE", "local")
        cls.authorization = _authorization_from_environment()
        cls.adapter = TerminusDBWikiCandidateStore(
            base_url=cls.base_url,
            store_id=cls.store_id,
            database=cls.database,
            remote=cls.remote,
            token=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_TOKEN"),
            username=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_USERNAME"),
            password=os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_PASSWORD"),
        )
        status, _, body = cls._request(
            "POST", f"/api/db/{cls.store_id}/{cls.database}",
            {"label": "SciWeave Wiki Candidate Integration", "comment": "candidate and formal exact commit"},
        )
        if status != 200:
            raise AssertionError(f"database creation failed: {status} {body[:400]}")
        cls.addClassCleanup(cls._delete_database)
        status, _, body = cls._request(
            "POST", f"/api/document/{cls.store_id}/{cls.database}?graph_type=schema&author=it&message=define-wiki-schema",
            _wiki_schema(),
        )
        if status != 200:
            raise AssertionError(f"schema definition failed: {status} {body[:400]}")
        status, _, body = cls._request(
            "POST", f"/api/document/{cls.store_id}/{cls.database}?author=it&message=seed-formal-base",
            [{"@type": "WikiRevision", "@id": "WikiRevision/base", "wiki_revision_id": "base", "title": "Base", "body_markdown": "base", "lifecycle_state": "formal"}],
        )
        if status != 200:
            raise AssertionError(f"base seed failed: {status} {body[:400]}")
        cls.base_commit = cls._head("main")

    @classmethod
    def _request(cls, method, path, payload=None):
        import urllib.error
        import urllib.request
        headers = {"Accept": "application/json"}
        if cls.authorization:
            headers["Authorization"] = cls.authorization
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(cls.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers or {}), error.read()

    @classmethod
    def _head(cls, branch):
        status, _, body = cls._request(
            "GET", f"/api/log/{cls.store_id}/{cls.database}/{cls.remote}/branch/{branch}?count=1"
        )
        if status != 200:
            raise AssertionError(f"log read failed: {status} {body[:400]}")
        return str(json.loads(body.decode())[0]["identifier"])

    @classmethod
    def _delete_database(cls):
        cls._request("DELETE", f"/api/db/{cls.store_id}/{cls.database}")

    def test_candidate_is_written_to_isolated_branch_and_exact_commit_reads_back(self):
        from llm_wiki.canonical import canonical_json
        documents = [
            {"@type": "WikiRevision", "@id": "WikiRevision/candidate", "wiki_revision_id": "candidate", "title": "Candidate", "body_markdown": "candidate body", "lifecycle_state": "candidate"},
            {"@type": "ResourceReference", "@id": "ResourceReference/candidate-ref", "reference_id": "candidate-ref", "source_revision_id": "candidate", "target_resource_version_id": "resource-v1", "reference_role": "evidence"},
        ]
        outcome = self.adapter.create_candidate_snapshot(
            "domain-integration", self.base_commit, canonical_json(documents),
            "candidate-op-integration",
        )

        self.assertEqual(outcome.status, "confirmed", outcome.reason_code)
        snapshot = self.adapter.read_exact_snapshot(
            outcome.store_id, self.database, outcome.branch_id, outcome.commit_hash
        )
        self.assertEqual(snapshot.status, "confirmed", snapshot.reason_code)
        self.assertEqual(snapshot.commit_hash, outcome.commit_hash)
        self.assertEqual(snapshot.content_digest, sha256_json(list(snapshot.documents)))
        for expected in documents:
            self.assertIn(expected, snapshot.documents)
        self.assertEqual(self._head("main"), self.base_commit)
        retry = self.adapter.create_candidate_snapshot(
            "domain-integration", self.base_commit, canonical_json(documents),
            "candidate-op-integration",
        )
        self.assertEqual(retry.status, "confirmed", retry.reason_code)
        self.assertEqual(retry.commit_hash, outcome.commit_hash)

    def test_formal_snapshot_returns_precisely_verifiable_formal_commit(self):
        from llm_wiki.canonical import canonical_json
        source_docs = [
            {"@type": "WikiRevision", "@id": "WikiRevision/formal-source", "wiki_revision_id": "formal-source", "title": "Formal source", "body_markdown": "approved body", "lifecycle_state": "candidate"},
            {"@type": "ResourceReference", "@id": "ResourceReference/formal-ref", "reference_id": "formal-ref", "source_revision_id": "formal-source", "target_resource_version_id": "resource-v2", "reference_role": "evidence"},
        ]
        candidate = self.adapter.create_candidate_snapshot(
            "domain-integration", self.base_commit, canonical_json(source_docs), "formal-source-" + uuid.uuid4().hex
        )
        candidate_snapshot = self.adapter.read_exact_snapshot(
            candidate.store_id, self.database, candidate.branch_id, candidate.commit_hash
        )
        self.assertEqual(candidate_snapshot.status, "confirmed", candidate_snapshot.reason_code)

        formal_operation_id = "formal-op-" + uuid.uuid4().hex
        outcome = self.adapter.create_formal_snapshot(
            {"store_id": candidate.store_id, "database": self.database,
             "branch_id": candidate.branch_id, "commit_hash": candidate.commit_hash},
            formal_operation_id,
        )

        self.assertEqual(outcome["status"], "confirmed", outcome.get("reason_code"))
        formal = self.adapter.read_exact_snapshot(
            outcome["store_id"], self.database, outcome["branch_id"], outcome["commit_hash"]
        )
        expected = [dict(doc, lifecycle_state="formal") if doc.get("@type") == "WikiRevision" else doc for doc in candidate_snapshot.documents]
        self.assertEqual(formal.status, "confirmed", formal.reason_code)
        self.assertEqual(formal.commit_hash, outcome["commit_hash"])
        self.assertEqual(list(formal.documents), expected)
        self.assertEqual(formal.content_digest, sha256_json(expected))
        self.assertNotEqual(outcome["commit_hash"], candidate.commit_hash)
        self.assertTrue(self.adapter.verify_formalization_commit(
            outcome["store_id"], self.database, outcome["branch_id"],
            outcome["commit_hash"], formal_operation_id,
        ))
        self.assertFalse(self.adapter.verify_formalization_commit(
            outcome["store_id"], self.database, outcome["branch_id"],
            outcome["commit_hash"], "different-operation",
        ))


def _wiki_schema():
    return [
        {"@type": "Class", "@id": "WikiRevision", "@key": {"@type": "Lexical", "@fields": ["wiki_revision_id"]}, "wiki_revision_id": "xsd:string", "title": "xsd:string", "body_markdown": "xsd:string", "lifecycle_state": "xsd:string"},
        {"@type": "Class", "@id": "ResourceReference", "@key": {"@type": "Lexical", "@fields": ["reference_id"]}, "reference_id": "xsd:string", "source_revision_id": "xsd:string", "target_resource_version_id": "xsd:string", "reference_role": "xsd:string"},
    ]
