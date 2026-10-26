"""Real TerminusDB integration test for the coordinator snapshot adapter.

Opt-in with ``SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1``. Starts a temporary
TerminusDB database seeded with a formal TaskNode/DependencyEdge route, boots
the research-map management MCP in-process, then reads the snapshot through
``ResearchMapMcpSnapshotPort`` (the exact ai4-2982 access path the coordinator
uses in production). Verifies the projected graph matches the seeded route.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import threading
import unittest
import uuid
from urllib.request import Request, urlopen

# The coordinator and research-map are separate deployment units in
# centre-control; the opt-in integration test reads research-map's management
# MCP through its source tree without coupling coordinator's uv.lock. Inject
# the two source paths only for this integration file.
import pathlib as _pathlib

_REPO = _pathlib.Path(__file__).resolve().parents[4]
for _relative in (
    "sci-weave/centre-control/research-map/src",
    "sci-weave/centre-control/shared/audit-trail/src",
):
    _candidate = str(_REPO / _relative)
    if os.path.isdir(_candidate) and _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from coordinator.adapter_snapshot import ResearchMapMcpSnapshotPort

REQUIRED_VARIABLES = (
    "SCIWEAVE_MAPPING_TERMINUSDB_URL",
    "SCIWEAVE_MAPPING_TERMINUSDB_STORE",
)


class _HttpBasic:
    def __init__(self, username: str, password: str) -> None:
        self.header = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode("ascii")

    def at(self, url: str, *, method: str = "GET", payload=None):
        body = None
        headers = {"Accept": "application/json", "Authorization": self.header}
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=15) as response:
                return response.status, response.read()
        except Exception as error:
            return getattr(error, "code", None), str(error).encode()


def _task_node(*, version_id: str, title: str, domain: str, logical_id: str, owner: str) -> dict:
    return {
        "@type": "TaskNode",
        "@id": f"TaskNode/{version_id}",
        "mapping_domain_id": domain,
        "logical_id": logical_id,
        "version_id": version_id,
        "title": title,
        "objective": "Coordinator integration route",
        "scope": "Integration test",
        "acceptance_criteria": ["Snapshot is readable"],
        "expected_outputs": ["Formal route"],
        "required_evidence": ["Seed"],
        "task_owner_id": owner,
        "executor_refs": ["agent-" + logical_id.lower()],
        "lifecycle_state": "formal",
        "created_by": "coordinator-it",
        "created_at": "2026-10-26T00:00:00Z",
    }


class CoordinatorSnapshotTerminusDBIntegrationTestCase(unittest.TestCase):
    """Real TerminusDB + in-process management MCP read via the coordinator port."""

    def setUp(self) -> None:
        if os.environ.get("SCIWEAVE_RUN_TERMINUSDB_INTEGRATION") != "1":
            raise unittest.SkipTest("integration disabled; set SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1")
        missing = [name for name in REQUIRED_VARIABLES if not os.environ.get(name)]
        if missing:
            self.fail("integration configuration missing: " + ", ".join(missing))

    def test_snapshot_port_reads_seeded_formal_route_through_management_mcp(self) -> None:
        base_url = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_URL"].rstrip("/")
        store_id = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_STORE"]
        username = os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_USERNAME")
        password = os.environ.get("SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD")
        if not username or not password:
            self.fail("integration credentials need both SCIWEAVE_MAPPING_TERMINUSDB_USERNAME and _PASSWORD")
        database = "sciweave_coordinator_it_" + uuid.uuid4().hex[:10]
        bot = _HttpBasic(username, password)

        # 1. temporary database + product schema
        status, body = bot.at(f"{base_url}/api/db/{store_id}/{database}",
                              method="POST", payload={"label": "coordinator it"})
        self.assertEqual(status, 200, f"database creation failed: {body!r}")
        self.addCleanup(lambda: bot.at(f"{base_url}/api/db/{store_id}/{database}", method="DELETE"))
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
                "executor_refs": {"@type": "Set", "@class": "xsd:string"},
                "created_by": "xsd:string", "created_at": "xsd:string",
            },
            {
                "@type": "Class", "@id": "DependencyEdge",
                "@key": {"@type": "Lexical", "@fields": ["version_id"]},
                "mapping_domain_id": "xsd:string", "logical_id": "xsd:string",
                "version_id": "xsd:string",
                "source_node_version_ref": {"@type": "Optional", "@class": "xsd:string"},
                "target_node_version_ref": {"@type": "Optional", "@class": "xsd:string"},
            },
        ]
        status, body = bot.at(
            f"{base_url}/api/document/{store_id}/{database}?graph_type=schema&author=it&message=schema",
            method="POST", payload=schema,
        )
        self.assertEqual(status, 200, f"schema setup failed: {body!r}")

        # 2. seed initial formal route T1 -> T2
        domain = "coordinator-it"
        nodes = [
            _task_node(version_id="t1-v1", title="T1 输入检查", domain=domain, logical_id="T1", owner="owner-1"),
            _task_node(version_id="t2-v1", title="T2 分析", domain=domain, logical_id="T2", owner="owner-1"),
        ]
        edges = [
            {
                "@type": "DependencyEdge",
                "@id": "DependencyEdge/e1-v1",
                "mapping_domain_id": domain,
                "logical_id": "E1",
                "version_id": "e1-v1",
                "source_node_version_ref": json.dumps({"logical_id": "T1", "version_id": "t1-v1", "mapping_domain_id": domain}),
                "target_node_version_ref": json.dumps({"logical_id": "T2", "version_id": "t2-v1", "mapping_domain_id": domain}),
            }
        ]
        status, body = bot.at(
            f"{base_url}/api/document/{store_id}/{database}?author=it&message=seed",
            method="POST", payload=nodes + edges,
        )
        self.assertEqual(status, 200, f"seed failed: {body!r}")
        status, body = bot.at(f"{base_url}/api/log/{store_id}/{database}/local/branch/main?count=1")
        self.assertEqual(status, 200, f"commit lookup failed: {body!r}")
        base_commit = json.loads(body.decode())[0]["identifier"]

        # 3. assemble management MCP over real services
        from research_mapping.candidate_submission import MappingCandidateService
        from research_mapping.domain import FormalMappingRevision, FormalizationResult
        from research_mapping.formal_query import FormalQueryService
        from research_mapping.formalization import MappingFormalizationService
        from research_mapping.management import MappingManagementService
        from research_mapping.management_mcp import create_management_mcp_server
        from research_mapping.review import MappingReviewService
        from research_mapping.sqlite_store import SqliteStore
        from research_mapping.terminus_store import TerminusDBStore

        with tempfile.TemporaryDirectory() as tmp:
            sqlite = SqliteStore(os.path.join(tmp, "coordinator-it.sqlite"))
            sqlite.initialize()
            formal_revision_id = "rev-base-" + uuid.uuid4().hex[:10]
            sqlite.add_formal_revision(FormalMappingRevision(
                formal_revision_id=formal_revision_id, mapping_domain_id=domain,
                terminus_store_id=store_id, formal_branch_id="main",
                formal_commit_hash=base_commit, base_formal_revision_id=None,
                source_proposal_id=None, approval_audit_event_id=None,
                published_by="project-owner", published_at="2026-10-26T00:00:00Z",
            ))
            sqlite.add_formalization_result(FormalizationResult(
                result_id="result-" + uuid.uuid4().hex, mapping_domain_id=domain,
                formalization_operation_id="op-" + uuid.uuid4().hex,
                attempt_number=1, result_status="succeeded",
                formal_revision_id=formal_revision_id, terminus_store_id=store_id,
                formal_commit_hash=base_commit, recorded_at="2026-10-26T00:00:00Z",
            ))
            sqlite.set_current_formal_revision(domain, formal_revision_id, updated_at="2026-10-26T00:00:00Z")
            terminus = TerminusDBStore(
                base_url=base_url, token=None, username=username, password=password,
                remote="local", store_id=store_id, database=database,
            )
            formal = FormalQueryService(sqlite_store=sqlite, terminus_store=terminus, terminus_database=database)
            candidate = MappingCandidateService(sqlite, terminus, terminus_database=database)
            review = MappingReviewService(sqlite, terminus, terminus_database=database)
            formalizer = MappingFormalizationService(
                sqlite, terminus, terminus_database=database,
                is_project_owner=lambda actor, domain_id: actor == "project-owner",
            )
            capabilities = {
                "reader": frozenset({"read"}),
                "owner": frozenset({"read", "candidate_review", "formalize", "centre"}),
            }
            management = MappingManagementService(
                formal_query=formal, candidate_service=candidate,
                caller_capabilities=capabilities,
                review_service=review, formalization_service=formalizer,
                sqlite_store=sqlite,
            )
            server = create_management_mcp_server(
                management, host="127.0.0.1", port=0,
                tokens={"tok-reader": "reader", "tok-owner": "owner"},
            )
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port_adapter = ResearchMapMcpSnapshotPort(
                    endpoint=f"http://127.0.0.1:{port}/mcp", token="tok-reader",
                )
                snapshot = port_adapter.get_formal_mapping_at_revision(domain, formal_revision_id)
                self.assertEqual(snapshot.mapping_domain_id, domain)
                self.assertEqual(snapshot.formal_revision_id, formal_revision_id)
                self.assertEqual(tuple(n.task_node_id for n in snapshot.nodes), ("T1", "T2"))
                self.assertEqual(snapshot.node_by_id("T1").version_id, "t1-v1")
                self.assertEqual(snapshot.node_by_id("T1").executor_refs, ("agent-t1",))
                self.assertEqual(snapshot.node_by_id("T1").task_owner_id, "owner-1")
                self.assertEqual(len(snapshot.edges), 1)
                edge = snapshot.edges[0]
                self.assertEqual(edge.source_node_id, "T1")
                self.assertEqual(edge.source_version_id, "t1-v1")
                self.assertEqual(edge.target_node_id, "T2")
                self.assertEqual(edge.target_version_id, "t2-v1")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()