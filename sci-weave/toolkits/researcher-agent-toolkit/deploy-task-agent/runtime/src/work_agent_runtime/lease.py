"""The Worker Lease, made durable enough to mean something (ai4-0fwc).

It used to be a `threading.Lock` plus a `set[str]` inside `WorkAgentRuntime`.
That is not a lease: it dies with the process, so two subscribers — or a
subscriber and a worker it spawned — never saw each other's holds. ADR-0002
puts the worker in a short-lived subprocess, which makes the in-process version
not merely weak but irrelevant.

This is a row in SQLite with an owner and an expiry. SQLite's own file locking
gives cross-process exclusion without a broker, and the expiry means a
subscriber that is killed mid-run does not hold a node forever.

Two shapes, on purpose:

``WorkerLease()``
    No path: the in-memory lock. Unit tests and the in-memory demo path, where
    there is exactly one process and a file would be noise.

``WorkerLease(path)``
    The real one. The subscriber passes the same SQLite file the inbox uses, so
    the lease and the inbox cannot disagree about which database is current.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

DEFAULT_LEASE_SECONDS = 1800.0


class LeaseHeldError(RuntimeError):
    """Another live owner holds this target."""


class WorkerLease:
    """Serialize work per target across processes.

    ``acquire`` returns False while *any* unexpired lease exists — including one
    this process took a moment ago. Letting the same owner re-acquire would make
    the lease useless as a guard: a second delivery in the same subscriber would
    silently renew the hold and start a competing worker, which is precisely the
    case the lease exists to stop.

    That leaves the long-call problem: the subscriber holds the lease while its
    worker runs, and a model call can outlast the TTL. `renew()` is the answer
    for a caller that can heartbeat; `WorkerSubprocess` cannot (it blocks in
    ``subprocess.run``), so the TTL is set generously and expiry is treated as
    "the previous owner is gone", never as "steal it". A steal would run two
    workers on one node; waiting for the TTL would stall a queue. 30 minutes of
    a blocked model call is already a failure worth replaying.
    """

    def __init__(self, path: str | Path | None = None, *, ttl_seconds: float = DEFAULT_LEASE_SECONDS, owner: str | None = None) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.path = None if path is None else str(path)
        self.ttl_seconds = float(ttl_seconds)
        self.owner = owner or f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._lock = threading.RLock()
        self._targets: set[str] = set()
        self._connection = None
        if self.path is not None:
            import sqlite3

            self._connection = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS worker_lease (
                    target_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    acquired_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
            )

    @property
    def durable(self) -> bool:
        return self._connection is not None

    def acquire(self, target_id: str) -> bool:
        if self._connection is None:
            with self._lock:
                if target_id in self._targets:
                    return False
                self._targets.add(target_id)
                return True
        now = time.time()
        with self._lock:
            try:
                # BEGIN IMMEDIATE takes the write lock before the read, so two
                # processes cannot both read "free" and then both write.
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT owner, expires_at FROM worker_lease WHERE target_id = ?",
                    (target_id,),
                ).fetchone()
                if row is not None and row["expires_at"] > now:
                    self._connection.rollback()
                    return False
                self._connection.execute(
                    """INSERT INTO worker_lease (target_id, owner, acquired_at, expires_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(target_id) DO UPDATE SET
                         owner = excluded.owner,
                         acquired_at = excluded.acquired_at,
                         expires_at = excluded.expires_at""",
                    (target_id, self.owner, now, now + self.ttl_seconds),
                )
                self._connection.commit()
                return True
            except Exception:
                self._connection.rollback()
                raise

    def renew(self, target_id: str) -> bool:
        """Extend a lease this owner still holds; False when it is gone."""
        if self._connection is None:
            with self._lock:
                return target_id in self._targets
        now = time.time()
        with self._lock:
            cursor = self._connection.execute(
                """UPDATE worker_lease SET expires_at = ?
                   WHERE target_id = ? AND owner = ? AND expires_at > ?""",
                (now + self.ttl_seconds, target_id, self.owner, now),
            )
            self._connection.commit()
            return cursor.rowcount == 1

    def release(self, target_id: str) -> None:
        if self._connection is None:
            with self._lock:
                self._targets.discard(target_id)
            return
        with self._lock:
            self._connection.execute(
                "DELETE FROM worker_lease WHERE target_id = ? AND owner = ?", (target_id, self.owner)
            )
            self._connection.commit()

    def holder(self, target_id: str) -> str | None:
        """The live owner of ``target_id``, or None. Expired rows are invisible."""
        if self._connection is None:
            with self._lock:
                return self.owner if target_id in self._targets else None
        with self._lock:
            row = self._connection.execute(
                "SELECT owner, expires_at FROM worker_lease WHERE target_id = ?", (target_id,)
            ).fetchone()
        if row is None or row["expires_at"] <= time.time():
            return None
        return row["owner"]

    def reap(self) -> int:
        """Delete expired rows; returns how many. Safe to call from any process."""
        if self._connection is None:
            return 0
        with self._lock:
            cursor = self._connection.execute("DELETE FROM worker_lease WHERE expires_at <= ?", (time.time(),))
            self._connection.commit()
            return cursor.rowcount

    def __enter__(self) -> "WorkerLease":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is not None:
            with self._lock:
                self._connection.close()
                self._connection = None
