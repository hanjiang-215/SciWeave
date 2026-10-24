"""Iris demo: run the real SciWeave platform publication flow end to end.

Starts the real Research Mapping management MCP (Streamable HTTP, real
TerminusDB), then drives it over JSON-RPC exactly as an agent harness would:
  get_formal_mapping -> submit_candidate -> preview_candidate
  -> record_review (approved) -> formalize_candidate -> get_formal_mapping
It also exercises a failure path (stale base candidate) and produces a
machine-readable evidence JSON for the ai4-aaff demo evidence card.

Only standard library is used. Connection settings come from environment
variables; nothing is hard-coded. The temporary TerminusDB database is
removed in ``finally``.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import threading
import uuid
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESEARCH_MAP_SRC = ROOT / "sci-weave" / "centre-control" / "research-map" / "src"
AUDIT_TRAIL_SRC = ROOT / "sci-weave" / "centre-control" / "shared" / "audit-trail" / "src"
sys.path.insert(0, str(RESEARCH_MAP_SRC))
sys.path.insert(0, str(AUDIT_TRAIL_SRC))

from research_mapping.domain import (  # noqa: E402
    FormalMappingRevision,
    FormalizationResult,
)
from research_mapping.formalization import MappingFormalizationService  # noqa: E402
from research_mapping.formal_query import FormalQueryService  # noqa: E402
from research_mapping.management import MappingManagementService, open_audit_database  # noqa: E402
from research_mapping.management_mcp import create_management_mcp_server  # noqa: E402
from research_mapping.review import MappingReviewService  # noqa: E402
from research_mapping.sqlite_store import SqliteStore  # noqa: E402
from research_mapping.terminus_store import TerminusDBStore  # noqa: E402


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name) or default


def _http_request(url: str, *, method: str = "GET", payload=None, token: str | None = None):
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class _HttpBasic:
    def __init__(self, username: str, password: str) -> None:
        self.header = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode("ascii")

    def at(self, url: str, *, method: str = "GET", payload=None):
        body = None
        headers = {"Accept": "application/json", "Authorization": self.header}
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()


def _mcp_call(base: str, token: str, tool: str, arguments: dict, request_id: int) -> dict:
    status, body = _http_request(
        f"{base}/mcp",
        method="POST",
        payload={"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                 "params": {"name": tool, "arguments": arguments}},
        token=token,
    )
    if status != 200:
        raise RuntimeError(f"MCP call {tool} http {status}: {body[:200]!r}")
    return json.loads(body.decode("utf-8"))


def _mcp_tools(base: str, token: str) -> list[str]:
    status, body = _http_request(
        f"{base}/mcp",
        method="POST",
        payload={"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}},
        token=token,
    )
    if status != 200:
        raise RuntimeError(f"tools/list http {status}")
    result = json.loads(body.decode("utf-8")).get("result", {})
    return [tool["name"] for tool in result.get("tools", [])]


def _task_node(*, version_id: str, title: str, state: str, domain: str,
               proposal_id: str | None = None, base_revision_id: str | None = None) -> dict:
    node = {
        "@type": "TaskNode",
        "@id": f"TaskNode/{version_id}",
        "mapping_domain_id": domain,
        "logical_id": f"task-{version_id}",
        "version_id": version_id,
        "title": title,
        "objective": "Reproduce UCI Iris baseline",
        "scope": "Demo evidence",
        "acceptance_criteria": ["Input snapshot is fixed and checkable"],
        "expected_outputs": ["Formal route revision"],
        "required_evidence": ["Owner approval"],
        "task_owner_id": "project-owner",
        "lifecycle_state": state,
        "created_by": "iris-demo",
        "created_at": "2026-10-24T00:00:00Z",
    }
    if proposal_id is not None:
        node["proposal_id"] = proposal_id
    if base_revision_id is not None:
        node["base_formal_revision_id"] = base_revision_id
    return node


def main() -> int:
    base_url = _env("SCIWEAVE_MAPPING_TERMINUSDB_URL", "http://127.0.0.1:6363").rstrip("/")
    store_id = _env("SCIWEAVE_MAPPING_TERMINUSDB_STORE", "admin")
    username = _env("SCIWEAVE_MAPPING_TERMINUSDB_USERNAME")
    password = _env("SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD")
    if not username or not password:
        print(json.dumps({"status": "failed", "error": (
            "SCIWEAVE_MAPPING_TERMINUSDB_USERNAME and SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD "
            "must be provided through environment variables"
        )}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    token = _env("SCIWEAVE_MAPPING_TERMINUSDB_TOKEN") or None
    bot = _HttpBasic(username, password)
    database = "sciweave_iris_demo_" + uuid.uuid4().hex[:8]

    events: list[dict] = []
    created = False
    evidence = {}

    def record(stage: str, payload: dict) -> None:
        events.append({"stage": stage, **payload})

    try:
        # --- 1. create a temporary TerminusDB database with product schema ---
        status, body = bot.at(f"{base_url}/api/db/{store_id}/{database}",
                              method="POST", payload={"label": "Iris demo", "comment": "temporary demo database"})
        if status != 200:
            raise RuntimeError(f"database creation failed ({status}): {body[:300]!r}")
        created = True
        record("create_database", {"status": status, "database": database})

        schema = [
            {
                "@type": "Class", "@id": "TaskNode",
                "@key": {"@type": "Lexical", "@fields": ["version_id"]},
                "mapping_domain_id": "xsd:string", "logical_id": "xsd:string",
                "version_id": "xsd:string", "title": "xsd:string", "objective": "xsd:string",
                "scope": "xsd:string",
                "acceptance_criteria": {"@type": "Set", "@class": "xsd:string"},
                "expected_outputs": {"@type": "Set", "@class": "xsd:string"},
                "required_evidence": {"@type": "Set", "@class": "xsd:string"},
                "task_owner_id": "xsd:string", "lifecycle_state": "xsd:string",
                "proposal_id": {"@type": "Optional", "@class": "xsd:string"},
                "base_formal_revision_id": {"@type": "Optional", "@class": "xsd:string"},
                "created_by": "xsd:string", "created_at": "xsd:string",
            },
            {
                "@type": "Class", "@id": "DependencyEdge",
                "@key": {"@type": "Lexical", "@fields": ["version_id"]},
                "mapping_domain_id": "xsd:string", "logical_id": "xsd:string",
                "version_id": "xsd:string",
                "source_node_version_ref": {"@type": "Optional", "@class": "xsd:string"},
                "target_node_version_ref": {"@type": "Optional", "@class": "xsd:string"},
                "dependency_kind": "xsd:string", "lifecycle_state": "xsd:string",
                "proposal_id": {"@type": "Optional", "@class": "xsd:string"},
                "base_formal_revision_id": {"@type": "Optional", "@class": "xsd:string"},
                "created_by": "xsd:string", "created_at": "xsd:string",
            },
        ]
        status, body = bot.at(
            f"{base_url}/api/document/{store_id}/{database}?graph_type=schema&author=iris-demo&message=schema",
            method="POST", payload=schema,
        )
        if status != 200:
            raise RuntimeError(f"schema setup failed ({status}): {body[:300]!r}")

        # --- 2. seed the initial formal route T1 -> T2 -> T3 ---
        base_nodes = [
            _task_node(version_id="t1-v1", title="T1 固定并检查输入", state="formal", domain="iris-demo"),
            _task_node(version_id="t2-v1", title="T2 执行基线分类", state="formal", domain="iris-demo"),
            _task_node(version_id="t3-v1", title="T3 研究人员复核并接纳", state="formal", domain="iris-demo"),
        ]
        status, body = bot.at(
            f"{base_url}/api/document/{store_id}/{database}?author=iris-demo&message=seed-formal-route",
            method="POST", payload=base_nodes,
        )
        if status != 200:
            raise RuntimeError(f"initial route seed failed ({status}): {body[:300]!r}")
        status, body = bot.at(f"{base_url}/api/log/{store_id}/{database}/local/branch/main?count=1")
        if status != 200:
            raise RuntimeError(f"base commit lookup failed ({status}): {body[:300]!r}")
        base_commit = json.loads(body.decode())[0]["identifier"]
        base_revision_id = "rev-base-" + uuid.uuid4().hex[:10]
        domain = "iris-demo"
        record("seed_initial_route", {"title_count": len(base_nodes), "base_commit": base_commit})

        # --- 3. assemble real services over the temporary database + temp SQLite ---
        terminus = TerminusDBStore(
            base_url=base_url, token=token, username=username, password=password,
            remote="local", store_id=store_id, database=database,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            sqlite = SqliteStore(os.path.join(temporary_directory, "iris.sqlite"))
            sqlite.initialize()
            sqlite.add_formal_revision(FormalMappingRevision(
                formal_revision_id=base_revision_id, mapping_domain_id=domain,
                terminus_store_id=store_id, formal_branch_id="main",
                formal_commit_hash=base_commit, base_formal_revision_id=None,
                source_proposal_id=None, approval_audit_event_id=None,
                published_by="project-owner", published_at="2026-10-24T00:00:00Z",
            ))
            sqlite.add_formalization_result(FormalizationResult(
                result_id="seed-result-" + uuid.uuid4().hex, mapping_domain_id=domain,
                formalization_operation_id="seed-operation-" + uuid.uuid4().hex,
                attempt_number=1, result_status="succeeded",
                formal_revision_id=base_revision_id, terminus_store_id=store_id,
                formal_commit_hash=base_commit, recorded_at="2026-10-24T00:00:00Z",
            ))
            sqlite.set_current_formal_revision(domain, base_revision_id, updated_at="2026-10-24T00:00:00Z")
            audit_path = os.path.join(temporary_directory, "audit.sqlite")
            audit = open_audit_database(audit_path) if audit_path else None
            try:
                return _run_flow(
                    terminus=terminus, sqlite=sqlite, audit=audit,
                    database=database, base_revision_id=base_revision_id,
                    domain=domain, store_id=store_id, base_commit=base_commit,
                    events=events,
                )
            finally:
                if audit is not None:
                    try:
                        audit.close()
                    except Exception:
                        pass
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error": str(error), "events": events},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    finally:
        if created:
            try:
                bot.at(f"{base_url}/api/db/{store_id}/{database}", method="DELETE")
            except Exception:
                pass
    return 0


def _run_flow(*, terminus, sqlite, audit, database, base_revision_id, domain,
              store_id, base_commit, events) -> int:
    from research_mapping.candidate_submission import MappingCandidateService
    candidate_service = MappingCandidateService(sqlite, terminus, terminus_database=database)
    review_service = MappingReviewService(sqlite, terminus, terminus_database=database)
    formalizer = MappingFormalizationService(
        sqlite, terminus, terminus_database=database,
        is_project_owner=lambda actor, mapping_domain: actor == "project-owner",
    )
    queries = FormalQueryService(sqlite_store=sqlite, terminus_store=terminus, terminus_database=database)
    capabilities = {
        "researcher": frozenset({"read", "candidate_submit"}),
        "reviewer": frozenset({"read", "candidate_review"}),
        "project-owner": frozenset({"read", "candidate_review", "formalize", "candidate_submit", "centre"}),
    }
    management = MappingManagementService(
        formal_query=queries, candidate_service=candidate_service,
        caller_capabilities=capabilities, audit_connection=audit,
        review_service=review_service, formalization_service=formalizer,
        sqlite_store=sqlite,
    )
    server = create_management_mcp_server(
        management, host="127.0.0.1", port=0,
        tokens={"iris-researcher": "researcher", "iris-reviewer": "reviewer",
                "iris-owner": "project-owner"},
    )
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    mcp_base = f"http://127.0.0.1:{port}"

    def record(stage: str, payload: dict) -> None:
        events.append({"stage": stage, **payload})

    try:
        # --- 4. run the publication flow over real MCP ---
        tools = _mcp_tools(mcp_base, "iris-owner")
        record("tools_list", {"tools": tools})
        if "get_formal_mapping" not in tools or "formalize_candidate" not in tools:
            raise RuntimeError(f"management MCP tool surface mismatch: {tools!r}")

        initial = _mcp_call(mcp_base, "iris-owner", "get_formal_mapping",
                            {"mapping_domain_id": domain}, request_id=1)
        record("get_formal_mapping_initial", initial)
        if initial["result"]["content"][0]["text"].count("formal_revision_id") == 0:
            raise RuntimeError("initial formal mapping not resolvable")

        proposal_id = "proposal-t4-" + uuid.uuid4().hex[:10]
        submission_id = "submission-t4-" + uuid.uuid4().hex[:10]
        idempotency_key = "idempotency-t4-" + uuid.uuid4().hex[:10]
        t4_node = _task_node(
            version_id="t4-v1", title="T4 分层交叉验证（路线变更）", state="candidate",
            domain=domain, proposal_id=proposal_id, base_revision_id=base_revision_id,
        )
        change_set = {
            "mapping_domain_id": domain, "submitter_id": "researcher",
            "submission_id": submission_id, "proposal_id": proposal_id,
            "base_formal_revision_id": base_revision_id,
            "nodes": [t4_node], "edges": [],
        }
        submitted = _mcp_call(mcp_base, "iris-owner", "submit_candidate",
                              {"change_set": change_set, "idempotency_key": idempotency_key}, request_id=2)
        record("submit_candidate_t4", submitted)
        submitted_text = submitted["result"]["content"][0]["text"]
        if '"status": "confirmed"' not in submitted_text:
            raise RuntimeError(f"candidate submit failed: {submitted_text[:300]!r}")
        submit_payload = json.loads(submitted_text)
        candidate_head = submit_payload["commit_hash"]

        denied_proposal_id = "proposal-denied-" + uuid.uuid4().hex[:10]
        denied_set = {
            "mapping_domain_id": domain, "submitter_id": "researcher",
            "submission_id": "submission-denied-" + uuid.uuid4().hex[:10],
            "proposal_id": denied_proposal_id,
            "base_formal_revision_id": base_revision_id,
            "nodes": [_task_node(
                version_id="t6-v1", title="T6 无提交权限尝试", state="candidate",
                domain=domain, proposal_id=denied_proposal_id,
                base_revision_id=base_revision_id,
            )],
            "edges": [],
        }
        denied = _mcp_call(mcp_base, "iris-reviewer", "submit_candidate",
                           {"change_set": denied_set, "idempotency_key": "idempotency-denied-" + uuid.uuid4().hex},
                           request_id=3)
        record("submit_candidate_denied_reviewer", denied)

        # A candidate under a stale base is rejected by the governance core.
        stale_set = dict(change_set)
        stale_set["submission_id"] = "submission-stale-" + uuid.uuid4().hex[:10]
        stale_set["proposal_id"] = "proposal-stale-" + uuid.uuid4().hex[:10]
        stale_node = _task_node(
            version_id="t5-v1", title="T5 过期基准上的提交", state="candidate",
            domain=domain, proposal_id=stale_set["proposal_id"], base_revision_id="rev-nonexistent",
        )
        stale_set["nodes"] = [stale_node]
        stale_set["base_formal_revision_id"] = "rev-nonexistent"
        stale = _mcp_call(mcp_base, "iris-owner", "submit_candidate",
                          {"change_set": stale_set, "idempotency_key": "idempotency-stale-" + uuid.uuid4().hex},
                          request_id=4)
        record("submit_candidate_stale_base", stale)
        stale_text = stale["result"]["content"][0]["text"]
        if '"stale_base"' not in stale_text and '"status": "confirmed"' not in stale_text:
            raise RuntimeError(f"unexpected stale-base outcome: {stale_text[:200]!r}")

        preview = _mcp_call(mcp_base, "iris-reviewer", "preview_candidate",
                            {"proposal_id": proposal_id, "base_formal_revision_id": base_revision_id,
                             "candidate_head": candidate_head}, request_id=5)
        record("preview_candidate_t4", preview)
        preview_text = preview["result"]["content"][0]["text"]
        if '"status": "available"' not in preview_text:
            raise RuntimeError(f"candidate preview failed: {preview_text[:300]!r}")
        preview_payload = json.loads(preview_text)
        buffer = review_service.create_buffer(preview_payload["preview_id"])

        rejected = _mcp_call(mcp_base, "iris-owner", "record_review",
                             {"buffer_id": buffer.buffer_id, "decision": "rejected",
                              "reason": "驳回分支演示：证据不足"}, request_id=6)
        record("record_review_rejected", rejected)
        rejection_payload = json.loads(rejected["result"]["content"][0]["text"])
        rejection_buffer_id = rejection_payload["buffer_id"]
        still_hidden_after_reject = _mcp_call(mcp_base, "iris-owner", "get_formal_mapping",
                                              {"mapping_domain_id": domain}, request_id=7)
        record("get_formal_mapping_after_reject", still_hidden_after_reject)

        second_buffer = review_service.create_buffer(preview_payload["preview_id"])
        approved = _mcp_call(mcp_base, "iris-owner", "record_review",
                             {"buffer_id": second_buffer.buffer_id, "decision": "approved",
                              "reason": "采纳 T4 路线变更：增加分层交叉验证"}, request_id=8)
        record("record_review_approved", approved)

        operation_id = "formalize-t4-" + uuid.uuid4().hex[:10]
        formalized = _mcp_call(mcp_base, "iris-owner", "formalize_candidate",
                               {"merge_request_id": second_buffer.buffer_id, "operation_id": operation_id},
                               request_id=9)
        record("formalize_candidate_t4", formalized)
        formalized_text = formalized["result"]["content"][0]["text"]
        if '"status": "succeeded"' not in formalized_text:
            raise RuntimeError(f"formalization failed: {formalized_text[:300]!r}")

        final = _mcp_call(mcp_base, "iris-owner", "get_formal_mapping",
                          {"mapping_domain_id": domain}, request_id=10)
        record("get_formal_mapping_final", final)
        final_text = final["result"]["content"][0]["text"]
        if "T4" not in final_text:
            raise RuntimeError("T4 did not appear in the formal mapping after formalization")

        listed = _mcp_call(mcp_base, "iris-owner", "list_candidates",
                           {"submission_id": submission_id}, request_id=11)
        record("list_candidates_t4", listed)

        evidence = {
            "dataset": "UCI Iris",
            "domain": domain,
            "base_revision_id": base_revision_id,
            "terminus_database": database,
            "flow": "get_formal_mapping -> submit_candidate -> preview_candidate -> "
                    "record_review -> formalize_candidate -> get_formal_mapping",
            "events": events,
            "failure_paths": {
                "reviewer_without_submit": "forbidden",
                "stale_base_candidate": stale_text,
                "rejected_review": rejection_payload.get("decision"),
            },
            "result": {
                "status": "completed",
                "formal_mapping_contains_t4": True,
                "candidate_head": candidate_head,
                "rejected_buffer_id": rejection_buffer_id,
            },
        }
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())