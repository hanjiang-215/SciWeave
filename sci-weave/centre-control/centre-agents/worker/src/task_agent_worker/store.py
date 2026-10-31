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

import json

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


def _parse_timestamp(value: str) -> float | None:
    """Return a POSIX timestamp for an ISO string, or None when unparseable."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _audit_worker_lost(
    connection: sqlite3.Connection, task_node_id: str, command_id: str | None, execution_id: str
) -> None:
    connection.execute(
        """INSERT INTO audit_events (event_type, task_node_id, command_id, execution_id, details, created_at)
           VALUES ('worker_lost', ?, ?, ?, '{}', ?)""",
        (task_node_id, command_id, execution_id, utc_now()),
    )


class ExecutionStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.RLock()
        self._tx_depth = 0
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
                confirmation_status TEXT NOT NULL DEFAULT 'awaiting',
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
        # ai4-odwi: transactional outbox for governance events that must survive a
        # crash between committing a terminal state and publishing it. The event
        # row is written in the same transaction as the state change, then a relay
        # publishes it and flips published_at; a crash leaves it pending for the
        # next drain instead of dropping the event.
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS governance_outbox (
                outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                published_at TEXT
            )
            """
        )
        self.connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run one write transaction while holding the write lock from the start.

        ai4-qt7x: SQLite's implicit BEGIN is DEFERRED, so a read-then-write
        transaction (claim: SELECT the queued row, then INSERT the lease) could
        interleave with another process's write and fail with "database is
        locked" instead of serializing. BEGIN IMMEDIATE takes the write lock up
        front. The RLock is re-entrant, so nested ``transaction()`` blocks reuse
        the outer transaction instead of opening a second one.
        """
        with self.lock:
            outer = self._tx_depth == 0
            if outer:
                self.connection.execute("BEGIN IMMEDIATE")
            self._tx_depth += 1
            try:
                yield self.connection
            except Exception:
                self._tx_depth -= 1
                if outer:
                    self.connection.rollback()
                raise
            self._tx_depth -= 1
            if outer:
                self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    # ------------------------------------------------------- lease recovery
    # ai4-qt7x: leases are inserted when a Worker starts and deleted when it
    # finishes. Nothing reaped them before, so a Worker killed mid-run held its
    # task_node_id forever (every later claim hit the primary key and returned)
    # and nothing re-dispatched an execution left queued by a dead process.

    def reap_orphan_leases(self) -> int:
        """Delete leases whose execution is no longer running; return the count."""
        with self.transaction() as connection:
            cursor = connection.execute(
                """DELETE FROM worker_leases
                   WHERE execution_id NOT IN (
                       SELECT execution_id FROM execution_records WHERE status = 'running'
                   )"""
            )
            return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0

    def reclaim_stale_leases(self, *, older_than_seconds: float) -> list[str]:
        """Fail executions whose Worker is gone, then release their leases.

        A lease older than the threshold belongs to a process that can no longer
        be trusted to report: mark the execution ``failed`` with
        ``worker_lost`` so the owner sees why, and drop the lease so the target
        can be claimed again. Deliberately coarse (there is no heartbeat), so the
        threshold must exceed the longest expected run.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - older_than_seconds
        reclaimed: list[str] = []
        with self.transaction() as connection:
            rows = connection.execute(
                """SELECT l.execution_id, l.task_node_id, l.acquired_at, e.command_id
                   FROM worker_leases l
                   LEFT JOIN execution_records e ON e.execution_id = l.execution_id"""
            ).fetchall()
            for row in rows:
                acquired = _parse_timestamp(row["acquired_at"])
                if acquired is None or acquired >= cutoff:
                    continue
                updated = connection.execute(
                    """UPDATE execution_records
                       SET status = 'failed', error_summary = 'worker_lost', updated_at = ?
                       WHERE execution_id = ? AND status = 'running'""",
                    (utc_now(), row["execution_id"]),
                )
                connection.execute(
                    "DELETE FROM worker_leases WHERE execution_id = ?", (row["execution_id"],)
                )
                _audit_worker_lost(
                    connection, row["task_node_id"], row["command_id"], row["execution_id"]
                )
                if updated.rowcount:
                    reclaimed.append(row["execution_id"])
        return reclaimed

    def queued_execution_ids_without_lease(self) -> list[str]:
        """Executions stuck in ``queued`` with no Worker claiming them."""
        with self.lock:
            rows = self.connection.execute(
                """SELECT e.execution_id FROM execution_records e
                   WHERE e.status = 'queued'
                     AND NOT EXISTS (
                         SELECT 1 FROM worker_leases l WHERE l.execution_id = e.execution_id
                     )
                   ORDER BY e.created_at, e.execution_id"""
            ).fetchall()
        return [row["execution_id"] for row in rows]

    # ------------------------------------------------------------ outbox
    def record_outbox_event(
        self,
        connection: sqlite3.Connection,
        *,
        event_type: str,
        dedupe_key: str,
        payload_json: str,
        created_at: str,
    ) -> None:
        """Stage a governance event inside a caller-owned transaction (ai4-odwi).

        Must be called with the same ``connection`` that commits the state change
        so the event and the terminal state are durable together; a duplicate
        dedupe_key is ignored so a retried write cannot stage twice.
        """
        connection.execute(
            """INSERT OR IGNORE INTO governance_outbox
               (event_type, dedupe_key, payload_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (event_type, dedupe_key, payload_json, created_at),
        )

    def pending_outbox_events(self, limit: int = 100) -> list[sqlite3.Row]:
        with self.lock:
            return self.connection.execute(
                """SELECT outbox_id, event_type, dedupe_key, payload_json, attempts
                   FROM governance_outbox
                   WHERE published_at IS NULL
                   ORDER BY outbox_id
                   LIMIT ?""",
                (limit,),
            ).fetchall()

    def mark_outbox_published(self, outbox_id: int, published_at: str) -> None:
        with self.lock:
            self.connection.execute(
                "UPDATE governance_outbox SET published_at = ? WHERE outbox_id = ?",
                (published_at, outbox_id),
            )
            self.connection.commit()

    def mark_outbox_failed(self, outbox_id: int, error: str) -> None:
        with self.lock:
            self.connection.execute(
                """UPDATE governance_outbox
                   SET attempts = attempts + 1, last_error = ?
                   WHERE outbox_id = ?""",
                (error, outbox_id),
            )
            self.connection.commit()

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
                          e.revision_of, e.confirmation_status,
                          e.created_at, e.started_at, e.finished_at,
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

    def confirm_execution(
        self,
        execution_id: str,
        decision: str,
        reason: str,
        *,
        idempotency_key: str,
    ) -> dict[str, object]:
        """B1: researcher confirms a finished execution.

        ``accepted`` -> confirmation_status='confirmed' and the task_completed
        governance event is staged in the SAME transaction, so downstream
        dispatch and the board only advance after a human confirms.
        ``rejected`` -> confirmation_status='rejected', status='rejected'
        (no completion event).
        """
        if decision not in {"accepted", "rejected"}:
            raise DispositionError("invalid_state", decision)
        if not reason.strip():
            raise DispositionError("invalid_state", "a confirmation needs a reason")
        now = utc_now()
        with self.transaction() as connection:
            replayed = connection.execute(
                """SELECT decision, resulting_status FROM review_decisions
                   WHERE idempotency_key = ?""",
                (idempotency_key,),
            ).fetchone()
            if replayed is not None:
                return {
                    "execution_id": execution_id,
                    "decision": replayed["decision"],
                    "confirmation_status": "confirmed" if replayed["decision"] == "accepted" else "rejected",
                    "idempotent": True,
                }
            row = connection.execute(
                "SELECT status, task_node_id, business_key, mapping_domain_id, draft_id, finished_at "
                "FROM execution_records WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if row is None:
                raise DispositionError("not_found", execution_id)
            if row["status"] != "completed":
                raise DispositionError("invalid_state", row["status"])
            if decision == "accepted":
                confirmation_status = "confirmed"
                connection.execute(
                    "UPDATE execution_records SET confirmation_status = ?, updated_at = ? "
                    "WHERE execution_id = ?",
                    (confirmation_status, now, execution_id),
                )
                completion_event = {
                    "execution_id": execution_id,
                    "task_node_id": row["task_node_id"],
                    "mapping_domain_id": row["mapping_domain_id"],
                    "business_key": row["business_key"],
                    "draft_id": row["draft_id"],
                    "finished_at": row["finished_at"] or now,
                }
                self.record_outbox_event(
                    connection,
                    event_type="task_completed",
                    dedupe_key=f"task_completed:{execution_id}",
                    payload_json=json.dumps(completion_event, ensure_ascii=False),
                    created_at=now,
                )
                resulting = "completed"
            else:
                confirmation_status = "rejected"
                resulting = "rejected"
                connection.execute(
                    "UPDATE execution_records SET status = ?, confirmation_status = ?, updated_at = ? "
                    "WHERE execution_id = ?",
                    (resulting, confirmation_status, now, execution_id),
                )
            connection.execute(
                """INSERT INTO review_decisions
                   (idempotency_key, execution_id, decision, reason, resulting_status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (idempotency_key, execution_id, decision, reason, resulting, now),
            )
            self._audit(connection, "execution_confirmed", execution_id, now)
        return {
            "execution_id": execution_id,
            "decision": decision,
            "confirmation_status": confirmation_status,
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