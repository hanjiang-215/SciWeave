"""Append-only interface-call audit ledger."""

from __future__ import annotations

import contextlib
import datetime as _datetime
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Iterator


_LOG = logging.getLogger("audit_trail")
_CALLER_TYPES = {"human", "agent", "system", "service"}
_RESULTS = {"ok", "error", "denied", "unknown"}
_PHASES = {"invoked", "completed", "attempted"}
# The ledger is opened once per service and shared by a threaded MCP HTTP
# server. sqlite3 connections default to same-thread use; the shared package
# therefore allows cross-thread access and serializes every ledger operation
# with one re-entrant lock so a single connection stays safe.
_CONNECTION_LOCK = threading.RLock()


class AuditUnavailableError(RuntimeError):
    """The audit database could not be opened or written."""


class AuditValidationError(ValueError):
    """A record or call lifecycle operation is invalid."""


@dataclass(frozen=True, slots=True)
class CallRecord:
    caller_id: str
    channel_id: str
    caller_type: str
    service: str
    tool: str
    target_object_type: str | None = None
    target_object_id: str | None = None
    args_digest: str | None = None
    error_code: str | None = None
    duration_ms: int | None = None
    refs: str | None = None

    def __post_init__(self) -> None:
        for name in ("caller_id", "channel_id", "caller_type", "service", "tool"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise AuditValidationError(f"{name} must be a non-empty string")
        if self.caller_type not in _CALLER_TYPES:
            raise AuditValidationError(f"invalid caller_type: {self.caller_type}")
        for name in ("target_object_type", "target_object_id", "args_digest", "error_code", "refs"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise AuditValidationError(f"{name} must be a string or None")
        if self.duration_ms is not None and (
            not isinstance(self.duration_ms, int) or self.duration_ms < 0
        ):
            raise AuditValidationError("duration_ms must be a non-negative integer or None")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_call (
    call_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    caller_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    caller_type TEXT NOT NULL CHECK (caller_type IN ('human', 'agent', 'system', 'service')),
    service TEXT NOT NULL,
    tool TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('invoked', 'completed', 'attempted')),
    result TEXT NOT NULL CHECK (result IN ('ok', 'error', 'denied', 'unknown')),
    target_object_type TEXT,
    target_object_id TEXT,
    args_digest TEXT,
    error_code TEXT,
    duration_ms INTEGER,
    refs TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_call_service_tool_time
    ON audit_call (service, tool, occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_call_target_time
    ON audit_call (target_object_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_call_caller_time
    ON audit_call (caller_id, occurred_at);
"""


def _now() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def open_connection(path: str, *, busy_timeout_ms: int = 5000, journal_mode: str = "WAL") -> sqlite3.Connection:
    if not isinstance(path, str) or not path:
        raise AuditValidationError("path must be a non-empty string")
    if not isinstance(busy_timeout_ms, int) or busy_timeout_ms < 0:
        raise AuditValidationError("busy_timeout_ms must be a non-negative integer")
    try:
        # check_same_thread=False lets one ledger connection serve the threaded
        # MCP HTTP server; all accessors serialize through _CONNECTION_LOCK.
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        try:
            if not isinstance(journal_mode, str) or not journal_mode:
                raise AuditValidationError("journal_mode must be a non-empty string")
            escaped_mode = journal_mode.replace("'", "''")
            conn.execute(f"PRAGMA journal_mode = '{escaped_mode}'")
        except sqlite3.DatabaseError:
            _LOG.debug("journal_mode %r unavailable; continuing", journal_mode)
        return conn
    except (sqlite3.Error, OSError) as exc:
        raise AuditUnavailableError("cannot open audit database") from exc


def init_audit_table(conn: sqlite3.Connection) -> None:
    with _CONNECTION_LOCK:
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
            try:
                conn.execute("PRAGMA journal_mode = 'WAL'")
            except sqlite3.DatabaseError:
                _LOG.debug("journal_mode 'WAL' unavailable; continuing")
            conn.executescript(_SCHEMA)
        except sqlite3.Error as exc:
            raise AuditUnavailableError("cannot initialize audit database") from exc


def _insert(conn: sqlite3.Connection, values: tuple[object, ...]) -> None:
    if conn.in_transaction:
        raise AuditValidationError("audit append cannot run inside a transaction")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO audit_call (call_id, occurred_at, caller_id, channel_id, caller_type, "
            "service, tool, phase, result, target_object_type, target_object_id, args_digest, "
            "error_code, duration_ms, refs) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _record_values(call_id: str, record: CallRecord, phase: str, result: str) -> tuple[object, ...]:
    return (call_id, _now(), record.caller_id, record.channel_id, record.caller_type,
            record.service, record.tool, phase, result, record.target_object_type,
            record.target_object_id, record.args_digest, record.error_code,
            record.duration_ms, record.refs)


def record_attempted(conn: sqlite3.Connection, record: CallRecord) -> str | None:
    call_id = _new_call_id()
    try:
        with _CONNECTION_LOCK:
            _insert(conn, _record_values(call_id, record, "attempted", "unknown"))
    except AuditValidationError:
        raise
    except Exception as exc:
        _LOG.warning("could not record attempted audit call: %s", exc)
        return None
    return call_id


def _new_call_id() -> str:
    import uuid
    return str(uuid.uuid4())


def begin_call(conn: sqlite3.Connection, record: CallRecord) -> str:
    call_id = _new_call_id()
    try:
        with _CONNECTION_LOCK:
            _insert(conn, _record_values(call_id, record, "invoked", "unknown"))
    except AuditValidationError:
        raise
    except Exception as exc:
        raise AuditUnavailableError("cannot record invoked audit call") from exc
    return call_id


def finish_call(conn: sqlite3.Connection, call_id: str, *, result: str,
                error_code: str | None = None, duration_ms: int | None = None) -> None:
    if result not in _RESULTS or result == "unknown":
        raise AuditValidationError("completed result must be ok, error, or denied")
    if duration_ms is not None and (not isinstance(duration_ms, int) or duration_ms < 0):
        raise AuditValidationError("duration_ms must be a non-negative integer or None")
    try:
        with _CONNECTION_LOCK:
            if conn.in_transaction:
                raise AuditValidationError("audit append cannot run inside a transaction")
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT 1 FROM audit_call WHERE call_id = ? AND phase = 'invoked' "
                "AND NOT EXISTS (SELECT 1 FROM audit_call c2 WHERE c2.call_id = audit_call.call_id "
                "AND c2.phase = 'completed') LIMIT 1", (call_id,)
            ).fetchone()
            if row is None:
                conn.rollback()
                raise AuditValidationError(f"no unfinished invoked call: {call_id}")
            conn.execute(
                "INSERT INTO audit_call SELECT call_id, ?, caller_id, channel_id, caller_type, service, tool, "
                "'completed', ?, target_object_type, target_object_id, args_digest, ?, ?, refs "
                "FROM audit_call WHERE call_id = ? AND phase = 'invoked' LIMIT 1",
                (_now(), result, error_code, duration_ms, call_id),
            )
            conn.commit()
    except AuditValidationError:
        raise
    except sqlite3.Error as exc:
        with contextlib.suppress(sqlite3.Error):
            conn.rollback()
        _LOG.warning("could not finish audit call %s: %s", call_id, exc)


def query_audit_calls(
    conn: sqlite3.Connection,
    *,
    caller_id: str | None = None,
    channel_id: str | None = None,
    service: str | None = None,
    tool: str | None = None,
    target_object_id: str | None = None,
    result: str | None = None,
    occurred_after: str | None = None,
    occurred_before: str | None = None,
) -> list[sqlite3.Row]:
    filters = {
        "caller_id": caller_id,
        "channel_id": channel_id,
        "service": service,
        "tool": tool,
        "target_object_id": target_object_id,
        "result": result,
        "occurred_after": occurred_after,
        "occurred_before": occurred_before,
    }
    allowed = {"caller_id", "channel_id", "service", "tool", "target_object_id", "result"}
    time_filters = {"occurred_after", "occurred_before"}
    unknown = (
        (set(filters) - allowed - time_filters)
        | {key for key, value in filters.items() if value is not None and not isinstance(value, str)}
    )
    if unknown:
        raise AuditValidationError(f"unsupported query filters: {sorted(unknown)}")
    clauses = []
    params: list[str] = []
    for key in allowed:
        if filters.get(key) is not None:
            clauses.append(f"{key} = ?")
            params.append(filters[key])
    for key, op in (("occurred_after", ">="), ("occurred_before", "<=")):
        value = filters.get(key)
        if value is not None:
            clauses.append(f"occurred_at {op} ?")
            params.append(value)
    sql = "SELECT * FROM audit_call"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY occurred_at DESC, rowid DESC"
    with _CONNECTION_LOCK:
        return list(conn.execute(sql, params).fetchall())


def find_unfinished_calls(conn: sqlite3.Connection, *, occurred_after: str | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM audit_call a WHERE a.phase = 'invoked' AND NOT EXISTS " \
          "(SELECT 1 FROM audit_call c WHERE c.call_id = a.call_id AND c.phase = 'completed')"
    params: list[str] = []
    if occurred_after is not None:
        sql += " AND a.occurred_at >= ?"
        params.append(occurred_after)
    sql += " ORDER BY a.occurred_at DESC, a.rowid DESC"
    with _CONNECTION_LOCK:
        return list(conn.execute(sql, params).fetchall())


@contextlib.contextmanager
def call_scope(conn: sqlite3.Connection, record: CallRecord, *, error_code: str | None = None) -> Iterator[str]:
    call_id = begin_call(conn, record)
    started = time.monotonic()
    try:
        yield call_id
    except Exception:
        finish_call(conn, call_id, result="error", error_code=error_code,
                    duration_ms=max(0, int((time.monotonic() - started) * 1000)))
        raise
    else:
        finish_call(conn, call_id, result="ok",
                    duration_ms=max(0, int((time.monotonic() - started) * 1000)))


__all__ = [
    "AuditUnavailableError", "AuditValidationError", "CallRecord", "begin_call",
    "call_scope", "finish_call", "find_unfinished_calls", "init_audit_table",
    "open_connection", "query_audit_calls", "record_attempted",
]
