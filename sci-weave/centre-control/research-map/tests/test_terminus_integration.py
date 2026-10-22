from __future__ import annotations

import base64
import json
import os
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from research_mapping.canonical import canonical_json
from research_mapping.terminus_store import TerminusDBStore

REQUIRED_VARIABLES = (
    "SCIWEAVE_MAPPING_TERMINUSDB_URL",
    "SCIWEAVE_MAPPING_TERMINUSDB_DATABASE",
    "SCIWEAVE_MAPPING_TERMINUSDB_STORE",
)


class TerminusDBExactCommitIntegrationTestCase(unittest.TestCase):
    """Opt-in checks against the pinned TerminusDB service."""

    def setUp(self) -> None:
        if os.environ.get("SCIWEAVE_RUN_TERMINUSDB_INTEGRATION") != "1":
            raise unittest.SkipTest("integration disabled; set SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1")
        missing = [name for name in REQUIRED_VARIABLES if not os.environ.get(name)]
        if missing:
            self.fail("integration configuration missing: " + ", ".join(missing))
        self.base_url = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_URL"]
        self.database = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_DATABASE"]
        self.store = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_STORE"]
        self.branch = os.environ.get("SCIWEAVE_MAPPING_INTEGRATION_BRANCH", "main")
        self.commit = os.environ.get("SCIWEAVE_MAPPING_INTEGRATION_COMMIT")
        self.head_commit = os.environ.get("SCIWEAVE_MAPPING_INTEGRATION_HEAD_COMMIT")
        self.adapter = TerminusDBStore(
            base_url=self.base_url,
            token=os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_TOKEN"),
            username=os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_USERNAME"),
            password=os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD"),
            remote=os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_REMOTE", "local"),
        )

    def test_reads_the_exact_commit_instead_of_the_branch_head(self) -> None:
        if not self.commit:
            self.skipTest("set SCIWEAVE_MAPPING_INTEGRATION_COMMIT to name an existing commit")
        outcome = self.adapter.read_exact_snapshot(self.store, self.database, self.branch, self.commit)
        self.assertEqual(outcome.status, "confirmed", outcome.reason_code)
        self.assertEqual((outcome.store_id, outcome.database, outcome.branch_id, outcome.commit_hash),
                         (self.store, self.database, self.branch, self.commit))
        self.assertTrue(outcome.content_digest)

    def test_historical_commit_differs_from_the_branch_head(self) -> None:
        if not self.commit or not self.head_commit:
            self.skipTest("set SCIWEAVE_MAPPING_INTEGRATION_COMMIT and SCIWEAVE_MAPPING_INTEGRATION_HEAD_COMMIT")
        if self.commit == self.head_commit:
            self.fail("historical commit must differ from the branch head commit")
        historical = self.adapter.read_exact_snapshot(self.store, self.database, self.branch, self.commit)
        head = self.adapter.read_exact_snapshot(self.store, self.database, self.branch, self.head_commit)
        self.assertEqual(historical.status, "confirmed", historical.reason_code)
        self.assertEqual(head.status, "confirmed", head.reason_code)
        self.assertNotEqual(tuple(d.get("@id") for d in historical.documents),
                            tuple(d.get("@id") for d in head.documents))

    def test_unknown_commit_is_never_confirmed(self) -> None:
        outcome = self.adapter.read_exact_snapshot(
            self.store, self.database, self.branch, "0000000000000000000000000000000000000000")
        self.assertIn(outcome.status, {"missing", "unavailable"}, outcome.reason_code)
        self.assertEqual(outcome.documents, ())

    def test_candidate_branch_creation_replay_and_cleanup(self) -> None:
        database = self.database + "_candidate_it_" + uuid.uuid4().hex[:10]
        headers = {"Accept": "application/json"}
        token = os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_TOKEN")
        username = os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_USERNAME")
        password = os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif username and password:
            headers["Authorization"] = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        elif username or password:
            self.fail("integration credentials need both username and password")

        def request(method, path, payload=None):
            request_headers = dict(headers)
            data = None
            if payload is not None:
                request_headers["Content-Type"] = "application/json"
                data = json.dumps(payload).encode()
            req = Request(self.base_url + path, data=data, headers=request_headers, method=method)
            try:
                with urlopen(req, timeout=10) as response:
                    return response.status, dict(response.headers), response.read()
            except HTTPError as error:
                return error.code, dict(error.headers or {}), error.read()

        created = False
        try:
            status, _, body = request("POST", f"/api/db/{self.store}/{database}",
                                      {"label": "Mapping candidate integration", "comment": "candidate branch"})
            if status != 200:
                self.fail(f"temporary database creation failed ({status}): {body[:300]!r}")
            created = True
            schema = [{"@type": "Class", "@id": "IntegrationCandidate",
                       "@key": {"@type": "Lexical", "@fields": ["candidate_id"]},
                       "candidate_id": "xsd:string", "value": "xsd:string"}]
            status, _, body = request("POST", f"/api/document/{self.store}/{database}?graph_type=schema&author=it&message=schema", schema)
            if status != 200:
                self.fail(f"temporary schema setup failed ({status}): {body[:300]!r}")
            seed = [{"@type": "IntegrationCandidate", "@id": "IntegrationCandidate/base", "candidate_id": "base", "value": "base"}]
            status, _, body = request("POST", f"/api/document/{self.store}/{database}?author=it&message=seed", seed)
            if status != 200:
                self.fail(f"base snapshot setup failed ({status}): {body[:300]!r}")
            status, _, body = request("GET", f"/api/log/{self.store}/{database}/local/branch/main?count=1")
            if status != 200:
                self.fail(f"base commit lookup failed ({status}): {body[:300]!r}")
            base_commit = json.loads(body.decode())[0]["identifier"]
            adapter = TerminusDBStore(
                base_url=self.base_url, token=token, username=username, password=password,
                remote=os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_REMOTE", "local"),
                store_id=self.store, database=database,
            )
            self.assertEqual(adapter.current_branch_head(self.store, database, "main"), base_commit)
            exact_base = adapter.read_exact_snapshot(self.store, database, "main", base_commit)
            self.assertEqual(exact_base.status, "confirmed", exact_base.reason_code)
            self.assertIn(seed[0], exact_base.documents)
            candidate_docs = [{"@type": "IntegrationCandidate", "@id": "IntegrationCandidate/candidate",
                               "candidate_id": "candidate", "value": "candidate"}]
            canonical = canonical_json(candidate_docs)
            identity = "candidate-integration-" + uuid.uuid4().hex
            first = adapter.create_candidate_snapshot("integration-domain", base_commit, canonical, identity)
            self.assertEqual(first.status, "confirmed", first.reason_code)
            exact = adapter.read_exact_snapshot(self.store, database, first.branch_id, first.commit_hash)
            self.assertEqual(exact.status, "confirmed", exact.reason_code)
            formal = adapter.create_formal_snapshot(
                self.store, database, first.branch_id, first.commit_hash, identity
            )
            self.assertEqual(formal.status, "confirmed", formal.reason_code)
            self.assertEqual(formal.commit_hash, first.commit_hash)
            self.assertEqual(formal.content_digest, exact.content_digest)
            self.assertIn(candidate_docs[0], exact.documents)
            self.assertIn(seed[0], exact.documents)
            self.assertEqual(adapter.create_candidate_snapshot("integration-domain", base_commit, canonical, identity), first)
        finally:
            if created:
                status, _, body = request("DELETE", f"/api/db/{self.store}/{database}")
                if status not in (200, 204):
                    self.fail(f"temporary database cleanup failed ({status}): {body[:300]!r}")


if __name__ == "__main__":
    unittest.main()
