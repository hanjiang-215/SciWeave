from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class ExecutionRecord:
    """Public projection of one Work Agent execution."""

    execution_id: str
    target_id: str
    status: str
    draft_id: str | None = None
    error_code: str | None = None
    failed_agent: str | None = None
    #: Where `draft_id` came from: ``runtime`` when this process read it off the
    #: draft box, ``agent_reported`` when the agent told us what it wrote
    #: (ai4-x0ay). The difference matters: the second is an unverified claim.
    draft_id_source: str | None = None


# Short compatibility name for callers that used the initial runtime prototype.
Execution = ExecutionRecord


class ExecutionStore:
    """Thread-safe execution record store used by the runtime boundary."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_event: dict[str, ExecutionRecord] = {}
        self._by_target: dict[str, ExecutionRecord] = {}

    def enqueue(self, target_id: str, event_id: str) -> ExecutionRecord:
        with self._lock:
            existing = self._by_event.get(event_id)
            if existing is not None:
                return existing
            execution = ExecutionRecord(str(uuid.uuid4()), target_id, "queued")
            self._by_event[event_id] = execution
            current = self._by_target.get(target_id)
            if current is None or current.status in {"completed", "failed"}:
                self._by_target[target_id] = execution
            return execution

    def start(self, execution: ExecutionRecord) -> bool:
        with self._lock:
            current = self._by_target.get(execution.target_id)
            if current is not execution or execution.status != "queued":
                return False
            updated = ExecutionRecord(execution.execution_id, execution.target_id, "running")
            self._replace(updated)
            return True

    def complete(self, execution: ExecutionRecord, draft_id: str, draft_id_source: str | None = None) -> ExecutionRecord:
        with self._lock:
            updated = ExecutionRecord(execution.execution_id, execution.target_id, "completed", draft_id, draft_id_source=draft_id_source)
            self._replace(updated)
            return updated

    def fail(self, execution: ExecutionRecord, error_code: str, failed_agent: str | None = None) -> ExecutionRecord:
        with self._lock:
            updated = ExecutionRecord(execution.execution_id, execution.target_id, "failed", None, error_code, failed_agent)
            self._replace(updated)
            return updated

    def get(self, execution_id: str) -> ExecutionRecord | None:
        with self._lock:
            return next(
                (item for item in self._by_event.values() if item.execution_id == execution_id),
                None,
            )

    def get_by_event(self, event_id: str) -> ExecutionRecord | None:
        with self._lock:
            return self._by_event.get(event_id)

    def _replace(self, updated: ExecutionRecord) -> None:
        for event_id, current in self._by_event.items():
            if current.execution_id == updated.execution_id:
                self._by_event[event_id] = updated
                break
        self._by_target[updated.target_id] = updated


# `WorkerLease` moved to `lease.py` when it gained a SQLite backing store
# (ai4-0fwc). Re-exported here so the many existing imports keep working.
from .lease import LeaseHeldError, WorkerLease  # noqa: E402  (after the dataclasses)


class DraftBox(Protocol):
    """Where a finished run leaves its draft.

    One shape only: ``write`` keyword arguments. The real writer
    (``BufferMCPDraftWriter``) and the in-memory double both implement it, so
    the runtime cannot be wired to a collaborator that lacks the method.
    """

    def write(self, *, target_id: str, payload: str) -> str: ...


class FakeDraftBox:
    def write(self, *, target_id: str, payload: str) -> str:
        return f"draft-{target_id}-{uuid.uuid4().hex[:8]}"


class WorkAgentRuntime:
    """The sole runtime seam used by all three service templates.

    ``handle_message`` keeps the legacy in-memory path (tests and local demos).
    ``handle_inbound`` is the durable inbox-first path used by the real
    subscriber: the message is recorded before any execution, a missing
    workflow binding keeps it ``awaiting_workflow_binding``, and duplicates or
    restarts are recovered from the inbox instead of being re-run.
    """

    def __init__(
        self,
        drafts: DraftBox | None = None,
        inbox: object | None = None,
        binding_resolver: Callable[[str], bool] | None = None,
        dispatcher: Callable[[str], object] | None = None,
    ) -> None:
        self.store = ExecutionStore()
        self.lease = WorkerLease()
        self.drafts: DraftBox = drafts or FakeDraftBox()
        self.inbox = inbox
        self.binding_resolver = binding_resolver
        # A callable that runs the handoff *somewhere else* and returns an
        # object with a ``status``. The subscriber passes one that spawns a
        # worker subprocess (ai4-0fwc); without it the runtime runs inline.
        self.dispatcher = dispatcher

    def handle_message(self, target_id: str, event_id: str, agent_definition: str = "") -> ExecutionRecord:
        return run_one(self.store, self.lease, self.drafts, target_id, event_id, agent_definition)

    def handle_inbound(
        self,
        target_id: str,
        event_id: str,
        agent_definition: str = "",
        *,
        task_text: str = "",
    ) -> ExecutionRecord:
        """Durable inbox-first path; falls back to ``handle_message`` without an inbox.

        Returns an ``ExecutionRecord`` whose ``status`` is
        ``awaiting_workflow_binding`` when the workflow binding is missing, or
        the completed/completed-or-duplicate execution otherwise.

        ``task_text`` is this handoff's instruction, recorded so the worker can
        hand it to the model (ai4-1e9e). It is stored even when empty: an empty
        value says "the producer sent no task text", which the worker turns into
        an explicit instruction instead of letting a node id pass for one.
        """
        if self.inbox is None:
            return self.handle_message(target_id, event_id, agent_definition)
        dedupe_key = f"{target_id}:{event_id}"
        bound = self.binding_resolver(target_id) if self.binding_resolver is not None else True
        status, _created = self.inbox.enqueue(
            dedupe_key,
            target_id,
            event_id,
            agent_definition,
            binding_present=bound,
            command_text=task_text,
        )
        if status == "awaiting_workflow_binding":
            return ExecutionRecord(dedupe_key, target_id, "awaiting_workflow_binding")
        existing = self.store.get_by_event(event_id)
        if existing is not None:
            return existing
        if status == "processed":
            # Duplicate delivery after a restart: never re-run a processed row.
            return ExecutionRecord(dedupe_key, target_id, "processed")
        if self.dispatcher is not None:
            return self._dispatch(dedupe_key, target_id, event_id)
        try:
            record = run_one(self.store, self.lease, self.drafts, target_id, event_id, agent_definition)
        except Exception:
            # The row stays ``queued``: a crashed or failed run must be
            # replayable by drain_queued() after a restart. Marking it here
            # would swallow the message for good.
            raise
        self.inbox.mark_processed(dedupe_key)
        return record

    def _dispatch(self, dedupe_key: str, target_id: str, event_id: str) -> ExecutionRecord:
        """Hand the claimed row to a worker process and report what it did.

        The lease is taken **here**, in the resident process, and held across
        the subprocess' whole lifetime. That ordering is what makes the lease
        meaningful: the worker cannot take it (a different owner would be
        refused), and a second delivery for the same target is refused while
        the first is still running.

        The row is deliberately left for the worker to mark ``processed``. If
        this process died right now, the row would still be ``queued`` and
        `drain_queued()` would re-drive it — the same failure rule as the
        inline path, only with a wider window.
        """
        execution = self.store.enqueue(target_id, event_id)
        if getattr(self.dispatcher, "deferred", False):
            # Dispatch is switched off in this process (`SCIWEAVE_WORKER_DISPATCH=0`):
            # the two roles run as separate services, so the row is left alone
            # for the standalone worker. Nothing is started and nothing is
            # marked, which is what "separate services" has to mean.
            return execution
        if not self.lease.acquire(target_id):
            # Another live owner: leave the row queued for whoever holds it.
            return execution
        try:
            if not self.store.start(execution):
                return execution
            outcome = self.dispatcher(dedupe_key)
            status = str(getattr(outcome, "status", "failed"))
            current = self.store.get(execution.execution_id) or execution
            if status == "completed":
                return self.store.complete(current, str(getattr(outcome, "draft_id", "") or ""))
            return self.store.fail(
                current,
                str(getattr(outcome, "status", "worker_failed")),
            )
        finally:
            self.lease.release(target_id)

    def bind(self, dedupe_key: str) -> ExecutionRecord | None:
        """Establish a workflow binding: ``awaiting_workflow_binding`` -> ``queued`` and run."""
        if self.inbox is None:
            return None
        row = self.inbox.get(dedupe_key)
        if row is None:
            return None
        self.inbox.bind(dedupe_key)
        return self.handle_inbound(
            row["target_id"],
            row["event_id"],
            row["agent_definition"],
            task_text=row.get("command_text", ""),
        )

    def drain_queued(self) -> list[ExecutionRecord]:
        """Re-drive persisted ``queued`` rows (restart recovery) and return executions."""
        if self.inbox is None:
            return []
        results: list[ExecutionRecord] = []
        for row in self.inbox.list_status("queued"):
            results.append(
                self.handle_inbound(
                    row["target_id"],
                    row["event_id"],
                    row["agent_definition"],
                    task_text=row.get("command_text", ""),
                )
            )
        return results

    def run_workflow(self, target_id: str, event_id: str, config: object, agent: Callable[..., str], workflow_name: str, prompt: str) -> ExecutionRecord:
        """Run a configured multi-agent workflow under this one lease/record."""
        from .workflows import WorkflowExecutor

        execution = self.store.enqueue(target_id, event_id)
        if not self.lease.acquire(target_id):
            return execution
        try:
            if not self.store.start(execution):
                return execution
            result = WorkflowExecutor(config, agent, self.drafts).run(workflow_name, prompt, target_id=target_id)
            current = self.store.get(execution.execution_id) or execution
            if result.status == "completed":
                return self.store.complete(
                    current, result.draft_id or "", getattr(result, "draft_id_source", None)
                )
            return self.store.fail(current, result.error_code or "workflow_failed", result.failed_agent)
        finally:
            self.lease.release(target_id)


def run_one(
    store: ExecutionStore,
    lease: WorkerLease,
    drafts: DraftBox,
    target_id: str,
    event_id: str,
    agent_definition: str,
) -> ExecutionRecord:
    execution = store.enqueue(target_id, event_id)
    if not lease.acquire(target_id):
        return execution
    try:
        if not store.start(execution):
            return execution
        draft_id = drafts.write(target_id=target_id, payload=f"{agent_definition}:{event_id}")
        return store.complete(store.get(execution.execution_id) or execution, draft_id)
    finally:
        lease.release(target_id)
