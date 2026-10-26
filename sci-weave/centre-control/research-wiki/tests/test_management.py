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

from llm_wiki.candidate_reader import WikiCandidateReader
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
        self.saved_documents = []

    def create_candidate_snapshot(self, domain_id, base_commit_ref, canonical_snapshot, idempotency_key):
        import json
        self.calls.append((domain_id, base_commit_ref, canonical_snapshot, idempotency_key))
        self.saved_documents = json.loads(canonical_snapshot)
        return {"status": "confirmed", "store_id": "wiki-store", "branch_id": "candidate-branch", "commit_hash": "candidate-commit"}

    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        import llm_wiki.canonical as canonical
        docs = self.base_documents if commit_hash == "base-commit" else self.saved_documents
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
        rules_dir = str(Path(self.tmp.name) / "rules")
        Path(rules_dir).mkdir()
        (Path(rules_dir) / "1.0.0.json").write_text(
            json.dumps({"version": "1.0.0", "checks": ["权限范围", "基准版本", "冲突", "影响范围"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        from llm_wiki.prereview import WikiPrereviewLog
        prereview_log = WikiPrereviewLog(self.sqlite, rules_dir=rules_dir)
        from llm_wiki.merged_candidate import WikiMergedCandidateService
        merged_candidate_service = WikiMergedCandidateService(
            self.sqlite, candidate, service_name="wiki-management",
        )
        from llm_wiki.governance_events import RecordingGovernanceEventPublisher
        self.governance_events = RecordingGovernanceEventPublisher()
        self.service = WikiManagementService(
            formal_query=formal,
            candidate_service=candidate,
            caller_capabilities={
                "reader": frozenset({"read"}),
                "submitter": frozenset({"candidate_submit"}),
                "centre": frozenset({"centre"}),
                "prereviewer": frozenset({"prereview_log"}),
                "merger": frozenset({"merged_candidate"}),
            },
            audit_connection=self.audit,
            sqlite_store=self.sqlite,
            prereview_log=prereview_log,
            merged_candidate_service=merged_candidate_service,
            governance_events=self.governance_events,
        )

    def test_list_wiki_candidates_reads_back_persisted_submissions(self):
        submitted = self.service.call_tool(
            "submit_wiki_candidate", {"document_change": _change(), "idempotency_key": "key-list"}, actor_id="submitter",
        )
        self.assertEqual(submitted.status, "ok")
        listed = self.service.call_tool("list_wiki_candidates", {"wiki_domain_id": DOMAIN}, actor_id="reader")
        self.assertEqual(listed.status, "ok")
        candidates = listed.result["candidates"]  # type: ignore[index]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["submission_id"], "submission-1")
        self.assertEqual(candidates[0]["status"], "candidate_created")

    def test_formal_read_requires_read_or_centre_capability(self):
        outcome = self.service.call_tool("get_formal_wiki", {"wiki_domain_id": DOMAIN}, actor_id="reader")
        self.assertEqual(outcome.status, "ok")
        denied = self.service.call_tool("get_formal_wiki", {"wiki_domain_id": DOMAIN}, actor_id="submitter")
        self.assertEqual(denied.error_code, "forbidden")

    def test_candidate_submit_publishes_governance_event(self) -> None:
        outcome = self.service.call_tool(
            "submit_wiki_candidate",
            {"document_change": _change(), "idempotency_key": "key-event-wiki"},
            actor_id="submitter",
        )
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(len(self.governance_events.events), 1)
        event = self.governance_events.events[0]
        self.assertEqual(event.event_type, "candidate_created")
        self.assertEqual(event.wiki_domain_id, DOMAIN)
        self.assertEqual(event.target["kind"], "candidate")
        self.assertEqual(event.dedupe_key, f"{DOMAIN}:submission-1:candidate-commit")

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

    def test_centre_has_no_write_capability_on_any_wiki_tool(self):
        """After ai4-5auy, centre grants only reads on the Wiki management MCP."""
        centre_calls = [
            {"tool": "submit_wiki_candidate", "args": {"document_change": _change(), "idempotency_key": "key-centre-1"}},
            {"tool": "create_wiki_merge_request", "args": {"proposal_id": "proposal-1", "merge_request_id": "mr-1"}},
            {"tool": "decide_wiki_review", "args": {"merge_request_id": "mr-1", "decision": "approved", "reason": "r", "selected_solution_id": "sol-1"}},
            {"tool": "formalize_wiki", "args": {"merge_request_id": "mr-1", "operation_id": "op-1"}},
            {"tool": "reconcile_wiki_formalization", "args": {"operation_id": "op-1"}},
            {"tool": "append_prereview_log", "args": {"candidate_id": "c-1", "candidate_head": "h", "rule_set_version": "1.0.0", "verdict": "passed", "checks": [{"name": "权限范围", "verdict": "passed"}]}},
            {"tool": "create_merged_candidate", "args": {"wiki_domain_id": DOMAIN, "source_proposal_ids": ["proposal-1"], "base_formal_revision_id": BASE, "document_change": _change(), "idempotency_key": "key-centre-merged"}},
        ]
        for call in centre_calls:
            outcome = self.service.call_tool(call["tool"], call["args"], actor_id="centre")
            if outcome.error_code == "unknown_tool":
                continue  # tool not injected in this test case; covered elsewhere
            self.assertEqual(
                outcome.error_code, "forbidden",
                f"{call['tool']} must be forbidden for a centre-only caller",
            )

    def test_prereview_and_merged_capabilities_are_independent(self):
        """prereview_log and merged_candidate are separate tiers; each alone is denied for the other."""
        prereview_args = {"candidate_id": "c-1", "candidate_head": "h", "rule_set_version": "1.0.0",
                          "verdict": "passed", "checks": [{"name": "权限范围", "verdict": "passed"}]}
        merged_args = {"wiki_domain_id": DOMAIN, "source_proposal_ids": ["proposal-1"],
                       "base_formal_revision_id": BASE, "document_change": _change(),
                       "idempotency_key": "key-independent"}
        # merger without prereview_log is denied for append_prereview_log
        denied_prereview = self.service.call_tool("append_prereview_log", prereview_args, actor_id="merger")
        self.assertEqual(denied_prereview.error_code, "forbidden")
        # prereviewer without merged_candidate is denied for create_merged_candidate
        denied_merged = self.service.call_tool("create_merged_candidate", merged_args, actor_id="prereviewer")
        self.assertEqual(denied_merged.error_code, "forbidden")

    def test_append_prereview_log_requires_prereview_capability_and_is_audited_as_write(self):
        arguments = {
            "candidate_id": "candidate-1", "candidate_head": "head-a",
            "base_formal_revision_id": BASE, "rule_set_version": "1.0.0",
            "verdict": "passed",
            "checks": [{"name": "权限范围", "verdict": "passed"}],
            "conflict_matrix": [],
        }
        denied = self.service.call_tool("append_prereview_log", arguments, actor_id="reader")
        self.assertEqual(denied.error_code, "forbidden")
        denied_centre = self.service.call_tool("append_prereview_log", arguments, actor_id="centre")
        self.assertEqual(denied_centre.error_code, "forbidden")
        outcome = self.service.call_tool("append_prereview_log", arguments, actor_id="prereviewer")
        self.assertEqual(outcome.status, "ok")
        self.assertIsNotNone(outcome.result["report_id"])  # type: ignore[index]
        rows = query_audit_calls(self.audit, service="wiki-management", tool="append_prereview_log")
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["phase"] for row in rows}, {"invoked", "completed"})

    def test_append_prereview_log_decision_path(self):
        for head in ("head-a", "head-b"):
            self.service.call_tool(
                "append_prereview_log",
                {"candidate_id": "candidate-2", "candidate_head": head,
                 "base_formal_revision_id": BASE, "rule_set_version": "1.0.0",
                 "verdict": "passed", "checks": [{"name": "权限范围", "verdict": "passed"}], "conflict_matrix": []},
                actor_id="prereviewer",
            )
        current = self.service._prereview_log.current_report("candidate-2", "head-b")
        self.assertIsNotNone(current)
        decision = self.service.call_tool(
            "append_prereview_log",
            {"candidate_id": "candidate-2", "candidate_head": "head-a",
             "reason": "head_moved", "superseding_report_id": current["report_id"]},
            actor_id="prereviewer",
        )
        self.assertEqual(decision.status, "ok")
        self.assertIsNotNone(decision.result["decision_id"])  # type: ignore[index]

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
        seven_tier = WikiConfig.from_environment({
            "SCIWEAVE_WIKI_SQLITE_PATH": "data/wiki.sqlite",
            "SCIWEAVE_WIKI_DOMAIN_ID": "domain-1",
            "SCIWEAVE_WIKI_TERMINUSDB_URL": "http://127.0.0.1:0",
            "SCIWEAVE_WIKI_TERMINUSDB_DATABASE": "db",
            "SCIWEAVE_WIKI_TERMINUSDB_STORE": "store",
            "SCIWEAVE_WIKI_MCP_HOST": "127.0.0.1",
            "SCIWEAVE_WIKI_MCP_PORT": "0",
            "SCIWEAVE_WIKI_MCP_TOKENS_JSON": '{"tok":"centre"}',
            "SCIWEAVE_WIKI_CALLER_CAPABILITIES_JSON": '{"centre":["centre","prereview_log","merged_candidate"]}',
        })
        self.assertEqual(
            seven_tier.caller_capabilities,
            {"centre": frozenset({"centre", "prereview_log", "merged_candidate"})},
        )
        with self.assertRaises(Exception):
            WikiConfig.from_environment({
                "SCIWEAVE_WIKI_SQLITE_PATH": "data/wiki.sqlite",
                "SCIWEAVE_WIKI_DOMAIN_ID": "domain-1",
                "SCIWEAVE_WIKI_TERMINUSDB_URL": "http://127.0.0.1:0",
                "SCIWEAVE_WIKI_TERMINUSDB_DATABASE": "db",
                "SCIWEAVE_WIKI_TERMINUSDB_STORE": "store",
                "SCIWEAVE_WIKI_MCP_HOST": "127.0.0.1",
                "SCIWEAVE_WIKI_MCP_PORT": "0",
                "SCIWEAVE_WIKI_MCP_TOKENS_JSON": '{"tok":"centre"}',
                "SCIWEAVE_WIKI_CALLER_CAPABILITIES_JSON": '{"centre":["centre","unknown_tier"]}',
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
        names = {tool["name"] for tool in body["result"]["tools"]}
        # The transport only serves tools backed by an injected domain service.
        self.assertIn("get_formal_wiki", names)
        self.assertIn("submit_wiki_candidate", names)
        self.assertTrue(names.issubset({tool["name"] for tool in TOOL_DEFINITIONS}))

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


class _FakeWikiTerminus:
    """Minimal Wiki snapshot store used when only formal wiring is needed."""

    def __init__(self):
        self._saved_documents = None

    def create_candidate_snapshot(self, domain_id, base_commit_ref, canonical_snapshot, idempotency_key):
        import json
        self._saved_documents = json.loads(canonical_snapshot)
        return {"status": "confirmed", "store_id": "wiki-store", "branch_id": "candidate-branch", "commit_hash": "candidate-commit"}

    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        import llm_wiki.canonical as canonical
        docs = self._saved_documents if commit_hash == "candidate-commit" else ({"@type": "WikiRevision", "wiki_revision_id": "revision-formal-1",
                 "wiki_domain_id": DOMAIN, "lifecycle_state": "formal"},)
        return WikiSnapshotRead.confirmed(
            store_id=store_id, database=database, branch_id=branch_id, commit_hash=commit_hash,
            documents=docs, content_digest=canonical.sha256_json(docs),
        )

    def read_resource_version(self, *args, **kwargs):
        return None


class _WikiReaderTerminus:
    """Return confirmed Wiki snapshots per commit, with fail injection."""

    def __init__(self, documents):
        self._documents = documents
        self.unavailable_commits = set()

    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        import llm_wiki.canonical as canonical
        docs = self._documents.get(commit_hash)
        if commit_hash in self.unavailable_commits or docs is None:
            return WikiSnapshotRead.unavailable("store_unavailable")
        return WikiSnapshotRead.confirmed(
            store_id=store_id, database=database, branch_id=branch_id, commit_hash=commit_hash,
            documents=tuple(docs), content_digest=canonical.sha256_json(docs),
        )


class ReviewableWikiCandidatesToolTestCase(unittest.TestCase):
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
        self.terminus = _WikiReaderTerminus({
            "candidate-commit": ({"@type": "WikiRevision", "wiki_revision_id": "revision-candidate-1",
                                  "wiki_domain_id": DOMAIN, "lifecycle_state": "candidate",
                                  "proposal_id": "proposal-1", "base_formal_revision_id": BASE, "title": "New"},),
            "candidate-commit-2": ({"@type": "WikiRevision", "wiki_revision_id": "revision-candidate-2",
                                    "wiki_domain_id": DOMAIN, "lifecycle_state": "candidate",
                                    "proposal_id": "proposal-2", "base_formal_revision_id": BASE, "title": "New2"},),
        })
        reader = WikiCandidateReader(
            sqlite_store=self.sqlite, terminus_store=self.terminus, terminus_database="wiki-db",
        )
        formal = WikiFormalQueryService(
            sqlite_store=self.sqlite, terminus_store=_FakeWikiTerminus(), terminus_database="wiki-db",
            resource_review_service=FakeReviews(),
        )
        candidate = WikiCandidateService(
            sqlite_store=self.sqlite, terminus_store=_FakeWikiTerminus(),
            resource_review_service=FakeReviews(), terminus_database="wiki-db",
        )
        from llm_wiki.merged_candidate import WikiMergedCandidateService
        merged_candidate_service = WikiMergedCandidateService(
            self.sqlite, candidate, service_name="wiki-management",
        )
        rules_dir = Path(self.tmp.name) / "rules"
        rules_dir.mkdir()
        (rules_dir / "1.0.0.json").write_text(
            json.dumps({"version": "1.0.0", "checks": ["权限范围", "冲突", "影响范围"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        from llm_wiki.prereview import WikiPrereviewLog
        self.prereview_log = WikiPrereviewLog(self.sqlite, rules_dir=str(rules_dir))
        self.service = WikiManagementService(
            formal_query=formal,
            candidate_service=candidate,
            candidate_reader=reader,
            caller_capabilities={
                "reader": frozenset({"read"}),
                "submitter": frozenset({"candidate_submit"}),
                "centre": frozenset({"centre"}),
                "merger": frozenset({"merged_candidate"}),
                "prereviewer": frozenset({"prereview_log"}),
            },
            sqlite_store=self.sqlite,
            merged_candidate_service=merged_candidate_service,
            prereview_log=self.prereview_log,
        )

    def _insert_candidate(self, proposal_id="proposal-1", *, submission_id="submission-1",
                          commit="candidate-commit", status="candidate", candidate_digest=None):
        import llm_wiki.canonical as canonical
        if candidate_digest is None:
            candidate_digest = canonical.sha256_json(self.terminus._documents[commit])
        with self.sqlite.connection() as db:
            db.execute("INSERT INTO wiki_buffer_submission VALUES (?,?,?,?,?,?,?,?,?)",
                (submission_id, DOMAIN, "researcher-1", BASE, f"key-{proposal_id}", "digest",
                 proposal_id, "now", "candidate_created"))
            db.execute("INSERT INTO wiki_proposal VALUES (?,?,?,?,?,?,?,?)",
                (proposal_id, DOMAIN, BASE, "wiki-store", f"candidate-branch/{proposal_id}",
                 status, "researcher-1", "now"))
            db.execute("INSERT INTO wiki_candidate_commit VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (f"candidate-id-{proposal_id}", DOMAIN, proposal_id, "wiki-store",
                 f"candidate-branch/{proposal_id}", commit, BASE, "digest", candidate_digest,
                 "researcher-1", "now"))
            db.commit()

    def test_lists_reviewable_candidates_with_snapshot_content(self):
        self._insert_candidate()
        outcome = self.service.call_tool(
            "list_reviewable_wiki_candidates", {"wiki_domain_id": DOMAIN}, actor_id="reader",
        )
        self.assertEqual(outcome.status, "ok")
        candidates = outcome.result["candidates"]  # type: ignore[index]
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["proposal_id"], "proposal-1")
        self.assertEqual(candidate["candidate_head"], "candidate-commit")
        self.assertEqual(candidate["snapshot_status"], "available")
        self.assertEqual(candidate["documents"][0]["@type"], "WikiRevision")

    def test_merged_candidate_is_excluded_from_reviewable_set(self):
        self._insert_candidate(status="merged")
        outcome = self.service.call_tool(
            "list_reviewable_wiki_candidates", {"wiki_domain_id": DOMAIN}, actor_id="reader",
        )
        self.assertEqual(outcome.result["candidates"], [])  # type: ignore[index]

    def test_snapshot_failure_is_isolated_per_candidate(self):
        self._insert_candidate(proposal_id="proposal-1", submission_id="submission-1", commit="candidate-commit")
        self._insert_candidate(proposal_id="proposal-2", submission_id="submission-2", commit="candidate-commit-2")
        self.terminus.unavailable_commits.add("candidate-commit-2")
        outcome = self.service.call_tool(
            "list_reviewable_wiki_candidates", {"wiki_domain_id": DOMAIN}, actor_id="centre",
        )
        self.assertEqual(outcome.status, "ok")
        by_proposal = {candidate["proposal_id"]: candidate for candidate in outcome.result["candidates"]}  # type: ignore[index]
        self.assertEqual(by_proposal["proposal-1"]["snapshot_status"], "available")
        self.assertEqual(by_proposal["proposal-2"]["snapshot_status"], "unavailable")
        self.assertEqual(by_proposal["proposal-2"]["reason_code"], "store_unavailable")

    def test_reviewable_list_exposes_prereview_status(self):
        """Owner can see whether a wiki candidate is blocked on a missing report."""
        self._insert_candidate(proposal_id="proposal-1", submission_id="submission-1", commit="candidate-commit")
        self._insert_candidate(proposal_id="proposal-2", submission_id="submission-2", commit="candidate-commit-2")
        appended = self.service.call_tool(
            "append_prereview_log",
            {"candidate_id": "submission-1", "candidate_head": "candidate-commit",
             "base_formal_revision_id": BASE, "rule_set_version": "1.0.0",
             "verdict": "passed",
             "checks": [{"name": "权限范围", "verdict": "passed"}],
             "conflict_matrix": []},
            actor_id="prereviewer",
        )
        self.assertEqual(appended.status, "ok")
        outcome = self.service.call_tool(
            "list_reviewable_wiki_candidates", {"wiki_domain_id": DOMAIN}, actor_id="reader",
        )
        self.assertEqual(outcome.status, "ok")
        by_submission = {c["submission_id"]: c for c in outcome.result["candidates"]}  # type: ignore[index]
        self.assertEqual(by_submission["submission-1"]["prereview_status"]["status"], "report_current")
        self.assertEqual(by_submission["submission-1"]["prereview_status"]["report_id"], appended.result["report_id"])  # type: ignore[index]
        self.assertEqual(by_submission["submission-2"]["prereview_status"]["status"], "missing_report")
        invalidated = self.service.call_tool(
            "append_prereview_log",
            {"candidate_id": "submission-1", "candidate_head": "candidate-commit", "reason": "base_moved"},
            actor_id="prereviewer",
        )
        self.assertEqual(invalidated.status, "ok")
        outcome = self.service.call_tool(
            "list_reviewable_wiki_candidates", {"wiki_domain_id": DOMAIN}, actor_id="reader",
        )
        status = outcome.result["candidates"][0]["prereview_status"]  # type: ignore[index]
        self.assertEqual(status["status"], "report_stale")
        self.assertEqual(status["reason"], "base_moved")

    def test_requires_read_or_centre_capability(self):
        self._insert_candidate()
        denied = self.service.call_tool(
            "list_reviewable_wiki_candidates", {"wiki_domain_id": DOMAIN}, actor_id="submitter",
        )
        self.assertEqual(denied.error_code, "forbidden")
        self.assertEqual(denied.result, None)

    def test_centre_no_longer_grants_wiki_write_tools(self):
        """centre is read-only after ai4-5auy; submit is forbidden for centre-only callers."""
        self._insert_candidate()
        outcome = self.service.call_tool(
            "submit_wiki_candidate",
            {"document_change": _change(), "idempotency_key": "key-centre-wiki"},
            actor_id="centre",
        )
        self.assertEqual(outcome.error_code, "forbidden")

    def test_create_wiki_merged_candidate_requires_merged_candidate_capability(self):
        self._insert_candidate(proposal_id="proposal-1", submission_id="submission-1", commit="candidate-commit")
        self._insert_candidate(proposal_id="proposal-2", submission_id="submission-2", commit="candidate-commit-2")
        document_change = _change(submission_id="submission-merged", proposal_id="proposal-merged")
        args = {
            "wiki_domain_id": DOMAIN,
            "source_proposal_ids": ["proposal-1", "proposal-2"],
            "base_formal_revision_id": BASE,
            "document_change": document_change,
            "idempotency_key": "key-wiki-merged",
        }
        denied = self.service.call_tool("create_merged_candidate", args, actor_id="centre")
        self.assertEqual(denied.error_code, "forbidden")
        outcome = self.service.call_tool("create_merged_candidate", args, actor_id="merger")
        self.assertEqual(outcome.status, "ok", outcome.reason_code)
        self.assertIsNotNone(outcome.result.get("commit_hash"))  # type: ignore[union-attr]

    def test_wiki_merged_candidate_rejects_nested_merge(self):
        self._insert_candidate(proposal_id="proposal-1", submission_id="submission-1", commit="candidate-commit")
        with self.sqlite.connection() as db:
            db.execute(
                "UPDATE wiki_buffer_submission SET submitter_id='merged:abc' WHERE submission_id='submission-1'"
            )
            db.commit()
        document_change = _change(submission_id="submission-merged", proposal_id="proposal-merged")
        args = {
            "wiki_domain_id": DOMAIN,
            "source_proposal_ids": ["proposal-1"],
            "base_formal_revision_id": BASE,
            "document_change": document_change,
            "idempotency_key": "key-wiki-nested",
        }
        outcome = self.service.call_tool("create_merged_candidate", args, actor_id="merger")
        self.assertEqual(outcome.error_code, "invalid_arguments")


if __name__ == "__main__":
    unittest.main()