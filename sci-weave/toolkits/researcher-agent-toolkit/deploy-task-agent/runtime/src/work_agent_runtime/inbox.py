"""Durable message inbox for the researcher-owned Work Agent subscriber.

Mirrors the Work Agent architecture: an inbound message is durably recorded
before any execution starts.  A missing workflow binding keeps the message in
``awaiting_workflow_binding`` until the binding is established; the message
then transitions to ``queued`` and is handed to the runtime.  Because the
inbox rows survive restarts, a crashed subscriber re-drives ``queued`` rows on
startup instead of silently dropping them, and duplicate deliveries are
blocked by the ``dedupe_key`` primary key.

States: ``awaiting_workflow_binding`` -> ``queued`` -> ``processed``.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Tuple

INBOX_STATUSES = ("awaiting_workflow_binding", "queued", "processed")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InboxError(RuntimeError):
    """Stable error raised on invalid inbox transitions or bad rows."""


class InboxStore:
    """SQLite-backed message inbox shared by the subscriber and the runtime.

    Only the inbox owns the ``dedupe_key`` uniqueness; the execution store
    remains the in-memory runtime boundary.  Schema bootstrap is idempotent;
    tests use a temp path so nothing leaks into the repository.
    """

    def __init__(self, path: str | Path):
        self.path = str(path)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.RLock()
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.initialize()

    def initialize(self, rebuild: bool = False) -> None:
        if rebuild:
            self.connection.execute("DROP TABLE IF EXISTS inbox_messages")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS inbox_messages (
                dedupe_key TEXT PRIMARY KEY,
                target_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                agent_definition TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('awaiting_workflow_binding', 'queued', 'processed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            try:
                yield self.connection
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def enqueue(self, dedupe_key: str, target_id: str, event_id: str, agent_definition: str = "", *, binding_present: bool) -> Tuple[str, bool]:
        """Record one inbound message; returns ``(status, created_new)``.

        ``status`` is ``queued`` when a workflow binding is present and
        ``awaiting_workflow_binding`` otherwise.  A duplicate ``dedupe_key``
        returns the persisted status with ``created_new=False``.
        """
        status = "queued" if binding_present else "awaiting_workflow_binding"
        now = utc_now()
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT status FROM inbox_messages WHERE dedupe_key = ?", (dedupe_key,)
            ).fetchone()
            if existing is not None:
                return existing["status"], False
            connection.execute(
                """INSERT INTO inbox_messages (dedupe_key, target_id, event_id, agent_definition, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (dedupe_key, target_id, event_id, agent_definition, status, now, now),
            )
            return status, True

    def bind(self, dedupe_key: str) -> None:
        """Establish the workflow binding: ``awaiting_workflow_binding`` -> ``queued``."""
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT status FROM inbox_messages WHERE dedupe_key = ?", (dedupe_key,)
            ).fetchone()
            if row is None:
                raise InboxError(f"inbox_row_missing: {dedupe_key}")
            if row["status"] == "processed":
                raise InboxError(f"inbox_already_processed: {dedupe_key}")
            if row["status"] == "awaiting_workflow_binding":
                connection.execute(
                    "UPDATE inbox_messages SET status = 'queued', updated_at = ? WHERE dedupe_key = ?",
                    (utc_now(), dedupe_key),
                )

    def mark_processed(self, dedupe_key: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE inbox_messages SET status = 'processed', updated_at = ? WHERE dedupe_key = ?",
                (utc_now(), dedupe_key),
            )

    def list_status(self, status: str) -> list[dict]:
        if status not in INBOX_STATUSES:
            raise InboxError(f"invalid_inbox_status: {status}")
        with self.lock:
            rows = self.connection.execute(
                "SELECT dedupe_key, target_id, event_id, agent_definition, status FROM inbox_messages WHERE status = ? ORDER BY created_at",
                (status,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get(self, dedupe_key: str) -> dict | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT dedupe_key, target_id, event_id, agent_definition, status FROM inbox_messages WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            return dict(row) if row is not None else None

    def close(self) -> None:
        with self.lock:
            self.connection.close()
