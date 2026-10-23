from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from audit_trail import query_audit_calls

from research_mapping.candidate_submission import MappingCandidateService
from research_mapping.config import MappingConfig
from research_mapping.domain import FormalMappingRevision, FormalizationResult, FormalQueryResult
from research_mapping.formal_query import FormalQueryService
from research_mapping.management import (
    ManagementCallOutcome,
    MappingManagementService,
    TOOL_DEFINITIONS,
)
from research_mapping.management_mcp import create_management_mcp_server
from research_mapping.sqlite_store import SqliteStore

DOMAIN = "domain-1"
BASE = "formal-1"


class _FakeTerminusForManagement:
    def create_candidate_snapshot(self, domain_id, base_commit_ref, canonical_snapshot, idempotency_key):
        return {"status": "confirmed", "store_id": "store", "branch_id": "candidate/x", "commit_hash": "commit-1"}


class _FakeFormalTerminus:
    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        from research_mapping.domain import SnapshotRead
        return SnapshotRead.confirmed(
            store_id=store_id, database=database, branch_id=branch_id, commit_hash=commit_hash,
            documents=({"@id": "TaskNode/t1", "@type": "TaskNode"},),
        )


def _node(logical_id="n1", version_id="n1-v1"):
    return {"@type": "TaskNode", "@id": f"TaskNode/{version_id}", "mapping_domain_id": DOMAIN,
            "logical_id": logical_id, "version_id": version_id, "title": logical_id, "objective": "o",
            "scope": "s", "acceptance_criteria": ["c"], "expected_outputs": ["o"], "required_evidence": ["e"],
            "task_owner_id": "owner", "lifecycle_state": "candidate", "proposal_id": "proposal-1",
            "base_formal_revision_id": BASE, "created_by": "hanjiang", "created_at": "2026-10-21T00:00:00Z"}


def _change_set(**overrides):
    payload = {"mapping_domain_id": DOMAIN, "submitter_id": "hanjiang", "submission_id": "submission-1",
               "proposal_id": "proposal-1", "base_formal_revision_id": BASE, "nodes": [_node()], "edges": []}
    payload.update(overrides)
    return payload


class ManagementServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        sqlite_path = os.path.join(self.tmp.name, "mapping.db")
        self.sqlite = SqliteStore(sqlite_path)
        self.sqlite.initialize()
        self.sqlite.add_formal_revision(FormalMappingRevision(
            formal_revision_id=BASE, mapping_domain_id=DOMAIN, terminus_store_id="store",
            formal_branch_id="formal", formal_commit_hash="base-commit", base_formal_revision_id=None,
            source_proposal_id=None, approval_audit_event_id=None, published_by="owner",
            published_at="2026-10-21T00:00:00Z",
        ))
        self.sqlite.add_formalization_result(FormalizationResult(
            result_id="result-1", mapping_domain_id=DOMAIN, formalization_operation_id="op-1",
            attempt_number=1, result_status="succeeded", formal_revision_id=BASE,
            terminus_store_id="store", formal_commit_hash="base-commit",
            recorded_at="2026-10-21T00:00:00Z",
        ))
        self.sqlite.set_current_formal_revision(DOMAIN, BASE, updated_at="2026-10-21T00:00:00Z")
        formal = FormalQueryService(
            sqlite_store=self.sqlite, terminus_store=_FakeFormalTerminus(), terminus_database="db",
        )
        candidate = MappingCandidateService(self.sqlite, _FakeTerminusForManagement(), terminus_database="db")
        audit_path = os.path.join(self.tmp.name, "audit.db")
        from audit_trail import init_audit_table, open_connection
        self.audit = open_connection(audit_path)
        self.addCleanup(self.audit.close)
        init_audit_table(self.audit)
        self.service = MappingManagementService(
            formal_query=formal,
            candidate_service=candidate,
            caller_capabilities={
                "reader": frozenset({"read"}),
                "submitter": frozenset({"candidate_submit"}),
                "centre": frozenset({"centre"}),
            },
            audit_connection=self.audit,
        )

    def test_formal_read_requires_read_or_centre_capability(self):
        outcome = self.service.call_tool(
            "get_formal_mapping", {"mapping_domain_id": DOMAIN}, actor_id="reader",
        )
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.result["formal_revision_id"], BASE)  # type: ignore[index]
        denied = self.service.call_tool(
            "get_formal_mapping", {"mapping_domain_id": DOMAIN}, actor_id="submitter",
        )
        self.assertEqual(denied.error_code, "forbidden")

    def test_candidate_submit_requires_candidate_submit_capability(self):
        outcome = self.service.call_tool(
            "submit_candidate", {"change_set": _change_set(), "idempotency_key": "key-1"}, actor_id="submitter",
        )
        self.assertEqual(outcome.status, "ok")
        denied = self.service.call_tool(
            "submit_candidate", {"change_set": _change_set(), "idempotency_key": "key-2"}, actor_id="reader",
        )
        self.assertEqual(denied.error_code, "forbidden")

    def test_unknown_tool_and_bad_arguments(self):
        outcome = self.service.call_tool("nope", {}, actor_id="reader")
        self.assertEqual(outcome.reason_code, "unknown_tool")
        self.assertEqual(self.service.call_tool(
            "get_formal_mapping", {}, actor_id="reader").error_code, "invalid_arguments")

    def test_read_is_recorded_attempted_in_audit(self):
        self.service.call_tool("get_formal_mapping", {"mapping_domain_id": DOMAIN}, actor_id="reader")
        rows = query_audit_calls(self.audit, service="mapping-management", tool="get_formal_mapping")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["caller_id"], "reader")
        self.assertEqual(rows[0]["phase"], "attempted")

    def test_write_has_invoked_and_completed_pair_in_audit(self):
        self.service.call_tool(
            "submit_candidate", {"change_set": _change_set(), "idempotency_key": "key-audit"}, actor_id="submitter",
        )
        rows = query_audit_calls(self.audit, service="mapping-management", tool="submit_candidate")
        self.assertEqual(len(rows), 2)
        phases = {row["phase"] for row in rows}
        self.assertEqual(phases, {"invoked", "completed"})

    def test_config_parses_tokens_and_capability_tiers(self):
        config = MappingConfig.from_environment({
            "SCIWEAVE_MAPPING_SQLITE_PATH": "data/mapping.sqlite",
            "SCIWEAVE_MAPPING_DOMAIN_ID": "domain-1",
            "SCIWEAVE_MAPPING_TERMINUSDB_URL": "http://127.0.0.1:0",
            "SCIWEAVE_MAPPING_TERMINUSDB_DATABASE": "db",
            "SCIWEAVE_MAPPING_TERMINUSDB_STORE": "store",
            "SCIWEAVE_MAPPING_MCP_HOST": "127.0.0.1",
            "SCIWEAVE_MAPPING_MCP_PORT": "0",
            "SCIWEAVE_MAPPING_MCP_TOKENS_JSON": '{"tok":"reader"}',
            "SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON": '{"reader":["read"]}',
            "SCIWEAVE_MAPPING_AUDIT_SQLITE_PATH": "data/audit.db",
        })
        self.assertEqual(config.mcp_tokens, {"tok": "reader"})
        self.assertEqual(config.caller_capabilities, {"reader": frozenset({"read"})})
        with self.assertRaises(Exception):
            MappingConfig.from_environment({
                "SCIWEAVE_MAPPING_SQLITE_PATH": "data/mapping.sqlite",
                "SCIWEAVE_MAPPING_DOMAIN_ID": "domain-1",
                "SCIWEAVE_MAPPING_TERMINUSDB_URL": "http://127.0.0.1:0",
                "SCIWEAVE_MAPPING_TERMINUSDB_DATABASE": "db",
                "SCIWEAVE_MAPPING_TERMINUSDB_STORE": "store",
                "SCIWEAVE_MAPPING_MCP_HOST": "127.0.0.1",
            })


