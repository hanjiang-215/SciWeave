"""Minimal MCP surface for the handoff coordinator (ai4-nzmm).

Root nodes are never auto-dispatched on a formal-revision event: the project
owner starts them explicitly through ``dispatch_root_task``. Without an MCP
entry that method was only reachable from Python, so a first version had no way
to start a task graph at all.

Only one tool is exposed. Everything else the coordinator does is driven by
Kafka events, and a read/observe surface would duplicate the domain MCPs.
"""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http import HTTPStatus
from typing import Any

_MAX_BODY_BYTES = 1 << 20

DISPATCH_TOOL = {
    "name": "dispatch_root_task",
    "description": (
        "Explicitly dispatch one root task node of a mapping domain. Root nodes "
        "are never auto-dispatched, so this is how a task graph starts. The node "
        "must exist in the latest formal snapshot and have no inbound edges; the "
        "call is idempotent through the handoff dedupe key. Requires the "
        "coordinator MCP token."
    ),
    "inputSchema": {
        "type": "object",
        "required": [
            "mapping_domain_id",
            "task_node_id",
            "target_node_version_ref",
            "trigger_revision_id",
        ],
        "properties": {
            "mapping_domain_id": {"type": "string"},
            "task_node_id": {"type": "string"},
            "target_node_version_ref": {"type": "string"},
            "trigger_revision_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}

TOOLS = [DISPATCH_TOOL]


class _CoordinatorHttpHandler(BaseHTTPRequestHandler):
    """Serve the coordinator MCP over Streamable HTTP at POST /mcp."""

    server_version = "SciWeaveCoordinator/1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(HTTPStatus.NO_CONTENT, None)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        self._send(HTTPStatus.OK, {"status": "ready", "protocol": "mcp-streamable-http"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mcp":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not self._authorized():
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > _MAX_BODY_BYTES:
            self._send(
                HTTPStatus.BAD_REQUEST if length <= 0 else HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": "invalid_payload" if length <= 0 else "payload_too_large"},
            )
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(
                HTTPStatus.BAD_REQUEST,
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse_error"}},
            )
            return
        if isinstance(payload, list):
            responses = [item for item in (_handle_single(self.server.service, request) for request in payload) if item]
            if not responses:
                self.send_response(HTTPStatus.ACCEPTED)
                self.end_headers()
                return
            self._send(HTTPStatus.OK, responses)
            return
        response = _handle_single(self.server.service, payload)  # type: ignore[attr-defined]
        if response is None:
            self.send_response(HTTPStatus.ACCEPTED)
            self.end_headers()
            return
        self._send(HTTPStatus.OK, response)

    def do_PUT(self) -> None:  # noqa: N802
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

    def do_PATCH(self) -> None:  # noqa: N802
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

    def do_DELETE(self) -> None:  # noqa: N802
        self._send(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization") or ""
        scheme, separator, token = header.partition(" ")
        expected = self.server.token  # type: ignore[attr-defined]
        if (
            separator
            and scheme.lower() == "bearer"
            and token.strip()
            and secrets.compare_digest(token.strip(), expected)
        ):
            return True
        self._drain_body()
        self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized", "message": "invalid bearer token"})
        return False

    def _drain_body(self) -> None:
        """Read the declared body before an early rejection.

        Answering 401 without consuming the body closes the socket while the
        client is still writing, so the caller sees a connection reset instead
        of the rejection. The read is bounded like a normal request.
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if length <= 0 or length > _MAX_BODY_BYTES:
            return
        try:
            self.rfile.read(length)
        except OSError:
            return

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


def _handle_single(service: Any, request: Any) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid_request"}}
    request_id = request.get("id")
    method = request.get("method")
    if isinstance(method, str) and method.startswith("notifications/"):
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "sciweave-coordinator", "version": "0.1.0"},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method != "tools/call":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "method_not_found"},
        }
    params = request.get("params") or {}
    if not isinstance(params, dict) or params.get("name") != DISPATCH_TOOL["name"]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": "unknown tool"},
        }
    arguments = params.get("arguments") or {}
    required = DISPATCH_TOOL["inputSchema"]["required"]
    if not isinstance(arguments, dict) or any(
        not isinstance(arguments.get(name), str) or not arguments.get(name, "").strip()
        for name in required
    ):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": "invalid params"},
        }
    try:
        accepted = service.dispatch_root_task(
            arguments["mapping_domain_id"],
            arguments["task_node_id"],
            arguments["target_node_version_ref"],
            trigger_revision_id=arguments["trigger_revision_id"],
        )
    except Exception:
        result = {"status": "failed", "reason_code": "dispatch_failed", "accepted": False}
    else:
        result = {
            "status": "dispatched" if accepted else "not_dispatched",
            "reason_code": None if accepted else "dispatch_not_accepted",
            "accepted": bool(accepted),
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
    }


class CoordinatorMcpServer(ThreadingHTTPServer):
    """Threading HTTP server carrying the service and the expected token."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], service: Any, token: str) -> None:
        super().__init__(address, _CoordinatorHttpHandler)
        self.service = service
        self.token = token


def create_coordinator_mcp_server(
    host: str, port: int, service: Any, token: str
) -> CoordinatorMcpServer:
    if not token:
        raise ValueError("a coordinator MCP token is required")
    return CoordinatorMcpServer((host, port), service, token)


def start_in_background(server: CoordinatorMcpServer) -> threading.Thread:
    """Serve in a daemon thread so the Kafka loop keeps the process alive."""
    thread = threading.Thread(target=server.serve_forever, name="coordinator-mcp", daemon=True)
    thread.start()
    return thread
