"""The single place that turns the Centre Agent's environment into a runnable config (ai4-349h).

Before this, the chain was: environment -> a hardcoded instruction string ->
fast-agent. Nothing in ``worker/`` read ``definitions/``, nothing read
``libs/mcp-libs/``, and the generated ``fast-agent.yaml`` had no ``mcp`` block,
so a prereview ran with no tools and a one-line instruction that did not mention
prereview. Editing a YAML changed nothing because no YAML was read.

Now it is::

    environment -> load_centre_config() -> CentreConfig -> fast-agent

``CentreConfig`` is everything one run needs: which workflow, which agents in
which order, what each may reach, and the fast-agent config text derived from the
MCP cards. It is resolved **once** and reused for every step, because reloading
the card catalog per step would let one run see two different catalogs.

Loading is strict. A missing directory, a non-``1.x`` version, an undeclared MCP
resource, an unknown workflow name, or a rule-set directory that does not
resolve all raise. There is no fallback to a built-in instruction: a Centre
Agent that starts and silently ignores its own definition is the failure this
module exists to remove.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .definitions import AgentDefinition, CentreDefinitions, DefinitionError, WorkflowDefinition, load_definitions
from .mcp_servers import (
    MCPCard,
    MCPServerConfigError,
    fast_agent_servers,
    load_cards,
    render_fast_agent_config,
)

#: Directories inside ``centre-agents/``, relative to its root.
SHIPPED = {
    "DEFINITIONS": "definitions",
    "MCP_LIBS": "libs/mcp-libs",
    "RULES": "rules",
}

#: The workflow the worker runs when nothing says otherwise. A default is right
#: while there is exactly one workflow: requiring a variable that has one legal
#: value is ceremony. A *wrong* value is still a hard error.
DEFAULT_WORKFLOW = "centre-prereview"

#: Instruction placeholder replaced by the resolved rule-set version. Exact
#: token only — instructions contain JSON braces, so a general template engine
#: would corrupt them.
RULE_SET_PLACEHOLDER = "{{rule_set_version}}"


class CentreConfigError(RuntimeError):
    """The Centre Agent's configuration cannot be loaded.

    Always names the variable and the path: the failure an operator actually
    hits is "I pointed it at the wrong directory", and a bare ``[invalid_shape]``
    does not say which of three roots is meant.
    """

    def __init__(self, variable: str, path: str, detail: str) -> None:
        self.variable = variable
        self.path = path
        self.detail = detail
        super().__init__(f"{variable} ({path}): {detail}")


@dataclass(frozen=True)
class CentreConfig:
    """One workflow, its agents in order, and everything they need to run."""

    workflow: WorkflowDefinition
    agents: tuple[AgentDefinition, ...]
    cards: Mapping[str, MCPCard]
    rule_set_version: str
    environ: Mapping[str, str]
    sources: Mapping[str, str] = field(default_factory=dict)
    #: Rendered during loading, not on first use: a missing ``*_MCP_URL`` is a
    #: deployment mistake, and discovering it half-way through a chain turns it
    #: into ``fast_agent_runtime_error``, which names nothing.
    fast_agent_config_text: str = ""

    @property
    def workflow_name(self) -> str:
        return self.workflow.name

    @property
    def sequence(self) -> tuple[str, ...]:
        return self.workflow.sequence

    def agent(self, name: str) -> AgentDefinition:
        for candidate in self.agents:
            if candidate.name == name:
                return candidate
        known = ", ".join(item.name for item in self.agents) or "(none)"
        raise CentreConfigError("SCIWEAVE_WORKFLOW", self.workflow.name, f"{name!r} is not in this chain; known agents: {known}")

    def instruction(self, name: str) -> str:
        """The agent's instruction with the rule-set version substituted in."""
        return self.agent(name).instruction.replace(RULE_SET_PLACEHOLDER, self.rule_set_version)

    def servers(self, name: str) -> dict[str, dict[str, Any]]:
        """The ``mcp.servers`` block for one agent: only what it declares."""
        return fast_agent_servers(self.agent(name).allowed_mcp_resources, self.cards, self.environ)

    def tools(self, name: str) -> dict[str, list[str]]:
        """The ``tools=`` filter map for one agent, keyed by server name."""
        return {server: list(names) for server, names in self.agent(name).allowed_tools.items()}

    def fast_agent_config(self) -> str:
        """One config file for the whole run: the union of every agent's servers.

        fast-agent resolves ``servers=`` against ``mcp.servers`` in the config
        file, so the file must declare every server any step may use while each
        ``@fast.agent`` still receives only its own names. Emitting one file per
        step would also work, but then two steps could disagree about a URL.
        """
        return self.fast_agent_config_text


def centre_root() -> Path:
    """``centre-agents/``, i.e. ``parents[3]`` of ``worker/src/<package>/assembly.py``."""
    return Path(__file__).resolve().parents[3]


def _root(variable: str, *, environ: Mapping[str, str], default: Path) -> Path:
    """The variable if set, else the shipped default; either way it must exist."""
    value = (environ.get(variable) or "").strip()
    path = Path(value).expanduser() if value else default
    if not path.exists():
        raise CentreConfigError(
            variable,
            str(path),
            "does not exist; unset the variable to use the directory shipped next to this package",
        )
    return path