class _ReviewFormalTerminus:
    def __init__(self):
        self.snapshots = {
            "base-commit": ({"@id": "TaskNode/n1", "@type": "TaskNode", "title": "Old", "lifecycle_state": "formal"},),
            "candidate-commit": ({"@id": "TaskNode/n1", "@type": "TaskNode", "title": "New", "lifecycle_state": "candidate"},),
        }
        self.branch_head = "candidate-commit"

    def current_branch_head(self, store_id, database, branch_id):
        return self.branch_head if branch_id == "candidate-branch" else "base-commit"

    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        from research_mapping.domain import SnapshotRead
        docs = self.snapshots.get(commit_hash)
        if docs is None:
            return SnapshotRead.unavailable("unavailable")
        return SnapshotRead.confirmed(store_id=store_id, database=database, branch_id=branch_id,
                                      commit_hash=commit_hash, documents=docs)

    def create_formal_snapshot(self, store_id, database, branch_id, commit_hash, operation_id):
        return self.read_exact_snapshot(store_id, database, branch_id, commit_hash)


class ReviewFormalizationToolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sqlite = SqliteStore(os.path.join(self.tmp.name, "mapping.db"))
        self.sqlite.initialize()
        self.sqlite.add_formal_revision(FormalMappingRevision(
            formal_revision_id=BASE, mapping_domain_id=DOMAIN, terminus_store_id="store",
            formal_branch_id="formal", formal_commit_hash="base-commit", base_formal_revision_id=None,
            source_proposal_id=None, approval_audit_event_id=None, published_by="owner",
            published_at="2026-10-22T00:00:00Z",
        ))
        self.sqlite.set_current_formal_revision(DOMAIN, BASE, updated_at="2026-10-22T00:00:00Z")
        with self.sqlite.connection() as db:
            db.execute("INSERT INTO mapping_submission VALUES (?,?,?,?,?,?,?,?,?)",
                ("submission", DOMAIN, "author", BASE, "key", "digest", "proposal", "now", "candidate_created"))
            db.execute("INSERT INTO mapping_proposal VALUES (?,?,?,?,?,?,?,?)",
                ("proposal", DOMAIN, BASE, "store", "candidate-branch", "candidate", "author", "now"))
            db.execute("INSERT INTO mapping_candidate_commit VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("candidate-id", DOMAIN, "proposal", "store", "candidate-branch", "candidate-commit", BASE,
                 "digest", "snapshot", "author", "now"))
            db.commit()
        self.terminus = _ReviewFormalTerminus()
        from research_mapping.formalization import MappingFormalizationService
        from research_mapping.review import MappingReviewService
        review = MappingReviewService(self.sqlite, self.terminus, terminus_database="db")
        formalization = MappingFormalizationService(
            self.sqlite, self.terminus, terminus_database="db",
            is_project_owner=lambda actor, domain: actor == "owner",
        )
        audit_path = os.path.join(self.tmp.name, "audit.db")
        from audit_trail import init_audit_table, open_connection
        self.audit = open_connection(audit_path)
        self.addCleanup(self.audit.close)
        init_audit_table(self.audit)
        from research_mapping.candidate_submission import MappingCandidateService
        self.service = MappingManagementService(
            formal_query=self._noop_formal(),
            candidate_service=MappingCandidateService(self.sqlite, self.terminus, terminus_database="db"),
            caller_capabilities={
                "reader": frozenset({"read"}),
                "reviewer": frozenset({"candidate_review"}),
                "owner": frozenset({"candidate_review", "formalize"}),
            },
            audit_connection=self.audit,
            review_service=review,
            formalization_service=formalization,
        )

    def _noop_formal(self):
        class Noop:
            def get_current(self, domain_id):
                return FormalQueryResult(status="no_formal_revision", mapping_domain_id=domain_id, reason_code="no_current_pointer")
        return Noop()

    def test_review_and_formalization_tools_require_their_capability_tiers(self):
        preview = self.service.call_tool(
            "preview_candidate", {"proposal_id": "proposal", "base_formal_revision_id": BASE, "candidate_head": "candidate-commit"},
            actor_id="reviewer",
        )
        self.assertEqual(preview.status, "ok")
        self.assertEqual(preview.result["status"], "available")  # type: ignore[index]
        denied = self.service.call_tool(
            "preview_candidate", {"proposal_id": "proposal", "base_formal_revision_id": BASE, "candidate_head": "candidate-commit"},
            actor_id="reader",
        )
        self.assertEqual(denied.error_code, "forbidden")
        formal_denied = self.service.call_tool(
            "formalize_candidate", {"merge_request_id": "buffer", "operation_id": "op"}, actor_id="reviewer",
        )
        self.assertEqual(formal_denied.error_code, "forbidden")

    def test_record_review_and_formalize_candidate_end_to_end(self):
        preview = self.service.call_tool(
            "preview_candidate", {"proposal_id": "proposal", "base_formal_revision_id": BASE, "candidate_head": "candidate-commit"},
            actor_id="reviewer",
        )
        self.assertEqual(preview.status, "ok")
        preview_id = preview.result["preview_id"]  # type: ignore[index]
        self.assertTrue(preview_id)
        from research_mapping.review import MappingReviewService
        buffer = MappingReviewService(self.sqlite, self.terminus, terminus_database="db").create_buffer(preview_id)
        decision = self.service.call_tool(
            "record_review", {"buffer_id": buffer.buffer_id, "decision": "approved", "reason": "looks good"}, actor_id="owner",
        )
        self.assertEqual(decision.status, "ok")
        self.assertEqual(decision.result["decision"], "approved")  # type: ignore[index]
        outcome = self.service.call_tool(
            "formalize_candidate", {"merge_request_id": buffer.buffer_id, "operation_id": "op-1"}, actor_id="owner",
        )
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.result["status"], "succeeded")  # type: ignore[index]


class ManagementMcpTransportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sqlite = SqliteStore(os.path.join(self.tmp.name, "mapping.db"))
        self.sqlite.initialize()
        self.service = MappingManagementService(
            formal_query=self._noop_formal(),
            candidate_service=MappingCandidateService(self.sqlite, _FakeTerminusForManagement(), terminus_database="db"),
            caller_capabilities={"reader": frozenset({"read"}), "submitter": frozenset({"candidate_submit"})},
        )
        server = create_management_mcp_server(
            self.service, host="127.0.0.1", port=0,
            tokens={"tok-reader": "reader", "tok-submitter": "submitter"},
        )
        self.server = server
        self.port = server.server_address[1]
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _noop_formal(self):
        class Noop:
            def get_current(self, domain_id):
                return FormalQueryResult(status="no_formal_revision", mapping_domain_id=domain_id, reason_code="no_current_pointer")
        return Noop()

    def _post(self, payload, token=None, path="/mcp"):
        body = json.dumps(payload, ensure_ascii=False).encode()
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_unauthenticated_and_unknown_token_are_rejected(self):
        status, body = self._post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(status, 401)
        status, body = self._post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token="tok-unknown")
        self.assertEqual(status, 401)

    def test_tools_list_is_served_after_authentication(self):
        status, body = self._post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token="tok-reader")
        self.assertEqual(status, 200)
        names = {tool["name"] for tool in body["result"]["tools"]}
        # The transport only serves tools backed by an injected domain service.
        self.assertIn("get_formal_mapping", names)
        self.assertIn("submit_candidate", names)
        self.assertTrue(names.issubset({tool["name"] for tool in TOOL_DEFINITIONS}))

    def test_denied_capability_returns_stable_error(self):
        status, body = self._post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "submit_candidate", "arguments": {"change_set": _change_set(), "idempotency_key": "k"}}},
            token="tok-reader",
        )
        self.assertEqual(status, 200)
        result = body["result"]
        self.assertTrue(result["isError"])
        error = json.loads(result["content"][0]["text"])
        self.assertEqual(error["code"], "forbidden")

    def test_health_requires_no_token(self):
        response = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=5)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read().decode("utf-8"))["protocol"], "mcp-streamable-http")


if __name__ == "__main__":
    unittest.main()