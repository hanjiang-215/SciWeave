"""Check a manifest against the tree it describes.

Every finding carries a stable code so a caller can assert on it. The point is
not "is the YAML well-formed" — `manifest.load_manifest` already refuses a bad
file — but "does the payload exist, parse, and stay inside the capability
ceiling the suite claims". Those are the three ways a suite can look complete
and hand the installing Agent nothing usable.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .manifest import (
    CAPABILITIES,
    HOOK_EVENTS,
    ManifestError,
    SuiteManifest,
    load_manifest,
)


@dataclass(frozen=True)
class Severity:
    """Two levels, because only one of them should fail a release."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    subject: str
    detail: str

    def render(self) -> str:
        return f"{self.severity:<7} {self.code:<28} {self.subject}: {self.detail}"


def _error(code: str, subject: str, detail: str) -> Finding:
    return Finding(Severity.ERROR, code, subject, detail)


def _warn(code: str, subject: str, detail: str) -> Finding:
    return Finding(Severity.WARNING, code, subject, detail)


def _skill_findings(suite: SuiteManifest) -> list[Finding]:
    findings: list[Finding] = []
    seen: dict[str, str] = {}
    seen_names: dict[str, str] = {}
    for skill in suite.skills:
        directory = suite.root / skill.path
        manifest_path = directory / "SKILL.md"
        if not manifest_path.is_file():
            findings.append(_error("skill_manifest_missing", skill.name, f"{skill.path}/SKILL.md does not exist"))
            continue
        text = manifest_path.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            findings.append(_error("skill_frontmatter_missing", skill.name, "SKILL.md must start with a --- frontmatter block"))
            continue
        parts = text.split("---")
        if len(parts) < 3:
            findings.append(_error("skill_frontmatter_missing", skill.name, "frontmatter block is not closed"))
            continue
        header = parts[1]
        declared = {}
        for line in header.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            declared[key.strip()] = value.strip()
        for key in ("name", "description"):
            if not declared.get(key):
                findings.append(_error("skill_frontmatter_incomplete", skill.name, f"frontmatter is missing {key}"))
        declared_name = declared.get("name")
        if declared_name in seen_names:
            findings.append(
                _error(
                    "skill_name_duplicate",
                    skill.name,
                    f"frontmatter name {declared_name!r} is also declared by {seen_names[declared_name]}",
                )
            )
        elif declared_name:
            seen_names[declared_name] = skill.path
        if skill.name in seen:
            findings.append(_error("skill_duplicate", skill.name, f"declared twice ({seen[skill.name]} and {skill.path})"))
        seen[skill.name] = skill.path
    return findings


def _mcp_findings(suite: SuiteManifest) -> list[Finding]:
    findings: list[Finding] = []
    ceiling = suite.capability_ceiling
    for card in suite.mcp:
        path = suite.root / card.card
        if not path.is_file():
            findings.append(_error("mcp_card_missing", card.name, f"{card.card} does not exist"))
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            findings.append(_error("mcp_card_invalid", card.name, f"{card.card}: {error}"))
            continue
        if not isinstance(payload, dict):
            findings.append(_error("mcp_card_invalid", card.name, f"{card.card} must be a JSON object"))
            continue
        declared_name = payload.get("name")
        if declared_name != card.name:
            findings.append(
                _error("mcp_name_mismatch", card.name, f"{card.card} declares name {declared_name!r}")
            )
        for key in ("transport", "tools"):
            if key not in payload:
                findings.append(_error("mcp_card_incomplete", card.name, f"{card.card} has no {key}"))
        transport = payload.get("transport")
        endpoint = payload.get("endpoint")
        if transport == "streamable-http" and not (isinstance(endpoint, dict) and endpoint.get("url_env")):
            findings.append(
                _error("mcp_card_incomplete", card.name, f"{card.card} is streamable-http but names no endpoint.url_env")
            )
        tools = payload.get("tools")
        if isinstance(tools, list):
            for tool in tools:
                if not isinstance(tool, dict) or not tool.get("name"):
                    findings.append(_error("mcp_card_incomplete", card.name, f"{card.card} has a tool without a name"))
                    break
            names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
            if len(names) != len(set(names)):
                findings.append(_error("mcp_duplicate_tool", card.name, f"{card.card} declares a tool twice"))

        for capability in card.capabilities:
            if capability not in CAPABILITIES:
                findings.append(
                    _error("capability_unknown", card.name, f"{capability!r} is not one of {', '.join(CAPABILITIES)}")
                )
            elif capability not in ceiling:
                findings.append(
                    _error(
                        "capability_over_ceiling",
                        card.name,
                        f"{capability!r} exceeds the {suite.effective_actor} ceiling "
                        f"({', '.join(sorted(ceiling))})",
                    )
                )
    return findings


