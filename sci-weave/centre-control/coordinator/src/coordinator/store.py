from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_log = logging.getLogger(__name__)

PENDING_WAITING = "waiting"
PENDING_READY = "ready"
PENDING_DISPATCHED_UNKNOWN = "dispatched_unknown"
PENDING_DONE = "done"
PENDING_SUPERSEDED = "superseded"
PENDING_FAILED = "failed"


class InvalidPendingTransition(Exception):
    """A PendingHandoff status change violates the allowed transition table."""

    def __init__(
        self,
        message: str,
        *,
        current: str,
        requested: str,
        task_node_id: str,
    ) -> None:
        super().__init__(message)
        self.current = current
        self.requested = requested
        self.task_node_id = task_node_id


# Valid next states per current state (ai4-zc85 / ai4-te1v). ``done`` is
# terminal: recompute must never roll it back to waiting.
_PENDING_TRANSITIONS = {
    PENDING_WAITING: {PENDING_READY, PENDING_DONE, PENDING_DISPATCHED_UNKNOWN, PENDING_SUPERSEDED, PENDING_FAILED},
    PENDING_READY: {PENDING_DONE, PENDING_DISPATCHED_UNKNOWN, PENDING_SUPERSEDED, PENDING_FAILED, PENDING_WAITING},
    # A dispatch whose outcome was never confirmed can be re-driven by
    # recompute once its gate is satisfied again: the pending fact returns to
    # ready and the dispatch retry policy (not a duplicate publish) owns the
    # actual re-send (ai4-zpyg).
    PENDING_DISPATCHED_UNKNOWN: {PENDING_DONE, PENDING_FAILED, PENDING_SUPERSEDED, PENDING_WAITING, PENDING_READY},
    PENDING_DONE: frozenset(),  # terminal; no rollback
    PENDING_SUPERSEDED: frozenset(),  # terminal
    PENDING_FAILED: {PENDING_SUPERSEDED},  # human may supersede a failure
}

DISPATCH_CREATED = "created"
DISPATCH_PUBLISHED = "published"
DISPATCH_RESULT_UNKNOWN = "result_unknown"
DISPATCH_FAILED = "failed"
DISPATCH_DEAD = "dead"

MSG_HANDOFF_READY = "task_handoff_ready"
MSG_HUMAN_NOTIFICATION = "human_notification_intent"
MSG_TERMINAL_SUMMARY = "task_terminal_summary"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class PendingHandoff:
    pending_handoff_id: str
    mapping_domain_id: str
    task_node_id: str
    target_node_version_ref: str
    upstream_source_refs: tuple[tuple[str, str], ...]
    executor_refs: tuple[str, ...]
    executor_agent_id: str | None
    status: str
    last_trigger_revision_id: str | None
    created_at: str
    updated_at: str
    # ai4-te1v / ai4-quvy: why the handoff is waiting, when it is
    # (blocking_dependency_missing, activation_condition_unknown, ...).
    waiting_reason: str | None = None


@dataclass(frozen=True)
class HandoffDispatch:
    dispatch_id: str
    pending_handoff_id: str
    dedupe_key: str
    message_type: str
    target_agent_id: str | None
    status: str
    attempt_count: int
    error_summary: str | None
    created_at: str
    updated_at: str


