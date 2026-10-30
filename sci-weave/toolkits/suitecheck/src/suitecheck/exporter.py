"""Export a declarative suite into a project-scoped Harness input directory.

Three boundaries are enforced here, because each is a way an export can look
successful while being wrong:

* the project root is explicit — never the shell's current directory;
* the destination is a generated directory under ``.sciweave/harness/``;
* no secret value reaches the output. Only variable *names* travel, so
  ``configuration.md`` is guidance, not configuration.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Union

from .manifest import MANIFEST_NAME, ManifestError, load_manifest
from .secrets import ASSIGNMENT, BEARER, looks_like_secret_value
from .project_layout import ProjectRootRequired, initialize_project


class ExportError(RuntimeError):
    """The suite cannot be exported without crossing a safety boundary."""


@dataclass(frozen=True)
class ExportResult:
    output_dir: Path
    manifest_path: Path


#: Runtime artifacts that are never part of a suite's published surface.
_IGNORED = shutil.ignore_patterns(
    ".env*", ".venv", "venv", "__pycache__", "*.pyc", ".git", "*.sqlite", "*.sqlite3", "*.log", "sessions",
)

def _language_files(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield every decodable text file under ``root``; skip binaries quietly."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


def _secret_offenders(root: Path) -> list[str]:
    """Return files that contain what looks like a real credential value."""
    offenders: list[str] = []
    for path, text in _language_files(root):
        if path.name == "manifest.json":
            continue
        assignment = any(looks_like_secret_value(match.group("value")) for match in ASSIGNMENT.finditer(text))
        if assignment or BEARER.search(text):
            offenders.append(str(path.relative_to(root)))
    return sorted(set(offenders))


def _safe_relative(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ExportError(f"refusing path outside suite: {relative}")
    source = (root / candidate).resolve()
    try:
        source.relative_to(root.resolve())
    except ValueError as error:
        raise ExportError(f"refusing path outside suite: {relative}") from error
    if not source.exists():
        raise ExportError(f"declared export path is missing: {relative}")
    return source


def _copy(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True, ignore=_IGNORED)
        return
    if _IGNORED(str(source.parent), [source.name]):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _previous(output: Path) -> Path:
    return output.with_name(f".{output.name}.previous")


def _recover(output: Path) -> None:
    """Restore a directory left behind by an interrupted refresh."""
    backup = _previous(output)
    if backup.is_dir() and not output.exists():
        backup.rename(output)
    elif backup.exists():
        shutil.rmtree(backup, ignore_errors=True)


def _refresh(staging: Path, output: Path) -> None:
    """Swap the generated directory in, keeping the old one until the swap wins."""
    _recover(output)
    backup: Path | None = None
    if output.exists():
        backup = _previous(output)
        output.rename(backup)
    try:
        staging.replace(output)
    except OSError:
        if backup is not None and not output.exists():
            backup.rename(output)
        raise
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)


def export_suite(suite_root: Union[Path, str], project_root: Union[Path, str, None]) -> ExportResult:
    """Copy ``suite_root`` into ``<project>/.sciweave/harness/<suite-id>/``."""
    if project_root is None or not str(project_root).strip():
        raise ProjectRootRequired("an explicit Harness project root is required")
    try:
        suite = load_manifest(suite_root)
    except ManifestError as error:
        raise ExportError(str(error)) from error
    if suite.export is None:
        raise ExportError(f"{suite.suite} does not declare export rules")

    layout = initialize_project(project_root)
    output = (layout.root / suite.export.harness_input).resolve()
    try:
        output.relative_to(layout.harness.resolve())
    except ValueError as error:
        raise ExportError("harness input must stay under .sciweave/harness") from error

    staging_parent = layout.sciweave / ".export-staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f"{suite.suite}-", dir=staging_parent))
    try:
        inputs: list[str] = []
        for relative in (MANIFEST_NAME, *suite.export.include, suite.export.configuration):
            if relative in suite.export.exclude:
                continue
            _copy(_safe_relative(suite.root, relative), staging / relative)
            inputs.append(Path(relative).as_posix())
        offenders = _secret_offenders(staging)
        if offenders:
            raise ExportError("export would carry a secret value; refusing to write Harness input: " + ", ".join(offenders))
        manifest = {
            "schema_version": 1,
            "suite": suite.suite,
            "version": suite.version,
            "role": suite.role,
            "actor": suite.effective_actor,
            "inputs": sorted(set(inputs)),
            "capabilities": [
                {
                    "name": item.name,
                    "platforms": {
                        platform: {"status": support.status, "limitations": list(support.limitations)}
                        for platform, support in item.platforms.items()
                    },
                }
                for item in suite.capabilities
            ],
            "environment": [
                {"name": item.name, "purpose": item.purpose, "required": item.required}
                for item in suite.env
            ],
            "configuration": suite.export.configuration,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _refresh(staging, output)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if staging_parent.exists() and not any(staging_parent.iterdir()):
            staging_parent.rmdir()
    return ExportResult(output, output / "manifest.json")


__all__ = ["ExportError", "ExportResult", "export_suite"]
