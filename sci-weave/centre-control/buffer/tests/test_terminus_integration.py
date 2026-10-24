from __future__ import annotations

import json
import os
import unittest
import urllib.error
import urllib.request
import uuid

from draft_buffer import BufferError
from draft_buffer.service import DraftBufferService
from draft_buffer.store import TerminusDBDraftStore


class BufferTerminusIntegrationTestCase(unittest.TestCase):
    """Exercise the real TerminusDB 12.0.8 adapter on a temporary database.

    Follows the repository's integration-test convention: skips unless
    SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1, builds a temporary database name,
    creates it, and deletes it in cleanup. Credentials are read from the
    process environment only; nothing is written to the repository.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("SCIWEAVE_RUN_TERMINUSDB_INTEGRATION") != "1":
            raise unittest.SkipTest(
                "integration disabled; set SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1"
            )
        cls.base_url = (
            os.environ.get("SCIWEAVE_BUFFER_TERMINUSDB_URL")
            or os.environ["SCIWEAVE_WIKI_TERMINUSDB_URL"]
        ).rstrip("/")
        cls.database = _temporary_database_name(
            os.environ.get("SCIWEAVE_BUFFER_TERMINUSDB_DATABASE")
            or os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_DATABASE")
            or "sciweave_buffer"
        )
        cls.credentials = {
            "token": os.environ.get("SCIWEAVE_BUFFER_TERMINUSDB_TOKEN")
            or os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_TOKEN"),
            "username": os.environ.get("SCIWEAVE_BUFFER_TERMINUSDB_USERNAME")
            or os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_USERNAME"),
            "password": os.environ.get("SCIWEAVE_BUFFER_TERMINUSDB_PASSWORD")
            or os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_PASSWORD"),
        }
        cls.authorization = _authorization_from_credentials(cls.credentials)

        status, _, body = cls._request("POST", f"/api/db/admin/{cls.database}",
                                       {"label": "SciWeave Buffer Integration", "comment": "draft buffer temp database"})
        if status != 200:
            raise AssertionError(f"database creation failed: {status} {body[:400]}")

        cls.store = TerminusDBDraftStore(
            base_url=cls.base_url,
            database=cls.database,
            username=os.environ.get("SCIWEAVE_BUFFER_TERMINUSDB_USERNAME")
            or os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_USERNAME"),
            password=os.environ.get("SCIWEAVE_BUFFER_TERMINUSDB_PASSWORD")
            or os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_PASSWORD"),
            token=os.environ.get("SCIWEAVE_BUFFER_TERMINUSDB_TOKEN")
            or os.environ.get("SCIWEAVE_WIKI_TERMINUSDB_TOKEN"),
        )
        cls.service = DraftBufferService(cls.store, {
            "mapping": frozenset({"reviewer-map"}),
            "wiki": frozenset({"reviewer-wiki"}),
        })
        cls.addClassCleanup(cls._deleted_database)

    @classmethod
    def _request(cls, method, path, payload=None):
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
    def _deleted_database(cls):
        cls._request("DELETE", f"/api/db/admin/{cls.database}")

    def test_full_draft_lifecycle_persists_exact_commit(self):
        created = self.service.create_draft(
            "wiki", "wiki_document", "Evidence draft", {"body": "draft"}, "researcher", "it-create-1",
        )
        created_id = created["draft_id"]

        submitted = self.service.submit_draft(created_id, "it-submit-1", actor_id="researcher")
        self.assertEqual(submitted["status"], "submitted")
        frozen = submitted["snapshot_commit"]
        self.assertTrue(frozen and isinstance(frozen, str))

        reviewed = self.service.review_draft(
            created_id, "accept", "reviewed on real store", "it-review-1", actor_id="reviewer-wiki",
        )
        self.assertEqual(reviewed["status"], "accepted")

        promoted = self.service.mark_promoted(
            created_id, "wiki-proposal-1", "candidate-commit-abc", "it-promote-1", actor_id="reviewer-wiki",
        )
        self.assertEqual(promoted["status"], "promoted")

        stored = self.service.read_draft(created_id, actor_id="reviewer-wiki")["draft"]
        self.assertEqual(stored["status"], "promoted")
        self.assertEqual(stored["submitted_commit"], frozen)
        self.assertEqual(stored["promoted_candidate_commit"], "candidate-commit-abc")
        self.assertEqual(stored["reviewer_id"], "reviewer-wiki")

        log_commits = self._branch_log_identifiers("main")
        self.assertIn(frozen, log_commits)
        self.assertNotEqual(self._branch_head("main"), frozen)

    def test_idempotent_create_and_review_replay_produce_no_second_records(self):
        first = self.service.create_draft(
            "mapping", "mapping_change", "Route change", {"route": "r1"}, "researcher", "it-create-2",
        )
        second = self.service.create_draft(
            "mapping", "mapping_change", "Route change", {"route": "r1"}, "researcher", "it-create-2",
        )
        self.assertEqual(first["draft_id"], second["draft_id"])
        self.service.submit_draft(first["draft_id"], "it-submit-2", actor_id="researcher")
        first_review = self.service.review_draft(
            first["draft_id"], "reject", "needs evidence", "it-review-2", actor_id="reviewer-map",
        )
        head_after_review = self._branch_head("main")
        self.service.review_draft(
            first["draft_id"], "reject", "needs evidence", "it-review-2", actor_id="reviewer-map",
        )
        self.assertEqual(head_after_review, self._branch_head("main"))
        listed = self.service.list_drafts("mapping", actor_id="reviewer-map")
        drafts_of_id = [row for row in listed if row["draft_id"] == first["draft_id"]]
        self.assertEqual(len(drafts_of_id), 1)

    def test_cross_namespace_review_is_rejected(self):
        created = self.service.create_draft(
            "wiki", "wiki_document", "Wiki-only draft", {}, "researcher", "it-create-3",
        )
        self.service.submit_draft(created["draft_id"], "it-submit-3", actor_id="researcher")
        with self.assertRaisesRegex(BufferError, "not authorized"):
            self.service.review_draft(
                created["draft_id"], "accept", "wrong reviewer", "it-review-3", actor_id="reviewer-map",
            )

    def _branch_head(self, branch):
        status, _, body = self._request(
            "GET", f"/api/log/admin/{self.database}/local/branch/{branch}?count=1"
        )
        if status != 200:
            raise AssertionError(f"log read failed: {status} {body[:400]}")
        return str(json.loads(body.decode())[0]["identifier"])

    def _branch_log_identifiers(self, branch):
        status, _, body = self._request(
            "GET", f"/api/log/admin/{self.database}/local/branch/{branch}?count=1000"
        )
        if status != 200:
            raise AssertionError(f"log read failed: {status} {body[:400]}")
        entries = json.loads(body.decode())
        return [str(entry["identifier"]) for entry in entries]


def _authorization_from_credentials(credentials):
    import base64
    if credentials["token"]:
        return f"Bearer {credentials['token']}"
    if credentials["username"] and credentials["password"]:
        raw = f"{credentials['username']}:{credentials['password']}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")
    return None


def _temporary_database_name(prefix: str) -> str:
    return f"it-{prefix.rstrip('-_')}-{uuid.uuid4().hex[:12]}"


if __name__ == "__main__":
    unittest.main()