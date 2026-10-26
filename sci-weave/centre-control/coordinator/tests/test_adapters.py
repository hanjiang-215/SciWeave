"""Adapter tests for the handoff coordinator (ai4-1y6q / ai4-zc85)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from coordinator.adapter_email import EmailMcpNotificationPublisher
from coordinator.adapter_publisher import KafkaHandoffPublisher
from coordinator.adapter_registry import RegistryMcpAvailabilityPort
from coordinator.adapter_snapshot import ResearchMapMcpSnapshotPort
from coordinator.ports import (
    DependencyEdgeDoc,
    FormalSnapshot,
    HandoffReadyMessage,
    NoSuchRevisionError,
    NotificationIntent,
    SnapshotInconsistentError,
    SnapshotUnavailableError,
    TaskNodeDoc,
)


class McpStub:
    """In-process Streamable HTTP MCP stub that records tools/call requests.

    ``responses`` maps tool name to either a callable(payload)->dict (result
    payload) or an Exception to raise as the HTTP body. Not-yet-configured
    tools fall back to a bare ``{"result": {}}`` envelope.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses: dict[str, Any] = {}
        self.http_errors: dict[str, int] = {}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def endpoint(self) -> str:
        host, port = self._server.server_address[:2]  # type: ignore[union-attr]
        return f"http://{host}:{port}/mcp"

    def __enter__(self) -> "McpStub":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()  # type: ignore[union-attr]
        self._server.server_close()  # type: ignore[union-attr]
        if self._thread:
            self._thread.join(timeout=5)