def _hook_findings(suite: SuiteManifest) -> list[Finding]:
    findings: list[Finding] = []
    for hook in suite.hooks:
        path = suite.root / hook.path
        if not path.is_file():
            findings.append(_error("hook_missing", hook.name, f"{hook.path} does not exist"))
            continue
        mode = path.stat().st_mode
        if not mode & stat.S_IXUSR:
            findings.append(_error("hook_not_executable", hook.name, f"{hook.path} is not executable"))
        if path.suffix not in {".sh", ".py"}:
            findings.append(_warn("hook_unexpected_kind", hook.name, f"{hook.path} is not .sh or .py"))
        if hook.event not in HOOK_EVENTS:
            findings.append(_error("hook_event_unknown", hook.name, hook.event))
    return findings


def _cron_findings(suite: SuiteManifest) -> list[Finding]:
    findings: list[Finding] = []
    for unit in suite.cron:
        path = suite.root / unit.path
        if not path.is_file():
            findings.append(_error("cron_missing", unit.name, f"{unit.path} does not exist"))
            continue
        if not unit.schedule.strip():
            findings.append(_error("cron_schedule_empty", unit.name, unit.path))
    return findings


def _command_findings(suite: SuiteManifest) -> list[Finding]:
    """An install/check command must at least name a program to run.

    `suitecheck` never executes these; `suitecheck run` does, explicitly. A
    manifest with an empty command list is a suite nobody can install, which is
    exactly the state `docs/AI4Sci-review-2026-10-22.md` recorded for all four
    toolkits.
    """
    findings: list[Finding] = []
    if not suite.install:
        findings.append(_error("install_commands_missing", suite.suite, "no install command is declared"))
    if not suite.check:
        findings.append(_error("check_commands_missing", suite.suite, "no check command is declared"))
    for label, commands in (("install", suite.install), ("check", suite.check)):
        for command in commands:
            if not command.strip():
                findings.append(_error("command_empty", suite.suite, f"{label}: empty command"))
            elif not command.split()[0].strip():
                findings.append(_error("command_empty", suite.suite, f"{label}: {command!r} has no program"))
    return findings


_SECRET_VALUE = re.compile(
    r"(?i)(?:^|\s)(?:[A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|CREDENTIAL)[A-Z0-9_]*)\s*=\s*\S+"
)


def _configuration_findings(suite: SuiteManifest) -> list[Finding]:
    if suite.export is None:
        return []
    findings: list[Finding] = []
    path = suite.root / suite.export.configuration
    if not path.is_file():
        findings.append(_error("configuration_missing", suite.suite, f"{path.name} does not exist"))
        return findings
    text = path.read_text(encoding="utf-8", errors="replace")
    if _SECRET_VALUE.search(text) or re.search(r"(?i)bearer\s+[A-Za-z0-9._~-]{8,}", text):
        findings.append(_error("configuration_secret_value", suite.suite, "configuration guidance must contain names, not secret values"))
    declared = {item.name: item for item in suite.env}
    for name in re.findall(r"(?m)^\s*[-*]?\s*`?([A-Z][A-Z0-9_]*)`?", text):
        if name not in declared and name.endswith(("TOKEN", "SECRET", "PASSWORD", "KEY")):
            findings.append(_error("configuration_undeclared_secret", name, "secret-like variable is not declared in suite.requires.env"))
    return findings