class _LockedConnection:
    """Serialize one sqlite3 connection across the poller thread and the threaded
    management-MCP worker threads.

    The coordinator owns a single sqlite3 connection (open without
    ``check_same_thread=False`` historically) that is used both by the dispatch
    poller thread and every management-MCP ``dispatch_root_task`` call served on a
    ThreadingHTTPServer worker thread. sqlite3 raises ``ProgrammingError: SQLite
    objects created in a thread can only be used in that same thread`` when a
    connection crosses threads, which surfaced as a swallowed ``dispatch_failed``.
    Wrapping the connection with an ``RLock`` and ``check_same_thread=False`` lets
    the one connection be shared safely and keeps statements serialized.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    def execute(self, *args, **kwargs):
        with self._lock:
            return self._conn.execute(*args, **kwargs)

    def executescript(self, *args, **kwargs):
        with self._lock:
            return self._conn.executescript(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        with self._lock:
            return self._conn.executemany(*args, **kwargs)

    def commit(self):
        with self._lock:
            return self._conn.commit()

    def rollback(self):
        with self._lock:
            return self._conn.rollback()

    def close(self):
        with self._lock:
            return self._conn.close()

    def __getattr__(self, name):
        # row_factory, isolation_level, etc. — guarded where they mutate shared state.
        return getattr(self._conn, name)

    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value):
        with self._lock:
            self._conn.row_factory = value


class CoordinatorStore:
    """SQLite state store for PendingHandoff, HandoffDispatch, completed facts and domain state.

    This store is owned by the coordinator and physically isolated from the domain
    SQLite/TerminusDB stores; the coordinator never opens those stores directly.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        if isinstance(connection, _LockedConnection):
            self.conn = connection
        else:
            self.conn = _LockedConnection(connection)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pending_handoff (
              pending_handoff_id TEXT PRIMARY KEY,
              mapping_domain_id TEXT NOT NULL,
              task_node_id TEXT NOT NULL,
              target_node_version_ref TEXT NOT NULL,
              upstream_source_refs TEXT NOT NULL,
              executor_refs TEXT NOT NULL DEFAULT '[]',
              executor_agent_id TEXT,
              status TEXT NOT NULL,
              last_trigger_revision_id TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              waiting_reason TEXT,
              UNIQUE (mapping_domain_id, task_node_id, target_node_version_ref)
            );
            CREATE TABLE IF NOT EXISTS handoff_dispatch (
              dispatch_id TEXT PRIMARY KEY,
              pending_handoff_id TEXT NOT NULL,
              dedupe_key TEXT NOT NULL,
              message_type TEXT NOT NULL,
              target_agent_id TEXT,
              status TEXT NOT NULL,
              attempt_count INTEGER NOT NULL,
              error_summary TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE (dedupe_key)
            );
            CREATE TABLE IF NOT EXISTS completed_fact (
              mapping_domain_id TEXT NOT NULL,
              task_node_id TEXT NOT NULL,
              version_ref TEXT NOT NULL,
              completed_at TEXT NOT NULL,
              PRIMARY KEY (mapping_domain_id, task_node_id, version_ref)
            );
            CREATE TABLE IF NOT EXISTS domain_state (
              mapping_domain_id TEXT PRIMARY KEY,
              latest_formal_revision_id TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshot_failure (
              mapping_domain_id TEXT NOT NULL,
              formal_revision_id TEXT NOT NULL,
              reason TEXT NOT NULL,
              recorded_at TEXT NOT NULL,
              PRIMARY KEY (mapping_domain_id, formal_revision_id)
            );
            """
        )
        # ai4-quvy: migrate pre-existing stores to the waiting_reason column.
        try:
            self.conn.execute("ALTER TABLE pending_handoff ADD COLUMN waiting_reason TEXT")
            self.conn.commit()
        except sqlite3.OperationalError:
            # Column already exists; the CREATE TABLE above has it for new stores.
            pass
        self.conn.commit()

    def upsert_pending_handoff(
        self,
        mapping_domain_id: str,
        task_node_id: str,
        target_node_version_ref: str,
        upstream_source_refs: tuple[tuple[str, str], ...],
        executor_refs: tuple[str, ...],
        status: str,
        trigger_revision_id: str | None,
        waiting_reason: str | None = None,
    ) -> PendingHandoff:
        now = now_iso()
        existing = self.get_pending_handoff(mapping_domain_id, task_node_id, target_node_version_ref)
        if existing is not None:
            if existing.status == PENDING_DONE:
                # ai4-zc85: done is terminal; a recompute after completion must
                # not overwrite the published fact (nor blow up the loop). Log a
                # requested status that differs so a caller is not silently
                # ignored (ai4-onvr).
                if status != PENDING_DONE:
                    _log.info(
                        "pending %s is done; ignoring requested status %s for %s",
                        task_node_id, status, mapping_domain_id,
                    )
                return existing
            self._guard_transition(existing, status)
            self.conn.execute(
                """
                UPDATE pending_handoff
                SET upstream_source_refs = ?, executor_refs = ?, status = ?,
                    last_trigger_revision_id = ?, updated_at = ?, waiting_reason = ?
                WHERE pending_handoff_id = ?
                """,
                (
                    json.dumps(list(upstream_source_refs)),
                    json.dumps(list(executor_refs)),
                    status,
                    trigger_revision_id,
                    now,
                    waiting_reason,
                    existing.pending_handoff_id,
                ),
            )
            self.conn.commit()
            return self.get_pending_handoff(mapping_domain_id, task_node_id, target_node_version_ref)
        pending_handoff_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO pending_handoff (
              pending_handoff_id, mapping_domain_id, task_node_id, target_node_version_ref,
              upstream_source_refs, executor_refs, executor_agent_id, status, last_trigger_revision_id,
              created_at, updated_at, waiting_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pending_handoff_id,
                mapping_domain_id,
                task_node_id,
                target_node_version_ref,
                json.dumps(list(upstream_source_refs)),
                json.dumps(list(executor_refs)),
                executor_refs[0] if executor_refs else None,
                status,
                trigger_revision_id,
                now,
                now,
                waiting_reason,
            ),
        )
        self.conn.commit()
        return self.get_pending_handoff(mapping_domain_id, task_node_id, target_node_version_ref)

    def get_pending_handoff(
        self, mapping_domain_id: str, task_node_id: str, target_node_version_ref: str
    ) -> PendingHandoff | None:
        row = self.conn.execute(
            """
            SELECT * FROM pending_handoff
            WHERE mapping_domain_id = ? AND task_node_id = ? AND target_node_version_ref = ?
            """,
            (mapping_domain_id, task_node_id, target_node_version_ref),
        ).fetchone()
        return self._row_to_pending(row)

    def get_pending_handoff_by_id(self, pending_handoff_id: str) -> PendingHandoff | None:
        row = self.conn.execute(
            "SELECT * FROM pending_handoff WHERE pending_handoff_id = ?", (pending_handoff_id,)
        ).fetchone()
        return self._row_to_pending(row)

    def list_pending_handoffs(self, statuses: tuple[str, ...] | None = None) -> list[PendingHandoff]:
        if statuses is None:
            rows = self.conn.execute("SELECT * FROM pending_handoff ORDER BY created_at").fetchall()
        else:
            placeholders = ", ".join("?" for _ in statuses)
            rows = self.conn.execute(
                f"SELECT * FROM pending_handoff WHERE status IN ({placeholders}) ORDER BY created_at",
                statuses,
            ).fetchall()
        return [self._row_to_pending(row) for row in rows]

    def set_pending_handoff_status(
        self,
        mapping_domain_id: str,
        task_node_id: str,
        target_node_version_ref: str,
        status: str,
        trigger_revision_id: str | None = None,
    ) -> PendingHandoff | None:
        existing = self.get_pending_handoff(mapping_domain_id, task_node_id, target_node_version_ref)
        if existing is None:
            return None
        if existing.status == PENDING_DONE and status != PENDING_DONE:
            # done is terminal; recovery / recompute must never roll it back.
            return existing
        self._guard_transition(existing, status)
        now = now_iso()
        self.conn.execute(
            """
            UPDATE pending_handoff
            SET status = ?, last_trigger_revision_id = COALESCE(?, last_trigger_revision_id), updated_at = ?
            WHERE mapping_domain_id = ? AND task_node_id = ? AND target_node_version_ref = ?
            """,
            (status, trigger_revision_id, now, mapping_domain_id, task_node_id, target_node_version_ref),
        )
        self.conn.commit()
        return self.get_pending_handoff(mapping_domain_id, task_node_id, target_node_version_ref)

    def _guard_transition(self, pending: PendingHandoff, next_status: str) -> None:
        # Same-state rewrite is an idempotent recompute (e.g. waiting kept
        # waiting across two events); everything else must follow the table.
        if next_status == pending.status:
            return
        allowed = _PENDING_TRANSITIONS.get(pending.status, frozenset())
        if next_status not in allowed:
            raise InvalidPendingTransition(
                f"{pending.status} -> {next_status} for {pending.task_node_id}",
                current=pending.status,
                requested=next_status,
                task_node_id=pending.task_node_id,
            )

    def mark_superseded(self, mapping_domain_id: str, task_node_id: str, target_node_version_ref: str) -> PendingHandoff | None:
        """Mark a non-terminal pending fact superseded (version moved on)."""
        return self.set_pending_handoff_status(
            mapping_domain_id, task_node_id, target_node_version_ref, PENDING_SUPERSEDED
        )

    def record_completed(self, mapping_domain_id: str, task_node_id: str, version_ref: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO completed_fact (mapping_domain_id, task_node_id, version_ref, completed_at)
            VALUES (?, ?, ?, ?)
            """,
            (mapping_domain_id, task_node_id, version_ref, now_iso()),
        )
        self.conn.commit()

    def has_completed(self, mapping_domain_id: str, task_node_id: str, version_ref: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM completed_fact WHERE mapping_domain_id = ? AND task_node_id = ? AND version_ref = ?",
            (mapping_domain_id, task_node_id, version_ref),
        ).fetchone()
        return row is not None

    def set_latest_revision(self, mapping_domain_id: str, formal_revision_id: str) -> None:
        self.conn.execute(
            """
            INSERT INTO domain_state (mapping_domain_id, latest_formal_revision_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT (mapping_domain_id)
            DO UPDATE SET latest_formal_revision_id = excluded.latest_formal_revision_id, updated_at = excluded.updated_at
            """,
            (mapping_domain_id, formal_revision_id, now_iso()),
        )
        self.conn.commit()

    def get_latest_revision(self, mapping_domain_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT latest_formal_revision_id FROM domain_state WHERE mapping_domain_id = ?",
            (mapping_domain_id,),
        ).fetchone()
        return row["latest_formal_revision_id"] if row is not None else None

    def list_domains(self) -> list[str]:
        rows = self.conn.execute("SELECT mapping_domain_id FROM domain_state ORDER BY mapping_domain_id").fetchall()
        return [row["mapping_domain_id"] for row in rows]

    def record_snapshot_failure(
        self, mapping_domain_id: str, formal_revision_id: str, reason: str
    ) -> None:
        """Record that a formal snapshot could not be read (ai4-98ye).

        One row per (domain, revision): the point is that the fact is
        observable, not that every retry is counted. Without it a silent skip
        is indistinguishable from "this domain had nothing to dispatch".
        """
        self.conn.execute(
            """
            INSERT INTO snapshot_failure (mapping_domain_id, formal_revision_id, reason, recorded_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (mapping_domain_id, formal_revision_id)
            DO UPDATE SET reason = excluded.reason, recorded_at = excluded.recorded_at
            """,
            (mapping_domain_id, formal_revision_id, reason, now_iso()),
        )
        self.conn.commit()

    def list_snapshot_failures(self) -> list[dict[str, str]]:
        rows = self.conn.execute(
            "SELECT * FROM snapshot_failure ORDER BY mapping_domain_id, formal_revision_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def clear_snapshot_failure(self, mapping_domain_id: str, formal_revision_id: str) -> None:
        self.conn.execute(
            "DELETE FROM snapshot_failure WHERE mapping_domain_id = ? AND formal_revision_id = ?",
            (mapping_domain_id, formal_revision_id),
        )
        self.conn.commit()

    def create_dispatch(
        self,
        pending_handoff_id: str,
        dedupe_key: str,
        message_type: str,
        target_agent_id: str | None,
    ) -> HandoffDispatch | None:
        """Create a dispatch record idempotently. Returns None when the dedupe_key already exists."""
        existing = self.conn.execute(
            "SELECT * FROM handoff_dispatch WHERE dedupe_key = ?", (dedupe_key,)
        ).fetchone()
        if existing is not None:
            return self._row_to_dispatch(existing)
        now = now_iso()
        dispatch_id = uuid.uuid4().hex
        try:
            self.conn.execute(
                """
                INSERT INTO handoff_dispatch (
                  dispatch_id, pending_handoff_id, dedupe_key, message_type, target_agent_id,
                  status, attempt_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    dispatch_id,
                    pending_handoff_id,
                    dedupe_key,
                    message_type,
                    target_agent_id,
                    DISPATCH_CREATED,
                    now,
                    now,
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            self.conn.rollback()
            existing = self.conn.execute(
                "SELECT * FROM handoff_dispatch WHERE dedupe_key = ?", (dedupe_key,)
            ).fetchone()
            return self._row_to_dispatch(existing)
        return self._row_to_dispatch(
            self.conn.execute("SELECT * FROM handoff_dispatch WHERE dispatch_id = ?", (dispatch_id,)).fetchone()
        )

    def get_dispatch(self, dispatch_id: str) -> HandoffDispatch | None:
        row = self.conn.execute("SELECT * FROM handoff_dispatch WHERE dispatch_id = ?", (dispatch_id,)).fetchone()
        return self._row_to_dispatch(row)

    def list_dispatches(self, statuses: tuple[str, ...] | None = None) -> list[HandoffDispatch]:
        if statuses is None:
            rows = self.conn.execute("SELECT * FROM handoff_dispatch ORDER BY created_at").fetchall()
        else:
            placeholders = ", ".join("?" for _ in statuses)
            rows = self.conn.execute(
                f"SELECT * FROM handoff_dispatch WHERE status IN ({placeholders}) ORDER BY created_at",
                statuses,
            ).fetchall()
        return [self._row_to_dispatch(row) for row in rows]

    def set_dispatch_status(
        self, dispatch_id: str, status: str, error_summary: str | None = None, attempt_count: int | None = None
    ) -> HandoffDispatch | None:
        now = now_iso()
        self.conn.execute(
            """
            UPDATE handoff_dispatch
            SET status = ?, error_summary = COALESCE(?, error_summary),
                attempt_count = COALESCE(?, attempt_count), updated_at = ?
            WHERE dispatch_id = ?
            """,
            (status, error_summary, attempt_count, now, dispatch_id),
        )
        self.conn.commit()
        return self.get_dispatch(dispatch_id)

    @staticmethod
    def _row_to_pending(row: sqlite3.Row | None) -> PendingHandoff | None:
        if row is None:
            return None
        return PendingHandoff(
            pending_handoff_id=row["pending_handoff_id"],
            mapping_domain_id=row["mapping_domain_id"],
            task_node_id=row["task_node_id"],
            target_node_version_ref=row["target_node_version_ref"],
            upstream_source_refs=tuple(
                (item[0], item[1]) for item in json.loads(row["upstream_source_refs"])
            ),
            executor_refs=tuple(
                str(item) for item in json.loads(row["executor_refs"] or "[]")
            ),
            executor_agent_id=row["executor_agent_id"],
            status=row["status"],
            last_trigger_revision_id=row["last_trigger_revision_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            waiting_reason=row["waiting_reason"] if "waiting_reason" in row.keys() else None,
        )

    @staticmethod
    def _row_to_dispatch(row: sqlite3.Row | None) -> HandoffDispatch | None:
        if row is None:
            return None
        return HandoffDispatch(
            dispatch_id=row["dispatch_id"],
            pending_handoff_id=row["pending_handoff_id"],
            dedupe_key=row["dedupe_key"],
            message_type=row["message_type"],
            target_agent_id=row["target_agent_id"],
            status=row["status"],
            attempt_count=row["attempt_count"],
            error_summary=row["error_summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )