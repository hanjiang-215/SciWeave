"""Durable execution state for the researcher-side Work Agent (ai4-58d0).

The in-memory ``ExecutionStore`` keeps an execution alive only as long as the
subscriber process. A disposition surface (query, cancel, answer, review) has to
run in a *different* process from the one that executes, so the state it acts on
must outlive that process: this store keeps executions, pending questions and
review decisions in SQLite.

It mirrors the in-memory store's method shape, so ``run_one`` and
``WorkflowExecutor`` accept either one.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from .runtime import ExecutionRecord

TERMINAL_STATUSES = ("completed", "failed", "cancelled")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS execution (
    execution_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    target_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'queued', 'running', 'waiting', 'completed', 'failed', 'cancelled'
    )),
    draft_id TEXT,
    draft_id_source TEXT,
    error_code TEXT,
    failed_agent TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS execution_pending ON execution (status, created_at);

CREATE TABLE IF NOT EXISTS execution_question (
    question_id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL REFERENCES execution(execution_id),
    question TEXT NOT NULL,
    answer TEXT,
    created_at TEXT NOT NULL,
    answered_at TEXT
);

CREATE TABLE IF NOT EXISTS execution_review (
    review_id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL REFERENCES execution(execution_id),
    decision TEXT NOT NULL CHECK(decision IN ('accepted', 'rejected')),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExecutionNotFound(LookupError):
    """Raised when a disposition tool names an execution that does not exist."""


class InvalidTransition(ValueError):
    """Raised when a disposition tool would move an execution backwards."""


class SqliteExecutionStore:
    """SQLite-backed execution state shared by the subscriber and the MCP role."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(_SCHEMA)
        self._migrate()
        self._connection.commit()

    def _migrate(self) -> None:
        """Add columns a pre-existing database does not have (ai4-x0ay).

        `CREATE TABLE IF NOT EXISTS` is a no-op on an installed database, and
        the kit ships with one, so every later column needs its own step. Read
        through `PRAGMA table_info` first: repeating the check is free, while a
        repeated `ALTER TABLE` is an error.
        """
        columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(execution)")}
        if "draft_id_source" not in columns:
            self._connection.execute("ALTER TABLE execution ADD COLUMN draft_id_source TEXT")

    def close(self) -> None:
        self._connection.close()

    # -- runtime boundary ---------------------------------------------------

    def enqueue(self, target_id: str, event_id: str) -> ExecutionRecord:
        now = _utc_now()
        with self._connection:
            self._connection.execute(
                """INSERT OR IGNORE INTO execution
                   (execution_id, event_id, target_id, status, created_at, updated_at)
                   VALUES (?, ?, ?, 'queued', ?, ?)""",
                (str(uuid.uuid4()), event_id, target_id, now, now),
            )
        record = self.get_by_event(event_id)
        assert record is not None  # the insert above guarantees the row
        return record

    def start(self, execution: ExecutionRecord) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                """UPDATE execution SET status = 'running', updated_at = ?
                   WHERE execution_id = ? AND status = 'queued'""",
                (_utc_now(), execution.execution_id),
            )
        return cursor.rowcount > 0

    def complete(
        self,
        execution: ExecutionRecord,
        draft_id: str,
        draft_id_source: str | None = None,
    ) -> ExecutionRecord:
        return self._transition(
            execution.execution_id,
            "completed",
            draft_id=draft_id,
            draft_id_source=draft_id_source,
        )

    def fail(
        self, execution: ExecutionRecord, error_code: str, failed_agent: str | None = None
    ) -> ExecutionRecord:
        return self._transition(
            execution.execution_id, "failed", error_code=error_code, failed_agent=failed_agent
        )

    def get(self, execution_id: str) -> ExecutionRecord | None:
        row = self._connection.execute(
            "SELECT * FROM execution WHERE execution_id = ?", (execution_id,)
        ).fetchone()
        return _record(row)

    def get_by_event(self, event_id: str) -> ExecutionRecord | None:
        row = self._connection.execute(
            "SELECT * FROM execution WHERE event_id = ?", (event_id,)
        ).fetchone()
        return _record(row)

    # -- disposition boundary ----------------------------------------------

    def list_pending(self, limit: int = 100) -> list[dict]:
        """Executions a human still has to act on, oldest first."""
        rows = self._connection.execute(
            """SELECT execution_id, target_id, status, draft_id, error_code, created_at
               FROM execution WHERE status IN ('queued', 'running', 'waiting')
               ORDER BY created_at, execution_id LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_all(self, limit: int = 200) -> list[dict]:
        rows = self._connection.execute(
            """SELECT execution_id, target_id, status, draft_id, draft_id_source, error_code,
                      created_at
               FROM execution ORDER BY created_at DESC, execution_id LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def cancel(self, execution_id: str) -> ExecutionRecord:
        """Cancel a non-terminal execution; a terminal one keeps its status."""
        with self._connection:
            cursor = self._connection.execute(
                """UPDATE execution SET status = 'cancelled', updated_at = ?
                   WHERE execution_id = ?
                     AND status IN ('queued', 'running', 'waiting')""",
                (_utc_now(), execution_id),
            )
        record = self.get(execution_id)
        if record is None:
            raise ExecutionNotFound(execution_id)
        if cursor.rowcount == 0:
            raise InvalidTransition(
                f"{execution_id} is already {record.status}; a cancel cannot reopen it"
            )
        return record

    def ask(self, execution_id: str, question: str) -> dict:
        """Record a question the agent cannot answer alone and park the execution."""
        if not question.strip():
            raise ValueError("a question cannot be empty")
        now = _utc_now()
        question_id = str(uuid.uuid4())
        with self._connection:
            row = self._connection.execute(
                "SELECT status FROM execution WHERE execution_id = ?", (execution_id,)
            ).fetchone()
            if row is None:
                raise ExecutionNotFound(execution_id)
            if row["status"] in TERMINAL_STATUSES:
                raise InvalidTransition(
                    f"{execution_id} is already {row['status']}; no question can be asked"
                )
            self._connection.execute(
                """INSERT INTO execution_question
                   (question_id, execution_id, question, created_at)
                   VALUES (?, ?, ?, ?)""",
                (question_id, execution_id, question, now),
            )
            self._connection.execute(
                "UPDATE execution SET status = 'waiting', updated_at = ? WHERE execution_id = ?",
                (now, execution_id),
            )
        return {
            "question_id": question_id,
            "execution_id": execution_id,
            "question": question,
            "status": "waiting",
        }

    def pending_questions(self, execution_id: str | None = None) -> list[dict]:
        query = """SELECT question_id, execution_id, question, created_at
                   FROM execution_question WHERE answer IS NULL"""
        arguments: tuple = ()
        if execution_id is not None:
            query += " AND execution_id = ?"
            arguments = (execution_id,)
        query += " ORDER BY created_at, question_id"
        return [dict(row) for row in self._connection.execute(query, arguments).fetchall()]

    def answer(self, question_id: str, answer: str) -> dict:
        """Record the human answer and hand the execution back to the queue."""
        if not answer.strip():
            raise ValueError("an answer cannot be empty")
        now = _utc_now()
        with self._connection:
            row = self._connection.execute(
                "SELECT execution_id, answer FROM execution_question WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            if row is None:
                raise ExecutionNotFound(question_id)
            if row["answer"] is not None:
                raise InvalidTransition(f"{question_id} was already answered")
            self._connection.execute(
                """UPDATE execution_question SET answer = ?, answered_at = ?
                   WHERE question_id = ?""",
                (answer, now, question_id),
            )
            self._connection.execute(
                """UPDATE execution SET status = 'queued', updated_at = ?
                   WHERE execution_id = ? AND status = 'waiting'""",
                (now, row["execution_id"]),
            )
        return {
            "question_id": question_id,
            "execution_id": row["execution_id"],
            "answer": answer,
            "status": "queued",
        }

    def review(self, execution_id: str, decision: str, reason: str) -> dict:
        """Record an append-only review decision on a finished execution."""
        if decision not in {"accepted", "rejected"}:
            raise ValueError("decision must be accepted or rejected")
        if not reason.strip():
            raise ValueError("a review needs a reason")
        now = _utc_now()
        with self._connection:
            row = self._connection.execute(
                "SELECT status FROM execution WHERE execution_id = ?", (execution_id,)
            ).fetchone()
            if row is None:
                raise ExecutionNotFound(execution_id)
            if row["status"] not in ("completed", "failed"):
                raise InvalidTransition(
                    f"{execution_id} is {row['status']}; only a finished execution can be reviewed"
                )
            review_id = str(uuid.uuid4())
            self._connection.execute(
                """INSERT INTO execution_review
                   (review_id, execution_id, decision, reason, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (review_id, execution_id, decision, reason, now),
            )
        return {
            "review_id": review_id,
            "execution_id": execution_id,
            "decision": decision,
            "reason": reason,
        }

    def reviews(self, execution_id: str) -> list[dict]:
        return [
            dict(row)
            for row in self._connection.execute(
                """SELECT review_id, decision, reason, created_at FROM execution_review
                   WHERE execution_id = ? ORDER BY rowid""",
                (execution_id,),
            ).fetchall()
        ]

    def _transition(
        self,
        execution_id: str,
        status: str,
        *,
        draft_id: str | None = None,
        draft_id_source: str | None = None,
        error_code: str | None = None,
        failed_agent: str | None = None,
    ) -> ExecutionRecord:
        with self._connection:
            cursor = self._connection.execute(
                """UPDATE execution
                   SET status = ?, draft_id = COALESCE(?, draft_id),
                       draft_id_source = COALESCE(?, draft_id_source),
                       error_code = COALESCE(?, error_code),
                       failed_agent = COALESCE(?, failed_agent),
                       updated_at = ?
                   WHERE execution_id = ? AND status NOT IN ('completed', 'failed', 'cancelled')""",
                (status, draft_id, draft_id_source, error_code, failed_agent, _utc_now(), execution_id),
            )
        record = self.get(execution_id)
        if record is None:
            raise ExecutionNotFound(execution_id)
        if cursor.rowcount == 0:
            # A cancel landed first: keep it rather than overwriting the state.
            return record
        return record


def _record(row: sqlite3.Row | None) -> ExecutionRecord | None:
    if row is None:
        return None
    return ExecutionRecord(
        execution_id=row["execution_id"],
        target_id=row["target_id"],
        status=row["status"],
        draft_id=row["draft_id"],
        error_code=row["error_code"],
        failed_agent=row["failed_agent"],
        draft_id_source=row["draft_id_source"],
    )
