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
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class DispositionError(Exception):
    """A disposition request the store refuses; ``code`` is a stable error code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

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
        # B6: the subscriber must publish task_completed, which the coordinator
        # routes by mapping_domain_id. The domain is not otherwise derivable from
        # execution_records, so persist it. Added via ALTER for existing DBs.
        columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(execution_records)")
        }
        if "mapping_domain_id" not in columns:
            self.connection.execute(
                "ALTER TABLE execution_records ADD COLUMN mapping_domain_id TEXT"
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

    def list_executions(self, *, limit: int = 200) -> list[dict[str, object]]:
        """Read-only execution summary for the dashboard source fragment."""
        with self.lock:
            rows = self.connection.execute(
                """SELECT execution_id, task_node_id, session_id, status,
                          trigger, trigger_ref, business_key, draft_id,
                          result_summary, error_summary, pending_question,
                          created_at, started_at, finished_at, updated_at
                   FROM execution_records
                   ORDER BY created_at DESC, execution_id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_recent_audit_events(self, *, limit: int = 100) -> list[dict[str, object]]:
        """Read-only recent audit events for the dashboard events collection."""
        with self.lock:
            rows = self.connection.execute(
                """SELECT event_type, task_node_id, execution_id, details, created_at
                   FROM audit_events
                   ORDER BY event_id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
    # -- disposition (ai4-4pyb follow-up: the gateway used to answer unimplemented) --

    def ask_question(self, execution_id: str, question: str) -> dict[str, object]:
        """Park a running execution until a human answers ``question``."""
        if not question.strip():
            raise DispositionError("invalid_state", "a question cannot be empty")
        now = utc_now()
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT status FROM execution_records WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if row is None:
                raise DispositionError("not_found", execution_id)
            if row["status"] not in {"queued", "running"}:
                raise DispositionError("invalid_state", row["status"])
            connection.execute(
                """UPDATE execution_records
                   SET status = 'waiting', pending_question = ?, updated_at = ?
                   WHERE execution_id = ?""",
                (question, now, execution_id),
            )
            self._audit(connection, "execution_question_asked", execution_id, now)
        return {"execution_id": execution_id, "status": "waiting", "pending_question": question}

    def answer_question(
        self, execution_id: str, answer: str, *, idempotency_key: str
    ) -> dict[str, object]:
        """Record the answer and queue a resumed execution that points at the original."""
        if not answer.strip():
            raise DispositionError("invalid_state", "an answer cannot be empty")
        now = utc_now()
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT execution_id FROM execution_records WHERE business_key = ?",
                (f"answer:{idempotency_key}",),
            ).fetchone()
            if existing is not None:
                return {
                    "execution_id": existing["execution_id"],
                    "status": "queued",
                    "idempotent": True,
                }
            row = connection.execute(
                "SELECT task_node_id, session_id, status, pending_question FROM execution_records"
                " WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if row is None:
                raise DispositionError("not_found", execution_id)
            if row["status"] != "waiting" or not row["pending_question"]:
                raise DispositionError("invalid_state", row["status"])
            resumed_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO execution_records
                   (execution_id, task_node_id, session_id, status, trigger, trigger_ref,
                    business_key, resume_of, created_at, updated_at)
                   VALUES (?, ?, ?, 'queued', 'resume', ?, ?, ?, ?, ?)""",
                (
                    resumed_id,
                    row["task_node_id"],
                    row["session_id"],
                    execution_id,
                    f"answer:{idempotency_key}",
                    execution_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """UPDATE execution_records
                   SET status = 'completed', pending_question = NULL, updated_at = ?
                   WHERE execution_id = ?""",
                (now, execution_id),
            )
            self._audit(connection, "execution_question_answered", execution_id, now)
        return {"execution_id": resumed_id, "resume_of": execution_id, "status": "queued"}

    def record_review(
        self, execution_id: str, decision: str, reason: str, *, idempotency_key: str
    ) -> dict[str, object]:
        """Append a disposition decision and move the execution to its resulting status."""
        resulting = {
            "request_revision": "needs_revision",
            "reject": "rejected",
            "request_human_takeover": "human_takeover",
        }.get(decision)
        if resulting is None:
            raise DispositionError("invalid_state", decision)
        if not reason.strip():
            raise DispositionError("invalid_state", "a review needs a reason")
        now = utc_now()
        with self.transaction() as connection:
            # Idempotency is checked before the state guard: replaying a decision
            # on an execution that the first call already moved must return the
            # first result, not an invalid_state error.
            replayed = connection.execute(
                """SELECT decision, resulting_status FROM review_decisions
                   WHERE idempotency_key = ?""",
                (idempotency_key,),
            ).fetchone()
            if replayed is not None:
                return {
                    "execution_id": execution_id,
                    "decision": replayed["decision"],
                    "status": replayed["resulting_status"],
                    "idempotent": True,
                }
            row = connection.execute(
                "SELECT status FROM execution_records WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if row is None:
                raise DispositionError("not_found", execution_id)
            if row["status"] not in {"completed", "failed", "needs_revision"}:
                raise DispositionError("invalid_state", row["status"])
            connection.execute(
                """INSERT INTO review_decisions
                   (idempotency_key, execution_id, decision, reason, resulting_status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (idempotency_key, execution_id, decision, reason, resulting, now),
            )
            connection.execute(
                "UPDATE execution_records SET status = ?, updated_at = ? WHERE execution_id = ?",
                (resulting, now, execution_id),
            )
            self._audit(connection, "execution_reviewed", execution_id, now)
        return {
            "execution_id": execution_id,
            "decision": decision,
            "status": resulting,
        }

    def _audit(self, connection: sqlite3.Connection, event_type: str, execution_id: str, now: str) -> None:
        row = connection.execute(
            "SELECT task_node_id FROM execution_records WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()
        connection.execute(
            """INSERT INTO audit_events (event_type, task_node_id, execution_id, details, created_at)
               VALUES (?, ?, ?, '{}', ?)""",
            (event_type, row["task_node_id"] if row else "", execution_id, now),
        )