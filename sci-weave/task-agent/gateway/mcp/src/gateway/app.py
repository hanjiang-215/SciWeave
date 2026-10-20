"""Gateway MCP v1 application and the minimal loopback health seam."""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .runtime import RuntimeAdapter, RuntimeOutcome, RuntimeRequest, TestRuntimeAdapter
from .store import ExecutionStore, utc_now

API_VERSION = "v1"
MCP_PROTOCOL_VERSION = "2025-03-26"


class GatewayApplication:
    def __init__(self, store: ExecutionStore, token: str, caller_id: str):
        self.store = store
        self.token = token
        self.caller_id = caller_id
        self.test_runtime_enabled = False
        self.runtime: RuntimeAdapter | None = None

    def enable_test_runtime(self, outcome: str = "success") -> None:
        self.test_runtime_enabled = True
        self.test_runtime_outcome = outcome
        self.runtime = TestRuntimeAdapter(outcome)

    def set_runtime(self, runtime: RuntimeAdapter) -> None:
        self.runtime = runtime
        self.test_runtime_enabled = True

    def authorize(self, supplied: str | None) -> bool:
        return bool(supplied) and secrets.compare_digest(supplied, self.token)

    def submit_owner_command(
        self, task_node_id: str, command_text: str, idempotency_key: str
    ) -> dict[str, Any]:
        command_id = str(uuid.uuid4())
        execution_id = str(uuid.uuid4())
        session_id = f"task_{task_node_id}_{uuid.uuid4().hex}"
        now = utc_now()
        with self.store.transaction() as connection:
            existing = connection.execute(
                "SELECT command_id FROM owner_commands WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                execution = connection.execute(
                    """
                    SELECT e.execution_id, e.task_node_id, e.session_id, e.status AS execution_status
                    FROM execution_records e WHERE e.command_id = ?
                    """,
                    (existing["command_id"],),
                ).fetchone()
                if execution is None:
                    raise RuntimeError("execution record missing for persisted command")
                return {**dict(execution), "command_id": existing["command_id"], "duplicate": True}

            session = connection.execute(
                "SELECT session_id FROM task_sessions WHERE task_node_id = ?", (task_node_id,)
            ).fetchone()
            if session is None:
                connection.execute(
                    "INSERT INTO task_sessions VALUES (?, ?, ?, ?)",
                    (task_node_id, session_id, now, now),
                )
            else:
                session_id = session["session_id"]
            connection.execute(
                "INSERT OR IGNORE INTO callers VALUES (?, ?)", (self.caller_id, now)
            )
            connection.execute(
                "INSERT INTO owner_commands VALUES (?, ?, ?, ?, ?, ?)",
                (command_id, task_node_id, self.caller_id, idempotency_key, command_text, now),
            )
            connection.execute(
                """INSERT INTO execution_records
                   (execution_id, command_id, task_node_id, session_id, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (execution_id, command_id, task_node_id, session_id, "queued", now, now),
            )
            self._audit(connection, "owner_command_received", task_node_id, command_id, execution_id, now)
            self._audit(connection, "execution_queued", task_node_id, command_id, execution_id, now)
        if self.test_runtime_enabled:
            threading.Thread(target=self._run_test_worker, args=(execution_id,), daemon=True).start()
        return {
            "command_id": command_id,
            "execution_id": execution_id,
            "task_node_id": task_node_id,
            "session_id": session_id,
            "execution_status": "queued",
            "duplicate": False,
        }

    def _run_test_worker(self, execution_id: str) -> None:
        now = utc_now()
        with self.store.transaction() as connection:
            execution = connection.execute(
                "SELECT execution_id, task_node_id, session_id, command_id FROM execution_records WHERE execution_id = ? AND status = 'queued'",
                (execution_id,),
            ).fetchone()
            if execution is None:
                return
            try:
                connection.execute(
                    "INSERT INTO worker_leases VALUES (?, ?, ?)",
                    (execution["task_node_id"], execution_id, now),
                )
            except sqlite3.IntegrityError:
                return
            connection.execute(
                "UPDATE execution_records SET status = 'running', started_at = ?, updated_at = ? WHERE execution_id = ?",
                (now, now, execution_id),
            )
            self._audit(connection, "worker_lease_acquired", execution["task_node_id"], execution["command_id"], execution_id, now)
        request = RuntimeRequest(
            execution_id=execution_id,
            task_node_id=execution["task_node_id"],
            session_id=execution["session_id"],
        )
        outcome = self.runtime.run(request) if self.runtime is not None else RuntimeOutcome("failed", error_summary="runtime_not_configured")
        finished_at = utc_now()
        status = outcome.status
        result_summary = outcome.result_summary
        error_summary = outcome.error_summary
        event_type = "worker_completed" if status == "awaiting_acceptance" else "worker_failed"
        with self.store.transaction() as connection:
            execution = connection.execute(
                "SELECT task_node_id, command_id FROM execution_records WHERE execution_id = ?", (execution_id,)
            ).fetchone()
            if execution is None:
                return
            connection.execute(
                """UPDATE execution_records SET status = ?, result_summary = ?, error_summary = ?,
                   finished_at = ?, updated_at = ? WHERE execution_id = ?""",
                (status, result_summary, error_summary, finished_at, finished_at, execution_id),
            )
            connection.execute("DELETE FROM worker_leases WHERE execution_id = ?", (execution_id,))
            self._audit(connection, event_type, execution["task_node_id"], execution["command_id"], execution_id, finished_at)
            self._audit(connection, "worker_lease_released", execution["task_node_id"], execution["command_id"], execution_id, finished_at)

    def query_execution(self, execution_id: str) -> dict[str, Any] | None:
        row = self.store.get_execution(execution_id)
        return dict(row) if row is not None else None

    def health(self) -> dict[str, Any]:
        storage = "ready" if self.store.health() else "unavailable"
        return {
            "status": "ready" if storage == "ready" else "unavailable",
            "gateway_api_version": API_VERSION,
            "components": {
                "mcp": "ready",
                "storage": storage,
                "ingest": "not_configured",
                "worker_runtime": "ready" if self.test_runtime_enabled else "not_configured",
            },
        }

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        event_type: str,
        task_node_id: str,
        command_id: str,
        execution_id: str,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events
                (event_type, task_node_id, command_id, execution_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_type, task_node_id, command_id, execution_id, "{}", now),
        )


def create_app(database: str, token: str, caller_id: str) -> GatewayApplication:
    return GatewayApplication(ExecutionStore(database), token, caller_id)


def make_handler(app: GatewayApplication):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            header = self.headers.get("Authorization", "")
            token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else None
            return app.authorize(token)

        def _json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("request body must be a JSON object")
            return body

        def do_GET(self) -> None:
            if self.path != "/health":
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                health = app.health()
                self._send(
                    HTTPStatus.OK,
                    {"status": health["status"], "gateway_api_version": health["gateway_api_version"]},
                )
            except sqlite3.Error:
                self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "unavailable", "gateway_api_version": API_VERSION})

        def do_POST(self) -> None:
            if self.path != "/mcp":
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            if not self._authorized():
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            try:
                request = self._json()
            except (ValueError, json.JSONDecodeError):
                self._send(HTTPStatus.BAD_REQUEST, self._protocol_error(None, -32700, "parse error"))
                return
            self._send(HTTPStatus.OK, self._dispatch(request))

        def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
            request_id = request.get("id")
            if request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                return self._protocol_error(request_id, -32600, "invalid request")
            method = request["method"]
            params = request.get("params", {})
            if not isinstance(params, dict):
                return self._protocol_error(request_id, -32602, "invalid params")
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "sciweave-task-agent-gateway", "version": API_VERSION},
                    },
                }
            if method == "tools/list":
                return self._result(request_id, {"tools": self._tools()})
            if method == "tools/call":
                return self._call_tool(request_id, params)
            return self._protocol_error(request_id, -32601, "method not found")

        def _call_tool(self, request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return self._protocol_error(request_id, -32602, "invalid params")
            try:
                if name == "submit_owner_command":
                    result = app.submit_owner_command(
                        self._required_string(arguments, "task_node_id"),
                        self._required_string(arguments, "command"),
                        self._required_string(arguments, "idempotency_key"),
                    )
                    return self._tool_result(request_id, result)
                if name == "query_execution":
                    result = app.query_execution(self._required_string(arguments, "execution_id"))
                    if result is None:
                        return self._tool_error(request_id, "not_found", "execution was not found")
                    return self._tool_result(request_id, result)
                if name == "health":
                    return self._tool_result(request_id, app.health())
                return self._protocol_error(request_id, -32602, "unknown tool")
            except ValueError:
                return self._protocol_error(request_id, -32602, "invalid params")
            except sqlite3.Error:
                return self._tool_error(request_id, "unavailable", "storage is unavailable")
            except Exception:
                return self._tool_error(request_id, "internal", "internal gateway error")

        @staticmethod
        def _required_string(arguments: dict[str, Any], name: str) -> str:
            value = arguments.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(name)
            return value.strip()

        @staticmethod
        def _tools() -> list[dict[str, Any]]:
            return [
                {"name": "submit_owner_command", "description": "Submit a durable owner command."},
                {"name": "query_execution", "description": "Query one execution."},
                {"name": "health", "description": "Read authenticated gateway health."},
            ]

        @staticmethod
        def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        def _tool_result(self, request_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
            return self._result(request_id, {"content": [{"type": "text", "text": json.dumps(payload)}]})

        def _tool_error(self, request_id: Any, code: str, message: str) -> dict[str, Any]:
            return self._result(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps({"error": {"code": code, "message": message}})}],
                    "isError": True,
                },
            )

        @staticmethod
        def _protocol_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

        def log_message(self, *_: object) -> None:
            return

    return Handler


def serve(app: GatewayApplication, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(app))
    try:
        server.serve_forever()
    finally:
        server.server_close()
