from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Execution:
    execution_id: str
    target_id: str
    status: str
    draft_id: str | None = None


class ExecutionStore:
    """Minimal durable-shaped state boundary for the template runtime."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_event: dict[str, Execution] = {}
        self._by_target: dict[str, Execution] = {}

    def enqueue(self, target_id: str, event_id: str) -> Execution:
        with self._lock:
            existing = self._by_event.get(event_id)
            if existing is not None:
                return existing
            execution = Execution(str(uuid.uuid4()), target_id, "queued")
            self._by_event[event_id] = execution
            current = self._by_target.get(target_id)
            if current is None or current.status in {"completed", "failed"}:
                self._by_target[target_id] = execution
            return execution

    def start(self, execution: Execution) -> bool:
        with self._lock:
            current = self._by_target.get(execution.target_id)
            if current is not execution or execution.status != "queued":
                return False
            updated = Execution(execution.execution_id, execution.target_id, "running")
            self._replace(updated)
            return True

    def complete(self, execution: Execution, draft_id: str) -> Execution:
        with self._lock:
            updated = Execution(execution.execution_id, execution.target_id, "completed", draft_id)
            self._replace(updated)
            return updated

    def get(self, execution_id: str) -> Execution | None:
        with self._lock:
            return next((item for item in self._by_event.values() if item.execution_id == execution_id), None)

    def _replace(self, updated: Execution) -> None:
        for event_id, current in self._by_event.items():
            if current.execution_id == updated.execution_id:
                self._by_event[event_id] = updated
                break
        self._by_target[updated.target_id] = updated


class WorkerLease:
    """Process-local target lease; the service template owns the process boundary."""

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
        self._handler: Callable[[str, str], Execution] | None = None

    def subscribe(self, handler: Callable[[str, str], Execution]) -> None:
        self._handler = handler

    def deliver(self, target_id: str, event_id: str) -> Execution:
        if self._handler is None:
            raise RuntimeError("subscriber is not configured")
        return self._handler(target_id, event_id)


def run_one(
    store: ExecutionStore,
    lease: WorkerLease,
    drafts: FakeDraftBox,
    target_id: str,
    event_id: str,
    agent_definition: str,
) -> Execution:
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
