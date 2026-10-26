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

from research_mapping import errors
from research_mapping.candidate_reader import MappingCandidateReader
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
from research_mapping.governance_events import RecordingGovernanceEventPublisher

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
        from research_mapping.formalization import MappingFormalizationService
        from research_mapping.review import MappingReviewService
        review = MappingReviewService(self.sqlite, _FakeFormalTerminus(), terminus_database="db")
        formalization = MappingFormalizationService(
            self.sqlite, _FakeFormalTerminus(), terminus_database="db",
            is_project_owner=lambda actor, domain: actor == "owner",
        )
        audit_path = os.path.join(self.tmp.name, "audit.db")
        from audit_trail import init_audit_table, open_connection
        self.audit = open_connection(audit_path)
        self.addCleanup(self.audit.close)
        init_audit_table(self.audit)
        rules_dir = os.path.join(self.tmp.name, "rules")
        os.makedirs(rules_dir)
        rule_path = os.path.join(rules_dir, "1.0.0.json")
        with open(rule_path, "w", encoding="utf-8") as handle:
            json.dump({"version": "1.0.0", "checks": ["权限范围", "基准版本", "冲突", "影响范围"]}, handle, ensure_ascii=False)
        from research_mapping.prereview import MappingPrereviewLog
        prereview_log = MappingPrereviewLog(self.sqlite, rules_dir=rules_dir)
        from research_mapping.merged_candidate import MappingMergedCandidateService
        merged_candidate_service = MappingMergedCandidateService(
            self.sqlite, candidate, service_name="mapping-management",
        )
        self.governance_events = RecordingGovernanceEventPublisher()
        self.service = MappingManagementService(
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
            review_service=review,
            formalization_service=formalization,
            sqlite_store=self.sqlite,
            prereview_log=prereview_log,
            merged_candidate_service=merged_candidate_service,
            governance_events=self.governance_events,
        )

    def test_list_candidates_reads_back_the_persisted_candidate_record(self):
        submitted = self.service.call_tool(
            "submit_candidate", {"change_set": _change_set(), "idempotency_key": "key-list"}, actor_id="submitter",
        )
        self.assertEqual(submitted.status, "ok")
        listed = self.service.call_tool(
            "list_candidates", {"submission_id": "submission-1"}, actor_id="reader",
        )
        self.assertEqual(listed.status, "ok")
        candidate = listed.result["candidate"]  # type: ignore[index]
        self.assertEqual(candidate["submission_id"], "submission-1")
        self.assertEqual(candidate["commit_hash"], "commit-1")
        self.assertEqual(candidate["proposal_id"], "proposal-1")

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

    def test_formal_read_at_revision_reads_an_activated_historical_snapshot(self):
        outcome = self.service.call_tool(
            "get_formal_mapping_at_revision",
            {"mapping_domain_id": DOMAIN, "formal_revision_id": BASE},
            actor_id="reader",
        )
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.result["status"], "available")  # type: ignore[index]
        self.assertEqual(outcome.result["formal_revision_id"], BASE)  # type: ignore[index]
        denied = self.service.call_tool(
            "get_formal_mapping_at_revision",
            {"mapping_domain_id": DOMAIN, "formal_revision_id": BASE},
            actor_id="submitter",
        )
        self.assertEqual(denied.error_code, "forbidden")

    def test_formal_read_at_revision_unknown_or_bad_arguments(self):
        unknown = self.service.call_tool(
            "get_formal_mapping_at_revision",
            {"mapping_domain_id": DOMAIN, "formal_revision_id": "no-such-revision"},
            actor_id="reader",
        )
        self.assertEqual(unknown.status, "ok")
        self.assertEqual(unknown.result["status"], "no_such_revision")  # type: ignore[index]
        self.assertEqual(unknown.result["reason_code"], errors.REVISION_NOT_FOUND)  # type: ignore[index]
        missing_arg = self.service.call_tool(
            "get_formal_mapping_at_revision", {"mapping_domain_id": DOMAIN}, actor_id="reader",
        )
        self.assertEqual(missing_arg.error_code, "invalid_arguments")

    def test_candidate_submit_requires_candidate_submit_capability(self):
        outcome = self.service.call_tool(
            "submit_candidate", {"change_set": _change_set(), "idempotency_key": "key-1"}, actor_id="submitter",
        )
        self.assertEqual(outcome.status, "ok")
        denied = self.service.call_tool(
            "submit_candidate", {"change_set": _change_set(), "idempotency_key": "key-2"}, actor_id="reader",
        )
        self.assertEqual(denied.error_code, "forbidden")

    def test_candidate_submit_publishes_governance_event(self) -> None:
        outcome = self.service.call_tool(
            "submit_candidate", {"change_set": _change_set(), "idempotency_key": "key-event"}, actor_id="submitter",
        )
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(len(self.governance_events.events), 1)
        event = self.governance_events.events[0]
        self.assertEqual(event.event_type, "candidate_created")
        self.assertEqual(event.mapping_domain_id, DOMAIN)
        self.assertEqual(event.target["kind"], "candidate")
        self.assertEqual(event.target["id"], "submission-1")
        self.assertEqual(event.dedupe_key, f"{DOMAIN}:submission-1:commit-1")

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

    def test_append_prereview_log_requires_centre_capability_and_is_audited_as_write(self):
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
        rows = query_audit_calls(self.audit, service="mapping-management", tool="append_prereview_log")
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

    def test_centre_write_tools_are_all_forbidden(self):
        """After ai4-5auy, centre grants only reads; every write tool is denied."""
        calls = [
            {"tool": "submit_candidate", "args": {"change_set": _change_set(), "idempotency_key": "key-centre-1"}},
            {"tool": "preview_candidate", "args": {"proposal_id": "proposal-1", "base_formal_revision_id": BASE, "candidate_head": "head-a"}},
            {"tool": "record_review", "args": {"buffer_id": "buffer-1", "decision": "approved", "reason": "r"}},
            {"tool": "formalize_candidate", "args": {"merge_request_id": "mr-1", "operation_id": "op-1"}},
            {"tool": "reconcile_formalization", "args": {"operation_id": "op-1"}},
            {"tool": "append_prereview_log", "args": {"candidate_id": "c-1", "candidate_head": "h", "rule_set_version": "1.0.0", "verdict": "passed", "checks": [{"name": "权限范围", "verdict": "passed"}]}},
            {"tool": "create_merged_candidate", "args": {"mapping_domain_id": DOMAIN, "source_proposal_ids": ["proposal-1"], "base_formal_revision_id": BASE, "change_set": _change_set(), "idempotency_key": "key-centre-merged"}},
        ]
        for call in calls:
            outcome = self.service.call_tool(call["tool"], call["args"], actor_id="centre")
            self.assertEqual(
                outcome.error_code, "forbidden",
                f"{call['tool']} must be forbidden for a centre-only caller",
            )

    def test_prereview_and_merged_capabilities_are_independent(self):
        """prereview_log and merged_candidate are separate tiers; each alone is denied for the other."""
        prereview_args = {"candidate_id": "c-1", "candidate_head": "h", "rule_set_version": "1.0.0",
                          "verdict": "passed", "checks": [{"name": "权限范围", "verdict": "passed"}]}
        merged_args = {"mapping_domain_id": DOMAIN, "source_proposal_ids": ["proposal-1"],
                       "base_formal_revision_id": BASE, "change_set": _change_set(),
                       "idempotency_key": "key-independent"}
        denied_prereview = self.service.call_tool("append_prereview_log", prereview_args, actor_id="merger")
        self.assertEqual(denied_prereview.error_code, "forbidden")
        denied_merged = self.service.call_tool("create_merged_candidate", merged_args, actor_id="prereviewer")
        self.assertEqual(denied_merged.error_code, "forbidden")

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
        # Seven capability tiers are accepted after ai4-5auy.
        seven_tier = MappingConfig.from_environment({
            "SCIWEAVE_MAPPING_SQLITE_PATH": "data/mapping.sqlite",
            "SCIWEAVE_MAPPING_DOMAIN_ID": "domain-1",
            "SCIWEAVE_MAPPING_TERMINUSDB_URL": "http://127.0.0.1:0",
            "SCIWEAVE_MAPPING_TERMINUSDB_DATABASE": "db",
            "SCIWEAVE_MAPPING_TERMINUSDB_STORE": "store",
            "SCIWEAVE_MAPPING_MCP_HOST": "127.0.0.1",
            "SCIWEAVE_MAPPING_MCP_PORT": "0",
            "SCIWEAVE_MAPPING_MCP_TOKENS_JSON": '{"tok":"centre"}',
            "SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON": '{"centre":["centre","prereview_log","merged_candidate"]}',
        })
        self.assertEqual(
            seven_tier.caller_capabilities,
            {"centre": frozenset({"centre", "prereview_log", "merged_candidate"})},
        )
        with self.assertRaises(Exception):
            MappingConfig.from_environment({
                "SCIWEAVE_MAPPING_SQLITE_PATH": "data/mapping.sqlite",
                "SCIWEAVE_MAPPING_DOMAIN_ID": "domain-1",
                "SCIWEAVE_MAPPING_TERMINUSDB_URL": "http://127.0.0.1:0",
                "SCIWEAVE_MAPPING_TERMINUSDB_DATABASE": "db",
                "SCIWEAVE_MAPPING_TERMINUSDB_STORE": "store",
                "SCIWEAVE_MAPPING_MCP_HOST": "127.0.0.1",
                "SCIWEAVE_MAPPING_MCP_PORT": "0",
                "SCIWEAVE_MAPPING_MCP_TOKENS_JSON": '{"tok":"centre"}',
                "SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON": '{"centre":["centre","unknown_tier"]}',
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


class _ReaderTerminus:
    """Return confirmed snapshots per commit, with per-commit fail injection."""

    def __init__(self, documents):
        self._documents = documents
        self.unavailable_commits = set()

    def read_exact_snapshot(self, store_id, database, branch_id, commit_hash):
        from research_mapping.domain import SnapshotRead
        docs = self._documents.get(commit_hash)
        if commit_hash in self.unavailable_commits or docs is None:
            return SnapshotRead.unavailable("store_unavailable")
        return SnapshotRead.confirmed(store_id=store_id, database=database, branch_id=branch_id,
                                      commit_hash=commit_hash, documents=tuple(docs))


class ReviewableCandidatesToolTestCase(unittest.TestCase):
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
        self.terminus = _ReaderTerminus({
            "candidate-commit": ({"@id": "TaskNode/n1", "@type": "TaskNode", "title": "New",
                                  "lifecycle_state": "candidate", "proposal_id": "proposal-1",
                                  "base_formal_revision_id": BASE},),
            "candidate-commit-2": ({"@id": "TaskNode/n2", "@type": "TaskNode", "title": "New2",
                                    "lifecycle_state": "candidate", "proposal_id": "proposal-2",
                                    "base_formal_revision_id": BASE},),
        })
        reader = MappingCandidateReader(
            sqlite_store=self.sqlite, terminus_store=self.terminus, terminus_database="db",
        )
        formal = FormalQueryService(
            sqlite_store=self.sqlite, terminus_store=_FakeFormalTerminus(), terminus_database="db",
        )
        candidate = MappingCandidateService(self.sqlite, _FakeTerminusForManagement(), terminus_database="db")
        from research_mapping.merged_candidate import MappingMergedCandidateService
        merged_service = MappingMergedCandidateService(self.sqlite, candidate, service_name="mapping-management")
        self.service = MappingManagementService(
            formal_query=formal,
            candidate_service=candidate,
            candidate_reader=reader,
            caller_capabilities={
                "reader": frozenset({"read"}),
                "submitter": frozenset({"candidate_submit"}),
                "centre": frozenset({"centre"}),
                "merger": frozenset({"merged_candidate"}),
            },
            sqlite_store=self.sqlite,
            merged_candidate_service=merged_service,
        )

    def _insert_candidate(self, proposal_id="proposal-1", *, submission_id="submission-1",
                          commit="candidate-commit", status="candidate", candidate_digest=None):
        from research_mapping.canonical import sha256_json
        if candidate_digest is None:
            candidate_digest = sha256_json(tuple(self.terminus._documents[commit]))
        with self.sqlite.connection() as db:
            db.execute("INSERT INTO mapping_submission VALUES (?,?,?,?,?,?,?,?,?)",
                (submission_id, DOMAIN, "author", BASE, f"key-{proposal_id}", "digest",
                 proposal_id, "now", "candidate_created"))
            db.execute("INSERT INTO mapping_proposal VALUES (?,?,?,?,?,?,?,?)",
                (proposal_id, DOMAIN, BASE, "store", f"candidate-branch/{proposal_id}",
                 status, "author", "now"))
            db.execute("INSERT INTO mapping_candidate_commit VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (f"candidate-id-{proposal_id}", DOMAIN, proposal_id, "store",
                 f"candidate-branch/{proposal_id}", commit, BASE, "digest", candidate_digest,
                 "author", "now"))
            db.commit()

    def test_lists_reviewable_candidates_with_snapshot_content(self):
        self._insert_candidate()
        outcome = self.service.call_tool(
            "list_reviewable_candidates", {"mapping_domain_id": DOMAIN}, actor_id="reader",
        )
        self.assertEqual(outcome.status, "ok")
        candidates = outcome.result["candidates"]  # type: ignore[index]
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["proposal_id"], "proposal-1")
        self.assertEqual(candidate["candidate_head"], "candidate-commit")
        self.assertEqual(candidate["snapshot_status"], "available")
        self.assertEqual(candidate["documents"][0]["@type"], "TaskNode")

    def test_merged_candidate_is_excluded_from_reviewable_set(self):
        self._insert_candidate(status="merged")
        outcome = self.service.call_tool(
            "list_reviewable_candidates", {"mapping_domain_id": DOMAIN}, actor_id="reader",
        )
        self.assertEqual(outcome.result["candidates"], [])  # type: ignore[index]

    def test_snapshot_failure_is_isolated_per_candidate(self):
        self._insert_candidate(proposal_id="proposal-1", submission_id="submission-1", commit="candidate-commit")
        self._insert_candidate(proposal_id="proposal-2", submission_id="submission-2", commit="candidate-commit-2")
        self.terminus.unavailable_commits.add("candidate-commit-2")
        outcome = self.service.call_tool(
            "list_reviewable_candidates", {"mapping_domain_id": DOMAIN}, actor_id="centre",
        )
        self.assertEqual(outcome.status, "ok")
        by_proposal = {candidate["proposal_id"]: candidate for candidate in outcome.result["candidates"]}  # type: ignore[index]
        self.assertEqual(by_proposal["proposal-1"]["snapshot_status"], "available")
        self.assertEqual(by_proposal["proposal-2"]["snapshot_status"], "unavailable")
        self.assertEqual(by_proposal["proposal-2"]["reason_code"], "store_unavailable")

    def test_requires_read_or_centre_capability(self):
        self._insert_candidate()
        denied = self.service.call_tool(
            "list_reviewable_candidates", {"mapping_domain_id": DOMAIN}, actor_id="submitter",
        )
        self.assertEqual(denied.error_code, "forbidden")
        self.assertEqual(denied.result, None)

    def test_centre_no_longer_grants_write_tools(self):
        """centre is read-only after ai4-5auy; every injected write tool is forbidden."""
        # This test case injects candidate_service only, so only submit_candidate
        # exists as a write tool; the review/formalization tools are covered in
        # ManagementServiceTestCase via their capability maps.
        centre_only = [call for call in [
            {
                "tool": "submit_candidate",
                "args": {"change_set": _change_set(), "idempotency_key": "key-centre-submit"},
            },
        ]]
        for call in centre_only:
            outcome = self.service.call_tool(call["tool"], call["args"], actor_id="centre")
            self.assertEqual(
                outcome.error_code, "forbidden",
                f"{call['tool']} must be forbidden for a centre-only caller",
            )
        # The six read tools still work under centre.
        self._insert_candidate()
        for tool, args in [
            ("get_formal_mapping", {"mapping_domain_id": DOMAIN}),
            ("list_candidates", {"submission_id": "submission-1"}),
            ("list_reviewable_candidates", {"mapping_domain_id": DOMAIN}),
        ]:
            outcome = self.service.call_tool(tool, args, actor_id="centre")
            self.assertEqual(
                outcome.status, "ok", f"{tool} must stay readable for centre",
            )

    def test_create_merged_candidate_requires_merged_candidate_capability(self):
        self._insert_candidate(proposal_id="proposal-1", submission_id="submission-1", commit="candidate-commit")
        self._insert_candidate(proposal_id="proposal-2", submission_id="submission-2", commit="candidate-commit-2")
        change_set = _change_set()
        change_set["submission_id"] = "submission-merged"
        change_set["proposal_id"] = "proposal-merged"
        change_set["nodes"][0]["proposal_id"] = "proposal-merged"
        args = {
            "mapping_domain_id": DOMAIN,
            "source_proposal_ids": ["proposal-1", "proposal-2"],
            "base_formal_revision_id": BASE,
            "change_set": change_set,
            "idempotency_key": "key-merged",
        }
        denied = self.service.call_tool("create_merged_candidate", args, actor_id="centre")
        self.assertEqual(denied.error_code, "forbidden")
        outcome = self.service.call_tool("create_merged_candidate", args, actor_id="merger")
        self.assertEqual(outcome.status, "ok", outcome.reason_code)
        self.assertIsNotNone(outcome.result.get("commit_hash"))  # type: ignore[union-attr]

    def test_merged_candidate_rejects_nested_merge(self):
        self._insert_candidate(proposal_id="proposal-1", submission_id="submission-1", commit="candidate-commit")
        # A merged candidate is recognisable by its submitter prefix; mark one source as merged.
        with self.sqlite.connection() as db:
            db.execute(
                "UPDATE mapping_submission SET submitter_id='merged:abc' WHERE submission_id='submission-1'"
            )
            db.commit()
        change_set = _change_set()
        change_set["submission_id"] = "submission-merged"
        change_set["proposal_id"] = "proposal-merged"
        change_set["nodes"][0]["proposal_id"] = "proposal-merged"
        # Source candidate 1 is a merged candidate -> nested merge must be rejected.
        # It must not even reach the submitter (which would also fail); the
        # merged candidate service rejects it before persistence.
        args = {
            "mapping_domain_id": DOMAIN,
            "source_proposal_ids": ["proposal-1"],
            "base_formal_revision_id": BASE,
            "change_set": change_set,
            "idempotency_key": "key-nested",
        }
        outcome = self.service.call_tool("create_merged_candidate", args, actor_id="merger")
        self.assertEqual(outcome.error_code, "invalid_arguments")


if __name__ == "__main__":
    unittest.main()