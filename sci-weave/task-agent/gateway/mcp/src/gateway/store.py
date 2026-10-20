"""SQLite persistence for Gateway platform state."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutionStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.RLock()
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.initialize()

    def initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS task_sessions (
                task_node_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS owner_commands (
                command_id TEXT PRIMARY KEY,
                task_node_id TEXT NOT NULL REFERENCES task_sessions(task_node_id),
                idempotency_key TEXT NOT NULL UNIQUE,
                command_text TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execution_records (
                execution_id TEXT PRIMARY KEY,
                command_id TEXT NOT NULL UNIQUE REFERENCES owner_commands(command_id),
                task_node_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                result_summary TEXT,
                error_summary TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                task_node_id TEXT NOT NULL,
                command_id TEXT,
                execution_id TEXT,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            try:
                yield self.connection
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def close(self) -> None:
        self.connection.close()

    def health(self) -> bool:
        with self.lock:
            self.connection.execute("SELECT 1").fetchone()
        return True

    def find_command_by_idempotency(self, key: str) -> sqlite3.Row | None:
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM owner_commands WHERE idempotency_key = ?", (key,)
            ).fetchone()

    def get_execution(self, execution_id: str) -> sqlite3.Row | None:
        with self.lock:
            return self.connection.execute(
                """
                SELECT e.*, c.idempotency_key, c.command_text, c.status AS command_status
                FROM execution_records e JOIN owner_commands c ON c.command_id = e.command_id
                WHERE e.execution_id = ?
                """,
                (execution_id,),
            ).fetchone()

    def get_execution_by_command(self, command_id: str) -> sqlite3.Row | None:
        with self.lock:
            return self.connection.execute(
                """
                SELECT e.*, c.idempotency_key, c.command_text, c.status AS command_status
                FROM execution_records e JOIN owner_commands c ON c.command_id = e.command_id
                WHERE e.command_id = ?
                """,
                (command_id,),
            ).fetchone()
