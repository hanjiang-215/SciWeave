from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping

from .formal_query import FormalQueryService

KNOWN_TASK_STATUSES = {"queued", "running", "waiting", "succeeded", "revision_required", "cancelled", "failed", "result_unknown", "unknown"}


def build_mapping_fragment(result: Any, *, observed_at: str | None = None) -> dict[str, object]:
    observed_at = observed_at or _utc_now()
    if getattr(result, "status", None) != "available":
        return {
            "observedAt": observed_at,
            "sourceStatus": "unavailable",
            "projects": [],
            "tasks": [],
            "events": [],
        }

    documents = tuple(getattr(result, "documents", ()))
    nodes = [document for document in documents if _is_type(document, "TaskNode")]
    edges = [document for document in documents if _is_type(document, "DependencyEdge")]
    node_ids = {_document_id(node): node for node in nodes}
    prerequisites: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        source = _reference_id(edge.get("source_node_version_ref") or edge.get("source_node_ref") or edge.get("source"))
        target = _reference_id(edge.get("target_node_version_ref") or edge.get("target_node_ref") or edge.get("target"))
        if source and target and target in prerequisites and source in node_ids:
            prerequisites[target].append(source)

    tasks = [_task_projection(node, prerequisites.get(_document_id(node), [])) for node in nodes]
    completed = sum(task["status"] == "succeeded" for task in tasks)
    project_id = str(getattr(result, "mapping_domain_id", "mapping"))
    revision_id = getattr(result, "formal_revision_id", None)
    return {
        "observedAt": observed_at,
        "sourceStatus": "fresh",
        "projects": [{
            "id": project_id,
            "name": project_id,
            "routeId": str(revision_id or project_id),
            "completed": completed,
            "total": len(tasks),
            "attentionCount": sum(task["attentionRank"] > 0 for task in tasks),
        }],
        "tasks": tasks,
        "events": [{
            "id": f"formal-release:{revision_id or 'unknown'}",
            "type": "formal_release",
            "title": "Research Mapping 正式版本已发布",
            "occurredAt": observed_at,
            "diagnostic": f"formal_revision: {revision_id}" if revision_id else None,
        }],
    }


def _task_projection(document: Mapping[str, Any], prerequisite_ids: list[str]) -> dict[str, object]:
    task_id = _document_id(document)
    status = _task_status(document)
    updated_at = _text(document.get("updated_at") or document.get("published_at") or document.get("created_at")) or _utc_now()
    return {
        "id": task_id,
        "projectId": _text(document.get("mapping_domain_id")) or "mapping",
        "name": _text(document.get("title") or document.get("logical_id")) or task_id,
        "status": status,
        "owner": _text(document.get("task_owner_id") or document.get("owner_id")) or "未指定",
        "prerequisiteIds": prerequisite_ids,
        "blockingReason": _text(document.get("blocking_reason")),
        "updatedAt": updated_at,
        "attentionRank": 1 if status in {"failed", "result_unknown"} else 0,
    }


def _task_status(document: Mapping[str, Any]) -> str:
    raw = _text(document.get("execution_status") or document.get("task_status") or document.get("status"))
    if raw in KNOWN_TASK_STATUSES:
        return raw
    if raw in {"complete", "completed", "formal"}:
        return "succeeded"
    return "unknown"


def _document_id(document: Mapping[str, Any]) -> str:
    return _text(document.get("version_id") or document.get("logical_id") or document.get("@id")) or "unknown-task"


def _reference_id(value: object) -> str | None:
    if isinstance(value, Mapping):
        return _text(value.get("version_id") or value.get("logical_id") or value.get("@id"))
    return _text(value)


def _is_type(document: Mapping[str, Any], suffix: str) -> bool:
    return str(document.get("@type", "")).endswith(suffix)


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class _MappingDashboardHandler(BaseHTTPRequestHandler):
    server_version = "SciWeaveResearchMapping/1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(HTTPStatus.NO_CONTENT, None)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(HTTPStatus.OK, {"status": "ready", "api_version": "mapping-dashboard-v1"})
            return
        if self.path != "/api/dashboard/source/mapping":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        token = self.server.dashboard_token  # type: ignore[attr-defined]
        if token and self.headers.get("Authorization") != f"Bearer {token}":
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            result = self.server.query_current()  # type: ignore[attr-defined]
            self._send(HTTPStatus.OK, build_mapping_fragment(result))
        except Exception:
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "mapping_query_unavailable"})

    def do_POST(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

    def _send(self, status: HTTPStatus, payload: object) -> None:
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class MappingDashboardServer(ThreadingHTTPServer):
    allow_reuse_address = True


def create_mapping_dashboard_server(query_current: Callable[[], Any], *, host: str, port: int, token: str | None = None) -> MappingDashboardServer:
    server = MappingDashboardServer((host, port), _MappingDashboardHandler)
    server.query_current = query_current  # type: ignore[attr-defined]
    server.dashboard_token = token  # type: ignore[attr-defined]
    return server


def run_mapping_dashboard_from_environment(service: FormalQueryService, domain_id: str) -> int:
    host = os.environ.get("SCIWEAVE_MAPPING_DASHBOARD_HOST", "").strip()
    port_text = os.environ.get("SCIWEAVE_MAPPING_DASHBOARD_PORT", "").strip()
    if not host or not port_text:
        raise RuntimeError("SCIWEAVE_MAPPING_DASHBOARD_HOST and SCIWEAVE_MAPPING_DASHBOARD_PORT are required")
    port = int(port_text)
    token = os.environ.get("SCIWEAVE_MAPPING_DASHBOARD_TOKEN") or None
    server = create_mapping_dashboard_server(lambda: service.get_current(domain_id), host=host, port=port, token=token)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0
