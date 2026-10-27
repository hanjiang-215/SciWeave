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

    def complete(self, execution: ExecutionRecord, draft_id: str) -> ExecutionRecord:
        with self._lock:
            updated = ExecutionRecord(execution.execution_id, execution.target_id, "completed", draft_id)
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


class WorkerLease:
    """Process-local lease that serializes work for one target."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._targets: set[str] = set()

    def acquire(self, target_id: str) -> bool:
        with self._lock:
            if target_id in self._targets:
                return False
            self._targets.add(target_id)
            return True

    def release(self, target_id: str) -> None:
        with self._lock:
            self._targets.discard(target_id)


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
    ) -> None:
        self.store = ExecutionStore()
        self.lease = WorkerLease()
        self.drafts: DraftBox = drafts or FakeDraftBox()
        self.inbox = inbox
        self.binding_resolver = binding_resolver

    def handle_message(self, target_id: str, event_id: str, agent_definition: str = "") -> ExecutionRecord:
        return run_one(self.store, self.lease, self.drafts, target_id, event_id, agent_definition)

    def handle_inbound(self, target_id: str, event_id: str, agent_definition: str = "") -> ExecutionRecord:
        """Durable inbox-first path; falls back to ``handle_message`` without an inbox.

        Returns an ``ExecutionRecord`` whose ``status`` is
        ``awaiting_workflow_binding`` when the workflow binding is missing, or
        the completed/completed-or-duplicate execution otherwise.
        """
        if self.inbox is None:
            return self.handle_message(target_id, event_id, agent_definition)
        dedupe_key = f"{target_id}:{event_id}"
        bound = self.binding_resolver(target_id) if self.binding_resolver is not None else True
        status, _created = self.inbox.enqueue(
            dedupe_key, target_id, event_id, agent_definition, binding_present=bound
        )
        if status == "awaiting_workflow_binding":
            return ExecutionRecord(dedupe_key, target_id, "awaiting_workflow_binding")
        existing = self.store.get_by_event(event_id)
        if existing is not None:
            return existing
        if status == "processed":
            # Duplicate delivery after a restart: never re-run a processed row.
            return ExecutionRecord(dedupe_key, target_id, "processed")
        try:
            record = run_one(self.store, self.lease, self.drafts, target_id, event_id, agent_definition)
        except Exception:
            # The row stays ``queued``: a crashed or failed run must be
            # replayable by drain_queued() after a restart. Marking it here
            # would swallow the message for good.
            raise
        self.inbox.mark_processed(dedupe_key)
        return record

    def bind(self, dedupe_key: str) -> ExecutionRecord | None:
        """Establish a workflow binding: ``awaiting_workflow_binding`` -> ``queued`` and run."""
        if self.inbox is None:
            return None
        row = self.inbox.get(dedupe_key)
        if row is None:
            return None
        self.inbox.bind(dedupe_key)
        return self.handle_inbound(row["target_id"], row["event_id"], row["agent_definition"])

    def drain_queued(self) -> list[ExecutionRecord]:
        """Re-drive persisted ``queued`` rows (restart recovery) and return executions."""
        if self.inbox is None:
            return []
        results: list[ExecutionRecord] = []
        for row in self.inbox.list_status("queued"):
            results.append(self.handle_inbound(row["target_id"], row["event_id"], row["agent_definition"]))
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
                return self.store.complete(current, result.draft_id or "")
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
