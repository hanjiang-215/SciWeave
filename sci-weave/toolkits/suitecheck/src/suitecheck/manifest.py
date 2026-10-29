"""The suite manifest: one YAML file that describes a whole deliverable.

Deliberately a *closed* schema. Every key below is read by
``suitecheck.validate``, and an unknown key is an error rather than a comment:
the failure mode this file exists to prevent is a manifest that reads well and
declares nothing the installer actually uses (the same defect `ai4-z3yq`
recorded for the runtime's three libs directories).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

MANIFEST_NAME = "suite.yaml"

#: The two halves of the 2x2 the suites are cut along: a *machine* suite is
#: installed by an Agent onto a host that runs it unattended; a *human* suite is
#: installed into an owner's own harness, where a person is in the loop.
ROLES = ("machine", "human")

#: Keys the validator understands. Anything else is `unknown_field`.
_TOP_LEVEL_KEYS = frozenset({
    "schema_version", "suite", "role", "actor", "title", "version", "summary", "boundary",
    "requires", "skills", "mcp", "hooks", "cron", "install", "check",
    "capabilities", "payloads", "export",
})
_SCHEMA_VERSION = 1
_PLATFORM_STATUSES = frozenset({"supported", "manual", "unsupported", "unverified"})
_RUNTIME_ROLES = frozenset({"runtime", "data", "service"})
_PAYLOAD_PATH_KEYS = frozenset({"path", "card"})
_EXPORT_KEYS = frozenset({"harness_input", "include", "exclude", "configuration"})
_ENV_ENTRY_KEYS = frozenset({"name", "purpose", "required"})
_CAPABILITY_ENTRY_KEYS = frozenset({"name", "platforms"})
_PLATFORM_KEYS = frozenset({"status", "limitations"})
_PAYLOAD_SECTIONS = frozenset({"skills", "mcp", "hooks", "cron", "runtime"})
_RUNTIME_ENTRY_KEYS = frozenset({"name", "path", "role"})
_REQUIRED_KEYS = ("suite", "role", "title", "version", "summary")
_BOUNDARY_KEYS = frozenset({"may_modify", "must_not"})
_REQUIRES_KEYS = frozenset({"env", "services"})

#: Capability tiers as the domain MCP services spell them (`_CAPABILITY_ORDER`
#: in research-mapping / llm_wiki). A suite's `mcp[].capabilities` list must use
#: these names so a reader can compare it with the server-side grants.
CAPABILITIES = (
    "read",
    "candidate_submit",
    "candidate_review",
    "formalize",
    "centre",
    "prereview_log",
    "merged_candidate",
)

#: What each role may be granted. This is the boundary the four suites exist to
#: make checkable, so it lives in code rather than in prose:
#:
#: * a machine-side Task Agent produces drafts; it must never be able to turn a
#:   candidate into a formal revision, and never to review one;
#: * a researcher (human + own harness) submits and promotes their own work but
#:   still cannot approve it;
#: * the Centre Agent pre-reviews and merges, and must never formalize;
#: * the Project Owner decides, and must not hold the `centre` tier (reading a
#:   domain *as the centre* would let it act on every candidate at once).
ROLE_CAPABILITIES: Mapping[str, frozenset[str]] = {
    "machine": frozenset({"read"}),
    "researcher": frozenset({"read", "candidate_submit"}),
    "centre": frozenset({"read", "centre", "prereview_log", "merged_candidate"}),
    "project_owner": frozenset({"read", "candidate_submit", "candidate_review", "formalize"}),
}

#: Role names the manifest may declare. `role` (machine|human) says *where* it
#: is installed; `actor` says *who* it acts as, and only the actor decides the
#: capability ceiling.
ACTORS = tuple(ROLE_CAPABILITIES)

HOOK_EVENTS = (
    "harness-open",
    "harness-close",
    "install-post",
    "worker-pre-start",
    "worker-pre-submit",
    "worker-post-run",
    "check-pre",
)


class ManifestError(ValueError):
    """A manifest cannot be read or is shaped wrongly."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"[{code}] {path}: {detail}")


@dataclass(frozen=True)
class SkillRef:
    name: str
    path: str


@dataclass(frozen=True)
class MCPRef:
    name: str
    card: str
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class HookRef:
    name: str
    path: str
    event: str


@dataclass(frozen=True)
class CronRef:
    name: str
    path: str
    schedule: str


