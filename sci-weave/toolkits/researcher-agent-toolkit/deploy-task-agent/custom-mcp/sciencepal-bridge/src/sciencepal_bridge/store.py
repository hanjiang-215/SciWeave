"""Small SQLite ledger for run idempotency and artifact manifests."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  thread_id TEXT,
  execution_id TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  agent_id TEXT,
  error TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
  run_id TEXT NOT NULL,
  name TEXT NOT NULL,
  path TEXT NOT NULL,
  size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  kind TEXT NOT NULL,
  PRIMARY KEY (run_id, path)
);
"""


class RunStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def find_by_idempotency(self, key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return dict(row) if row else None

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def add_run(
        self,
        *,
        run_id: str,
        thread_id: str | None,
        execution_id: str | None,
        idempotency_key: str,
        status: str,
        agent_id: str | None,
    ) -> dict[str, Any]:
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs
                  (run_id, thread_id, execution_id, idempotency_key, status, agent_id, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (run_id, thread_id, execution_id, idempotency_key, status, agent_id, now, now),
            )
        return self.get(run_id) or {}

    def update_status(self, run_id: str, status: str, error: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, error = ?, updated_at = ? WHERE run_id = ?",
                (status, error, time.time(), run_id),
            )

    def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name, path, size, sha256, kind FROM artifacts WHERE run_id = ? ORDER BY path",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_artifacts(self, run_id: str, artifacts: list[dict[str, Any]]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO artifacts (run_id, name, path, size, sha256, kind)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        str(item["name"]),
                        str(item["path"]),
                        int(item["size"]),
                        str(item["sha256"]),
                        str(item["kind"]),
                    )
                    for item in artifacts
                ],
            )
