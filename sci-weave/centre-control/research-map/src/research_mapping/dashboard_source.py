from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping

from .formal_query import FormalQueryService

KNOWN_TASK_STATUSES = {"queued", "running", "waiting", "succeeded", "revision_required", "cancelled", "failed", "result_unknown", "unknown"}

# Mapping from the execution store's terminal statuses to dashboard task statuses.
_EXECUTION_STATUS_MAP = {
    "completed": "succeeded",
    "running": "running",
    "queued": "queued",
    "waiting": "waiting",
    "failed": "failed",
    "cancelled": "cancelled",
    "needs_revision": "revision_required",
    "rejected": "failed",
    "human_takeover": "waiting",
    "result_unknown": "result_unknown",
}


class ExecutionStatusResolver:
    """Read-only projection of execution facts onto mapping task statuses (B7).

    The mapping dashboard's only status source used to be the task-node
    document's own ``execution_status``/``task_status``/``status`` field, which
    nothing ever writes, so every task showed ``unknown`` even after execution
    finished. This resolver derives a task's status from the gateway
    ``execution_records`` table (the same source the queue dashboard reads),
    keyed by ``(mapping_domain_id, task_node_version_ref)`` parsed from the
    execution ``business_key``. It only *reads*; the formal mapping stays
    immutable.
    """

    def __init__(self, sqlite_path: str) -> None:
        self.sqlite_path = sqlite_path
        self._cache: dict[tuple[str, str], str] | None = None

    def _load(self) -> dict[tuple[str, str], str]:
        # Build once per fragment read; the table is small and the dashboard is
        # polled, so a per-request snapshot keeps it simple and consistent.
        result: dict[tuple[str, str], str] = {}
        try:
            connection = sqlite3.connect(f"file:{self.sqlite_path}?mode=ro", uri=True)
        except sqlite3.Error:
            return result
        try:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT task_node_id, business_key, mapping_domain_id, status
                   FROM execution_records"""
            ).fetchall()
        except sqlite3.Error:
            return result
        finally:
            connection.close()
        for row in rows:
            version_ref = _version_ref_from_business_key(row["business_key"])
            mapped = _EXECUTION_STATUS_MAP.get(str(row["status"]))
            if mapped is None or not version_ref:
                continue
            for key in _candidate_keys(row["mapping_domain_id"], row["task_node_id"], version_ref):
                # Later rows (newer executions) win, matching list ordering intent.
                result[key] = mapped
        return result

    def lookup(self, *, mapping_domain_id: str | None, task_node_id: str, version_ref: str) -> str | None:
        if self._cache is None:
            self._cache = self._load()
        for key in _candidate_keys(mapping_domain_id, task_node_id, version_ref):
            if key in self._cache:
                return self._cache[key]
        return None


def _version_ref_from_business_key(business_key: object) -> str:
    text = _text(business_key)
    if not text:
        return ""
    parts = text.split(":", 3)
    return parts[1] if len(parts) > 1 else ""


def _candidate_keys(mapping_domain_id: object, task_node_id: object, version_ref: object) -> list[tuple[str, str]]:
    node = str(task_node_id or "")
    version = str(version_ref or "")
    domain = str(mapping_domain_id or "")
    return [(domain, f"{node}:{version}"), ("", f"{node}:{version}")]


def build_mapping_fragment(
    result: Any,
    *,
    observed_at: str | None = None,
    execution_status_resolver: "ExecutionStatusResolver | None" = None,
) -> dict[str, object]:
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

    tasks = [
        _task_projection(
            node,
            prerequisites.get(_document_id(node), []),
            execution_status_resolver=execution_status_resolver,
            mapping_domain_id=str(getattr(result, "mapping_domain_id", "mapping")) or "mapping",
        )
        for node in nodes
    ]
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


def _task_projection(
    document: Mapping[str, Any],
    prerequisite_ids: list[str],
    *,
    execution_status_resolver: "ExecutionStatusResolver | None" = None,
    mapping_domain_id: str | None = None,
) -> dict[str, object]:
    task_id = _document_id(document)
    status = _task_status(
        document,
        execution_status_resolver=execution_status_resolver,
        mapping_domain_id=mapping_domain_id,
    )
    updated_at = _text(document.get("updated_at") or document.get("published_at") or document.get("created_at")) or _utc_now()
    # ai4-fnzt: the dashboard shows "TASK NODE · <id>" and, without a separate
    # logical id, that surfaced the immutable version id (e.g. ``v1``). Keep
    # ``id`` as the unique node id (routing/dependencies key off it) but also
    # expose the stable ``logicalId`` so the UI can label the logical task.
    logical_id = _text(document.get("logical_id")) or task_id
    return {
        "id": task_id,
        "logicalId": logical_id,
        "projectId": _text(document.get("mapping_domain_id")) or "mapping",
        "name": _text(document.get("title") or document.get("logical_id")) or task_id,
        "status": status,
        "owner": _text(document.get("task_owner_id") or document.get("owner_id")) or "未指定",
        "prerequisiteIds": prerequisite_ids,
        "blockingReason": _text(document.get("blocking_reason")),
        "updatedAt": updated_at,
        "attentionRank": 1 if status in {"failed", "result_unknown"} else 0,
    }


def _task_status(
    document: Mapping[str, Any],
    *,
    execution_status_resolver: "ExecutionStatusResolver | None" = None,
    mapping_domain_id: str | None = None,
) -> str:
    raw = _text(document.get("execution_status") or document.get("task_status") or document.get("status"))
    if raw in KNOWN_TASK_STATUSES:
        return raw
    if raw in {"complete", "completed", "formal"}:
        return "succeeded"
    # B7 fallback: the node document carries no status (nothing writes it), so
    # derive it from the execution fact when a resolver is configured.
    if execution_status_resolver is not None:
        version_ref = _text(document.get("version_id") or document.get("logical_id")) or ""
        derived = execution_status_resolver.lookup(
            mapping_domain_id=mapping_domain_id,
            task_node_id=_text(document.get("logical_id")) or _document_id(document),
            version_ref=version_ref,
        )
        if derived is not None:
            return derived
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
            resolver: ExecutionStatusResolver | None = getattr(self.server, "execution_status_resolver", None)
            self._send(HTTPStatus.OK, build_mapping_fragment(result, execution_status_resolver=resolver))
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


def create_mapping_dashboard_server(query_current: Callable[[], Any], *, host: str, port: int, token: str | None = None, execution_status_resolver: ExecutionStatusResolver | None = None) -> MappingDashboardServer:
    server = MappingDashboardServer((host, port), _MappingDashboardHandler)
    server.query_current = query_current  # type: ignore[attr-defined]
    server.dashboard_token = token  # type: ignore[attr-defined]
    server.execution_status_resolver = execution_status_resolver  # type: ignore[attr-defined]
    return server


def run_mapping_dashboard_from_environment(service: FormalQueryService, domain_id: str) -> int:
    host = os.environ.get("SCIWEAVE_MAPPING_DASHBOARD_HOST", "").strip()
    port_text = os.environ.get("SCIWEAVE_MAPPING_DASHBOARD_PORT", "").strip()
    if not host or not port_text:
        raise RuntimeError("SCIWEAVE_MAPPING_DASHBOARD_HOST and SCIWEAVE_MAPPING_DASHBOARD_PORT are required")
    port = int(port_text)
    token = os.environ.get("SCIWEAVE_MAPPING_DASHBOARD_TOKEN") or None
    # B7: opt-in projection of execution facts onto task status. Point this at
    # the gateway execution SQLite DB (SCIWEAVE_GATEWAY_DB) so finished tasks
    # read as succeeded instead of a permanent unknown.
    execution_db = os.environ.get("SCIWEAVE_MAPPING_EXECUTION_DB", "").strip()
    resolver = ExecutionStatusResolver(execution_db) if execution_db else None
    server = create_mapping_dashboard_server(
        lambda: service.get_current(domain_id),
        host=host,
        port=port,
        token=token,
        execution_status_resolver=resolver,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0
