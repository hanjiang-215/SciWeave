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

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from task_agent_worker.store import ExecutionStore, utc_now

from .service import SubscriberService

if TYPE_CHECKING:
    from .completion_publisher import CompletionPublisher


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
        completion_publisher: "CompletionPublisher | None" = None,
    ) -> None:
        self.store = store
        self.service = service
        self.runtime = runtime
        self.draft_writer = draft_writer
        self.completion_publisher = completion_publisher

    def run_once(self, task_node_id: str) -> dict[str, Any] | None:
        """Claim and execute the next queued record of one target.

        Returns the terminal execution dict, or ``None`` when nothing is queued.
        Only one Worker runs per target at a time because the lease insert is
        atomic; different targets may run concurrently.
        """
        # ai4-odwi: replay any completion event a previous crash left staged
        # before doing new work, so the queue self-heals on the next iteration.
        self.drain_outbox()
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
                          business_key, resume_of, revision_of, mapping_domain_id
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
        completion_event: dict[str, Any] | None = None
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
            if status == "completed" and self.completion_publisher is not None:
                # ai4-odwi: stage the task_completed event in the SAME
                # transaction as the terminal state, so a crash after commit but
                # before publish can never lose it -- the drain below or the next
                # run_once() replays it from the outbox.
                completion_event = {
                    "execution_id": claimed["execution_id"],
                    "task_node_id": claimed["task_node_id"],
                    "mapping_domain_id": claimed.get("mapping_domain_id"),
                    "business_key": claimed.get("business_key"),
                    "draft_id": draft_id,
                    "finished_at": now,
                }
                self.store.record_outbox_event(
                    connection,
                    event_type="task_completed",
                    dedupe_key=f"task_completed:{claimed['execution_id']}",
                    payload_json=json.dumps(completion_event, ensure_ascii=False),
                    created_at=now,
                )
        result = {
            **claimed,
            "status": status,
            "result_summary": result_summary,
            "error_summary": error_summary,
            "draft_id": draft_id,
            "finished_at": now,
        }
        # Best-effort immediate delivery; anything still pending is retried by
        # drain_outbox() (called at the start of every run_once and the CLI).
        if status == "completed" and self.completion_publisher is not None:
            self.drain_outbox()
        return result

    def drain_outbox(self) -> int:
        """Publish any staged governance events not yet confirmed (ai4-odwi).

        Returns the number of events successfully delivered. Idempotent: a row is
        only marked published after the publisher returns without raising.
        """
        if self.completion_publisher is None:
            return 0
        delivered = 0
        for row in self.store.pending_outbox_events():
            try:
                payload = json.loads(row["payload_json"])
                self.completion_publisher.publish(execution=payload)
            except Exception:  # noqa: BLE001 - leave it pending for the next drain
                self.store.mark_outbox_failed(row["outbox_id"], "publish_failed")
                continue
            self.store.mark_outbox_published(row["outbox_id"], utc_now())
            delivered += 1
        return delivered


class _Failed:
    status = "failed"

    def __init__(self, error_summary: str) -> None:
        self.result_summary = None
        self.error_summary = error_summary