def _make_handler(stub: McpStub):
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            method = payload.get("method")
            if method == "initialize":
                body = json.dumps(
                    {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"protocolVersion": "2025-03-26"}}
                ).encode()
                self._reply(200, body)
                return
            if method == "tools/call":
                params = payload.get("params") or {}
                tool = params.get("name", "")
                stub.calls.append((tool, params.get("arguments") or {}))
                if tool in stub.http_errors:
                    self._reply(stub.http_errors[tool], b"{}")
                    return
                if tool in stub.responses:
                    handler = stub.responses[tool]
                    if isinstance(handler, Exception):
                        self._reply(200, json.dumps({"error": {"message": str(handler)}}).encode())
                        return
                    text = json.dumps(handler, ensure_ascii=False) if not isinstance(handler, str) else handler
                    body = json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": payload.get("id"),
                            "result": {"content": [{"type": "text", "text": text}]},
                        }
                    ).encode()
                    self._reply(200, body)
                    return
                self._reply(200, json.dumps({"jsonrpc": "2.0", "id": payload.get("id"), "result": {}}).encode())
                return
            self._reply(200, json.dumps({"jsonrpc": "2.0", "id": payload.get("id"), "result": {}}).encode())

        def _reply(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            return

    return _Handler


# ------------------------------------------------------------------ snapshot


def _mapping_documents() -> list[dict[str, Any]]:
    return [
        {
            "@type": "TaskNode",
            "@id": "TaskNode/t1-v1",
            "mapping_domain_id": "iris-demo",
            "logical_id": "T1",
            "version_id": "t1-v1",
            "title": "T1",
            "task_owner_id": "owner-1",
            "executor_refs": ["agent-1"],
        },
        {
            "@type": "TaskNode",
            "@id": "TaskNode/t2-v1",
            "mapping_domain_id": "iris-demo",
            "logical_id": "T2",
            "version_id": "t2-v1",
            "title": "T2",
            "task_owner_id": "owner-1",
            "executor_refs": ["agent-2"],
        },
        {
            "@type": "DependencyEdge",
            "@id": "DependencyEdge/e1-v1",
            "mapping_domain_id": "iris-demo",
            "logical_id": "E1",
            "version_id": "e1-v1",
            "dependency_kind": "blocking",
            "source_node_version_ref": {"logical_id": "T1", "version_id": "t1-v1", "mapping_domain_id": "iris-demo"},
            "target_node_version_ref": {"logical_id": "T2", "version_id": "t2-v1", "mapping_domain_id": "iris-demo"},
        },
    ]


def test_snapshot_adapter_reads_revision_and_projects_graph() -> None:
    with McpStub() as stub:
        stub.responses["get_formal_mapping_at_revision"] = {
            "status": "available",
            "reason_code": "ok",
            "mapping_domain_id": "iris-demo",
            "formal_revision_id": "rev-2",
            "documents": _mapping_documents(),
        }
        port = ResearchMapMcpSnapshotPort(endpoint=stub.endpoint, token="tok")
        snapshot = port.get_formal_mapping_at_revision("iris-demo", "rev-2")
        assert isinstance(snapshot, FormalSnapshot)
        assert snapshot.formal_revision_id == "rev-2"
        assert (tuple(n.task_node_id for n in snapshot.nodes)) == ("T1", "T2")
        assert snapshot.node_by_id("T1").executor_refs == ("agent-1",)
        assert snapshot.node_by_id("T2").task_owner_id == "owner-1"
        edge = snapshot.edges[0]
        assert isinstance(edge, DependencyEdgeDoc)
        assert edge.source_node_id == "T1"
        assert edge.source_version_id == "t1-v1"
        assert edge.target_node_id == "T2"
        # the correct tool was called with exact arguments
        assert ("get_formal_mapping_at_revision", {"mapping_domain_id": "iris-demo", "formal_revision_id": "rev-2"}) in stub.calls


def test_snapshot_adapter_maps_stable_errors() -> None:
    with McpStub() as stub:
        stub.responses["get_formal_mapping_at_revision"] = {"status": "no_such_revision", "reason_code": "revision_not_found"}
        port = ResearchMapMcpSnapshotPort(endpoint=stub.endpoint, token="tok")
        with pytest.raises(NoSuchRevisionError):
            port.get_formal_mapping_at_revision("iris-demo", "rev-missing")

        stub.responses["get_formal_mapping_at_revision"] = {"status": "inconsistent", "reason_code": "node_count_mismatch"}
        with pytest.raises(SnapshotInconsistentError):
            port.get_formal_mapping_at_revision("iris-demo", "rev-bad")

        stub.responses["get_formal_mapping_at_revision"] = {"status": "unavailable", "reason_code": "store_unavailable"}
        with pytest.raises(SnapshotUnavailableError):
            port.get_formal_mapping_at_revision("iris-demo", "rev-down")


def test_snapshot_adapter_unreachable_endpoint_raises_unavailable() -> None:
    port = ResearchMapMcpSnapshotPort(endpoint="http://127.0.0.1:1/mcp", token="tok", timeout_seconds=0.2)
    with pytest.raises(SnapshotUnavailableError):
        port.get_formal_mapping_at_revision("iris-demo", "rev-2")


# ------------------------------------------------------------------ registry


def test_registry_adapter_requires_active_and_online() -> None:
    with McpStub() as stub:
        stub.responses["get_agent_registration"] = {
            "agent_id": "agent-1",
            "status": "active",
            "agent_instances": [{"agent_instance_id": "i1", "runtime_status": "online"}],
        }
        port = RegistryMcpAvailabilityPort(endpoint=stub.endpoint, token="tok")
        assert port.is_available("agent-1") is True

        stub.responses["get_agent_registration"] = {
            "agent_id": "agent-1",
            "status": "active",
            "agent_instances": [{"agent_instance_id": "i1", "runtime_status": "offline"}],
        }
        assert port.is_available("agent-1") is False

        stub.responses["get_agent_registration"] = {
            "agent_id": "agent-1",
            "status": "revoked",
            "agent_instances": [{"agent_instance_id": "i1", "runtime_status": "online"}],
        }
        assert port.is_available("agent-1") is False


def test_registry_adapter_failures_are_conservative() -> None:
    with McpStub() as stub:
        stub.responses["get_agent_registration"] = RuntimeError("registry unavailable")
        port = RegistryMcpAvailabilityPort(endpoint=stub.endpoint, token="tok")
        assert port.is_available("agent-1") is False
    port = RegistryMcpAvailabilityPort(endpoint="http://127.0.0.1:1/mcp", token="tok", timeout_seconds=0.2)
    assert port.is_available("agent-1") is False


# ------------------------------------------------------------------ publisher


def test_kafka_publisher_builds_per_agent_topic() -> None:
    publisher = KafkaHandoffPublisher("127.0.0.1:9092")
    try:
        assert publisher._topic_for("agent-1") == "sciweave.task-handoff.agent-1"
        assert publisher._topic_for("") is None
        assert publisher._topic_for("  ") is None
    finally:
        publisher.close()


def test_email_publisher_requires_configured_endpoint() -> None:
    with pytest.raises(ValueError):
        EmailMcpNotificationPublisher(endpoint="", token="tok")
    with pytest.raises(ValueError):
        EmailMcpNotificationPublisher(endpoint="http://x/mcp", token="")


def test_email_publisher_submits_intent() -> None:
    with McpStub() as stub:
        stub.responses["send_notification"] = {"notification_id": "notification-1", "status": "accepted"}
        publisher = EmailMcpNotificationPublisher(endpoint=stub.endpoint, token="tok")
        publisher.publish(
            NotificationIntent(
                notification_kind="agent_unavailable",
                recipients=("principal-1",),
                subject="任务交接等待人工处理",
                body="TaskNode T1 的执行者不可用。",
                related={"mapping_domain_id": "iris-demo", "task_node_id": "T1"},
            )
        )
        names = [name for name, _ in stub.calls]
        assert "send_notification" in names
        args = stub.calls[names.index("send_notification")][1]
        assert args["notification_kind"] == "agent_unavailable"
        assert args["recipients"] == [{"principal_id": "principal-1"}]
        assert args["schema_version"] == "1"