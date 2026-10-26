"""Researcher-side disposition MCP (ai4-58d0).

The six tools the work-agent flow documents: ``health``, ``query_execution``,
``list_pending``, ``cancel_execution``, ``answer_question`` and
``review_execution``. They act on the durable execution store, so the surface
runs in its own process and still sees what the subscriber executed.

Every tool takes no actor argument: the bearer token is the caller's identity
and the store records nothing about who asked. That is deliberate for this
version -- the researcher-side deployment is single-tenant per agent id.
"""

from __future__ import annotations

import json
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from .durable import ExecutionNotFound, InvalidTransition, SqliteExecutionStore

_MAX_BODY_BYTES = 1 << 20


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "required": required,
            "properties": properties,
            "additionalProperties": False,
        },
    }


_ID = {"type": "string"}
TOOLS = [
    _tool(
        "health",
        "Report whether the disposition surface and its execution store are usable.",
        {},
        [],
    ),
    _tool(
        "query_execution",
        "Read one execution: status, draft id, error code and failed agent.",
        {"execution_id": _ID},
        ["execution_id"],
    ),
    _tool(
        "list_pending",
        "List executions that still need a human: queued, running or waiting for an answer.",
        {},
        [],
    ),
    _tool(
        "cancel_execution",
        "Cancel a queued, running or waiting execution. A finished execution keeps its status.",
        {"execution_id": _ID},
        ["execution_id"],
    ),
    _tool(
        "answer_question",
        "Answer a pending question and put its execution back in the queue.",
        {"question_id": _ID, "answer": {"type": "string"}},
        ["question_id", "answer"],
    ),
    _tool(
        "review_execution",
        "Record an append-only review decision (accepted or rejected) on a finished execution.",
        {
            "execution_id": _ID,
            "decision": {"type": "string", "enum": ["accepted", "rejected"]},
            "reason": {"type": "string"},
        },
        ["execution_id", "decision", "reason"],
    ),
]


def _dispatch(store: SqliteExecutionStore, name: str, arguments: dict) -> dict:
    if name == "health":
        return {"status": "ready", "pending": len(store.list_pending())}
    if name == "query_execution":
        record = store.get(arguments["execution_id"])
        if record is None:
            raise ExecutionNotFound(arguments["execution_id"])
        return {
            "execution_id": record.execution_id,
            "target_id": record.target_id,
            "status": record.status,
            "draft_id": record.draft_id,
            "error_code": record.error_code,
            "failed_agent": record.failed_agent,
            "reviews": store.reviews(record.execution_id),
        }
    if name == "list_pending":
        return {"executions": store.list_pending()}
    if name == "cancel_execution":
        record = store.cancel(arguments["execution_id"])
        return {"execution_id": record.execution_id, "status": record.status}
    if name == "answer_question":
        return store.answer(arguments["question_id"], arguments["answer"])
    if name == "review_execution":
        return store.review(
            arguments["execution_id"], arguments["decision"], arguments["reason"]
        )
    raise KeyError(name)


_HANDLERS: dict[str, Callable[[SqliteExecutionStore, dict], dict]] = {
    tool["name"]: _dispatch for tool in TOOLS
}


def _handle_single(store: SqliteExecutionStore, request: Any) -> dict[str, Any] | None:
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
                "serverInfo": {"name": "sciweave-task-agent-disposition", "version": "0.1.0"},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method != "tools/call":
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method_not_found"}}
    params = request.get("params") or {}
    if not isinstance(params, dict) or params.get("name") not in _HANDLERS:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "unknown tool"}}
    name = params["name"]
    arguments = params.get("arguments") or {}
    schema = next(tool["inputSchema"] for tool in TOOLS if tool["name"] == name)
    if not isinstance(arguments, dict) or any(
        not isinstance(arguments.get(field), str) or not arguments.get(field, "").strip()
        for field in schema["required"]
    ):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "invalid params"}}
    try:
        payload = _dispatch(store, name, arguments)
    except ExecutionNotFound:
        payload = {"status": "not_found"}
    except InvalidTransition as error:
        payload = {"status": "invalid_transition", "message": str(error)}
    except ValueError as error:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(error)}}
    except Exception:
        payload = {"status": "failed", "reason_code": "store_unavailable"}
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]},
    }


class _DispositionHttpHandler(BaseHTTPRequestHandler):
    """Serve the disposition MCP over Streamable HTTP at POST /mcp."""

    server_version = "SciWeaveTaskAgentDisposition/1"

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
            responses = [
                item
                for item in (_handle_single(self.server.store, request) for request in payload)  # type: ignore[attr-defined]
                if item
            ]
            if not responses:
                self.send_response(HTTPStatus.ACCEPTED)
                self.end_headers()
                return
            self._send(HTTPStatus.OK, responses)
            return
        response = _handle_single(self.server.store, payload)  # type: ignore[attr-defined]
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


class DispositionMcpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], store: SqliteExecutionStore, token: str) -> None:
        super().__init__(address, _DispositionHttpHandler)
        self.store = store
        self.token = token


def create_disposition_server(
    host: str, port: int, store: SqliteExecutionStore, token: str
) -> DispositionMcpServer:
    if not token:
        raise ValueError("a disposition MCP token is required")
    return DispositionMcpServer((host, port), store, token)
