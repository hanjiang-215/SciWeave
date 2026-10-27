"""Real fast-agent runtime for the researcher-side worker (ai4-g1km).

The researcher-owned worker shell used to stop at a placeholder: the only
runtime was the deterministic passthrough that writes a stub history. This
module is the actual model loop, ported from the centre-side worker
(``sci-weave/centre-control/centre-agents/worker/src/task_agent_worker/runtime.py``)
so both codebases run the same shape: one fast-agent session per execution,
history on, compaction off.

``fast_agent`` is imported lazily: the runtime package stays importable (and its
tests runnable) without the dependency, and a missing package is reported as
``fast_agent_unavailable`` instead of an ImportError in the middle of a run.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class AgentRequest(Protocol):
    """What one model call needs to know about the execution."""

    execution_id: str
    task_node_id: str
    session_id: str
    command_text: str


@dataclass(frozen=True)
class AgentOutcome:
    status: str
    result_summary: str | None = None
    error_summary: str | None = None


@dataclass(frozen=True)
class FastAgentSettings:
    api_key: str | None
    base_url: str
    model: str
    home: Path
    session_dir: str = "sessions"
    connection_scope: str = "local"

    def validate_for_model_call(self) -> None:
        if not self.api_key or self.api_key.startswith("replace-with-"):
            raise ValueError("DEEPSEEK_API_KEY must be configured")
        if not self.base_url.startswith("https://"):
            raise ValueError("DEEPSEEK_BASE_URL must be an https endpoint")
        if not self.model.strip():
            raise ValueError("DEEPSEEK_MODEL must be configured")
        session_path = Path(self.session_dir)
        if session_path.is_absolute() or any(part in {".", ".."} for part in session_path.parts):
            raise ValueError("session_dir must stay within the agent home")


class FastAgentDeepSeekRuntime:
    """One real DeepSeek-backed fast-agent loop per worker process."""

    def __init__(self, settings: FastAgentSettings) -> None:
        settings.validate_for_model_call()
        self.settings = settings

    def run(self, request: AgentRequest) -> AgentOutcome:
        return self._execute(request, resumed=False)

    def resume(self, request: AgentRequest) -> AgentOutcome:
        return self._execute(request, resumed=True)

    def cancel(self, execution_id: str) -> AgentOutcome:
        return AgentOutcome("cancelled", error_summary="cancelled")

    def _execute(self, request: AgentRequest, resumed: bool) -> AgentOutcome:
        try:
            return asyncio.run(self._run_agent(request, resumed))
        except OSError:
            return AgentOutcome("failed", error_summary="runtime_storage_unavailable")
        except ImportError:
            return AgentOutcome("failed", error_summary="fast_agent_unavailable")
        except Exception:
            return AgentOutcome("failed", error_summary="fast_agent_runtime_error")

    async def _run_agent(self, request: AgentRequest, resumed: bool) -> AgentOutcome:
        from fast_agent import FastAgent
        from fast_agent.context import get_initialized_context

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
                "sciweave-researcher-task-agent",
                config_path=config_path,
                home=self.settings.home / self.settings.session_dir,
                parse_cli_args=False,
                quiet=True,
            )

            @fast.agent(
                name=agent_name,
                instruction=(
                    "You are a SciWeave researcher-side Task Agent. Complete the "
                    "owner's command concisely and state what you did not verify. "
                    f"Connection scope: {self.settings.connection_scope}. "
                    f"Session: {request.session_id}."
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
                        worker_loop.outcome = AgentOutcome(
                            "failed", error_summary="session_manager_unavailable"
                        )
                        return
                    if resumed:
                        restored = await manager.resume_session_agents_async(
                            {agent_name: agent},
                            request.session_id,
                            fallback_agent_name=agent_name,
                        )
                        if restored is None:
                            worker_loop.outcome = AgentOutcome(
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
                    summary = self._redact_and_truncate_summary(
                        str(response), (self.settings.api_key or "",)
                    )
                    outcome = "fast-agent resumed" if resumed else "fast-agent completed"
                    worker_loop.outcome = AgentOutcome(
                        "completed", result_summary=f"{outcome}: {summary}"
                    )

            worker_loop.outcome = AgentOutcome(
                "failed", error_summary="fast_agent_runtime_error"
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
        config_path.write_text(
            "compaction:\n  auto: false\nsession_history: true\n", encoding="utf-8"
        )
        return config_path

    @staticmethod
    def _redact_and_truncate_summary(value: str, sensitive_values: tuple[str, ...]) -> str:
        redacted = value
        for secret in sensitive_values:
            if secret:
                redacted = redacted.replace(secret, "[redacted]")
        normalized = " ".join(redacted.split())
        return normalized[:500] or "empty model response"


class PassthroughAgentRuntime:
    """Credential-free double: deterministic, writes no session history.

    Only reachable when ``SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME=1`` is set
    explicitly, so a missing key can never silently produce a fake completion.
    """

    def __init__(self, connection_scope: str = "local") -> None:
        self.connection_scope = connection_scope

    def run(self, request: AgentRequest) -> AgentOutcome:
        return AgentOutcome(
            "completed",
            result_summary=f"passthrough: {request.command_text[:200]}",
        )

    def resume(self, request: AgentRequest) -> AgentOutcome:
        return self.run(request)

    def cancel(self, execution_id: str) -> AgentOutcome:
        return AgentOutcome("cancelled", error_summary="cancelled")


def build_agent_runtime(environ: dict[str, str] | None = None):
    """Build the runtime the worker shell uses, or fail with what is missing.

    Returns either ``FastAgentDeepSeekRuntime`` or ``PassthroughAgentRuntime``.
    Raises ``ValueError`` when the real runtime is expected but incomplete: a
    shell that starts and does nothing is worse than one that refuses to start.
    """
    env = os.environ if environ is None else environ
    if env.get("SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME", "").strip() == "1":
        return PassthroughAgentRuntime(env.get("SCIWEAVE_WORKER_CONNECTION_SCOPE", "local"))
    settings = FastAgentSettings(
        api_key=env.get("DEEPSEEK_API_KEY"),
        base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=env.get("DEEPSEEK_MODEL", "deepseek-chat"),
        home=Path(env.get("SCIWEAVE_FAST_AGENT_HOME", ".fast-agent")),
        session_dir=env.get("SCIWEAVE_FAST_AGENT_SESSION_DIR", "sessions"),
        connection_scope=env.get("SCIWEAVE_WORKER_CONNECTION_SCOPE", "local"),
    )
    return FastAgentDeepSeekRuntime(settings)
