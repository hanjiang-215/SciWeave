"""Worker runner for one execution, driven by the subscriber process.

This module mirrors the durable lease discipline of ``gateway.app`` without
sharing MCP code: the same SQLite store is shared, the state machine is the
single source of truth, and only the caller that acquired the lease runs the
Worker loop for a target.

The outcome is written back through the shared store.  When the runtime reports
``completed`` and a draft writer is configured, the result is pushed to the
central draft buffer first; only a successful draft write flips the record to
``completed`` with a ``draft_id``.  A failed draft write flips it to ``failed``
with error summary ``draft_submission_failed``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from task_agent_worker.store import ExecutionStore, utc_now

from .service import SubscriberService


@dataclass(frozen=True)
class WorkerRequest:
    """Execution identity passed to one Worker loop (mirrors the worker runtime)."""

    execution_id: str
    task_node_id: str
    session_id: str
    command_text: str


class RuntimeOutcomeLike(Protocol):
    status: str
    result_summary: str | None
    error_summary: str | None


class RuntimeLike(Protocol):
    def run(self, request: WorkerRequest) -> RuntimeOutcomeLike: ...
    def resume(self, request: WorkerRequest) -> RuntimeOutcomeLike: ...


class DraftWriter(Protocol):
    def write(self, *, execution: dict[str, Any], result_summary: str) -> str:
        """Persist one execution result into the central draft buffer and return its id."""


class DraftWriteError(Exception):
    """Thrown by a DraftWriter when the central draft buffer rejects the write."""


class SubscriberWorkerRunner:
    """Claims the lease, runs one Worker loop, and persists the terminal state."""

    def __init__(
        self,
        store: ExecutionStore,
        service: SubscriberService,
        runtime: RuntimeLike,
        draft_writer: DraftWriter | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.runtime = runtime
        self.draft_writer = draft_writer

    def run_once(self, task_node_id: str) -> dict[str, Any] | None:
        """Claim and execute the next queued record of one target.

        Returns the terminal execution dict, or ``None`` when nothing is queued.
        Only one Worker runs per target at a time because the lease insert is
        atomic; different targets may run concurrently.
        """
        claimed = self._claim(task_node_id)
        if claimed is None:
            return None
        return self._execute(claimed)

    def _claim(self, task_node_id: str) -> dict[str, Any] | None:
        now = utc_now()
        with self.store.transaction() as connection:
            existing_lease = connection.execute(
                "SELECT execution_id FROM worker_leases WHERE task_node_id = ?",
                (task_node_id,),
            ).fetchone()
            if existing_lease is not None:
                return None
            queued = connection.execute(
                """SELECT execution_id, task_node_id, session_id, trigger, trigger_ref,
                          business_key, resume_of, revision_of
                   FROM execution_records
                   WHERE task_node_id = ? AND status = 'queued'
                   ORDER BY created_at, rowid LIMIT 1""",
                (task_node_id,),
            ).fetchone()
            if queued is None:
                return None
            try:
                connection.execute(
                    "INSERT INTO worker_leases VALUES (?, ?, ?)",
                    (task_node_id, queued["execution_id"], now),
                )
            except Exception:
                return None
            connection.execute(
                "UPDATE execution_records SET status = 'running', started_at = ?, updated_at = ? WHERE execution_id = ?",
                (now, now, queued["execution_id"]),
            )
            connection.execute(
                """INSERT INTO audit_events
                   (event_type, task_node_id, execution_id, details, created_at)
                   VALUES ('worker_lease_acquired', ?, ?, '{}', ?)""",
                (task_node_id, queued["execution_id"], now),
            )
            return dict(queued)

    def _execute(self, claimed: dict[str, Any]) -> dict[str, Any]:
        request = WorkerRequest(
            execution_id=claimed["execution_id"],
            task_node_id=claimed["task_node_id"],
            session_id=claimed["session_id"],
            command_text=f"Execute TaskNode {claimed['task_node_id']} triggered by {claimed.get('trigger_ref') or ''}".strip(),
        )
        try:
            outcome = self.runtime.resume(request) if claimed.get("resume_of") else self.runtime.run(request)
        except Exception:
            outcome = _Failed("runtime_exception")
        if outcome.status not in {"completed", "waiting", "failed", "cancelled"}:
            outcome = _Failed("invalid_runtime_outcome")

        draft_id: str | None = None
        if outcome.status == "completed" and self.draft_writer is not None:
            try:
                draft_id = self.draft_writer.write(
                    execution=claimed,
                    result_summary=outcome.result_summary or "",
                )
            except DraftWriteError:
                return self._persist(claimed, "failed", error_summary="draft_submission_failed")
            if draft_id is None:
                return self._persist(claimed, "failed", error_summary="draft_submission_failed")
        return self._persist(
            claimed,
            outcome.status,
            result_summary=outcome.result_summary,
            error_summary=outcome.error_summary,
            draft_id=draft_id,
        )

    def _persist(
        self,
        claimed: dict[str, Any],
        status: str,
        *,
        result_summary: str | None = None,
        error_summary: str | None = None,
        draft_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.store.transaction() as connection:
            updated = connection.execute(
                """UPDATE execution_records SET status = ?, result_summary = ?,
                   error_summary = ?, draft_id = ?, finished_at = ?, updated_at = ?
                   WHERE execution_id = ? AND status = 'running'""",
                (status, result_summary, error_summary, draft_id, now, now, claimed["execution_id"]),
            )
            if updated.rowcount == 0:
                # The record left 'running' while the Worker was busy: a cancel
                # (or another terminal write) landed first. Keep that state
                # instead of overwriting it, and release the lease (ai4-k6m2).
                connection.execute(
                    "DELETE FROM worker_leases WHERE execution_id = ?",
                    (claimed["execution_id"],),
                )
                current = connection.execute(
                    "SELECT * FROM execution_records WHERE execution_id = ?",
                    (claimed["execution_id"],),
                ).fetchone()
                return dict(current) if current is not None else dict(claimed)
            connection.execute(
                "DELETE FROM worker_leases WHERE execution_id = ?",
                (claimed["execution_id"],),
            )
            event = {
                "completed": "worker_completed",
                "waiting": "worker_waiting",
                "cancelled": "worker_cancelled",
                "failed": "worker_failed",
            }.get(status, "worker_terminal")
            connection.execute(
                """INSERT INTO audit_events
                   (event_type, task_node_id, execution_id, details, created_at)
                   VALUES (?, ?, ?, '{}', ?)""",
                (event, claimed["task_node_id"], claimed["execution_id"], now),
            )
        return {
            **claimed,
            "status": status,
            "result_summary": result_summary,
            "error_summary": error_summary,
            "draft_id": draft_id,
            "finished_at": now,
        }


class _Failed:
    status = "failed"

    def __init__(self, error_summary: str) -> None:
        self.result_summary = None
        self.error_summary = error_summary