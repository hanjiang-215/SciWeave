from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from research_mapping.candidate_submission import MappingCandidateService
from research_mapping.domain import FormalMappingRevision, FormalizationResult
from research_mapping.formal_query import FormalQueryService
from research_mapping.formalization import MappingFormalizationService
from research_mapping.review import MappingReviewService
from research_mapping.sqlite_store import SqliteStore
from research_mapping.terminus_store import TerminusDBStore


REQUIRED_VARIABLES = (
    "SCIWEAVE_MAPPING_TERMINUSDB_URL",
    "SCIWEAVE_MAPPING_TERMINUSDB_DATABASE",
    "SCIWEAVE_MAPPING_TERMINUSDB_STORE",
)


def _task_node(*, version_id: str, title: str, state: str, domain: str,
               proposal_id: str | None = None, base_revision_id: str | None = None):
    node = {
        "@type": "TaskNode",
        "@id": f"TaskNode/{version_id}",
        "mapping_domain_id": domain,
        "logical_id": "task-integration",
        "version_id": version_id,
        "title": title,
        "objective": "Verify service-level publication",
        "scope": "Integration test",
        "acceptance_criteria": ["The approved candidate is queryable"],
        "expected_outputs": ["A formal task mapping"],
        "required_evidence": ["Owner approval"],
        "task_owner_id": "project-owner",
        "lifecycle_state": state,
        "created_by": "integration-test",
        "created_at": "2026-10-22T00:00:00Z",
    }
    if proposal_id is not None:
        node["proposal_id"] = proposal_id
    if base_revision_id is not None:
        node["base_formal_revision_id"] = base_revision_id
    return node


class MappingServiceTerminusDBIntegrationTestCase(unittest.TestCase):
    """Opt-in real TerminusDB + temporary SQLite publication-flow check."""

    def setUp(self) -> None:
        if os.environ.get("SCIWEAVE_RUN_TERMINUSDB_INTEGRATION") != "1":
            raise unittest.SkipTest("integration disabled; set SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1")
        missing = [name for name in REQUIRED_VARIABLES if not os.environ.get(name)]
        if missing:
            self.fail("integration configuration missing: " + ", ".join(missing))

    def test_candidate_commit_is_hidden_until_owner_approved_sqlite_activation(self) -> None:
        base_url = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_URL"].rstrip("/")
        store_id = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_STORE"]
        database = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_DATABASE"] + "_flow_it_" + uuid.uuid4().hex[:10]
        token = os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_TOKEN")
        username = os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_USERNAME")
        password = os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD")
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif username and password:
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = "Basic " + credentials
        elif username or password:
            self.fail("integration credentials need both username and password")

        def request(method: str, path: str, payload=None):
            request_headers = dict(headers)
            data = None
            if payload is not None:
                request_headers["Content-Type"] = "application/json"
                data = json.dumps(payload).encode()
            req = Request(base_url + path, data=data, headers=request_headers, method=method)
            try:
                with urlopen(req, timeout=10) as response:
                    return response.status, dict(response.headers), response.read()
            except HTTPError as error:
                return error.code, dict(error.headers or {}), error.read()

        created = False
        try:
            status, _, body = request(
                "POST", f"/api/db/{store_id}/{database}",
                {"label": "Mapping service integration", "comment": "temporary flow database"},
            )
            if status != 200:
                self.fail(f"temporary database creation failed ({status}): {body[:300]!r}")
            created = True

            domain = "mapping-integration-" + uuid.uuid4().hex
            base_revision_id = "base-" + uuid.uuid4().hex
            proposal_id = "proposal-" + uuid.uuid4().hex
            submission_id = "submission-" + uuid.uuid4().hex
            idempotency_key = "idempotency-" + uuid.uuid4().hex
            operation_id = "formalization-" + uuid.uuid4().hex
            base_node = _task_node(version_id="base-v1", title="Base mapping", state="formal", domain=domain)
            # No fixed port or external fixture: initialize only the TaskNode fields
            # used by the service flow, then seed an exact main-branch base Commit.
            schema = [{
                "@type": "Class", "@id": "TaskNode",
                "@key": {"@type": "Lexical", "@fields": ["version_id"]},
                "mapping_domain_id": "xsd:string", "logical_id": "xsd:string",
                "version_id": "xsd:string", "title": "xsd:string", "objective": "xsd:string",
                "scope": "xsd:string", "acceptance_criteria": {"@type": "Set", "@class": "xsd:string"},
                "expected_outputs": {"@type": "Set", "@class": "xsd:string"},
                "required_evidence": {"@type": "Set", "@class": "xsd:string"},
                "task_owner_id": "xsd:string", "lifecycle_state": "xsd:string",
                "proposal_id": {"@type": "Optional", "@class": "xsd:string"},
                "base_formal_revision_id": {"@type": "Optional", "@class": "xsd:string"},
                "created_by": "xsd:string", "created_at": "xsd:string",
            }]
            status, _, body = request(
                "POST", f"/api/document/{store_id}/{database}?graph_type=schema&author=it&message=schema", schema
            )
            if status != 200:
                self.fail(f"temporary schema setup failed ({status}): {body[:300]!r}")
            status, _, body = request(
                "POST", f"/api/document/{store_id}/{database}?author=it&message=base", [base_node]
            )
            if status != 200:
                self.fail(f"base snapshot setup failed ({status}): {body[:300]!r}")
            status, _, body = request("GET", f"/api/log/{store_id}/{database}/local/branch/main?count=1")
            if status != 200:
                self.fail(f"base commit lookup failed ({status}): {body[:300]!r}")
            base_commit = json.loads(body.decode())[0]["identifier"]

            terminus = TerminusDBStore(
                base_url=base_url,
                token=token,
                username=username,
                password=password,
                remote=os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_REMOTE", "local"),
                store_id=store_id,
                database=database,
            )
            with tempfile.TemporaryDirectory() as temporary_directory:
                sqlite = SqliteStore(os.path.join(temporary_directory, "mapping.db"))
                sqlite.initialize()
                sqlite.add_formal_revision(FormalMappingRevision(
                    formal_revision_id=base_revision_id,
                    mapping_domain_id=domain,
                    terminus_store_id=store_id,
                    formal_branch_id="main",
                    formal_commit_hash=base_commit,
                    base_formal_revision_id=None,
                    source_proposal_id=None,
                    approval_audit_event_id=None,
                    published_by="project-owner",
                    published_at="2026-10-22T00:00:00Z",
                ))
                sqlite.add_formalization_result(FormalizationResult(
                    result_id="seed-result-" + uuid.uuid4().hex,
                    mapping_domain_id=domain,
                    formalization_operation_id="seed-operation-" + uuid.uuid4().hex,
                    attempt_number=1,
                    result_status="succeeded",
                    formal_revision_id=base_revision_id,
                    terminus_store_id=store_id,
                    formal_commit_hash=base_commit,
                    recorded_at="2026-10-22T00:00:00Z",
                ))
                sqlite.set_current_formal_revision(domain, base_revision_id, updated_at="2026-10-22T00:00:00Z")
                candidates = MappingCandidateService(sqlite, terminus, terminus_database=database)
                reviews = MappingReviewService(sqlite, terminus, terminus_database=database)
                formalizer = MappingFormalizationService(
                    sqlite, terminus, terminus_database=database,
                    is_project_owner=lambda actor, mapping_domain: (
                        actor == "project-owner" and mapping_domain == domain
                    ),
                )
                queries = FormalQueryService(
                    sqlite_store=sqlite, terminus_store=terminus, terminus_database=database
                )

                initial = queries.get_current(domain)
                self.assertEqual(initial.status, "available", initial.reason_code)
                self.assertEqual(initial.formal_revision_id, base_revision_id)
                self.assertEqual([doc["title"] for doc in initial.documents], ["Base mapping"])

                submitted = candidates.submit({
                    "mapping_domain_id": domain,
                    "submitter_id": "integration-test",
                    "submission_id": submission_id,
                    "proposal_id": proposal_id,
                    "base_formal_revision_id": base_revision_id,
                    "nodes": [_task_node(
                        version_id="candidate-v1", title="Approved candidate", state="candidate",
                        domain=domain, proposal_id=proposal_id, base_revision_id=base_revision_id,
                    )],
                    "edges": [],
                }, idempotency_key)
                self.assertEqual(submitted.status, "confirmed", submitted.reason_code)
                self.assertIsNotNone(submitted.commit_hash)
                # The immutable candidate Commit exists in TerminusDB, while current
                # formal queries still resolve only through the original SQLite pointer.
                candidate_snapshot = terminus.read_exact_snapshot(
                    store_id, database, submitted.branch_id, submitted.commit_hash
                )
                self.assertEqual(candidate_snapshot.status, "confirmed", candidate_snapshot.reason_code)
                self.assertIn("Approved candidate", [doc["title"] for doc in candidate_snapshot.documents])
                hidden = queries.get_current(domain)
                self.assertEqual(hidden.status, "available", hidden.reason_code)
                self.assertEqual(hidden.formal_revision_id, base_revision_id)
                self.assertEqual([doc["title"] for doc in hidden.documents], ["Base mapping"])

                preview = reviews.preview(proposal_id, base_revision_id, submitted.commit_hash)
                self.assertEqual(preview.status, "available", preview.reason_code)
                self.assertTrue(preview.changes)
                buffer = reviews.create_buffer(preview.preview_id)
                self.assertEqual(buffer.candidate_commit_hash, submitted.commit_hash)

                not_approved = formalizer.formalize(buffer.buffer_id, operation_id + "-before-approval")
                self.assertEqual(not_approved.status, "failed")
                self.assertEqual(not_approved.reason_code, "owner_approval_required")
                still_hidden = queries.get_current(domain)
                self.assertEqual(still_hidden.status, "available", still_hidden.reason_code)
                self.assertEqual(still_hidden.formal_revision_id, base_revision_id)

                reviews.record_review(buffer.buffer_id, "project-owner", "approved", "Integration approval")
                formalized = formalizer.formalize(buffer.buffer_id, operation_id)
                self.assertEqual(formalized.status, "succeeded", formalized.reason_code)
                current = queries.get_current(domain)
                self.assertEqual(current.status, "available", current.reason_code)
                self.assertEqual(current.formal_revision_id, formalized.formal_revision_id)
                self.assertEqual(current.commit_hash, submitted.commit_hash)
                self.assertEqual(
                    [doc["title"] for doc in current.documents],
                    ["Base mapping", "Approved candidate"],
                )
        finally:
            if created:
                status, _, body = request("DELETE", f"/api/db/{store_id}/{database}")
                if status not in (200, 204):
                    self.fail(f"temporary database cleanup failed ({status}): {body[:300]!r}")


if __name__ == "__main__":
    unittest.main()