@dataclass(frozen=True)
class EnvRequirement:
    name: str
    purpose: str
    required: bool


@dataclass(frozen=True)
class PlatformSupport:
    status: str
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class CapabilitySupport:
    name: str
    platforms: Mapping[str, PlatformSupport]


@dataclass(frozen=True)
class RuntimeRef:
    name: str
    path: str
    role: str


@dataclass(frozen=True)
class ExportRules:
    harness_input: str
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    configuration: str


@dataclass(frozen=True)
class SuiteManifest:
    schema_version: int
    suite: str
    role: str
    title: str
    version: str
    summary: str
    root: Path
    actor: str | None = None
    boundary: Mapping[str, Any] = field(default_factory=dict)
    requires: Mapping[str, Any] = field(default_factory=dict)
    env: tuple[EnvRequirement, ...] = ()
    capabilities: tuple[CapabilitySupport, ...] = ()
    payloads: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)
    export: ExportRules | None = None
    skills: tuple[SkillRef, ...] = ()
    mcp: tuple[MCPRef, ...] = ()
    hooks: tuple[HookRef, ...] = ()
    cron: tuple[CronRef, ...] = ()
    install: tuple[str, ...] = ()
    check: tuple[str, ...] = ()

    @property
    def effective_actor(self) -> str:
        """The actor whose capability ceiling applies.

        Defaults to the role name when `actor` is absent, so a manifest may
        omit the key; the two only differ for the machine side, where the
        installer role (`machine`) and the identity that calls MCP
        (`researcher`) are genuinely different.
        """
        return self.actor or ("researcher" if self.role == "machine" else self.role)

    @property
    def capability_ceiling(self) -> frozenset[str]:
        return ROLE_CAPABILITIES[self.effective_actor]


