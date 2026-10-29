"""Export a declarative suite into a project-scoped Harness input directory."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from .manifest import MANIFEST_NAME, ManifestError, load_manifest
from .project_layout import ProjectRootRequired, initialize_project


class ExportError(RuntimeError):
    """The suite cannot be exported without crossing a safety boundary."""


@dataclass(frozen=True)
class ExportResult:
    output_dir: Path
    manifest_path: Path


_SKIP_NAMES = {".env", ".venv", "__pycache__", ".git"}
_SKIP_DIR_NAMES = {".venv", "__pycache__", ".git", "tests"}
_SECRET_MARKERS = ("TOKEN=", "SECRET=", "PASSWORD=", "API_KEY=", "PASSWD=")


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


def _copy_tree(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(
            source,
            destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".env", ".env.example", ".venv", "__pycache__", "tests", "*.sqlite", "*.sqlite3", "*.log"),
        )
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def export_suite(suite_root: Union[Path, str], project_root: Union[Path, str, None]) -> ExportResult:
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
            if relative in suite.export.exclude or Path(relative).name in _SKIP_NAMES:
                continue
            source = _safe_relative(suite.root, relative)
            destination = staging / relative
            _copy_tree(source, destination)
            inputs.append(relative.replace(os.sep, "/"))
        for leaked in staging.rglob(".env"):
            leaked.unlink()
        rendered_files = [
            path for path in staging.rglob("*")
            if path.is_file() and path.name != "manifest.json" and path.suffix not in {".example", ".md"}
        ]
        rendered = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in rendered_files)
        if any(marker in rendered for marker in _SECRET_MARKERS):
            offenders = [str(path.relative_to(staging)) for path in rendered_files if any(marker in path.read_text(encoding="utf-8", errors="replace") for marker in _SECRET_MARKERS)]
            raise ExportError("export would include a secret assignment: " + ", ".join(offenders))
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
                if hasattr(item, "platforms")
            ],
            "environment": [
                {"name": item.name, "purpose": item.purpose, "required": item.required}
                for item in suite.env
            ],
            "configuration": suite.export.configuration,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if output.exists():
            shutil.rmtree(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        if staging_parent.exists() and not any(staging_parent.iterdir()):
            staging_parent.rmdir()
    return ExportResult(output, output / "manifest.json")


__all__ = ["ExportError", "ExportResult", "export_suite"]
