from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping

from .management import ManagementCallOutcome, ManagementDenied, WikiManagementService

_MAX_BODY_BYTES = 1_000_000


class _WikiManagementHttpHandler(BaseHTTPRequestHandler):
    """Serve the Wiki management MCP over Streamable HTTP at POST /mcp.

    The caller identity is resolved from ``Authorization: Bearer <token>``
    against the configured token map and injected into every ``tools/call``.
    Server-side capability tiers are enforced by ``WikiManagementService``:
    an unauthenticated or unknown token receives HTTP 401, a caller without
    the required capability receives a stable ``forbidden`` result, and the
    body never leaks tokens or stack traces.
    """

    server_version = "SciWeaveWikiManagement/1"

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
        actor = self._authenticated_actor()
        if actor is None:
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > _MAX_BODY_BYTES:
            self._send(HTTPStatus.BAD_REQUEST if length <= 0 else HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid_payload" if length <= 0 else "payload_too_large"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse_error"}})
            return
        if isinstance(payload, list):
            responses = [_handle_single(self.server.service, item, actor) for item in payload]
            responses = [response for response in responses if response is not None]
            if not responses:
                self.send_response(HTTPStatus.ACCEPTED)
                self.end_headers()
                return
            self._send(HTTPStatus.OK, responses)
            return
        response = _handle_single(self.server.service, payload, actor)  # type: ignore[attr-defined]
        if response is None:
            self.send_response(HTTPStatus.ACCEPTED)
            self.end_headers()
            return
        self._send(HTTPStatus.OK, response)

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def _authenticated_actor(self) -> str | None:
        header = self.headers.get("Authorization") or ""
        scheme, separator, token = header.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token.strip():
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized", "message": "missing bearer token"})
            return None
        actor = self.server.tokens.get(token.strip())  # type: ignore[attr-defined]
        if actor is None:
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized", "message": "unknown bearer token"})
            return None
        return actor

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


def _handle_single(service: WikiManagementService, request: Any, actor: str) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid_request"}}
    request_id = request.get("id")
    method = request.get("method")
    if isinstance(method, str) and method.startswith("notifications/"):
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "sciweave-wiki-management", "version": "0.1.0"},
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        from .management import TOOL_DEFINITIONS
        available = {tool["name"] for tool in TOOL_DEFINITIONS if tool["name"] in service._handlers()}
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": [tool for tool in TOOL_DEFINITIONS if tool["name"] in available]}}
    if method == "tools/call":
        params = request.get("params") or {}
        tool = params.get("name", "")
        arguments = dict((params.get("arguments") or {}))
        try:
            outcome = service.call_tool(tool, arguments, actor_id=actor)
        except ManagementDenied:
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": json.dumps({"code": "forbidden"}, ensure_ascii=False)}],
                "isError": True,
            }}
        except (TypeError, ValueError) as error:
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": json.dumps({"code": "invalid_arguments", "message": str(error)}, ensure_ascii=False)}],
                "isError": True,
            }}
        if outcome.status == "ok" and outcome.result is not None:
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": json.dumps(outcome.result, ensure_ascii=False)}],
                "structuredContent": outcome.result,
                "isError": False,
            }}
        code = outcome.reason_code or outcome.error_code or "internal"
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "content": [{"type": "text", "text": json.dumps({"code": code, "message": code}, ensure_ascii=False)}],
            "isError": True,
        }}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method_not_found"}}


class WikiManagementMcpServer(ThreadingHTTPServer):
    allow_reuse_address = True


def create_wiki_management_mcp_server(
    service: WikiManagementService,
    *,
    host: str,
    port: int,
    tokens: Mapping[str, str],
) -> WikiManagementMcpServer:
    server = WikiManagementMcpServer((host, port), _WikiManagementHttpHandler)
    server.service = service  # type: ignore[attr-defined]
    server.tokens = dict(tokens)  # type: ignore[attr-defined]
    return server


def run_wiki_management_server_from_config(config, service: WikiManagementService) -> int:
    if config.mcp_host is None or config.mcp_port is None:
        raise ValueError("SCIWEAVE_WIKI_MCP_HOST and SCIWEAVE_WIKI_MCP_PORT are required for the management endpoint")
    if not config.mcp_tokens:
        raise ValueError("SCIWEAVE_WIKI_MCP_TOKENS_JSON is required; an unauthenticated management endpoint is not allowed")
    server = create_wiki_management_mcp_server(service, host=config.mcp_host, port=config.mcp_port, tokens=config.mcp_tokens)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0