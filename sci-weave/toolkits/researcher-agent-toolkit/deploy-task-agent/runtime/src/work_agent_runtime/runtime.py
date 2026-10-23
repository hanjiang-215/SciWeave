from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Callable


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


class FakeDraftBox:
    def create_draft(self, target_id: str, payload: str) -> str:
        return f"draft-{target_id}-{uuid.uuid4().hex[:8]}"


class FakeQueue:
    def __init__(self) -> None:
        self._handler: Callable[[str, str], ExecutionRecord] | None = None

    def subscribe(self, handler: Callable[[str, str], ExecutionRecord]) -> None:
        self._handler = handler

    def deliver(self, target_id: str, event_id: str) -> ExecutionRecord:
        if self._handler is None:
            raise RuntimeError("subscriber is not configured")
        return self._handler(target_id, event_id)


class WorkAgentRuntime:
    """The sole runtime seam used by all three service templates."""

    def __init__(self, drafts: FakeDraftBox | None = None) -> None:
        self.store = ExecutionStore()
        self.lease = WorkerLease()
        self.drafts = drafts or FakeDraftBox()

    def handle_message(self, target_id: str, event_id: str, agent_definition: str = "") -> ExecutionRecord:
        return run_one(self.store, self.lease, self.drafts, target_id, event_id, agent_definition)

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
    drafts: FakeDraftBox,
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
        draft_id = drafts.create_draft(target_id, f"{agent_definition}:{event_id}")
        return store.complete(store.get(execution.execution_id) or execution, draft_id)
    finally:
        lease.release(target_id)