def _rule_set_version(rules_dir: Path, environ: Mapping[str, str]) -> str:
    """Pick the rule-set version this run reports.

    Explicit ``CENTRE_PREREVIEW_RULE_SET_VERSION`` wins; otherwise a directory
    holding exactly one ``*.json`` names the version. More than one without an
    explicit choice is an error rather than "take the newest": a report records
    only the version string, so silently picking one makes historical reports
    incomparable, which is the exact failure ``rule_set_missing`` exists to
    prevent.
    """
    explicit = (environ.get("CENTRE_PREREVIEW_RULE_SET_VERSION") or "").strip()
    available = sorted(path.stem for path in rules_dir.glob("*.json"))
    if explicit:
        if explicit not in available:
            raise CentreConfigError(
                "CENTRE_PREREVIEW_RULE_SET_VERSION",
                str(rules_dir),
                f"{explicit!r} has no {explicit}.json; available: {', '.join(available) or '(none)'}",
            )
        version = explicit
    elif len(available) == 1:
        version = available[0]
    else:
        raise CentreConfigError(
            "CENTRE_PREREVIEW_RULE_SET_VERSION",
            str(rules_dir),
            f"set it explicitly; the directory holds {len(available)} rule sets "
            f"({', '.join(available) or '(none)'})",
        )
    try:
        document = json.loads((rules_dir / f"{version}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CentreConfigError("CENTRE_RULES_DIR", str(rules_dir), f"cannot read {version}.json: {error}") from error
    if (
        not isinstance(document, dict)
        or document.get("version") != version
        or not isinstance(document.get("checks"), list)
        or not document["checks"]
        or not all(isinstance(name, str) and name for name in document["checks"])
    ):
        raise CentreConfigError(
            "CENTRE_RULES_DIR",
            str(rules_dir),
            f"{version}.json must carry version == {version!r} and a non-empty checks list",
        )
    return version


def load_centre_config(
    environ: Mapping[str, str] | None = None, *, root: Path | None = None
) -> CentreConfig:
    """Resolve the environment into one runnable configuration."""
    env = dict(os.environ) if environ is None else dict(environ)
    base = Path(root) if root is not None else centre_root()

    definitions_path = _root("CENTRE_DEFINITIONS_PATH", environ=env, default=base / SHIPPED["DEFINITIONS"])
    try:
        definitions: CentreDefinitions = load_definitions(definitions_path)
    except DefinitionError as error:
        raise CentreConfigError("CENTRE_DEFINITIONS_PATH", str(definitions_path), str(error)) from error

    cards_path = _root("CENTRE_MCP_LIBS_PATH", environ=env, default=base / SHIPPED["MCP_LIBS"])
    try:
        cards = load_cards(cards_path)
    except MCPServerConfigError as error:
        raise CentreConfigError("CENTRE_MCP_LIBS_PATH", str(cards_path), str(error)) from error

    rules_dir = _root("CENTRE_RULES_DIR", environ=env, default=base / SHIPPED["RULES"])
    rule_set_version = _rule_set_version(rules_dir, env)

    workflow_name = (env.get("SCIWEAVE_WORKFLOW") or "").strip() or DEFAULT_WORKFLOW
    try:
        workflow = definitions.workflow(workflow_name)
        agents = definitions.chain(workflow_name)
    except DefinitionError as error:
        raise CentreConfigError("SCIWEAVE_WORKFLOW", str(definitions_path), str(error)) from error

    for agent in agents:
        unknown = sorted(set(agent.allowed_mcp_resources) - set(cards))
        if unknown:
            raise CentreConfigError(
                "CENTRE_DEFINITIONS_PATH",
                str(definitions_path),
                f"agent {agent.name!r} declares {', '.join(unknown)}, which no card in {cards_path} provides",
            )
        unknown_tools = sorted(
            f"{server}.{tool}"
            for server, names in agent.allowed_tools.items()
            for tool in names
            if server not in cards or tool not in cards[server].tools
        )
        if unknown_tools:
            raise CentreConfigError(
                "CENTRE_DEFINITIONS_PATH",
                str(definitions_path),
                f"agent {agent.name!r} declares tools no card provides: {', '.join(unknown_tools)}",
            )
        undeclared = sorted(set(agent.allowed_tools) - set(agent.allowed_mcp_resources))
        if undeclared:
            raise CentreConfigError(
                "CENTRE_DEFINITIONS_PATH",
                str(definitions_path),
                f"agent {agent.name!r} filters tools on {', '.join(undeclared)} without declaring the resource",
            )

    # Render here rather than on first use: this is where a missing ``*_MCP_URL``
    # is still a configuration error with a variable name, instead of a
    # ``fast_agent_runtime_error`` half-way through a chain.
    merged: dict[str, dict[str, Any]] = {}
    try:
        for agent in agents:
            merged.update(fast_agent_servers(agent.allowed_mcp_resources, cards, env))
    except MCPServerConfigError as error:
        raise CentreConfigError("CENTRE_MCP_LIBS_PATH", str(cards_path), str(error)) from error
    fast_agent_config = render_fast_agent_config(merged)
    return CentreConfig(
        workflow=workflow,
        agents=agents,
        cards=cards,
        rule_set_version=rule_set_version,
        environ=env,
        sources={
            "CENTRE_DEFINITIONS_PATH": str(definitions_path),
            "CENTRE_MCP_LIBS_PATH": str(cards_path),
            "CENTRE_RULES_DIR": str(rules_dir),
        },
        fast_agent_config_text=fast_agent_config,
    )
