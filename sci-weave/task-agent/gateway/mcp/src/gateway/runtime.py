"""Runtime adapter boundary for one Task Agent Worker loop."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RuntimeRequest:
    """The stable execution identity passed to one Worker loop."""

    execution_id: str
    task_node_id: str
    session_id: str


@dataclass(frozen=True)
class RuntimeOutcome:
    """A sanitized Worker result that Gateway can persist."""

    status: str
    result_summary: str | None = None
    error_summary: str | None = None


class RuntimeAdapter(Protocol):
    """Port implemented by test and fast-agent Worker runtimes."""

    def run(self, request: RuntimeRequest) -> RuntimeOutcome: ...

    def resume(self, request: RuntimeRequest) -> RuntimeOutcome: ...

    def cancel(self, execution_id: str) -> RuntimeOutcome: ...


class TestRuntimeAdapter:
    """Deterministic, process-safe runtime used only by Gateway behavior tests."""

    def __init__(self, outcome: str = "success", duration_seconds: float = 0) -> None:
        self.outcome = outcome
        self.duration_seconds = duration_seconds

    def run(self, request: RuntimeRequest) -> RuntimeOutcome:
        if self.duration_seconds:
            time.sleep(self.duration_seconds)
        if self.outcome == "success":
            return RuntimeOutcome("awaiting_acceptance", result_summary="test runtime completed")
        if self.outcome == "exception":
            raise RuntimeError("test runtime exception")
        if self.outcome == "timeout":
            raise TimeoutError("test runtime timeout")
        if self.outcome == "waiting":
            return RuntimeOutcome("waiting", result_summary="test runtime needs an answer")
        if self.outcome == "cancelled":
            return self.cancel(request.execution_id)
        return RuntimeOutcome("failed", error_summary=self.outcome)

    def resume(self, request: RuntimeRequest) -> RuntimeOutcome:
        return self.run(request)

    def cancel(self, execution_id: str) -> RuntimeOutcome:
        return RuntimeOutcome("cancelled", error_summary="cancelled")
