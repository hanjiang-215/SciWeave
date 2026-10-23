"""Configuration-only Agent resource registry owned by runtime."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping
import os
import yaml

class ResourceKind(StrEnum):
    PROMPT = "prompt"
    TASK_MODE = "task_mode"
    VALIDATOR = "validator"
    FORMATTER = "formatter"
    WORKFLOW_HELPER = "workflow_helper"

class ResourceError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code, self.detail = code, detail
        super().__init__(f"[{code}] {detail}")
class ResourceConflictError(ResourceError): pass
class ResourceNotFoundError(ResourceError): pass
class ResourceVersionError(ResourceError): pass

@dataclass(frozen=True)
class AgentResource:
    name: str
    version: str
    kind: ResourceKind | str
    value: Any
    source: str = "standard"
    @property
    def identifier(self) -> str: return f"{self.name}@{self.version}"
    def __post_init__(self):
        if not self.name or "@" in self.name: raise ValueError("resource name must be non-empty and exclude '@'")
        _version(self.version)
        object.__setattr__(self, "kind", ResourceKind(self.kind))
        object.__setattr__(self, "value", deepcopy(self.value))

def _version(value: str) -> tuple[int, int, int]:
    try: parts = tuple(int(part) for part in value.split("."))
    except (AttributeError, ValueError): raise ValueError(f"invalid resource version: {value!r}") from None
    if len(parts) not in (1, 2, 3) or any(part < 0 for part in parts): raise ValueError(f"invalid resource version: {value!r}")
    return (*parts, 0, 0)[:3]

def _constraint(reference: str):
    if "@" not in reference: return reference, None
    name, version = reference.rsplit("@", 1)
    if not name or not version: raise ResourceVersionError("invalid_resource_reference", reference)
    return name, _version(version)

class ResourceRegistry:
    def __init__(self, standard: Iterable[AgentResource] = (), local: Iterable[AgentResource] = ()):
        self._resources = {}
        self._add(standard, False); self._add(local, True)
    def _add(self, resources, allow_override):
        for resource in resources:
            key = (resource.name, resource.version)
            if key in self._resources:
                if allow_override and self._resources[key].source == "standard": self._resources[key] = resource
                else: raise ResourceConflictError("resource_conflict", resource.identifier)
            else: self._resources[key] = resource
    def __iter__(self): return iter(self.references())
    def references(self): return frozenset(item.identifier for item in self._resources.values())
    def resolve(self, reference):
        name, requested = _constraint(reference)
        candidates = [r for (candidate, _), r in self._resources.items() if candidate == name and (requested is None or _version(r.version)[0] == requested[0])]
        if not candidates: raise ResourceVersionError("incompatible_resource_version", reference) if any(c == name for c, _ in self._resources) else ResourceNotFoundError("unknown_resource", name)
        eligible = [r for r in candidates if requested is None or _version(r.version) >= requested]
        if not eligible: raise ResourceVersionError("incompatible_resource_version", reference)
        return deepcopy(max(eligible, key=lambda r: (r.source == "local", _version(r.version))))

def load_agent_registry(*, standard_path: str | Path | None = None, local_path: str | Path | None = None) -> ResourceRegistry:
    standard_root = Path(standard_path) if standard_path is not None else _optional_path("AGENT_LIBS_PATH")
    local_root = Path(local_path) if local_path is not None else _optional_path("LOCAL_AGENT_LIBS")
    standard = _load_resources(standard_root, "standard")
    local = _load_resources(local_root, "local")
    return ResourceRegistry(standard, local)

def _optional_path(name: str) -> Path | None:
    value = os.getenv(name, "")
    return Path(value) if value else None

def _load_resources(root: Path | None, source: str):
    if root is None or not root.exists():
        return []
    result = []
    for path in sorted((*root.rglob("*.yaml"), *root.rglob("*.yml"), *root.rglob("*.json"))):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, Mapping): raise ResourceError("invalid_resource", str(path))
        result.append(AgentResource(str(data["name"]), str(data["version"]), data["kind"], data.get("value", data.get("content", data)), source))
    return result
