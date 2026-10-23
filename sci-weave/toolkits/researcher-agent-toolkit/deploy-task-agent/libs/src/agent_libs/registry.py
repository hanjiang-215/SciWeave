"""Resource discovery and deterministic resolution for Task Agent definitions."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping


class ResourceKind(StrEnum):
    PROMPT = "prompt"
    TASK_MODE = "task_mode"
    VALIDATOR = "validator"
    FORMATTER = "formatter"
    WORKFLOW_HELPER = "workflow_helper"


class ResourceError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"[{code}] {detail}")


class ResourceConflictError(ResourceError):
    pass


class ResourceNotFoundError(ResourceError):
    pass


class ResourceVersionError(ResourceError):
    pass


@dataclass(frozen=True)
class AgentResource:
    """An immutable, named resource. Versions use major.minor.patch semantics."""
    name: str
    version: str
    kind: ResourceKind | str
    value: Any
    source: str = "standard"

    @property
    def identifier(self) -> str:
        return f"{self.name}@{self.version}"

    def __post_init__(self) -> None:
        if not self.name or "@" in self.name:
            raise ValueError("resource name must be non-empty and exclude '@'")
        _version(self.version)
        object.__setattr__(self, "kind", ResourceKind(self.kind))
        object.__setattr__(self, "value", deepcopy(self.value))


def _version(value: str) -> tuple[int, int, int]:
    try:
        parts = tuple(int(part) for part in value.split("."))
    except (AttributeError, ValueError):
        raise ValueError(f"invalid resource version: {value!r}") from None
    if len(parts) not in (1, 2, 3) or any(part < 0 for part in parts):
        raise ValueError(f"invalid resource version: {value!r}")
    return (*parts, 0, 0)[:3]


def _constraint(reference: str) -> tuple[str, tuple[int, int, int] | None]:
    if "@" in reference:
        name, version = reference.rsplit("@", 1)
        if not name or not version:
            raise ResourceVersionError("invalid_resource_reference", reference)
        return name, _version(version)
    return reference, None


class ResourceRegistry:
    """Resolves standard resources and local extensions without mutating either input."""
    def __init__(self, standard: Iterable[AgentResource] | None = None, local: Iterable[AgentResource] = ()) -> None:
        self._resources: dict[tuple[str, str], AgentResource] = {}
        if standard is None:
            standard = STANDARD_RESOURCES
        self._add(standard, allow_override=False)
        self._add(local, allow_override=True)

    def _add(self, resources: Iterable[AgentResource], *, allow_override: bool) -> None:
        for resource in resources:
            key = (resource.name, resource.version)
            if key in self._resources:
                existing = self._resources[key]
                if allow_override and existing.source == "standard":
                    self._resources[key] = resource
                    continue
                raise ResourceConflictError("resource_conflict", resource.identifier)
            self._resources[key] = resource

    def __iter__(self):
        return iter(self.references())

    def references(self) -> frozenset[str]:
        return frozenset(resource.identifier for resource in self._resources.values())

    def resolve(self, reference: str) -> AgentResource:
        name, requested = _constraint(reference)
        candidates = [r for (candidate, _), r in self._resources.items() if candidate == name and (requested is None or _version(r.version)[0] == requested[0])]
        if not candidates:
            if any(candidate == name for candidate, _ in self._resources):
                raise ResourceVersionError("incompatible_resource_version", reference)
            raise ResourceNotFoundError("unknown_resource", name)
        eligible = [r for r in candidates if requested is None or _version(r.version) >= requested]
        if not eligible:
            raise ResourceVersionError("incompatible_resource_version", reference)
        # Local resources have precedence at the selected version, then newest version.
        return deepcopy(max(eligible, key=lambda r: (r.source == "local", _version(r.version))))


STANDARD_RESOURCES = (
    AgentResource("research.prompt", "1.0.0", ResourceKind.PROMPT, "Answer with evidence and mark uncertainty."),
    AgentResource("research.task", "1.0.0", ResourceKind.TASK_MODE, {"mode": "research", "steps": ("collect", "verify", "summarize")}),
    AgentResource("research.validate", "1.0.0", ResourceKind.VALIDATOR, {"required": ("claim", "evidence")}),
    AgentResource("research.format", "1.0.0", ResourceKind.FORMATTER, {"format": "markdown", "sections": ("answer", "evidence")}),
    AgentResource("research.workflow", "1.0.0", ResourceKind.WORKFLOW_HELPER, {"workflow": "sequential-research"}),
)
