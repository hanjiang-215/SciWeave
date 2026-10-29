"""Fast-agent runtimes used by the Centre Agent Worker.

Two of them: a passthrough that writes a stub history so automated checks can run
without a model credential, and the real DeepSeek-backed one. The real one owns no
knowledge of the job — the workflow, its steps and their instructions all come from
``definitions/`` via ``CentreConfig``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

#: The fast-agent app name. One constant because it appears in both runtimes and a
#: typo in one of them would only surface as a second, empty session directory.
APP_NAME = "sciweave-centre-agent-worker"

from .assembly import CentreConfig, load_centre_config
from .config import WorkerSettings, ensure_relative_session_dir

if TYPE_CHECKING:  # pragma: no cover - typing only
    # ``fast_agent`` is imported inside the functions that need it so a test can
    # put a stand-in package into ``sys.modules`` and inspect the kwargs the
    # runtime hands to the framework.
    from fast_agent import FastAgent


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

    def __init__(self, home: str | Path, connection_scope: str, session_dir: str) -> None:
        ensure_relative_session_dir(session_dir, "session_dir must stay within Worker home")
        self.home = Path(home)
        self.connection_scope = connection_scope
        self.session_dir = session_dir

    def run(self, request: RuntimeRequest) -> WorkerOutcome:
        try:
            from fast_agent import FastAgent

            self.home.mkdir(parents=True, exist_ok=True)
            FastAgent(APP_NAME, home=self.home, parse_cli_args=False, quiet=True)
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
            return WorkerOutcome("completed", result_summary="fast-agent passthrough completed")
        except (OSError, ValueError):
            logging.getLogger("task_agent_worker").exception(
                "passthrough runtime storage unavailable for execution %s", request.execution_id
            )
            return WorkerOutcome("failed", error_summary="runtime_storage_unavailable")
        except Exception:
            logging.getLogger("task_agent_worker").exception(
                "passthrough runtime failed for execution %s", request.execution_id
            )
            return WorkerOutcome("failed", error_summary="fast_agent_runtime_error")

    def resume(self, request: RuntimeRequest) -> WorkerOutcome:
        outcome = self.run(request)
        if outcome.status == "completed":
            return WorkerOutcome("completed", result_summary="fast-agent passthrough resumed")
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
    """One real DeepSeek-backed fast-agent chain per Worker process.

    The chain, its agents, their instructions, models, MCP resources and tool
    filters all come from ``definitions/`` (ai4-349h). Nothing about the job is
    spelled in this file any more: the instruction used to be a hardcoded
    "complete the owner's command concisely", which is a Task Agent sentence in a
    component whose only job is candidate prereview.
    """

    def __init__(self, settings: WorkerSettings, config: CentreConfig | None = None) -> None:
        settings.validate_for_model_call()
        self.settings = settings
        # Loading in the constructor, not on the first handoff: a missing
        # definition directory or an undeclared MCP resource is a deployment
        # mistake, and discovering it half-way through a chain turns it into
        # ``fast_agent_runtime_error``, which says nothing about what is missing.
        self.config = config if config is not None else load_centre_config()

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
            logging.getLogger("task_agent_worker").exception(
                "fast-agent runtime storage unavailable for execution %s", request.execution_id
            )
            return WorkerOutcome("failed", error_summary="runtime_storage_unavailable")
        except Exception:
            logging.getLogger("task_agent_worker").exception(
                "fast-agent runtime failed for execution %s", request.execution_id
            )
            return WorkerOutcome("failed", error_summary="fast_agent_runtime_error")

    def model_for(self, agent_name: str) -> str:
        """The model one agent calls: its own name, unless it is a placeholder.

        ``configure-in-your-own-environment`` is the shipped placeholder; it means
        "take ``SCIWEAVE_WORKER_MODEL``". A real name in the YAML wins, so one
        agent can be pinned without touching `.env`. Both missing is an error —
        see ``settings.validate_for_model_call``.
        """
        configured = self.config.agent(agent_name).model.strip()
        if configured and not configured.startswith("configure-"):
            return configured
        return self.settings.model

    async def _run_agent(self, request: RuntimeRequest, resumed: bool) -> WorkerOutcome:
        from fast_agent import FastAgent
        from fast_agent.context import get_initialized_context
        # ai4-heb2: errors used to reach the caller as a bare
        # ``fast_agent_runtime_error`` with no log line, so an operator saw a
        # failed execution and nothing else. Record what happened, where.
        _log = logging.getLogger("task_agent_worker")
        self.settings.home.mkdir(parents=True, exist_ok=True)
        original_environment = {
            "OPENAI__API_KEY": os.environ.get("OPENAI__API_KEY"),
            "OPENAI__BASE_URL": os.environ.get("OPENAI__BASE_URL"),
        }
        config_path = self._write_fast_agent_config()
        os.environ["OPENAI__API_KEY"] = self.settings.api_key or ""
        os.environ["OPENAI__BASE_URL"] = self.settings.base_url
        try:
            chain_name = self.config.workflow_name
            fast = FastAgent(
                APP_NAME,
                config_path=config_path,
                home=self.settings.home / self.settings.session_dir,
                parse_cli_args=False,
                quiet=True,
            )
            for name in self.config.sequence:
                self._register_agent(fast, name)
            self._register_chain(fast)

            async def worker_loop() -> None:
                async with fast.run() as app:
                    agent = getattr(app, chain_name)
                    context = get_initialized_context()
                    manager = context.session_manager if context is not None else None
                    if manager is None:
                        worker_loop.outcome = WorkerOutcome(
                            "failed", error_summary="session_manager_unavailable"
                        )
                        return
                    if resumed:
                        restored = await manager.resume_session_agents_async(
                            {chain_name: agent}, request.session_id, fallback_agent_name=chain_name
                        )
                        if restored is None:
                            worker_loop.outcome = WorkerOutcome(
                                "failed", error_summary="session_restore_failed"
                            )
                            return
                    else:
                        manager.create_session_with_id(
                            request.session_id,
                            {
                                "connection_scope": self.settings.connection_scope,
                                "workflow": chain_name,
                                "rule_set_version": self.config.rule_set_version,
                            },
                            metadata_id_key=None,
                        )
                    response = await agent.send(request.command_text)
                    summary = self._redact_and_truncate_summary(
                        str(response), (self.settings.api_key or "",)
                    )
                    outcome = "fast-agent resumed" if resumed else "fast-agent completed"
                    worker_loop.outcome = WorkerOutcome(
                        "completed", result_summary=f"{outcome} [{chain_name}]: {summary}"
                    )

            worker_loop.outcome = WorkerOutcome("failed", error_summary="fast_agent_runtime_error")
            await worker_loop()
            return worker_loop.outcome
        finally:
            for name, value in original_environment.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def _register_agent(self, fast: FastAgent, name: str) -> None:
        """Register one chain step with exactly what its definition grants."""
        agent = self.config.agent(name)

        @fast.agent(
            name=name,
            instruction=self.config.instruction(name),
            model=f"openai.{self.model_for(name)}",
            # Only the cards this agent declares. An empty list is correct and
            # meaningful: an agent that checks branch facts has no MCP tools at
            # all, rather than inheriting whatever else happens to be configured.
            servers=list(agent.allowed_mcp_resources),
            # Per-server tool allowlist. Without it the reader agent would get
            # ``append_prereview_log`` from the same server it uses to read.
            tools=self.config.tools(name),
            # ``None`` is not the same as omitting this argument: the default is
            # fast-agent's SKILLS_DEFAULT sentinel, which resolves to whatever the
            # context or home directory holds. An unattended Centre Worker must
            # run exactly the skills it was told to, which here is none.
            skills=[],
            # Each step gets the chain's message, not its own conversation. A
            # history-carrying child inside a cumulative chain would see the
            # previous run's turn as well as this one's.
            use_history=False,
        )
        # The decorator registers ``step`` as the agent's entry point; its body
        # is deliberately empty because the chain drives every step.
        async def step() -> None:
            return None

    def _register_chain(self, fast: FastAgent) -> None:
        workflow = self.config.workflow

        @fast.chain(
            name=workflow.name,
            sequence=list(workflow.sequence),
            cumulative=workflow.cumulative,
            default=True,
        )
        async def chain() -> None:
            return None

    def _write_fast_agent_config(self) -> Path:
        config_path = self.settings.home / "fast-agent.yaml"
        config_path.write_text(self.config.fast_agent_config(), encoding="utf-8")
        return config_path

    @staticmethod
    def _redact_and_truncate_summary(value: str, sensitive_values: tuple[str, ...]) -> str:
        redacted = value
        for secret in sensitive_values:
            if secret:
                redacted = redacted.replace(secret, "[redacted]")
        normalized = " ".join(redacted.split())
        return normalized[:500] or "empty model response"