def _strings(value: Any, code: str, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ManifestError(code, path, "must be a list of strings")
    items = tuple(value)
    if not all(isinstance(item, str) and item.strip() for item in items):
        raise ManifestError(code, path, "must be a list of non-empty strings")
    return items


def _required_text(data: Mapping[str, Any], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"missing_{key}", f"{path}.{key}", "required non-empty string")
    return value.strip()


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ManifestError("invalid_shape", path, "must be an object")
    return value


def _closed(data: Mapping[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = sorted(set(map(str, data)) - allowed)
    if unknown:
        raise ManifestError("unknown_field", path, ", ".join(unknown))


def _relative_path(value: Any, path: str) -> str:
    text = _required_value_text(value, path)
    candidate = Path(text)
    if candidate.is_absolute() or "\\" in text or any(part in {"", ".", ".."} for part in text.split("/")):
        raise ManifestError("invalid_path", path, "must be a normalized relative path without traversal")
    return text


def _required_value_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError("invalid_value", path, "required non-empty string")
    return value.strip()


def _refs(items: Any, path: str, *, allow_empty: bool) -> list[Mapping[str, Any]]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise ManifestError("invalid_shape", path, "must be a list")
    if not allow_empty and not items:
        raise ManifestError("empty_section", path, "must declare at least one entry")
    if not all(isinstance(item, Mapping) for item in items):
        raise ManifestError("invalid_shape", path, "every entry must be an object")
    return list(items)


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ManifestError("invalid_value", path, "must be boolean")
    return value


def _env_requirements(value: Any, path: str) -> tuple[EnvRequirement, ...]:
    if value is None:
        return ()
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(EnvRequirement(item, "declared by the suite", True) for item in _strings(value, "invalid_env", path))
    entries = _refs(value, path, allow_empty=True)
    result: list[EnvRequirement] = []
    for index, item in enumerate(entries):
        label = f"{path}[{index}]"
        _closed(item, _ENV_ENTRY_KEYS, label)
        name = _required_value_text(item.get("name"), f"{label}.name")
        purpose = _required_value_text(item.get("purpose"), f"{label}.purpose")
        result.append(EnvRequirement(name, purpose, _bool(item.get("required"), f"{label}.required")))
    return tuple(result)


def _capability_support(value: Any, path: str, ceiling: frozenset[str]) -> tuple[CapabilitySupport, ...]:
    entries = _refs(value, path, allow_empty=True)
    result: list[CapabilitySupport] = []
    for index, item in enumerate(entries):
        label = f"{path}[{index}]"
        _closed(item, _CAPABILITY_ENTRY_KEYS, label)
        name = _required_value_text(item.get("name"), f"{label}.name")
        if name not in CAPABILITIES:
            raise ManifestError("capability_unknown", f"{label}.name", f"{name!r} is not supported")
        if name not in ceiling:
            raise ManifestError("capability_over_ceiling", f"{label}.name", f"{name!r} exceeds actor ceiling")
        platforms = item.get("platforms")
        if not isinstance(platforms, Mapping) or not platforms:
            raise ManifestError("invalid_platforms", f"{label}.platforms", "must be a non-empty object")
        support: dict[str, PlatformSupport] = {}
        for platform, raw in platforms.items():
            platform_label = f"{label}.platforms.{platform}"
            if not isinstance(platform, str) or not platform.strip():
                raise ManifestError("invalid_platform", platform_label, "platform name must be non-empty")
            details = _mapping(raw, platform_label)
            _closed(details, _PLATFORM_KEYS, platform_label)
            status = _required_value_text(details.get("status"), f"{platform_label}.status")
            if status not in _PLATFORM_STATUSES:
                raise ManifestError("invalid_platform_status", f"{platform_label}.status", f"must be one of {sorted(_PLATFORM_STATUSES)}")
            limitations = _strings(details.get("limitations"), "invalid_limitations", f"{platform_label}.limitations")
            if status in {"manual", "unsupported", "unverified"} and not limitations:
                raise ManifestError("platform_limitation_missing", platform_label, "non-supported status requires limitations")
            support[platform] = PlatformSupport(status, limitations)
        result.append(CapabilitySupport(name, support))
    return tuple(result)


def _payloads(value: Any, path: str) -> Mapping[str, tuple[Any, ...]]:
    if value is None:
        return {}
    data = _mapping(value, path)
    _closed(data, _PAYLOAD_SECTIONS, path)
    parsed: dict[str, tuple[Any, ...]] = {}
    for section in _PAYLOAD_SECTIONS:
        entries = _refs(data.get(section), f"{path}.{section}", allow_empty=True)
        refs: list[Any] = []
        for index, item in enumerate(entries):
            label = f"{path}.{section}[{index}]"
            allowed = _PAYLOAD_PATH_KEYS if section == "mcp" else frozenset({"name", "path"})
            if section == "runtime":
                allowed = _RUNTIME_ENTRY_KEYS
            _closed(item, allowed, label)
            name = _required_value_text(item.get("name"), f"{label}.name")
            resource_key = "card" if section == "mcp" else "path"
            resource = _relative_path(item.get(resource_key), f"{label}.{resource_key}")
            if section == "runtime":
                role = _required_value_text(item.get("role"), f"{label}.role")
                if role not in _RUNTIME_ROLES:
                    raise ManifestError("invalid_runtime_role", f"{label}.role", f"must be one of {sorted(_RUNTIME_ROLES)}")
                refs.append(RuntimeRef(name, resource, role))
            elif section == "mcp":
                refs.append(MCPRef(name, resource))
            else:
                refs.append((name, resource))
        parsed[section] = tuple(refs)
    return parsed


def _export_rules(value: Any, path: str) -> ExportRules | None:
    if value is None:
        return None
    data = _mapping(value, path)
    _closed(data, _EXPORT_KEYS, path)
    return ExportRules(
        _relative_path(data.get("harness_input"), f"{path}.harness_input"),
        _strings(data.get("include"), "invalid_include", f"{path}.include"),
        _strings(data.get("exclude"), "invalid_exclude", f"{path}.exclude"),
        _relative_path(data.get("configuration"), f"{path}.configuration"),
    )


def load_manifest(path: Path | str) -> SuiteManifest:
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / MANIFEST_NAME
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ManifestError("manifest_read_error", str(manifest_path), str(error)) from error
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise ManifestError("manifest_invalid_yaml", str(manifest_path), str(error)) from error
    if not isinstance(data, Mapping):
        raise ManifestError("invalid_shape", str(manifest_path), "must be a mapping")

    _closed(data, _TOP_LEVEL_KEYS, "suite")
    schema_version = data.get("schema_version", _SCHEMA_VERSION)
    if type(schema_version) is not int or schema_version != _SCHEMA_VERSION:
        raise ManifestError("unsupported_schema_version", "suite.schema_version", f"supported version is {_SCHEMA_VERSION}")
    for key in _REQUIRED_KEYS:
        _required_text(data, key, "suite")

    role = _required_text(data, "role", "suite")
    if role not in ROLES:
        raise ManifestError("invalid_role", "suite.role", f"must be one of {', '.join(ROLES)}")
    actor = data.get("actor")
    if actor is not None:
        if not isinstance(actor, str) or actor not in ACTORS:
            raise ManifestError("invalid_actor", "suite.actor", f"must be one of {', '.join(ACTORS)}")
        if role == "human" and actor == "machine":
            raise ManifestError("role_actor_mismatch", "suite.actor", "a human suite cannot act as a machine")

    boundary = _mapping(data.get("boundary"), "suite.boundary")
    _closed(boundary, _BOUNDARY_KEYS, "suite.boundary")
    for key in ("may_modify", "must_not"):
        _strings(boundary.get(key), f"invalid_{key}", f"suite.boundary.{key}")

    requires = _mapping(data.get("requires"), "suite.requires")
    _closed(requires, _REQUIRES_KEYS, "suite.requires")
    for key in ("env", "services"):
        if key == "env" and isinstance(requires.get(key), list) and any(isinstance(item, Mapping) for item in requires.get(key, ())):
            continue
        _strings(requires.get(key), f"invalid_{key}", f"suite.requires.{key}")
    env = _env_requirements(requires.get("env"), "suite.requires.env")

    capabilities = _capability_support(data.get("capabilities"), "suite.capabilities", ROLE_CAPABILITIES[actor or ("researcher" if role == "machine" else role)])
    payloads = _payloads(data.get("payloads"), "suite.payloads")
    export = _export_rules(data.get("export"), "suite.export")

    skills: list[SkillRef] = []
    for index, item in enumerate(_refs(data.get("skills"), "suite.skills", allow_empty=True)):
        path_label = f"suite.skills[{index}]"
        _closed(item, frozenset({"name", "path"}), path_label)
        skills.append(
            SkillRef(_required_text(item, "name", path_label), _relative_path(item.get("path"), f"{path_label}.path"))
        )

    mcp: list[MCPRef] = []
    for index, item in enumerate(_refs(data.get("mcp"), "suite.mcp", allow_empty=True)):
        path_label = f"suite.mcp[{index}]"
        _closed(item, frozenset({"name", "card", "capabilities"}), path_label)
        capabilities = _strings(item.get("capabilities"), "invalid_capabilities", f"{path_label}.capabilities")
        mcp.append(
            MCPRef(
                _required_text(item, "name", path_label),
                _relative_path(item.get("card"), f"{path_label}.card"),
                capabilities,
            )
        )

    hooks: list[HookRef] = []
    for index, item in enumerate(_refs(data.get("hooks"), "suite.hooks", allow_empty=True)):
        path_label = f"suite.hooks[{index}]"
        _closed(item, frozenset({"name", "path", "event"}), path_label)
        event = _required_text(item, "event", path_label)
        if event not in HOOK_EVENTS:
            raise ManifestError("invalid_hook_event", f"{path_label}.event", f"must be one of {', '.join(HOOK_EVENTS)}")
        hooks.append(HookRef(_required_text(item, "name", path_label), _required_text(item, "path", path_label), event))

    cron: list[CronRef] = []
    for index, item in enumerate(_refs(data.get("cron"), "suite.cron", allow_empty=True)):
        path_label = f"suite.cron[{index}]"
        _closed(item, frozenset({"name", "path", "schedule"}), path_label)
        cron.append(
            CronRef(
                _required_text(item, "name", path_label),
                _required_text(item, "path", path_label),
                _required_text(item, "schedule", path_label),
            )
        )

    install = _strings(data.get("install"), "invalid_install", "suite.install")
    check = _strings(data.get("check"), "invalid_check", "suite.check")

    return SuiteManifest(
        schema_version=schema_version,
        suite=_required_text(data, "suite", "suite"),
        role=role,
        title=_required_text(data, "title", "suite"),
        version=_required_text(data, "version", "suite"),
        summary=" ".join(_required_text(data, "summary", "suite").split()),
        root=manifest_path.parent,
        actor=actor,
        boundary=boundary,
        requires=requires,
        env=env,
        capabilities=capabilities,
        payloads=payloads,
        export=export,
        skills=tuple(skills),
        mcp=tuple(mcp),
        hooks=tuple(hooks),
        cron=tuple(cron),
        install=install,
        check=check,
    )
