"""Immutable, validated configuration for researcher Task Agents."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import yaml
from pathlib import Path
from typing import Any, Mapping

SUPPORTED_WORKFLOW_TYPES = ("Router", "Orchestrator", "Parallel", "Agents as Tools")

# Legal keys per section. Anything else is a stable `unknown_field` error instead of
# being silently dropped: a YAML key that never reaches the runtime is worse than a
# rejected one, because the researcher sees a config that "loads fine" and does nothing.
_TOP_LEVEL_KEYS = frozenset({"agents", "workflows", "version", "name"})
_AGENT_KEYS = frozenset({
    "name", "identity", "instruction", "model", "allowed_mcp_resources", "resources",
    "references", "tools", "allowed_domain_mcps", "children",
})
_WORKFLOW_KEYS = frozenset({"name", "type", "entry_agent", "sub_agents", "summarizer", "final_writer"})


class ConfigError(ValueError):
    """Stable error raised when a Task Agent configuration is invalid."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"[{code}] {path}: {detail}")


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    identity: str
    instruction: str
    model: str
    allowed_mcp_resources: tuple[str, ...]
    resources: tuple[str, ...]
    references: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    workflow_type: str
    entry_agent: str
    sub_agents: tuple[str, ...]
    summarizer: str
    final_writer: str


@dataclass(frozen=True)
class TaskAgentConfig:
    agents: Mapping[str, AgentDefinition]
    workflows: Mapping[str, WorkflowDefinition]
    mcp_catalog: Mapping[str, Any] = None


def _required(data: Mapping[str, Any], key: str, path: str) -> Any:
    value = data.get(key)
    if value is None or value == "":
        raise ConfigError(f"missing_{key}", f"{path}.{key}", "required")
    return value


