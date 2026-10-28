"""Load the Centre Agent's agent and workflow definitions (ai4-349h).

Until this module existed the Centre Agent had no description layer at all: the
prereview instruction was one hardcoded string in ``runtime.py`` — "You are a
SciWeave Task Agent Worker. Complete the owner's command concisely." — which
says neither "prereview" nor "never approve a candidate", and the chain of
steps (take a snapshot, check branch facts, judge conflicts, write the verdict,
notify) could only be implied by prose inside that string.

The vocabulary is the Task Agent template's, because both sides are Work Agent
instances and a maintainer should not have to learn two ways to describe one
agent. Only two things differ, and both are documented in
``definitions/schema.yaml``:

- one more workflow type, ``Chain``;
- ``allowed_tools`` instead of the template's ``tools`` (which there means "the
  sub-agents of an Agents-as-Tools workflow" — the same key meaning two things
  across two codebases is a trap for the next reader).

Loading is strict on purpose. A missing directory, a non-``1.x`` version, an
undeclared MCP resource, or a ``sequence`` naming an unknown agent all raise
instead of falling back. ``assembly`` makes the same choice one level up and
repeats this paragraph there on purpose: the two are read by different people,
and a reader who only opens one of them should still learn why nothing has a
default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

#: Workflow type this side adds. The template's four types all describe "who
#: dispatches to whom"; prereview has no dispatch, no parallelism and no loop.
CHAIN = "Chain"

_TOP_LEVEL_KEYS = frozenset({"version", "name", "agents", "workflows"})
_AGENT_KEYS = frozenset(
    {
        "identity",
        "instruction",
        "model",
        "allowed_mcp_resources",
        "allowed_tools",
        "resources",
        "references",
    }
)
_WORKFLOW_KEYS = frozenset({"type", "sequence", "cumulative"})


class DefinitionError(ValueError):
    """A definition document the runtime refuses; ``code`` is a stable code."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"[{code}] {path}: {detail}")


@dataclass(frozen=True)
class AgentDefinition:
    """One agent as declared: what it is told, and what it may reach."""

    name: str
    identity: str
    instruction: str
    model: str
    allowed_mcp_resources: tuple[str, ...] = ()
    allowed_tools: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    resources: tuple[str, ...] = ()
    references: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowDefinition:
    """One ``Chain``: an ordered sequence, plus the template's derived fields.

    ``entry_agent`` / ``summarizer`` / ``final_writer`` are required by the Task
    Agent template's schema and are derived here rather than written by hand.
    Making an author fill in three fields that the sequence already determines is
    how the two get out of step.

    Nothing in this worker reads the three: fast-agent's ``@fast.chain`` takes the
    sequence and infers the rest, and a Centre Agent has exactly one workflow, so
    "which one is the entry" is not a question anything asks. They stay because
    ``schema.yaml`` publishes them as part of the v1 vocabulary — a second workflow
    type, or a consumer that speaks the template, would need them, and an author
    who reads the schema should find the derived values documented truthfully.
    """

    name: str
    sequence: tuple[str, ...]
    cumulative: bool = True
    type: str = CHAIN

    @property
    def entry_agent(self) -> str:
        return self.sequence[0]

    @property
    def summarizer(self) -> str:
        return self.sequence[-1]

    @property
    def final_writer(self) -> str:
        return self.sequence[-1]


@dataclass(frozen=True)
class CentreDefinitions:
    """Every agent and workflow declared under one directory."""

    agents: Mapping[str, AgentDefinition]
    workflows: Mapping[str, WorkflowDefinition]
    sources: tuple[str, ...] = ()

    def workflow(self, name: str) -> WorkflowDefinition:
        try:
            return self.workflows[name]
        except KeyError as error:
            known = ", ".join(sorted(self.workflows)) or "(none)"
            raise DefinitionError(
                "unknown_workflow", name, f"no workflow declares this name; known workflows: {known}"
            ) from error

    def agent(self, name: str) -> AgentDefinition:
        try:
            return self.agents[name]
        except KeyError as error:
            known = ", ".join(sorted(self.agents)) or "(none)"
            raise DefinitionError(
                "unknown_agent", name, f"no definition declares this agent; known agents: {known}"
            ) from error

    def chain(self, workflow_name: str) -> tuple[AgentDefinition, ...]:
        """The agents of one workflow, in execution order."""
        return tuple(self.agent(name) for name in self.workflow(workflow_name).sequence)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DefinitionError("invalid_shape", path, "must be an object")
    return value


