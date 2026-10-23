from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from audit_trail import init_audit_table, open_connection, query_audit_calls

from llm_wiki.candidate_submission import WikiCandidateService
from llm_wiki.config import WikiConfig
from llm_wiki.formal_domain import WikiSnapshotRead
from llm_wiki.formal_query import WikiFormalQueryService
from llm_wiki.management import TOOL_DEFINITIONS, WikiManagementService
from llm_wiki.management_mcp import create_wiki_management_mcp_server
from llm_wiki.sqlite_store import SqliteStore

DOMAIN = "domain-1"
BASE = "base-rev"


class FakeCandidateStore:
    def __init__(self):
        self.calls = []
        self.base_documents = []

    def create_candidate_snapshot(self, domain_id, base_commit_ref, canonical_snapshot, idempotency_key):
        self.calls.append((domain_id, base_commit_ref, canonical_snapshot, idempotency_key))
        return {"status": "confirmed", "store_id": "wiki-store", "branch_id": "candidate-branch", "commit_hash": "candidate-commit"}

    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        import llm_wiki.canonical as canonical
        docs = self.base_documents if commit_hash == "base-commit" else []
        return WikiSnapshotRead.confirmed(
            store_id=store_id, database=database, branch_id=branch_id, commit_hash=commit_hash,
            documents=docs, content_digest=canonical.sha256_json(docs),
        )


class FakeQualification:
    status = "pending"
    reason_code = "no_effective_decision"
    review_id = None
    use_scope = ()
    limitations = ()
    unknown_facts = ()


class FakeReviews:
    def get_current_qualification(self, resource_version_id, requested_scope=None):
        return FakeQualification()


def _change(**overrides):
    payload = {
        "submission_id": "submission-1", "proposal_id": "proposal-1",
        "wiki_domain_id": DOMAIN, "submitter_id": "researcher-1",
        "base_formal_revision_id": BASE,
        "document": {
            "@type": "WikiRevision", "wiki_revision_id": "revision-candidate-1",
            "document_id": "document-1", "category": "concept", "title": "Test",
            "body_markdown": "Full body", "created_by": "researcher-1",
            "created_at": "2026-10-22T00:00:00Z",
        },
        "references": [],
    }
    payload.update(overrides)
    return payload


class WikiManagementServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sqlite = SqliteStore(str(Path(self.tmp.name) / "wiki.sqlite"))
        self.sqlite.initialize()
        self.sqlite.add_formal_revision(
            formal_revision_id=BASE, wiki_domain_id=DOMAIN, terminus_store_id="wiki-store",
            formal_branch_id="main", formal_commit_hash="base-commit", content_snapshot_digest="base-digest",
        )
        self.sqlite.set_current_formal_revision(DOMAIN, BASE)
        self.terminus = FakeCandidateStore()
        self.terminus.base_documents = [{
            "@type": "WikiRevision", "wiki_revision_id": "revision-formal-1",
            "wiki_domain_id": DOMAIN, "lifecycle_state": "formal",
        }]
        formal = WikiFormalQueryService(
            sqlite_store=self.sqlite, terminus_store=self.terminus,
            terminus_database="wiki-db", resource_review_service=FakeReviews(),
        )
        candidate = WikiCandidateService(
            sqlite_store=self.sqlite, terminus_store=self.terminus,
            resource_review_service=FakeReviews(), terminus_database="wiki-db",
        )
        audit_path = str(Path(self.tmp.name) / "audit.db")
        self.audit = open_connection(audit_path)
        self.addCleanup(self.audit.close)
        init_audit_table(self.audit)
        self.service = WikiManagementService(
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
        outcome = self.service.call_tool("get_formal_wiki", {"wiki_domain_id": DOMAIN}, actor_id="reader")
        self.assertEqual(outcome.status, "ok")
        denied = self.service.call_tool("get_formal_wiki", {"wiki_domain_id": DOMAIN}, actor_id="submitter")
        self.assertEqual(denied.error_code, "forbidden")

    def test_candidate_submit_requires_candidate_submit_capability(self):
        outcome = self.service.call_tool(
            "submit_wiki_candidate", {"document_change": _change(), "idempotency_key": "key-1"}, actor_id="submitter",
        )
        self.assertEqual(outcome.status, "ok")
        denied = self.service.call_tool(
            "submit_wiki_candidate", {"document_change": _change(), "idempotency_key": "key-2"}, actor_id="reader",
        )
        self.assertEqual(denied.error_code, "forbidden")

    def test_unknown_tool_and_bad_arguments(self):
        outcome = self.service.call_tool("nope", {}, actor_id="reader")
        self.assertEqual(outcome.reason_code, "unknown_tool")
        self.assertEqual(self.service.call_tool("get_formal_wiki", {}, actor_id="reader").error_code, "invalid_arguments")

    def test_read_is_recorded_attempted_in_audit(self):
        self.service.call_tool("get_formal_wiki", {"wiki_domain_id": DOMAIN}, actor_id="reader")
        rows = query_audit_calls(self.audit, service="wiki-management", tool="get_formal_wiki")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["caller_id"], "reader")
        self.assertEqual(rows[0]["phase"], "attempted")

    def test_write_has_invoked_and_completed_pair_in_audit(self):
        self.service.call_tool(
            "submit_wiki_candidate", {"document_change": _change(), "idempotency_key": "key-audit"}, actor_id="submitter",
        )
        rows = query_audit_calls(self.audit, service="wiki-management", tool="submit_wiki_candidate")
        self.assertEqual(len(rows), 2)
        phases = {row["phase"] for row in rows}
        self.assertEqual(phases, {"invoked", "completed"})

    def test_config_parses_tokens_and_capability_tiers(self):
        config = WikiConfig.from_environment({
            "SCIWEAVE_WIKI_SQLITE_PATH": "data/wiki.sqlite",
            "SCIWEAVE_WIKI_DOMAIN_ID": "domain-1",
            "SCIWEAVE_WIKI_TERMINUSDB_URL": "http://127.0.0.1:0",
            "SCIWEAVE_WIKI_TERMINUSDB_DATABASE": "db",
            "SCIWEAVE_WIKI_TERMINUSDB_STORE": "store",
            "SCIWEAVE_WIKI_MCP_HOST": "127.0.0.1",
            "SCIWEAVE_WIKI_MCP_PORT": "0",
            "SCIWEAVE_WIKI_MCP_TOKENS_JSON": '{"tok":"reader"}',
            "SCIWEAVE_WIKI_CALLER_CAPABILITIES_JSON": '{"reader":["read"]}',
            "SCIWEAVE_WIKI_AUDIT_SQLITE_PATH": "data/audit.db",
        })
        self.assertEqual(config.mcp_tokens, {"tok": "reader"})
        self.assertEqual(config.caller_capabilities, {"reader": frozenset({"read"})})
        with self.assertRaises(Exception):
            WikiConfig.from_environment({
                "SCIWEAVE_WIKI_SQLITE_PATH": "data/wiki.sqlite",
                "SCIWEAVE_WIKI_DOMAIN_ID": "domain-1",
                "SCIWEAVE_WIKI_TERMINUSDB_URL": "http://127.0.0.1:0",
                "SCIWEAVE_WIKI_TERMINUSDB_DATABASE": "db",
                "SCIWEAVE_WIKI_TERMINUSDB_STORE": "store",
                "SCIWEAVE_WIKI_MCP_HOST": "127.0.0.1",
            })


class WikiManagementMcpTransportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sqlite = SqliteStore(str(Path(self.tmp.name) / "wiki.sqlite"))
        self.sqlite.initialize()
        self.service = WikiManagementService(
            formal_query=self._noop_formal(),
            candidate_service=WikiCandidateService(
                sqlite_store=self.sqlite, terminus_store=FakeCandidateStore(),
                resource_review_service=FakeReviews(), terminus_database="wiki-db",
            ),
            caller_capabilities={"reader": frozenset({"read"}), "submitter": frozenset({"candidate_submit"})},
        )
        server = create_wiki_management_mcp_server(
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
            def get_current(self, wiki_domain_id):
                from llm_wiki.formal_domain import WikiFormalQueryResult
                return WikiFormalQueryResult(status="no_formal_revision", wiki_domain_id=wiki_domain_id, reason_code="no_current_pointer")
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
        self.assertEqual(len(body["result"]["tools"]), len(TOOL_DEFINITIONS))

    def test_denied_capability_returns_stable_error(self):
        status, body = self._post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "submit_wiki_candidate", "arguments": {"document_change": _change(), "idempotency_key": "k"}}},
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