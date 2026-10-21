"""Fast-agent runtimes used by the Task Agent Worker."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fast_agent import FastAgent
from fast_agent.context import get_initialized_context

from .config import WorkerSettings


class RuntimeRequest(Protocol):
    execution_id: str
    task_node_id: str
    session_id: str
    command_text: str


@dataclass(frozen=True)
class WorkerOutcome:
    status: str
    result_summary: str | None = None
    error_summary: str | None = None


class FastAgentPassthroughRuntime:
    """Credential-free runtime used only by automated integration checks."""

    def __init__(self, home: str | Path, connection_scope: str = "task-agent", session_dir: str = "sessions") -> None:
        self.home = Path(home)
        self.connection_scope = connection_scope
        self.session_dir = session_dir

    def run(self, request: RuntimeRequest) -> WorkerOutcome:
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            FastAgent("sciweave-task-agent-worker", home=self.home, parse_cli_args=False, quiet=True)
            history_dir = self.home / self.session_dir / request.task_node_id
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
        outcome = self.run(request)
        if outcome.status == "awaiting_acceptance":
            return WorkerOutcome("awaiting_acceptance", result_summary="fast-agent passthrough resumed")
        return outcome

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


class FastAgentDeepSeekRuntime:
    """One real DeepSeek-backed fast-agent loop per Worker process."""

    def __init__(self, settings: WorkerSettings) -> None:
        settings.validate_for_model_call()
        self.settings = settings

    def run(self, request: RuntimeRequest) -> WorkerOutcome:
        return self._execute(request, resumed=False)

    def resume(self, request: RuntimeRequest) -> WorkerOutcome:
        return self._execute(request, resumed=True)

    def cancel(self, execution_id: str) -> WorkerOutcome:
        return WorkerOutcome("cancelled", error_summary="cancelled")

    def _execute(self, request: RuntimeRequest, resumed: bool) -> WorkerOutcome:
        try:
            return asyncio.run(self._run_agent(request, resumed))
        except OSError:
            return WorkerOutcome("failed", error_summary="runtime_storage_unavailable")
        except Exception:
            return WorkerOutcome("failed", error_summary="fast_agent_runtime_error")

    async def _run_agent(self, request: RuntimeRequest, resumed: bool) -> WorkerOutcome:
        self.settings.home.mkdir(parents=True, exist_ok=True)
        original_environment = {
            "OPENAI__API_KEY": os.environ.get("OPENAI__API_KEY"),
            "OPENAI__BASE_URL": os.environ.get("OPENAI__BASE_URL"),
        }
        config_path = self._write_fast_agent_config()
        os.environ["OPENAI__API_KEY"] = self.settings.api_key or ""
        os.environ["OPENAI__BASE_URL"] = self.settings.base_url
        try:
            agent_name = f"worker-{request.task_node_id}"
            fast = FastAgent(
                "sciweave-task-agent-worker",
                config_path=config_path,
                home=self.settings.home / self.settings.session_dir,
                parse_cli_args=False,
                quiet=True,
            )

            @fast.agent(
                name=agent_name,
                instruction=(
                    "You are a SciWeave Task Agent Worker. Complete the owner's command concisely. "
                    f"Connection scope: {self.settings.connection_scope}. Session: {request.session_id}."
                ),
                model=f"openai.{self.settings.model}",
                use_history=True,
            )
            async def worker_loop() -> None:
                async with fast.run() as app:
                    agent = getattr(app, agent_name)
                    context = get_initialized_context()
                    manager = context.session_manager if context is not None else None
                    if manager is None:
                        return
                    if resumed:
                        restored = await manager.resume_session_agents_async(
                            {agent_name: agent}, request.session_id, fallback_agent_name=agent_name
                        )
                        if restored is None:
                            worker_loop.outcome = WorkerOutcome(
                                "failed", error_summary="session_restore_failed"
                            )
                            return
                    else:
                        manager.create_session_with_id(
                            request.session_id,
                            {"connection_scope": self.settings.connection_scope},
                            metadata_id_key=None,
                        )
                    response = await agent.send(request.command_text)
                    summary = self._sanitize_summary(str(response))
                    outcome = "fast-agent resumed" if resumed else "fast-agent completed"
                    worker_loop.outcome = WorkerOutcome(
                        "awaiting_acceptance", result_summary=f"{outcome}: {summary}"
                    )

            await worker_loop()
            return worker_loop.outcome
        finally:
            for name, value in original_environment.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def _write_fast_agent_config(self) -> Path:
        config_path = self.settings.home / "fast-agent.yaml"
        config_path.write_text("compaction:\n  auto: false\nsession_history: true\n", encoding="utf-8")
        return config_path

    @staticmethod
    def _sanitize_summary(value: str) -> str:
        normalized = " ".join(value.split())
        return normalized[:500] or "empty model response"