def _strings(value: Any, code: str, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise DefinitionError(code, path, "must be a list of non-empty strings")
    return tuple(value)


def _required(data: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in data:
        raise DefinitionError("missing_field", f"{path}.{key}", "is required")
    return data[key]


def _reject_unknown(data: Mapping[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = sorted(set(map(str, data)) - allowed)
    if unknown:
        raise DefinitionError("unknown_field", path, ", ".join(unknown))


def _agent(name: str, raw: Any, path: str) -> AgentDefinition:
    data = _mapping(raw, path)
    _reject_unknown(data, _AGENT_KEYS, path)
    identity = str(_required(data, "identity", path))
    if not identity.strip():
        raise DefinitionError("invalid_identity", f"{path}.identity", "must not be empty")
    instruction = str(_required(data, "instruction", path))
    if not instruction.strip():
        raise DefinitionError("invalid_instruction", f"{path}.instruction", "must not be empty")
    model = str(_required(data, "model", path))
    if not model.strip():
        raise DefinitionError("invalid_model", f"{path}.model", "must not be empty")
    tools: dict[str, tuple[str, ...]] = {}
    raw_tools = data.get("allowed_tools") or {}
    if not isinstance(raw_tools, Mapping):
        raise DefinitionError("invalid_tools", f"{path}.allowed_tools", "must map a server name to a tool list")
    for server, names in raw_tools.items():
        tools[str(server)] = _strings(names, "invalid_tools", f"{path}.allowed_tools.{server}")
        if not tools[str(server)]:
            raise DefinitionError(
                "invalid_tools",
                f"{path}.allowed_tools.{server}",
                "an empty tool list would hand the agent the whole server; list the tools it needs",
            )
    return AgentDefinition(
        name=name,
        identity=identity,
        instruction=instruction,
        model=model,
        allowed_mcp_resources=_strings(
            data.get("allowed_mcp_resources"), "invalid_mcp_resources", f"{path}.allowed_mcp_resources"
        ),
        allowed_tools=tools,
        resources=_strings(data.get("resources"), "invalid_resources", f"{path}.resources"),
        references=_strings(data.get("references"), "invalid_references", f"{path}.references"),
    )


def _workflow(name: str, raw: Any, path: str) -> WorkflowDefinition:
    data = _mapping(raw, path)
    _reject_unknown(data, _WORKFLOW_KEYS, path)
    workflow_type = str(_required(data, "type", path))
    if workflow_type != CHAIN:
        raise DefinitionError(
            "unknown_workflow_type",
            f"{path}.type",
            f"{workflow_type!r} is not {CHAIN!r}; this side declares only ordered chains",
        )
    sequence = _strings(_required(data, "sequence", path), "invalid_sequence", f"{path}.sequence")
    if not sequence:
        raise DefinitionError("missing_sequence", f"{path}.sequence", "at least one agent is required")
    if len(set(sequence)) != len(sequence):
        raise DefinitionError(
            "duplicate_sequence_entry", f"{path}.sequence", "an agent appears twice in one chain"
        )
    cumulative = data.get("cumulative", True)
    if not isinstance(cumulative, bool):
        raise DefinitionError("invalid_cumulative", f"{path}.cumulative", "must be true or false")
    return WorkflowDefinition(name=name, sequence=sequence, cumulative=cumulative)


def _documents(source: str | Path) -> list[tuple[Path, Mapping[str, Any]]]:
    path = Path(source)
    paths = [path] if path.is_file() else sorted((*path.glob("*.yaml"), *path.glob("*.yml")))
    if not paths:
        raise DefinitionError(
            "no_definitions", str(path), "no *.yaml or *.yml files found; the runtime has nothing to run"
        )
    documents: list[tuple[Path, Mapping[str, Any]]] = []
    for item in paths:
        if item.name == "schema.yaml":
            # The schema is documentation. It is loaded by nobody, and letting it
            # in would make every install fail on a file that declares no agents.
            continue
        try:
            data = yaml.safe_load(item.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise DefinitionError("invalid_document", str(item), "expected valid YAML") from error
        if not isinstance(data, Mapping):
            raise DefinitionError("invalid_document", str(item), "expected a YAML object")
        documents.append((item, data))
    if not documents:
        raise DefinitionError(
            "no_definitions", str(path), "the only YAML files present are documentation"
        )
    return documents


def load_definitions(source: str | Path) -> CentreDefinitions:
    """Read one file or every ``*.yaml`` under a directory into one namespace."""
    agents: dict[str, AgentDefinition] = {}
    workflows: dict[str, WorkflowDefinition] = {}
    seen: dict[str, str] = {}
    sources: list[str] = []
    for document_path, document in _documents(source):
        label = str(document_path)
        sources.append(label)
        version = document.get("version", "")
        if not isinstance(version, str) or not version.startswith("1."):
            raise DefinitionError("unsupported_config_version", f"{label}.version", str(version))
        # Required sections are checked before the key whitelist: a flat document
        # (``version`` + one agent's fields at top level) is a mistake people
        # actually make, and "`agents` is required" says what to do while
        # "unknown field: alpha, identity, instruction" does not.
        raw_agents = _mapping(_required(document, "agents", label), f"{label}.agents")
        _reject_unknown(document, _TOP_LEVEL_KEYS, label)
        for name, raw in raw_agents.items():
            if not isinstance(name, str) or not name:
                raise DefinitionError("invalid_agent_name", f"{label}.agents", "names must be non-empty strings")
            if name in seen:
                raise DefinitionError(
                    "duplicate_definition",
                    name,
                    f"agent {name!r} is declared by both {seen[name]} and {label}; rename one of them",
                )
            seen[name] = label
            agents[name] = _agent(name, raw, f"{label}.agents.{name}")
        for name, raw in (document.get("workflows") or {}).items():
            if not isinstance(name, str) or not name:
                raise DefinitionError(
                    "invalid_workflow_name", f"{label}.workflows", "names must be non-empty strings"
                )
            if name in workflows:
                raise DefinitionError(
                    "duplicate_definition", name, f"workflow {name!r} is declared more than once"
                )
            workflows[name] = _workflow(name, raw, f"{label}.workflows.{name}")
    if not agents:
        raise DefinitionError("no_definitions", str(source), "the document declares no agents")
    for workflow in workflows.values():
        for name in workflow.sequence:
            if name not in agents:
                known = ", ".join(sorted(agents)) or "(none)"
                raise DefinitionError(
                    "unknown_agent",
                    f"{workflow.name}.sequence",
                    f"{name!r} is not declared; known agents: {known}",
                )
    return CentreDefinitions(agents=agents, workflows=workflows, sources=tuple(sources))