def _strings(value: Any, code: str, path: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ConfigError(code, path, "must be a list of strings")
    result = tuple(value)
    if not all(isinstance(item, str) and (allow_empty or item) for item in result):
        raise ConfigError(code, path, "must be a list of strings")
    return result


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError("invalid_shape", path, "must be an object")
    return value


def _reject_unknown_keys(data: Mapping[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = sorted(set(map(str, data)) - allowed)
    if unknown:
        raise ConfigError("unknown_field", path, ", ".join(unknown))


def _optional_path(name: str, *fallbacks: str) -> Path | None:
    """First non-empty environment variable wins; `LOCAL_WORKFLOW_LIBS` keeps the
    unprefixed spelling of its two siblings usable."""
    for candidate in (name, *fallbacks):
        value = os.getenv(candidate, "")
        if value:
            return Path(value)
    return None


def load_config(source: Mapping[str, Any] | str | Path, *, known_mcp_resources: set[str] | frozenset[str] = frozenset(), known_agent_resources: set[str] | frozenset[str] = frozenset(), mcp_catalog: Mapping[str, Any] | None = None) -> TaskAgentConfig:
    """Load and validate a mapping or JSON document without contacting services."""
    if isinstance(source, Path):
        try:
            source = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError("config_read_error", str(source), str(exc)) from exc
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except json.JSONDecodeError as exc:
            raise ConfigError("invalid_document", "config", "expected JSON object") from exc
    root = _mapping(source, "config")
    _reject_unknown_keys(root, _TOP_LEVEL_KEYS, "config")
    raw_agents = _mapping(_required(root, "agents", "config"), "config.agents")
    raw_workflows = _mapping(_required(root, "workflows", "config"), "config.workflows")
    agents: dict[str, AgentDefinition] = {}
    for name, raw in raw_agents.items():
        if not isinstance(name, str) or not name:
            raise ConfigError("invalid_agent_name", "config.agents", "names must be non-empty strings")
        data = _mapping(raw, f"config.agents.{name}")
        _reject_unknown_keys(data, _AGENT_KEYS, f"config.agents.{name}")
        mcp = _strings(data.get("allowed_mcp_resources", data.get("allowed_domain_mcps")), "invalid_mcp_resources", f"config.agents.{name}.allowed_mcp_resources")
        unknown_mcp = sorted(set(mcp) - set(known_mcp_resources))
        if unknown_mcp:
            raise ConfigError("unknown_mcp_resource", f"config.agents.{name}.allowed_mcp_resources", ", ".join(unknown_mcp))
        resources = _strings(data.get("resources"), "invalid_agent_resources", f"config.agents.{name}.resources")
        unknown_resources = sorted(set(resources) - set(known_agent_resources))
        if unknown_resources:
            raise ConfigError("unknown_agent_resource", f"config.agents.{name}.resources", ", ".join(unknown_resources))
        agents[name] = AgentDefinition(name, str(_required(data, "identity", f"config.agents.{name}")), str(_required(data, "instruction", f"config.agents.{name}")), str(_required(data, "model", f"config.agents.{name}")), mcp, resources, _strings(data.get("references"), "invalid_references", f"config.agents.{name}.references"), _strings(data.get("tools", data.get("children")), "invalid_agent_links", f"config.agents.{name}.tools"))
    workflows: dict[str, WorkflowDefinition] = {}
    for name, raw in raw_workflows.items():
        data = _mapping(raw, f"config.workflows.{name}")
        _reject_unknown_keys(data, _WORKFLOW_KEYS, f"config.workflows.{name}")
        workflow_type = _required(data, "type", f"config.workflows.{name}")
        if workflow_type not in SUPPORTED_WORKFLOW_TYPES:
            raise ConfigError("unknown_workflow_type", f"config.workflows.{name}.type", str(workflow_type))
        sub_agents = _strings(_required(data, "sub_agents", f"config.workflows.{name}"), "missing_sub_agents", f"config.workflows.{name}.sub_agents")
        if not sub_agents:
            raise ConfigError("missing_sub_agents", f"config.workflows.{name}.sub_agents", "at least one required")
        workflows[name] = WorkflowDefinition(name, workflow_type, str(_required(data, "entry_agent", f"config.workflows.{name}")), sub_agents, str(_required(data, "summarizer", f"config.workflows.{name}")), str(_required(data, "final_writer", f"config.workflows.{name}")))
    _validate_references(agents, workflows)
    return TaskAgentConfig(dict(agents), dict(workflows), mcp_catalog or {})


def _read_documents(source: str | Path, *, allow_empty: bool = False) -> list[tuple[Path, Mapping[str, Any]]]:
    """Read one Workflow YAML file or every YAML file in a directory."""
    path = Path(source)
    paths = [path] if path.is_file() else sorted((*path.glob("*.yaml"), *path.glob("*.yml")))
    if not paths:
        if allow_empty:
            # The shipped `libs/local-workflow-libs/` holds only a README. A researcher
            # who points LOCAL_WORKFLOW_LIBS_PATH at an empty directory means "no
            # overrides", not "the kit is broken".
            return []
        raise ConfigError("config_read_error", str(path), "no YAML files found")
    documents: list[tuple[Path, Mapping[str, Any]]] = []
    for item in paths:
        try:
            data = yaml.safe_load(item.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError("invalid_document", str(item), "expected valid YAML object") from exc
        if not isinstance(data, Mapping):
            raise ConfigError("invalid_document", str(item), "expected YAML object")
        version = data.get("version", "1.0.0")
        if not isinstance(version, str) or not version.startswith("1."):
            raise ConfigError("unsupported_config_version", f"{item}.version", str(version))
        documents.append((item, data))
    return documents


def _merge_documents(documents: list[tuple[Path, Mapping[str, Any]]], source_label: str) -> dict[str, dict[str, Any]]:
    """Merge `agents` / `workflows` sections of one source; duplicates within it are errors."""
    merged: dict[str, dict[str, Any]] = {"agents": {}, "workflows": {}}
    for item, document in documents:
        is_workflow_document = "agents" in document or "workflows" in document
        if is_workflow_document:
            # Only checked for real Workflow documents: a flat single-agent file has
            # agent keys at the top level, and that case must report `no_definitions`
            # rather than a misleading `unknown_field`.
            _reject_unknown_keys(document, _TOP_LEVEL_KEYS, str(item))
        for section in ("agents", "workflows"):
            values = document.get(section, {})
            if not isinstance(values, Mapping):
                raise ConfigError("invalid_shape", f"config.{section}", "must be an object")
            duplicate = set(merged[section]).intersection(values)
            if duplicate:
                raise ConfigError("duplicate_definition", f"config.{section}", ", ".join(sorted(duplicate)))
            merged[section].update(values)
    if not merged["agents"] and not merged["workflows"]:
        # A directory of flat agent files parses to zero definitions. Returning an empty
        # project with exit code 0 is how the researcher ends up with a config that looks
        # loaded and does nothing, so this is a hard error instead.
        raise ConfigError(
            "no_definitions",
            source_label,
            "files parsed but declared no agents or workflows; wrap flat agent files in an 'agents:' section",
        )
    return merged


def load_workflow_yaml(source: str | Path, *, known_mcp_resources: set[str] | frozenset[str] = frozenset(), known_agent_resources: set[str] | frozenset[str] = frozenset(), mcp_catalog: Mapping[str, Any] | None = None) -> TaskAgentConfig:
    """Load one Workflow YAML file or all YAML files in a directory."""
    merged = _merge_documents(_read_documents(source), str(source))
    return load_config(merged, known_mcp_resources=known_mcp_resources, known_agent_resources=known_agent_resources, mcp_catalog=mcp_catalog)


def load_workflow_libs(*, standard_path: str | Path | None = None, local_path: str | Path | None = None, known_mcp_resources: set[str] | frozenset[str] = frozenset(), known_agent_resources: set[str] | frozenset[str] = frozenset(), mcp_catalog: Mapping[str, Any] | None = None) -> TaskAgentConfig:
    """Load the standard Workflow libs, then let the researcher's local libs override them.

    Mirrors `load_agent_registry` / `load_mcp_registry`: `WORKFLOW_LIBS_PATH` is the
    shipped directory, `LOCAL_WORKFLOW_LIBS_PATH` is the researcher's own directory, and
    a local definition wins over the standard one it shares a name with.
    """
    standard_root = Path(standard_path) if standard_path is not None else _optional_path("WORKFLOW_LIBS_PATH")
    local_root = Path(local_path) if local_path is not None else _optional_path("LOCAL_WORKFLOW_LIBS_PATH", "LOCAL_WORKFLOW_LIBS")
    merged: dict[str, dict[str, Any]] = {"agents": {}, "workflows": {}}
    for root, is_local in ((standard_root, False), (local_root, True)):
        if root is None:
            continue
        if not root.exists():
            # A missing local directory is normal (most researchers have none); a missing
            # standard directory means the kit was not deployed and is worth failing on.
            if is_local:
                continue
            raise ConfigError("config_read_error", str(root), "no YAML files found")
        documents = _read_documents(root, allow_empty=is_local)
        if not documents:
            continue
        section = _merge_documents(documents, str(root))
        for name in ("agents", "workflows"):
            merged[name].update(section[name])
    if not merged["agents"] and not merged["workflows"]:
        raise ConfigError("no_definitions", "config", "no Workflow libs configured; set WORKFLOW_LIBS_PATH")
    return load_config(merged, known_mcp_resources=known_mcp_resources, known_agent_resources=known_agent_resources, mcp_catalog=mcp_catalog)


def workflow_to_fast_agent_input(config: TaskAgentConfig, workflow_name: str) -> dict[str, Any]:
    """Convert validated project configuration to framework-neutral adapter input."""
    try:
        workflow = config.workflows[workflow_name]
    except KeyError as exc:
        raise ConfigError("unknown_workflow", "config.workflows", workflow_name) from exc
    return {
        "name": workflow.name,
        "type": workflow.workflow_type,
        "entry_agent": workflow.entry_agent,
        "sub_agents": list(workflow.sub_agents),
        "summarizer": workflow.summarizer,
        "final_writer": workflow.final_writer,
        "agents": {
            name: {
                "instruction": agent.instruction,
                "model": agent.model,
                "servers": list(agent.allowed_mcp_resources),
                "tools": list(agent.tools),
            }
            for name, agent in config.agents.items()
        },
    }


def _validate_references(agents: Mapping[str, AgentDefinition], workflows: Mapping[str, WorkflowDefinition]) -> None:
    graph: dict[str, set[str]] = {name: set(agent.tools) for name, agent in agents.items()}
    for name, agent in agents.items():
        for target in agent.tools:
            if target not in agents:
                raise ConfigError("unknown_agent", f"config.agents.{name}.tools", target)
    for name, workflow in workflows.items():
        for field, target in (("entry_agent", workflow.entry_agent), ("summarizer", workflow.summarizer), ("final_writer", workflow.final_writer)):
            if target not in agents:
                raise ConfigError("unknown_agent", f"config.workflows.{name}.{field}", target)
        for target in workflow.sub_agents:
            if target not in agents:
                raise ConfigError("unknown_agent", f"config.workflows.{name}.sub_agents", target)
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting:
            raise ConfigError("cyclic_reference", "config.agents", node)
        if node in visited:
            return
        visiting.add(node)
        for target in sorted(graph[node]):
            visit(target)
        visiting.remove(node)
        visited.add(node)
    for node in sorted(graph):
        visit(node)
