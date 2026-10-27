"""Read-only dashboard source for the queue / subscriber side.

``dashboard-api`` declares four source slots (mapping, wiki, gateway, queue) but
nothing served the ``queue`` slot, so the Web dashboard's "message listener"
area was permanently unavailable. This module is that source: it exposes the
subscriber's own view — which topics it consumes, under which consumer group,
whether the execution store is reachable, and the most recent queue events — and
never message bodies or credentials.

The payload shape follows ``sci-weave/centre-control/dashboard-api``: an
aggregated ``{observedAt, sourceStatus, services, events}`` fragment. Service
entries use ``name`` (not ``label``) and the ``role``/``status`` vocabularies the
front end validates, so the browser accepts the snapshot instead of rejecting it.

Only the standard library is used.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

# Front end accepts exactly these event types (web-ui `isDashboardEvent`).
EVENT_TYPES = {
    "message_received": "message_received",
    "execution_completed": "execution_completed",
    "execution_failed": "mcp_failure",
    "execution_queued": "message_received",
}

EVENT_TITLES = {
    "message_received": "收到交接消息并登记为待执行",
    "execution_completed": "执行完成并写入结果",
    "execution_failed": "执行失败，需要人工处置",
    "execution_queued": "执行已入队",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_queue_fragment(
    *,
    store: Any,
    topics: list[str],
    group_id: str | None,
    queue_kind: str,
    observed_at: str | None = None,
    event_limit: int = 20,
) -> dict[str, object]:
    """Project the subscriber's state into a dashboard source fragment."""
    observed_at = observed_at or _utc_now()
    healthy = False
    try:
        healthy = bool(store.health())
    except Exception:  # noqa: BLE001 - a broken store must degrade, not crash
        healthy = False

    status = "online" if healthy else "unavailable"
    services: list[dict[str, object]] = [
        {
            "id": "subscriber",
            "name": f"消息监听（{', '.join(topics)}）" if topics else "消息监听",
            "role": "centre-agent",
            "status": status,
        },
        {
            "id": "queue",
            "name": f"消息队列（{queue_kind}）",
            "role": "centre-agent",
            "status": status,
        },
    ]
    if group_id:
        services.append(
            {
                "id": "consumer-group",
                "name": f"消费组（{group_id}）",
                "role": "centre-agent",
                "status": status,
            }
        )

    events: list[dict[str, object]] = []
    if healthy:
        try:
            rows = store.list_recent_audit_events(limit=event_limit)
        except Exception:  # noqa: BLE001
            return {
                "observedAt": observed_at,
                "sourceStatus": "unavailable",
                "services": services,
                "events": [],
            }
        for row in rows or ():
            raw_type = str(row.get("event_type") or "")
            mapped = EVENT_TYPES.get(raw_type)
            if mapped is None:
                continue
            created_at = str(row.get("created_at") or observed_at)
            execution_id = str(row.get("execution_id") or "")
            task_node_id = str(row.get("task_node_id") or "")
            events.append(
                {
                    "id": f"queue:{raw_type}:{execution_id or task_node_id}:{created_at}",
                    "type": mapped,
                    "title": EVENT_TITLES.get(raw_type, raw_type),
                    "occurredAt": created_at,
                    "diagnostic": f"task {task_node_id}" if task_node_id else None,
                }
            )
    return {
        "observedAt": observed_at,
        "sourceStatus": "fresh" if healthy else "unavailable",
        "services": services,
        "events": events[:event_limit],
    }


class _QueueDashboardHandler(BaseHTTPRequestHandler):
    server_version = "SciWeaveQueueDashboard/1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(HTTPStatus.NO_CONTENT, None)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(HTTPStatus.OK, {"status": "ready", "api_version": "queue-dashboard-v1"})
            return
        if self.path not in ("/api/dashboard/source/queue", "/sources"):
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        token = self.server.dashboard_token  # type: ignore[attr-defined]
        if token and self.headers.get("Authorization") != f"Bearer {token}":
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            self._send(HTTPStatus.OK, self.server.build_fragment())  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "queue_dashboard_unavailable"})

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


class QueueDashboardServer(ThreadingHTTPServer):
    allow_reuse_address = True


def create_queue_dashboard_server(
    build_fragment: Callable[[], dict[str, object]],
    *,
    host: str,
    port: int,
    token: str | None = None,
) -> QueueDashboardServer:
    server = QueueDashboardServer((host, port), _QueueDashboardHandler)
    server.build_fragment = build_fragment  # type: ignore[attr-defined]
    server.dashboard_token = token  # type: ignore[attr-defined]
    return server
