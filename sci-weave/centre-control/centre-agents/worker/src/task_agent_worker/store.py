"""Shared SQLite persistence for one Work Agent.

This package is the single persistence boundary shared by ``gateway/mcp`` and
``gateway/subscriber``.  It owns the schema, the idempotent bootstrap, the
constrained table access, the state-machine transitions, the Worker Lease, the
audit log and the health reads.  It does not know about MCP, queues or Worker
business logic.

Two ingoing paths create execution records:

- ``owner_command`` trigger: the Operator MCP disposition surface (legacy test
  seam kept for backward compatibility);
- ``queue`` trigger: one inbound message from the central queue.  The inbound
  message carries ``trigger_ref`` (the queue event id) and a ``business_key``
  derived from the references required by the message-queue contract
  (``(task_node_id, target_node_version_ref, trigger_revision_id)`` for Task
  Agent hand-offs).

The execution status machine is:

``queued -> running -> {waiting, completed, needs_revision, rejected,
human_takeover, failed, cancelled}``

``needs_revision``, ``rejected`` and ``human_takeover`` are reachable from the
Worker Looper / disposition surface but are not persisted by this store
directly; the state CHECK constraint accepts them so both components share one
table shape.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

EXECUTION_STATUSES = (
    "queued",
    "running",
    "waiting",
    "completed",
    "needs_revision",
    "rejected",
    "human_takeover",
    "failed",
    "cancelled",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ExecutionStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.RLock()
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.initialize()

    def initialize(self, rebuild: bool = False) -> None:
        """Idempotent schema bootstrap.

        ``rebuild=True`` drops the execution tables first; used only by tests on
        temp databases so both the current shape and the pre-trigger shape can
        be bootstrapped without peeking at the table internals.
        """
        if rebuild:
            self.connection.executescript(
                """
                DROP TABLE IF EXISTS review_decisions;
                DROP TABLE IF EXISTS worker_leases;
                DROP TABLE IF EXISTS audit_events;
                DROP TABLE IF EXISTS execution_records;
                DROP TABLE IF EXISTS owner_commands;
                DROP TABLE IF EXISTS callers;
                DROP TABLE IF EXISTS task_sessions;
                """
            )
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS task_sessions (
                task_node_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS callers (
                caller_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS owner_commands (
                command_id TEXT PRIMARY KEY,
                task_node_id TEXT NOT NULL REFERENCES task_sessions(task_node_id),
                caller_id TEXT NOT NULL REFERENCES callers(caller_id),
                idempotency_key TEXT NOT NULL UNIQUE,
                command_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execution_records (
                execution_id TEXT PRIMARY KEY,
                command_id TEXT UNIQUE REFERENCES owner_commands(command_id),
                task_node_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'waiting', 'completed', 'needs_revision', 'rejected', 'human_takeover', 'failed', 'cancelled')),
                trigger TEXT NOT NULL DEFAULT 'owner_command',
                trigger_ref TEXT,
                business_key TEXT UNIQUE,
                draft_id TEXT,
                result_summary TEXT,
                error_summary TEXT,
                pending_question TEXT,
                resume_of TEXT REFERENCES execution_records(execution_id),
                revision_of TEXT REFERENCES execution_records(execution_id),
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS review_decisions (
                idempotency_key TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL REFERENCES execution_records(execution_id),
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                resulting_status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS worker_leases (
                task_node_id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL UNIQUE REFERENCES execution_records(execution_id),
                acquired_at TEXT NOT NULL
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

    def get_execution(self, execution_id: str) -> sqlite3.Row | None:
        with self.lock:
            return self.connection.execute(
                """SELECT e.execution_id, e.task_node_id, e.session_id,
                          e.status AS execution_status, e.trigger, e.trigger_ref,
                          e.business_key, e.draft_id, e.result_summary,
                          e.error_summary, e.pending_question, e.resume_of,
                          e.revision_of, e.created_at, e.started_at, e.finished_at,
                          e.updated_at, c.command_id, c.command_text,
                          c.idempotency_key, c.caller_id
                   FROM execution_records e
                   LEFT JOIN owner_commands c ON c.command_id = e.command_id
                   WHERE e.execution_id = ?""",
                (execution_id,),
            ).fetchone()

    def get_execution_by_business_key(self, business_key: str) -> sqlite3.Row | None:
        with self.lock:
            return self.connection.execute(
                "SELECT * FROM execution_records WHERE business_key = ?",
                (business_key,),
            ).fetchone()