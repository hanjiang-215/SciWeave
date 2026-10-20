"""Gateway application and HTTP seam for the MVP."""

from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .store import ExecutionStore, utc_now


class GatewayApplication:
    def __init__(self, store: ExecutionStore, token: str):
        self.store = store
        self.token = token

    def authorize(self, supplied: str | None) -> bool:
        return bool(supplied) and secrets.compare_digest(supplied, self.token)

    def submit_command(self, task_node_id: str, command_text: str, idempotency_key: str) -> dict[str, Any]:
        command_id = str(uuid.uuid4())
        execution_id = str(uuid.uuid4())
        session_id = f"task_{task_node_id}_{uuid.uuid4().hex}"
        now = utc_now()
        with self.store.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM owner_commands WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                execution = connection.execute(
                    "SELECT * FROM execution_records WHERE command_id = ?", (existing["command_id"],)
                ).fetchone()
                return self._command_response(existing, execution, duplicate=True)

            session = connection.execute(
                "SELECT * FROM task_sessions WHERE task_node_id = ?", (task_node_id,)
            ).fetchone()
            if session is None:
                connection.execute(
                    "INSERT INTO task_sessions VALUES (?, ?, ?, ?, ?)",
                    (task_node_id, session_id, "active", now, now),
                )
            else:
                session_id = session["session_id"]
            connection.execute(
                "INSERT INTO owner_commands VALUES (?, ?, ?, ?, ?, ?, ?)",
                (command_id, task_node_id, idempotency_key, command_text, "accepted", now, now),
            )
            connection.execute(
                "INSERT INTO execution_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (execution_id, command_id, task_node_id, session_id, "created", None, None, now, now),
            )
            self._audit(connection, "command.accepted", task_node_id, command_id, execution_id, now)
        return {
            "command_id": command_id,
            "execution_id": execution_id,
            "task_node_id": task_node_id,
            "session_id": session_id,
            "command_status": "accepted",
            "execution_status": "created",
            "duplicate": False,
        }

    def execution(self, execution_id: str) -> dict[str, Any] | None:
        row = self.store.get_execution(execution_id)
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _audit(connection: sqlite3.Connection, event_type: str, task_node_id: str, command_id: str, execution_id: str, now: str) -> None:
        connection.execute(
            "INSERT INTO audit_events (event_type, task_node_id, command_id, execution_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (event_type, task_node_id, command_id, execution_id, "{}", now),
        )

    @staticmethod
    def _command_response(command: sqlite3.Row, execution: sqlite3.Row | None, duplicate: bool) -> dict[str, Any]:
        if execution is None:
            raise RuntimeError("execution record missing for persisted command")
        return {
            "command_id": command["command_id"],
            "execution_id": execution["execution_id"],
            "task_node_id": command["task_node_id"],
            "session_id": execution["session_id"],
            "command_status": command["status"],
            "execution_status": execution["status"],
            "duplicate": duplicate,
        }


def create_app(database: str, token: str) -> GatewayApplication:
    return GatewayApplication(ExecutionStore(database), token)


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
            return app.authorize(header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else None)

        def _json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length))

        def do_GET(self) -> None:
            if self.path == "/health":
                try:
                    self._send(HTTPStatus.OK, {"status": "ready", "storage": app.store.health()})
                except sqlite3.Error:
                    self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "unavailable"})
                return
            if not self._authorized():
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            prefix = "/v1/executions/"
            if self.path.startswith(prefix):
                execution = app.execution(self.path[len(prefix):])
                self._send(HTTPStatus.OK if execution else HTTPStatus.NOT_FOUND, execution or {"error": "not_found"})
                return
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:
            if not self._authorized():
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            if self.path != "/v1/commands":
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                data = self._json()
                if not isinstance(data, dict):
                    raise ValueError("request body must be a JSON object")
                fields = (data.get("task_node_id"), data.get("command"), data.get("idempotency_key"))
                if not all(isinstance(field, str) and field.strip() for field in fields):
                    raise ValueError("task_node_id, command and idempotency_key are required")
                response = app.submit_command(*[field.strip() for field in fields])
            except (ValueError, json.JSONDecodeError) as error:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            self._send(HTTPStatus.OK if response["duplicate"] else HTTPStatus.ACCEPTED, response)

        def log_message(self, *_: object) -> None:
            return

    return Handler


def serve(app: GatewayApplication, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(app))
    try:
        server.serve_forever()
    finally:
        server.server_close()
