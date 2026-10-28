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
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .mcp_servers import MCPServerConfigError, fast_agent_servers, render_fast_agent_config
from .skills import SkillsConfig, SkillsConfigError, load_skills

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def _relative_session_dir(value: str, message: str) -> None:
    """Reject a session dir that could escape the agent home on either platform.

    ``Path(...).is_absolute()`` is not enough here: on POSIX ``Path("C:/absolute")``
    is relative and ``Path(r"..\\..\\outside")`` is a single path part, so both
    would slip through and land under the working directory instead of being
    refused (ai4-grlc). The checks are therefore textual as well as pathlib-based.
    """
    if not value or not value.strip():
        raise ValueError(message)
    if Path(value).is_absolute() or _DRIVE_PREFIX.match(value):
        raise ValueError(message)
    parts = [part for part in value.replace("\\", "/").split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValueError(message)


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
        _relative_session_dir(self.session_dir, "session_dir must stay within the agent home")


class FastAgentDeepSeekRuntime:
    """One real DeepSeek-backed fast-agent loop per worker process.

    ``config`` is optional so the runtime stays usable in a bare smoke test, but
    a worker built through `build_agent_runtime` always passes one (ai4-z3yq):
    without it the agent's instruction, name and allowed MCP resources come from
    constants in this file, and every YAML the researcher edited is ignored.
    """

    def __init__(
        self,
        settings: FastAgentSettings,
        config: object | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        settings.validate_for_model_call()
        self.settings = settings
        self.config = config
        # The MCP URL variables are read from this mapping rather than from
        # `os.environ` so a caller can hand the runtime an explicit environment
        # (tests, or the worker's `--env-file`). Defaulting to `os.environ` keeps
        # the bare constructor usable.
        self.environ = dict(os.environ) if environ is None else dict(environ)
        # Translate the MCP cards now, not on the first handoff (ai4-x0ay). A
        # missing `*_MCP_URL` is a deployment mistake; discovering it half-way
        # through a model run turns it into `fast_agent_runtime_error`, which
        # says nothing about the missing variable. This way the worker refuses
        # to start, like it does for every other configuration defect.
        self._mcp_servers()
        # Same reasoning for skills: resolve the directories here so a wrong
        # `SCIWEAVE_SKILLS_PATH` fails at startup. `fast_agent` would otherwise
        # fall back to scanning the home directory, and a worker that silently
        # ran with no skills (or with a stranger's) looks identical to a healthy
        # one until the model improvises (ai4-4r0h follow-up).
        self.skills = load_skills(self.environ)

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
            agent_name = self._agent_name(request)
            fast = FastAgent(
                "sciweave-researcher-task-agent",
                config_path=config_path,
                home=self.settings.home / self.settings.session_dir,
                parse_cli_args=False,
                quiet=True,
            )

            @fast.agent(
                name=agent_name,
                instruction=self._instruction(request),
                model=f"openai.{self._model()}",
                # Only the cards this agent declares (ai4-x0ay). An empty list
                # is correct and meaningful: a definition that grants no MCP
                # resource gets an agent with no MCP tools, rather than one
                # inheriting whatever happens to be configured elsewhere.
                servers=list(self._servers()),
                # Likewise for skills: a path list, or ``None`` for "no skills".
                # ``None`` is deliberate rather than omitting the argument —
                # the default is fast-agent's ``SKILLS_DEFAULT`` sentinel, which
                # resolves to whatever is in the home directory. An unattended
                # worker must run exactly the skills its suite shipped
                # (ai4-4r0h follow-up; see `skills.py`).
                skills=list(self.skills.directories) if self.skills else None,
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

    def _definition(self):
        """The configured `AgentDefinition` for this worker, or ``None``.

        ``None`` only happens for a runtime constructed without a config, which
        is the bare-smoke-test path; the worker always has one.
        """
        agent = getattr(self.config, "agent", None)
        return None if agent is None else agent

    def _agent_name(self, request: AgentRequest) -> str:
        """The configured agent name.

        Not derived from the task node any more: the name is now a *configured*
        identity, and `Assembly` selects it by ``SCIWEAVE_AGENT_ID``. Deriving it
        from the node made every execution a differently named agent, so history
        and `mcp.servers` could never be pinned to a definition (ai4-z3yq).
        """
        definition = self._definition()
        return definition.name if definition is not None else "researcher-task-agent"

    def _model(self) -> str:
        """The model to call: the definition's, unless it is a placeholder.

        The shipped definitions say ``configure-in-your-own-environment`` and the
        workflow examples say ``configure-locally``; both mean "take it from the
        environment". A real name in the YAML wins, so a researcher can pin one
        agent to a different model without touching `.env`.
        """
        definition = self._definition()
        configured = (definition.model if definition is not None else "").strip()
        if configured and not configured.startswith("configure-"):
            return configured
        return self.settings.model

    def _instruction(self, request: AgentRequest) -> str:
        """The configured instruction, with run-scoped facts appended.

        The old instruction was a hardcoded sentence, so editing
        `agent-definitions/agents/*.yaml` changed nothing. Configured text comes
        first and unmodified; the run-scoped lines are appended because the
        model needs to know which session and connection scope it is in, and
        those are not properties of the definition.
        """
        definition = self._definition()
        if definition is None:
            body = (
                "You are a SciWeave researcher-side Task Agent. Complete the "
                "owner's command concisely and state what you did not verify."
            )
        else:
            body = definition.instruction
        return (
            f"{body.rstrip()}\n\n"
            f"Connection scope: {self.settings.connection_scope}.\n"
            f"Session: {request.session_id}."
        )

    def _servers(self) -> tuple[str, ...]:
        """The MCP servers this agent may use, as fast-agent server names."""
        definition = self._definition()
        return () if definition is None else tuple(definition.allowed_mcp_resources)

    def _mcp_servers(self) -> dict[str, dict]:
        """Translate this agent's cards into `mcp.servers` entries.

        Returns an empty mapping when the runtime was built without a config
        (the bare smoke test). A missing environment variable raises
        `MCPServerConfigError` rather than dropping the server: an agent that
        quietly has one tool fewer than its definition says will improvise.
        """
        names = self._servers()
        if not names:
            return {}
        catalog = getattr(self.config, "project", None)
        catalog = getattr(catalog, "mcp_catalog", None) or {}
        return fast_agent_servers(names, catalog, self.environ)

    def _write_fast_agent_config(self) -> Path:
        config_path = self.settings.home / "fast-agent.yaml"
        config_path.write_text(
            render_fast_agent_config(self._mcp_servers()), encoding="utf-8"
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

    ``mcp`` is the stand-in for the agent's MCP tools and exists for the
    key-free end-to-end test (ai4-x0ay). When an agent that holds the
    `draft-buffer` card gets one, this double *does* create the draft and
    *does* send the notification — through the real draft box and the fake
    service — so the workflow's state machine, `draft_id` hand-off and inbox
    bookkeeping are all genuinely exercised. What stays fake is the model.

    Without ``mcp`` the double returns plain text, and a workflow whose final
    writer owns the draft box ends ``draft_id_missing``. That is the honest
    outcome: the double cannot call a tool it does not have, and inventing an
    id would be exactly the fabricated-success this runtime exists to prevent.
    """

    def __init__(
        self,
        connection_scope: str = "local",
        config: object | None = None,
        mcp: object | None = None,
    ) -> None:
        self.connection_scope = connection_scope
        self.mcp = mcp
        # The configuration is still loaded, even though this runtime ignores
        # the model. Without it the passthrough path could not exercise the
        # workflow wiring at all, and every test of "does the worker run the
        # configured workflow" would need a real key — which is exactly the
        # reason the wiring stayed broken (ai4-x0ay).
        self.config = config

    def run(self, request: AgentRequest) -> AgentOutcome:
        definition = getattr(self.config, "agent", None)
        cards = set(getattr(definition, "allowed_mcp_resources", ()) or ())
        if self.mcp is not None and "draft-buffer" in cards:
            return self._run_with_tools(request, cards)
        return AgentOutcome(
            "completed",
            result_summary=f"passthrough: {request.command_text[:200]}",
        )

    def _run_with_tools(self, request: AgentRequest, cards: set[str]) -> AgentOutcome:
        """Create the draft and notify, then answer in the JSON contract.

        The ids are the ones the tools returned, so an `agent_reported` draft id
        here is as real as the draft box behind it. The summary says the model
        was a double, because a reviewer must not mistake this for a model
        answer.
        """
        try:
            draft = self.mcp.create_draft(  # type: ignore[attr-defined]
                namespace="wiki",
                kind="wiki_document",
                title=request.task_node_id or "handoff",
                payload=f"passthrough draft for {request.task_node_id}",
                idempotency_key=f"draft:{request.execution_id}",
            )
        except Exception as error:  # a tool failure is a failed step, not a crash
            return AgentOutcome("failed", error_summary=f"create_draft failed: {error}")
        if "email-service" in cards:
            self._notify(request, draft["draft_id"])
        return AgentOutcome(
            "completed",
            result_summary=json.dumps(
                {
                    "draft_id": draft["draft_id"],
                    "summary": f"passthrough double wrote a draft for {request.task_node_id}",
                }
            ),
        )

    def _notify(self, request: AgentRequest, draft_id: str) -> None:
        """Best effort: a notification failure must not lose the draft."""
        from .notifications import build_intent

        intent = build_intent(
            execution_id=request.execution_id,
            task_node_id=request.task_node_id,
            # Deliberately not a real principal: the double has no mapping to
            # read an owner from, and a plausible-looking id would be a lie a
            # reviewer could mistake for a real recipient.
            recipient_principal_id="passthrough:owner",
            subject=f"Draft ready for {request.task_node_id}"[:200],
            body=f"passthrough double created draft {draft_id}",
        )
        try:
            self.mcp.send_notification(**intent.to_dict())  # type: ignore[attr-defined]
        except Exception:
            # Nothing to retry: the draft exists and is the thing that matters.
            pass

    def resume(self, request: AgentRequest) -> AgentOutcome:
        return self.run(request)

    def cancel(self, execution_id: str) -> AgentOutcome:
        return AgentOutcome("cancelled", error_summary="cancelled")


def build_agent_runtime(
    environ: dict[str, str] | None = None,
    *,
    config: object | None = None,
    mcp: object | None = None,
):
    """Build the runtime the worker shell uses, or fail with what is missing.

    Loads the researcher's agent definition, MCP cards, workflow libs and agent
    resources before constructing the runtime (ai4-z3yq). Without that step the
    YAML a researcher edits is never read, which is the whole reason this
    factory exists rather than a bare constructor call.

    Returns either ``FastAgentDeepSeekRuntime`` or ``PassthroughAgentRuntime``.
    Raises ``ValueError`` when the real runtime is expected but incomplete, and
    ``WorkerConfigError`` when the configuration cannot be loaded: a shell that
    starts and silently ignores the configuration is worse than one that
    refuses to start.
    """
    env = os.environ if environ is None else environ
    if env.get("SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME", "").strip() == "1":
        # The passthrough loads the configuration too: it ignores the model, but
        # it still has to know which workflow and which agents were configured,
        # otherwise the workflow wiring could only be exercised with a real key
        # (ai4-x0ay).
        if config is None:
            from .assembly import load_worker_config

            config = load_worker_config(env)
        # `mcp` is only meaningful for the double; the real runtime gets its
        # tools from fast-agent, so passing one there is a mistake worth naming.
        if mcp is not None and env.get("SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME", "").strip() != "1":
            raise ValueError("mcp= is only accepted by the passthrough runtime")
        return PassthroughAgentRuntime(
            env.get("SCIWEAVE_WORKER_CONNECTION_SCOPE", "local"), config, mcp
        )
    settings = FastAgentSettings(
        api_key=env.get("DEEPSEEK_API_KEY"),
        base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=env.get("DEEPSEEK_MODEL", "deepseek-chat"),
        home=Path(env.get("SCIWEAVE_FAST_AGENT_HOME", ".fast-agent")),
        session_dir=env.get("SCIWEAVE_FAST_AGENT_SESSION_DIR", "sessions"),
        connection_scope=env.get("SCIWEAVE_WORKER_CONNECTION_SCOPE", "local"),
    )
    # Validate the credentials *before* loading the configuration. Both failures
    # are hard stops, but a researcher who has not filled in the key should be
    # told that, not sent looking for a missing YAML directory.
    settings.validate_for_model_call()
    if config is None:
        from .assembly import load_worker_config

        config = load_worker_config(env)
    return FastAgentDeepSeekRuntime(settings, config, env)