def _manifest_findings(suite: SuiteManifest) -> list[Finding]:
    findings: list[Finding] = []
    for capability in suite.capabilities:
        if not hasattr(capability, "platforms"):
            continue
        if "windows" not in capability.platforms:
            findings.append(_error("windows_status_missing", capability.name, "each capability must declare Windows status"))
    names: dict[str, tuple[str, bool]] = {}
    for item in suite.env:
        previous = names.get(item.name)
        current = (item.purpose, item.required)
        if previous is not None and previous != current:
            findings.append(_error("env_requirement_conflict", item.name, "environment variable has conflicting requirements"))
        names[item.name] = current
    return findings


def _boundary_findings(suite: SuiteManifest) -> list[Finding]:
    findings: list[Finding] = []
    if not suite.boundary.get("may_modify"):
        findings.append(_error("boundary_missing", suite.suite, "boundary.may_modify is empty"))
    if not suite.boundary.get("must_not"):
        findings.append(_error("boundary_missing", suite.suite, "boundary.must_not is empty"))
    for label, value in os.environ.items():
        if label in suite.requires.get("env", ()) and value and "://" in value:
            findings.append(
                _warn("env_looks_like_secret", suite.suite, f"{label} is set in this environment; manifests must not carry values")
            )
    return findings


def validate_suite(suite_or_path: SuiteManifest | Path | str) -> list[Finding]:
    """Every finding for one suite, most severe first per section order."""
    suite = suite_or_path if isinstance(suite_or_path, SuiteManifest) else load_manifest(suite_or_path)
    findings: list[Finding] = []
    findings.extend(_boundary_findings(suite))
    findings.extend(_manifest_findings(suite))
    findings.extend(_configuration_findings(suite))
    findings.extend(_skill_findings(suite))
    findings.extend(_mcp_findings(suite))
    findings.extend(_hook_findings(suite))
    findings.extend(_cron_findings(suite))
    findings.extend(_command_findings(suite))
    if not suite.skills and not suite.mcp:
        # A suite may legitimately declare no cards: a suite that only installs
        # configuration for a service whose MCP clients live in that service's
        # own source has no card inside its tree to point at (the retired
        # `centre-agent-toolkit` was one, ai4-349h / ai4-0wg0). What stays an
        # error is a manifest that declares no payload at all — that is the
        # shape this check exists for.
        findings.append(_error("suite_empty", suite.suite, "declares neither skills nor MCP cards"))
    return findings


def duplicate_skills(suites: Iterable[SuiteManifest]) -> list[Finding]:
    """Skill names that two suites both declare.

    Checked across suites rather than inside one, because that is the failure
    that actually bites: a researcher installs their own suite and the Project
    Owner's into one harness, and the second silently overrides the first
    (`fast_agent` merges manifests by name and keeps the later one). Naming
    every skill after its suite is one way to avoid it; this check is what makes
    the guarantee hold for a suite someone else wrote.
    """
    findings: list[Finding] = []
    owners: dict[str, str] = {}
    for suite in suites:
        for skill in suite.skills:
            manifest_path = suite.root / skill.path / "SKILL.md"
            if not manifest_path.is_file():
                continue
            text = manifest_path.read_text(encoding="utf-8", errors="replace")
            declared = ""
            for line in text.split("---")[1].splitlines() if text.startswith("---") else ():
                key, _, value = line.partition(":")
                if key.strip() == "name":
                    declared = value.strip()
                    break
            if not declared:
                continue
            prior = owners.get(declared)
            if prior is not None and prior != suite.suite:
                findings.append(
                    _error("skill_name_shared_between_suites", declared, f"declared by both {prior} and {suite.suite}")
                )
            owners.setdefault(declared, suite.suite)
    return findings


def find_suites(root: Path | str) -> list[Path]:
    """Every `suite.yaml` under *root*, one level deep enough for this repo."""
    base = Path(root)
    return sorted(path.parent for path in base.glob("*/suite.yaml"))


def errors(findings: Iterable[Finding]) -> list[Finding]:
    return [finding for finding in findings if finding.severity == Severity.ERROR]


__all__ = [
    "Finding",
    "Severity",
    "ManifestError",
    "validate_suite",
    "duplicate_skills",
    "find_suites",
    "errors",
]
