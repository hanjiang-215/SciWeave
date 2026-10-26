"""Real Redpanda + real TerminusDB end-to-end for the coordinator chain.

Opt-in: ``SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1`` and
``SCIWEAVE_RUN_KAFKA_INTEGRATION=1`` (Redpanda must be reachable on the
configured bootstrap). Seeds a formal T1->T2 route in a temporary
TerminusDB database, boots the research-map management MCP in-process with an
executor agent registered online in a stub Registry, then drives:

    publish formal_revision_published -> coord consumer routes it
    -> coordinator reads the snapshot via real management MCP
    -> publishes task_handoff_ready to sciweave.task-handoff.<agent_id>
    -> a plain kafka consumer reads the envelope back

This is the exact handoff chain the demo shows (ai4-csyj / ai4-p5f3).
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
import uuid

_REPO = pathlib.Path(__file__).resolve().parents[4]
for _relative in (
    "sci-weave/centre-control/research-map/src",
    "sci-weave/centre-control/shared/audit-trail/src",
):
    _candidate = str(_REPO / _relative)
    if os.path.isdir(_candidate) and _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from coordinator.adapter_events import GovernanceEventConsumer, KafkaGovernanceEventConsumer
from coordinator.adapter_publisher import KafkaHandoffPublisher
from coordinator.adapter_registry import RegistryMcpAvailabilityPort
from coordinator.adapter_snapshot import ResearchMapMcpSnapshotPort
from coordinator.ports import AgentState
from coordinator.service import CoordinatorService
from coordinator.store import CoordinatorStore


class _HttpBasic:
    def __init__(self, username: str, password: str) -> None:
        self.header = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode("ascii")

    def at(self, url: str, *, method: str = "GET", payload=None):
        from urllib.request import Request, urlopen

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
        "objective": "Coordinator e2e route",
        "scope": "Integration test",
        "acceptance_criteria": ["Snapshot is readable"],
        "expected_outputs": ["Formal route"],
        "required_evidence": ["Seed"],
        "task_owner_id": owner,
        "executor_refs": ["agent-" + logical_id.lower()],
        "lifecycle_state": "formal",
        "created_by": "coordinator-e2e",
        "created_at": "2026-10-26T00:00:00Z",
    }


class CoordinatorHandoffE2E(unittest.TestCase):
    """formal_revision_published -> snapshot -> task_handoff_ready over real infra."""

    def setUp(self) -> None:
        if os.environ.get("SCIWEAVE_RUN_TERMINUSDB_INTEGRATION") != "1":
            raise unittest.SkipTest("integration disabled; set SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1")
        if os.environ.get("SCIWEAVE_RUN_KAFKA_INTEGRATION") != "1":
            raise unittest.SkipTest("kafka integration disabled; set SCIWEAVE_RUN_KAFKA_INTEGRATION=1")
        for name in ("SCIWEAVE_MAPPING_TERMINUSDB_URL", "SCIWEAVE_MAPPING_TERMINUSDB_STORE",
                     "SCIWEAVE_MAPPING_TERMINUSDB_USERNAME", "SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD"):
            if not os.environ.get(name):
                self.fail(f"integration configuration missing: {name}")
        self.bootstrap = os.environ.get("SCIWEAVE_COORDINATOR_KAFKA_BOOTSTRAP", "127.0.0.1:19092")

    def test_governance_event_drives_handoff_publish(self) -> None:
        base_url = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_URL"].rstrip("/")
        store_id = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_STORE"]
        username = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_USERNAME"]
        password = os.environ["SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD"]
        database = "sciweave_coord_e2e_" + uuid.uuid4().hex[:10]
        bot = _HttpBasic(username, password)

        # --- 1. temporary database + schema + seed route T1 -> T2 ---
        status, body = bot.at(f"{base_url}/api/db/{store_id}/{database}",
                              method="POST", payload={"label": "coordinator e2e"})
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
            f"{base_url}/api/document/{store_id}/{database}?graph_type=schema&author=e2e&message=schema",
            method="POST", payload=schema,
        )
        self.assertEqual(status, 200, f"schema failed: {body!r}")
        domain = "coordinator-e2e"
        nodes = [
            _task_node(version_id="t1-v1", title="T1", domain=domain, logical_id="T1", owner="owner-1"),
            _task_node(version_id="t2-v1", title="T2", domain=domain, logical_id="T2", owner="owner-1"),
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
            f"{base_url}/api/document/{store_id}/{database}?author=e2e&message=seed",
            method="POST", payload=nodes + edges,
        )
        self.assertEqual(status, 200, f"seed failed: {body!r}")
        status, body = bot.at(f"{base_url}/api/log/{store_id}/{database}/local/branch/main?count=1")
        self.assertEqual(status, 200)
        base_commit = json.loads(body.decode())[0]["identifier"]

        # --- 2. research-map management MCP over real services ---
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
            sqlite = SqliteStore(os.path.join(tmp, "coordinator-e2e.sqlite"))
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
            management = MappingManagementService(
                formal_query=formal, candidate_service=candidate,
                caller_capabilities={"reader": frozenset({"read"}), "owner": frozenset({"read", "centre"})},
                review_service=review, formalization_service=formalizer,
                sqlite_store=sqlite,
            )
            server = create_management_mcp_server(
                management, host="127.0.0.1", port=0,
                tokens={"tok-reader": "reader"},
            )
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                self._run_chain(domain, formal_revision_id, f"http://127.0.0.1:{port}/mcp")
            finally:
                server.shutdown()
                server.server_close()

    def _run_chain(self, domain: str, formal_revision_id: str, mcp_endpoint: str) -> None:
        # coordinator real adapters (snapshot via real MCP, handoff via real Redpanda)
        snapshot_port = ResearchMapMcpSnapshotPort(endpoint=mcp_endpoint, token="tok-reader")
        publisher = KafkaHandoffPublisher(self.bootstrap)
        notifications = _NoopNotifications()
        agents = _StubRegistry({"agent-t1"})  # T1's executor refs = agent-t1, online
        store = CoordinatorStore(__import__("sqlite3").connect(":memory:"))
        service = CoordinatorService(store, snapshot_port, publisher, notifications, agents)

        consumer = KafkaGovernanceEventConsumer(
            self.bootstrap,
            f"coord-e2e-{uuid.uuid4().hex[:8]}",
        )
        try:
            router = GovernanceEventConsumer(service)

            # --- 3. publish formal_revision_published on real Redpanda ---
            from kafka import KafkaProducer

            producer = KafkaProducer(
                bootstrap_servers=self.bootstrap,
                value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
            )
            envelope = {
                "event_id": "e2e-" + uuid.uuid4().hex,
                "event_type": "formal_revision_published",
                "schema_version": "1",
                "mapping_domain_id": domain,
                "occurred_at": "2026-10-26T00:00:00Z",
                "dedupe_key": f"{domain}:{formal_revision_id}",
                "target": {"kind": "formal_revision", "id": formal_revision_id},
                "payload": {"formal_revision_id": formal_revision_id, "domain": "mapping"},
            }
            producer.send("sciweave.governance-events", key=None, value=envelope).get(timeout=10)
            producer.close()

            # --- 4. coordinator consumes and dispatches ---
            # A fresh group with earliest re-reads governance events left by
            # earlier runs; only the envelope for the current revision counts.
            handled = 0
            deadline = time.time() + 30
            while time.time() < deadline and handled == 0:
                for record in consumer.poll(timeout_ms=500):
                    event = router.handle(record)
                    if event is not None and event.formal_revision_id == formal_revision_id:
                        handled += 1
                        consumer.commit()
                        break
                time.sleep(0.2)
            self.assertEqual(handled, 1, "formal_revision_published was not consumed")

            # --- 4b. root node T1 is never auto-dispatched; PO triggers it ---
            # (ai4-te1v: zero-inbound nodes only via dispatch_root_task). The
            # coordinator's on_formal_revision_published still recorded the
            # latest revision; now dispatch the root explicitly.
            service.store.set_latest_revision(domain, formal_revision_id)
            self.assertTrue(
                service.dispatch_root_task(domain, "T1", "t1-v1", trigger_revision_id=formal_revision_id),
                "dispatch_root_task failed",
            )

            # --- 5. a plain kafka consumer reads task_handoff_ready back ---
            from kafka import KafkaConsumer as KC

            listener = KC(
                bootstrap_servers=self.bootstrap,
                group_id="coord-e2e-listener-" + uuid.uuid4().hex[:8],
                auto_offset_reset="earliest",
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            )
            topic = "sciweave.task-handoff.agent-t1"
            listener.subscribe([topic])
            seen = False
            deadline = time.time() + 30
            while time.time() < deadline and not seen:
                for records in listener.poll(timeout_ms=500).values():
                    for record in records:
                        value = record.value or {}
                        # Ignore envelopes left by earlier runs on the same
                        # broker: only the handoff for the current revision
                        # counts as evidence.
                        if value.get("trigger_revision_id") != formal_revision_id:
                            continue
                        self.assertEqual(value.get("message_type"), "task_handoff_ready")
                        self.assertEqual(value.get("task_node_id"), "T1")
                        self.assertEqual(value.get("target_agent_id"), "agent-t1")
                        seen = True
                time.sleep(0.2)
            listener.close()
            self.assertTrue(seen, f"no task_handoff_ready observed on {topic}")
        finally:
            consumer.close()
            publisher.close()


class _NoopNotifications:
    def publish(self, intent) -> None:
        return


class _StubRegistry:
    def __init__(self, online: set[str]) -> None:
        self.online = online

    def state_of(self, agent_id: str) -> AgentState:
        # Ids the stub does not know are registered-but-offline: the e2e path
        # only cares that they cannot take work.
        return AgentState.AVAILABLE if agent_id in self.online else AgentState.UNAVAILABLE


if __name__ == "__main__":
    unittest.main()