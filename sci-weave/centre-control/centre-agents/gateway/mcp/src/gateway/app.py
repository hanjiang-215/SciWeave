"""Gateway MCP v1 application and the minimal loopback health seam."""

from __future__ import annotations

import json
import multiprocessing
import secrets
import sqlite3
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from task_agent_worker.config import WorkerSettings
from task_agent_worker.runtime import FastAgentDeepSeekRuntime, FastAgentPassthroughRuntime

from .runtime import RuntimeAdapter, RuntimeOutcome, RuntimeRequest, TestRuntimeAdapter
from .store import ExecutionStore, utc_now

API_VERSION = "v1"
MCP_PROTOCOL_VERSION = "2025-03-26"


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


def run_worker_process(database: str, execution_id: str, runtime: RuntimeAdapter) -> None:
    """Claim, execute, and release one durable Worker lease in a child process."""
    store = ExecutionStore(database)
    try:
        now = utc_now()
        with store.transaction() as connection:
            execution = connection.execute(
                "SELECT e.execution_id, e.task_node_id, e.session_id, e.command_id, e.resume_of, c.command_text "
                "FROM execution_records e JOIN owner_commands c ON c.command_id = e.command_id "
                "WHERE execution_id = ? AND status = 'queued'",
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
                "UPDATE execution_records SET status = 'running', started_at = ?, updated_at = ? "
                "WHERE execution_id = ?",
                (now, now, execution_id),
            )
            _audit(connection, "worker_lease_acquired", execution["task_node_id"], execution["command_id"], execution_id, now)
            _audit(connection, "worker_started", execution["task_node_id"], execution["command_id"], execution_id, now)

        request = RuntimeRequest(
            execution_id,
            execution["task_node_id"],
            execution["session_id"],
            execution["command_text"],
        )
        try:
            outcome = runtime.resume(request) if execution["resume_of"] else runtime.run(request)
        except TimeoutError:
            outcome = RuntimeOutcome("failed", error_summary="timeout")
        except Exception:
            outcome = RuntimeOutcome("failed", error_summary="exception")
        if outcome.status not in {"awaiting_acceptance", "waiting", "failed", "cancelled"}:
            outcome = RuntimeOutcome("failed", error_summary="invalid_runtime_outcome")

        finished_at = utc_now()
        event_type = {
            "awaiting_acceptance": "worker_completed",
            "waiting": "worker_waiting",
            "cancelled": "worker_cancelled",
            "failed": "worker_failed",
        }[outcome.status]
        with store.transaction() as connection:
            execution = connection.execute(
                "SELECT task_node_id, command_id FROM execution_records WHERE execution_id = ?", (execution_id,)
            ).fetchone()
            if execution is None:
                return
            connection.execute(
                """UPDATE execution_records SET status = ?, result_summary = ?, error_summary = ?,
                   pending_question = ?, finished_at = ?, updated_at = ? WHERE execution_id = ?""",
                (outcome.status, outcome.result_summary, outcome.error_summary,
                 outcome.result_summary if outcome.status == "waiting" else None,
                 finished_at, finished_at, execution_id),
            )
            connection.execute("DELETE FROM worker_leases WHERE execution_id = ?", (execution_id,))
            _audit(connection, event_type, execution["task_node_id"], execution["command_id"], execution_id, finished_at)
            _audit(connection, "worker_lease_released", execution["task_node_id"], execution["command_id"], execution_id, finished_at)
            next_execution = connection.execute(
                """SELECT execution_id FROM execution_records
                   WHERE task_node_id = ? AND status = 'queued'
                   ORDER BY created_at, execution_id LIMIT 1""",
                (execution["task_node_id"],),
            ).fetchone()
        if next_execution is not None:
            start_worker_process(database, next_execution["execution_id"], runtime)
    finally:
        store.close()


def start_worker_process(database: str, execution_id: str, runtime: RuntimeAdapter) -> None:
    """Start one independently exiting local Worker process."""
    process = multiprocessing.get_context("spawn").Process(
        target=run_worker_process, args=(database, execution_id, runtime)
    )
    process.start()


