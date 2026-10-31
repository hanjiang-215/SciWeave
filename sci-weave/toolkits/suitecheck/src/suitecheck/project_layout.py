"""Project-scoped SciWeave directory layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union


class ProjectRootRequired(ValueError):
    """Raised when a caller has not supplied an explicit project root."""


@dataclass(frozen=True)
class ProjectLayout:
    root: Path
    sciweave: Path
    harness: Path
    runtime: Path
    data: Path
    project: Path
    env: Path
    gitignore: Path


def initialize_project(root: Union[Path, str, None]) -> ProjectLayout:
    if root is None or not str(root).strip():
        raise ProjectRootRequired("an explicit Harness project root is required")
    project_root = Path(root).expanduser().resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    sciweave = project_root / ".sciweave"
    directories = {
        "harness": sciweave / "harness",
        "runtime": sciweave / "runtime",
        "data": sciweave / "data",
        "project": sciweave / "project",
    }
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    env = sciweave / ".env"
    gitignore = sciweave / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            """# Generated Harness inputs and runtime code\n/harness/\n/runtime/\n\n# Project-instance state and secrets\n/data/\n/.env\n*.sqlite3\n*.sqlite\n*.log\n/services/\n\n# User definitions are shareable by explicit path, not blanket-ignored\n!/project/\n!/project/**/*.yaml\n!/project/**/*.yml\n!/project/**/*.json\n!/project/**/*.md\n""",
            encoding="utf-8",
        )
    return ProjectLayout(project_root, sciweave, directories["harness"], directories["runtime"], directories["data"], directories["project"], env, gitignore)


__all__ = ["ProjectLayout", "ProjectRootRequired", "initialize_project"]
