"""Load the researcher's configuration into a shape the worker can run (ai4-z3yq).

Until this module existed, `libs/agent-libs/`, `libs/mcp-libs/`,
`libs/workflow-libs/` and `agent-definitions/` were described in the README and
`.env.example` as the things a researcher edits, and `config.py` /
`resources.py` / `mcp_resources.py` could all load them — but nothing in
`runtime/src` or `service-template/` ever called a loader. Editing the YAML
changed nothing, and the worker's agent was a hardcoded instruction string.

This is the single place that reads the environment and returns everything the
worker needs, so the chain is:

    environment -> load_worker_config() -> WorkerConfig -> fast-agent

Two directories hold two different things, which is why both are kept:

``agent-definitions/agents/``
    `AgentDefinition` objects — ``identity`` / ``instruction`` / ``model`` /
    ``allowed_mcp_resources``. This is what the model is told to be.

``libs/agent-libs/``
    `AgentResource` objects, addressed by name from an agent's ``resources:``
    list — prompt fragments, formatters, task patterns, validators. This is
    material an agent references, not the agent itself.

A definition is selected by ``SCIWEAVE_AGENT_ID``: the same value that names
the subscriber's topic names the agent, so one identity runs through the whole
kit instead of a topic name here and an agent name there.

Loading is strict on purpose. A missing shipped directory or an invalid
definition raises instead of falling back to a built-in agent: a worker that
starts and silently ignores the researcher's YAML is the bug this module was
written for.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .config import AgentDefinition, ConfigError, TaskAgentConfig, load_workflow_yaml
from .mcp_resources import MCPRegistry, load_mcp_registry
from .resources import ResourceRegistry, load_agent_registry

#: Directories inside the kit, relative to its root. `install.sh` copies all
#: four next to `.env`, so a researcher who never sets a variable still gets the
#: shipped configuration rather than nothing.
#: Public so `test_installation.py` can check `install.sh` copies all of them.
SHIPPED = {
    "AGENT_DEFINITIONS_PATH": "agent-definitions/agents",
    "MCP_LIBS_PATH": "libs/mcp-libs",
    "WORKFLOW_LIBS_PATH": "libs/workflow-libs",
    "AGENT_LIBS_PATH": "libs/agent-libs",
}


class WorkerConfigError(RuntimeError):
    """The researcher's configuration cannot be loaded.

    Always names the variable and the directory, because the failure a
    researcher actually hits is "I typed the path wrong", and a bare
    ``[invalid_document]`` does not say which of four roots is meant.
    """

    def __init__(self, variable: str, path: str, detail: str) -> None:
        self.variable = variable
        self.path = path
        self.detail = detail
        super().__init__(f"{variable} ({path}): {detail}")


@dataclass(frozen=True)
class WorkerConfig:
    """Everything the worker needs, resolved and validated."""

    agent: AgentDefinition
    project: TaskAgentConfig
    resources: ResourceRegistry
    mcp: MCPRegistry
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def agent_name(self) -> str:
        return self.agent.name

    def resource(self, reference: str):
        return self.resources.resolve(reference)


def kit_root() -> Path:
    """The kit directory: four levels above ``runtime/src/work_agent_runtime``."""
    return Path(__file__).resolve().parents[3]


def _root(variable: str, *, environ: dict[str, str], default: Path, must_exist: bool) -> Path:
    """Resolve one configuration root: the variable if set, else the kit default.

    Falling back to the kit default rather than to ``None`` matters: setting one
    override must not silently disable the other three, and an installed kit
    always has its shipped directories next to `.env`.
    """
    value = (environ.get(variable) or "").strip()
    path = Path(value).expanduser() if value else default
    if must_exist and not path.exists():
        raise WorkerConfigError(
            variable,
            str(path),
            f"does not exist; install.sh copies the shipped directory here, "
            f"or point {variable} at your own",
        )
    return path


def _merge(*projects: tuple[str, TaskAgentConfig]) -> TaskAgentConfig:
    """Merge agent/workflow definitions from several roots; later wins on conflict.

    Anthropic's own `load_workflow_libs` merges standard-then-local. Here the
    roots are different *kinds* of file rather than override pairs, so a
    duplicate name is a deployment mistake worth reporting, not something to
    silently resolve by order.
    """
    agents: dict[str, AgentDefinition] = {}
    workflows = {}
    catalog: dict = {}
    seen: dict[str, str] = {}
    for label, project in projects:
        for name, agent in project.agents.items():
            if name in seen:
                raise WorkerConfigError(
                    label, name, f"agent {name!r} is also defined by {seen[name]}; rename one of them"
                )
            seen[name] = label
            agents[name] = agent
        workflows.update(project.workflows)
        catalog.update(project.mcp_catalog)
    return TaskAgentConfig(agents, workflows, catalog)


def load_worker_config(environ: dict[str, str] | None = None, *, root: Path | None = None) -> WorkerConfig:
    """Load agent definitions, MCP cards, workflow libs and agent resources.

    Raises `WorkerConfigError` naming the variable, the directory and the
    underlying `ConfigError`, or `KeyError`-free `WorkerConfigError` when
    ``SCIWEAVE_AGENT_ID`` names an agent no definition declares.
    """
    env = dict(os.environ) if environ is None else dict(environ)
    base = Path(root) if root is not None else kit_root()

    mcp_path = _root("MCP_LIBS_PATH", environ=env, default=base / SHIPPED["MCP_LIBS_PATH"], must_exist=True)
    try:
        mcp = load_mcp_registry(
            standard_mcp_libs=mcp_path,
            local_mcp_libs=(env.get("LOCAL_MCP_LIBS") or "").strip() or None,
        )
    except Exception as error:  # MCPResourceError and friends carry their own codes
        raise WorkerConfigError("MCP_LIBS_PATH", str(mcp_path), str(error)) from error
    known_mcp = {resource.name for resource in mcp.resources}

    agent_libs_path = _root("AGENT_LIBS_PATH", environ=env, default=base / SHIPPED["AGENT_LIBS_PATH"], must_exist=True)
    try:
        resources = load_agent_registry(standard_path=agent_libs_path)
    except Exception as error:
        raise WorkerConfigError("AGENT_LIBS_PATH", str(agent_libs_path), str(error)) from error

    definition_roots = [
        (
            "AGENT_DEFINITIONS_PATH",
            _root("AGENT_DEFINITIONS_PATH", environ=env, default=base / SHIPPED["AGENT_DEFINITIONS_PATH"], must_exist=True),
        ),
    ]
    local_definitions = (env.get("LOCAL_AGENT_DEFINITIONS_PATH") or "").strip()
    if local_definitions:
        local_path = Path(local_definitions).expanduser()
        if not local_path.exists():
            raise WorkerConfigError("LOCAL_AGENT_DEFINITIONS_PATH", str(local_path), "does not exist")
        definition_roots.append(("LOCAL_AGENT_DEFINITIONS_PATH", local_path))

    workflow_path = _root("WORKFLOW_LIBS_PATH", environ=env, default=base / SHIPPED["WORKFLOW_LIBS_PATH"], must_exist=True)
    definition_roots.append(("WORKFLOW_LIBS_PATH", workflow_path))

    loaded: list[tuple[str, TaskAgentConfig]] = []
    for variable, path in definition_roots:
        try:
            loaded.append(
                (
                    f"{variable}={path}",
                    load_workflow_yaml(
                        path,
                        known_mcp_resources=known_mcp,
                        known_agent_resources=set(resources.references())
                        if hasattr(resources, "references")
                        else set(),
                        mcp_catalog=mcp.catalog(),
                    ),
                )
            )
        except ConfigError as error:
            raise WorkerConfigError(variable, str(path), f"[{error.code}] {error.path}: {error.detail}") from error

    project = _merge(*loaded)
    agent_id = (env.get("SCIWEAVE_AGENT_ID") or "").strip()
    if not agent_id:
        raise WorkerConfigError(
            "SCIWEAVE_AGENT_ID",
            "-",
            "must name the agent this kit runs; it also names the subscriber topic",
        )
    if agent_id not in project.agents:
        known = ", ".join(sorted(project.agents)) or "(none)"
        raise WorkerConfigError(
            "SCIWEAVE_AGENT_ID",
            agent_id,
            f"no definition declares this agent; known agents: {known}. "
            f"Add it under AGENT_DEFINITIONS_PATH or change SCIWEAVE_AGENT_ID",
        )

    return WorkerConfig(
        agent=project.agents[agent_id],
        project=project,
        resources=resources,
        mcp=mcp,
        sources={variable: str(path) for variable, path in definition_roots},
    )