class GatewayApplication:
    def __init__(self, store: ExecutionStore, token: str, caller_id: str):
        self.store = store
        self.token = token
        self.caller_id = caller_id
        self.test_runtime_enabled = False
        self.runtime: RuntimeAdapter | None = None

    def enable_test_runtime(self, outcome: str = "success", duration_seconds: float = 0) -> None:
        self.test_runtime_enabled = True
        self.test_runtime_outcome = outcome
        self.runtime = TestRuntimeAdapter(outcome, duration_seconds)

    def enable_fast_agent_passthrough_runtime(
        self, home: str, connection_scope: str, session_dir: str
    ) -> None:
        """Use the credential-free fast-agent runtime for local integration validation."""
        self.set_runtime(FastAgentPassthroughRuntime(home, connection_scope, session_dir))

    def enable_fast_agent_deepseek_runtime(self, settings: WorkerSettings) -> None:
        """Use the configured DeepSeek API for one real fast-agent loop per Worker."""
        self.set_runtime(FastAgentDeepSeekRuntime(settings))

    def set_runtime(self, runtime: RuntimeAdapter) -> None:
        self.runtime = runtime
        self.test_runtime_enabled = True

    def authorize(self, supplied: str | None) -> bool:
        return bool(supplied) and secrets.compare_digest(supplied, self.token)

    def submit_owner_command(
        self, task_node_id: str, command_text: str, idempotency_key: str, resume_of: str | None = None
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

            resume_execution = None
            if resume_of is not None:
                resume_execution = connection.execute(
                    "SELECT task_node_id, session_id, status FROM execution_records WHERE execution_id = ?",
                    (resume_of,),
                ).fetchone()
                if resume_execution is None:
                    raise LookupError("resume execution missing")
                if resume_execution["status"] != "waiting" or resume_execution["task_node_id"] != task_node_id:
                    raise RuntimeError("invalid_state")
                session_id = resume_execution["session_id"]
            session = connection.execute(
                "SELECT session_id FROM task_sessions WHERE task_node_id = ?", (task_node_id,)
            ).fetchone()
            if session is None:
                connection.execute(
                    "INSERT INTO task_sessions VALUES (?, ?, ?, ?)",
                    (task_node_id, session_id, now, now),
                )
            elif resume_execution is None:
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
                   (execution_id, command_id, task_node_id, session_id, status, resume_of, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (execution_id, command_id, task_node_id, session_id, "queued", resume_of, now, now),
            )
            self._audit(connection, "owner_command_received", task_node_id, command_id, execution_id, now)
            self._audit(connection, "execution_queued", task_node_id, command_id, execution_id, now)
        if self.test_runtime_enabled:
            self._schedule_test_worker(execution_id)
        return {
            "command_id": command_id,
            "execution_id": execution_id,
            "task_node_id": task_node_id,
            "session_id": session_id,
            "execution_status": "queued",
            "duplicate": False,
        }

    def _schedule_test_worker(self, execution_id: str) -> None:
        if self.runtime is None:
            return
        start_worker_process(self.store.path, execution_id, self.runtime)

    def query_execution(self, execution_id: str) -> dict[str, Any] | None:
        row = self.store.get_execution(execution_id)
        return dict(row) if row is not None else None

    def cancel_execution(self, execution_id: str) -> dict[str, Any] | None:
        now = utc_now()
        with self.store.transaction() as connection:
            execution = connection.execute(
                "SELECT execution_id, task_node_id, command_id, status FROM execution_records WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if execution is None:
                return None
            if execution["status"] in {"accepted", "needs_revision", "rejected", "human_takeover", "failed", "cancelled"}:
                return {"execution_id": execution_id, "execution_status": execution["status"], "accepted": False}
            connection.execute(
                "UPDATE execution_records SET status = 'cancelled', finished_at = ?, updated_at = ? WHERE execution_id = ?",
                (now, now, execution_id),
            )
            self._audit(connection, "execution_cancelled", execution["task_node_id"], execution["command_id"], execution_id, now)
            return {"execution_id": execution_id, "execution_status": "cancelled", "accepted": True}

    def list_pending(self, task_node_id: str | None = None) -> list[dict[str, Any]]:
        statuses = ("blocked", "queued", "running", "waiting", "awaiting_acceptance")
        placeholders = ", ".join("?" for _ in statuses)
        query = f"""SELECT execution_id, task_node_id, session_id, status AS execution_status,
                         result_summary, error_summary, created_at, updated_at
                    FROM execution_records WHERE status IN ({placeholders})"""
        arguments: tuple[str, ...] = statuses
        if task_node_id is not None:
            query += " AND task_node_id = ?"
            arguments += (task_node_id,)
        query += " ORDER BY created_at, execution_id"
        with self.store.lock:
            rows = self.store.connection.execute(query, arguments).fetchall()
        return [dict(row) for row in rows]

    def review_execution(
        self, execution_id: str, decision: str, reason: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        status_by_decision = {
            "accept": "accepted",
            "request_revision": "needs_revision",
            "reject": "rejected",
            "request_human_takeover": "human_takeover",
        }
        if decision not in status_by_decision:
            raise ValueError("decision")
        now = utc_now()
        successor_id: str | None = None
        with self.store.transaction() as connection:
            previous = connection.execute(
                "SELECT execution_id, resulting_status FROM review_decisions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if previous is not None:
                return {
                    "execution_id": previous["execution_id"],
                    "execution_status": previous["resulting_status"],
                    "duplicate": True,
                }
            execution = connection.execute(
                """SELECT e.task_node_id, e.command_id, e.session_id, e.status, c.command_text
                   FROM execution_records e JOIN owner_commands c ON c.command_id = e.command_id
                   WHERE e.execution_id = ?""",
                (execution_id,),
            ).fetchone()
            if execution is None:
                return None
            if execution["status"] != "awaiting_acceptance":
                raise RuntimeError("invalid_state")
            resulting_status = status_by_decision[decision]
            connection.execute(
                "UPDATE execution_records SET status = ?, finished_at = ?, updated_at = ? WHERE execution_id = ?",
                (resulting_status, now, now, execution_id),
            )
            if decision == "request_revision":
                successor_id = str(uuid.uuid4())
                successor_command_id = str(uuid.uuid4())
                connection.execute(
                    "INSERT INTO owner_commands VALUES (?, ?, ?, ?, ?, ?)",
                    (successor_command_id, execution["task_node_id"], self.caller_id,
                     f"revision:{idempotency_key}", execution["command_text"], now),
                )
                connection.execute(
                    """INSERT INTO execution_records
                       (execution_id, command_id, task_node_id, session_id, status, revision_of, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)""",
                    (successor_id, successor_command_id, execution["task_node_id"], execution["session_id"], execution_id, now, now),
                )
                self._audit(connection, "execution_revision_queued", execution["task_node_id"], successor_command_id, successor_id, now)
            connection.execute(
                "INSERT INTO review_decisions VALUES (?, ?, ?, ?, ?, ?)",
                (idempotency_key, execution_id, decision, reason, resulting_status, now),
            )
            self._audit(connection, "execution_reviewed", execution["task_node_id"], execution["command_id"], execution_id, now)
        if successor_id is not None and self.test_runtime_enabled:
            self._schedule_test_worker(successor_id)
        result: dict[str, Any] = {
            "execution_id": execution_id,
            "execution_status": resulting_status,
            "duplicate": False,
        }
        if successor_id is not None:
            result["successor_execution_id"] = successor_id
        return result

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
                    resume_of = arguments.get("execution_id")
                    if resume_of is not None and (not isinstance(resume_of, str) or not resume_of.strip()):
                        raise ValueError("execution_id")
                    result = app.submit_owner_command(
                        self._required_string(arguments, "task_node_id"),
                        self._required_string(arguments, "command"),
                        self._required_string(arguments, "idempotency_key"),
                        resume_of.strip() if resume_of else None,
                    )
                    return self._tool_result(request_id, result)
                if name == "query_execution":
                    result = app.query_execution(self._required_string(arguments, "execution_id"))
                    if result is None:
                        return self._tool_error(request_id, "not_found", "execution was not found")
                    return self._tool_result(request_id, result)
                if name == "cancel_execution":
                    result = app.cancel_execution(self._required_string(arguments, "execution_id"))
                    if result is None:
                        return self._tool_error(request_id, "not_found", "execution was not found")
                    return self._tool_result(request_id, result)
                if name == "list_pending":
                    task_node_id = arguments.get("task_node_id")
                    if task_node_id is not None and (not isinstance(task_node_id, str) or not task_node_id.strip()):
                        raise ValueError("task_node_id")
                    return self._tool_result(request_id, app.list_pending(task_node_id.strip() if task_node_id else None))
                if name == "review_execution":
                    result = app.review_execution(
                        self._required_string(arguments, "execution_id"),
                        self._required_string(arguments, "decision"),
                        self._required_string(arguments, "reason"),
                        self._required_string(arguments, "idempotency_key"),
                    )
                    if result is None:
                        return self._tool_error(request_id, "not_found", "execution was not found")
                    return self._tool_result(request_id, result)
                if name == "health":
                    return self._tool_result(request_id, app.health())
                return self._protocol_error(request_id, -32602, "unknown tool")
            except ValueError:
                return self._protocol_error(request_id, -32602, "invalid params")
            except LookupError:
                return self._tool_error(request_id, "not_found", "execution was not found")
            except RuntimeError as error:
                if str(error) == "invalid_state":
                    return self._tool_error(request_id, "invalid_state", "execution cannot be reviewed in its current state")
                return self._tool_error(request_id, "internal", "internal gateway error")
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
                {"name": "cancel_execution", "description": "Request cancellation of an execution."},
                {"name": "list_pending", "description": "List pending executions."},
                {"name": "review_execution", "description": "Review a completed execution."},
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
