"""A credential-free fast-agent Worker runtime for local integration checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fast_agent import FastAgent


class RuntimeRequest(Protocol):
    execution_id: str
    task_node_id: str
    session_id: str


@dataclass(frozen=True)
class WorkerOutcome:
    status: str
    result_summary: str | None = None
    error_summary: str | None = None


class FastAgentPassthroughRuntime:
    """Persist a TaskNode-scoped fast-agent session without a model provider.

    The adapter creates fast-agent with its configured persistent home, then records
    one passthrough loop in the TaskNode session history. It deliberately performs no
    model invocation, so integration tests never require or retain provider credentials.
    """

    def __init__(self, home: str | Path, connection_scope: str = "task-agent") -> None:
        self.home = Path(home)
        self.connection_scope = connection_scope

    def run(self, request: RuntimeRequest) -> WorkerOutcome:
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            FastAgent(
                "sciweave-task-agent-worker",
                home=self.home,
                parse_cli_args=False,
                quiet=True,
            )
            history_dir = self.home / "sessions" / request.task_node_id
            history_dir.mkdir(parents=True, exist_ok=True)
            history_path = history_dir / "history.json"
            history = self._read_history(history_path, request.session_id)
            history["events"].append(
                {
                    "execution_id": request.execution_id,
                    "connection_scope": self.connection_scope,
                    "mode": "passthrough",
                    "compaction": False,
                }
            )
            history_path.write_text(json.dumps(history, sort_keys=True), encoding="utf-8")
            return WorkerOutcome("awaiting_acceptance", result_summary="fast-agent passthrough completed")
        except (OSError, ValueError):
            return WorkerOutcome("failed", error_summary="runtime_storage_unavailable")
        except Exception:
            return WorkerOutcome("failed", error_summary="fast_agent_runtime_error")

    def resume(self, request: RuntimeRequest) -> WorkerOutcome:
        return self.run(request)

    def cancel(self, execution_id: str) -> WorkerOutcome:
        return WorkerOutcome("cancelled", error_summary="cancelled")

    @staticmethod
    def _read_history(history_path: Path, session_id: str) -> dict[str, object]:
        if not history_path.exists():
            return {"session_id": session_id, "events": []}
        history = json.loads(history_path.read_text(encoding="utf-8"))
        if history.get("session_id") != session_id or not isinstance(history.get("events"), list):
            raise ValueError("invalid session history")
        return history
