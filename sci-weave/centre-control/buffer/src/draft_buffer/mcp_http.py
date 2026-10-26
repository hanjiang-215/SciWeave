from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping

from . import BufferError

_MAX_BODY_BYTES = 1_000_000


class _McpHttpHandler(BaseHTTPRequestHandler):
    """Serve MCP JSON-RPC requests over Streamable HTTP at POST /mcp.

    The endpoint is a single HTTP JSON-RPC entrypoint: ``initialize``,
    ``notifications/initialized``, ``ping``, ``tools/list`` and ``tools/call``
    are accepted at ``/mcp``. The caller identity is resolved from the
    ``Authorization: Bearer`` header against the configured token map and is
    injected into ``tools/call`` as ``_trusted_actor_id``; a client-supplied
    actor argument is never trusted. Unauthenticated or unknown tokens receive
    HTTP 401, and the response body never leaks tokens or stack traces.
    """

    server_version = "SciWeaveDraftBuffer/1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(HTTPStatus.NO_CONTENT, None)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        self._send(HTTPStatus.OK, {"status": "ready", "protocol": "mcp-streamable-http"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mcp":
            self._drain_body()
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
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse_error"}})
            return
        if isinstance(payload, list):
            responses: list[dict[str, Any]] = []
            for item in payload:
                response = _handle_single(self.server.dispatch, item, actor)  # type: ignore[attr-defined]
                if response is not None:
                    responses.append(response)
            if not responses:
                self.send_response(HTTPStatus.ACCEPTED)
                self.end_headers()
                return
            self._send(HTTPStatus.OK, responses)
            return
        response = _handle_single(self.server.dispatch, payload, actor)  # type: ignore[attr-defined]
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
            self._drain_body()
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized", "message": "missing bearer token"})
            return None
        actor = self.server.tokens.get(token.strip())  # type: ignore[attr-defined]
        if actor is None:
            self._drain_body()
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized", "message": "unknown bearer token"})
            return None
        return actor

    def _drain_body(self) -> None:
        """Consume the declared body before answering an early rejection.

        Rejecting before reading the body closes the socket while the client is
        still writing, which surfaces as a connection reset (WinError 10053)
        instead of the 401 the client is waiting for. The read is bounded by the
        same limit as a normal request so an unauthenticated caller cannot make
        the server buffer an unbounded body.
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


def _handle_single(dispatch: Callable[[Mapping[str, Any]], dict[str, Any]], request: Any, actor: str) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid_request"}}
    method = request.get("method")
    if isinstance(method, str) and method.startswith("notifications/"):
        dispatch(request)
        return None
    if method == "tools/call":
        cloned = dict(request)
        cloned["_trusted_actor_id"] = actor
        params = cloned.get("params")
        arguments = dict((params or {}).get("arguments") or {})
        arguments.pop("actor_id", None)
        cloned["params"] = dict(params or {})
        cloned["params"]["arguments"] = arguments
        return dispatch(cloned)
    return dispatch(request)


class McpHttpServer(ThreadingHTTPServer):
    allow_reuse_address = True


def create_mcp_server(dispatch: Callable[[Mapping[str, Any]], dict[str, Any]], *, host: str, port: int, tokens: Mapping[str, str]) -> McpHttpServer:
    server = McpHttpServer((host, port), _McpHttpHandler)
    server.dispatch = dispatch  # type: ignore[attr-defined]
    server.tokens = dict(tokens)  # type: ignore[attr-defined]
    return server


def run_mcp_server_from_config(config, dispatch: Callable[[Mapping[str, Any]], dict[str, Any]]) -> int:
    if config.mcp_host is None or config.mcp_port is None:
        raise BufferError("configuration_invalid", "SCIWEAVE_BUFFER_MCP_HOST and SCIWEAVE_BUFFER_MCP_PORT are required for the MCP endpoint")
    if not config.tokens:
        raise BufferError("configuration_invalid", "SCIWEAVE_BUFFER_MCP_TOKENS_JSON is required; an unauthenticated MCP endpoint is not allowed")
    server = create_mcp_server(dispatch, host=config.mcp_host, port=config.mcp_port, tokens=config.tokens)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0
