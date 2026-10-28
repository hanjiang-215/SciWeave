"""Where the worker's skills come from (ai4-4r0h follow-up).

The kit could always hand an agent MCP servers and an instruction, but never a
skill: `fast_agent`'s ``skills=`` parameter was simply not passed, so the agent
config kept its ``SKILLS_DEFAULT`` sentinel and every ``SKILL.md`` in the kit was
documentation.

Two variables, both explicit, and no third fallback:

``SCIWEAVE_SKILLS_PATH``
    One or more directories holding ``<skill>/SKILL.md``, separated by
    ``os.pathsep`` — the same shape as ``PATH``, so one variable can name the
    shipped skills and a shared team directory.

``LOCAL_SKILLS_PATH``
    The researcher's own directory, loaded after the shipped one so a local
    ``SKILL.md`` with the same name wins.

**Neither falls back to anything.** `fast_agent` will happily scan
``~/.fast-agent/skills`` on its own when nothing is passed; the boundary spec
(`docs/superpowers/specs/2026-10-23-agent-suite-boundary-design.md`) forbids
that, because a worker running unattended on a researcher's machine must not
pick up whatever skills happen to be lying in a home directory.

The kit's own ``deploy-task-agent-skills/`` is deliberately *not* a fallback
either. Those skills teach a personal Agent how to deploy and configure the
kit; handing them to the worker's own model loop would tell an unattended agent
to edit the very installation it is running from. A worker with no declared
directory runs with no skills, which is a legitimate configuration.

A *set* variable pointing at a missing directory is an error. That is the
distinction that matters: unset is a decision, wrong is a mistake.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SHIPPED_VARIABLE = "SCIWEAVE_SKILLS_PATH"
LOCAL_VARIABLE = "LOCAL_SKILLS_PATH"

#: The file a real skill directory must contain. fast-agent only descends one
#: level, so `<root>/<skill>/SKILL.md` is the only layout it recognises.
MANIFEST_FILENAME = "SKILL.md"


class SkillsConfigError(ValueError):
    """A declared skills directory cannot be used."""

    def __init__(self, code: str, variable: str, path: str, detail: str) -> None:
        self.code = code
        self.variable = variable
        self.path = path
        self.detail = detail
        super().__init__(f"[{code}] {variable} ({path}): {detail}")


@dataclass(frozen=True)
class SkillsConfig:
    """The directories to load, in order, plus where each came from."""

    directories: tuple[Path, ...] = ()
    sources: tuple[tuple[str, Path], ...] = ()

    def __bool__(self) -> bool:
        return bool(self.directories)

    def __len__(self) -> int:
        return len(self.directories)


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(os.pathsep) if part.strip()]


def _checked(variable: str, path: Path) -> Path:
    """A declared directory must exist, be a directory, and hold a manifest.

    The last check is what catches the common mistake: pointing the variable at
    the *skill* directory instead of its parent. fast-agent would then find no
    ``<child>/SKILL.md`` and load zero skills without complaint.
    """
    if not path.exists():
        raise SkillsConfigError(
            "skills_directory_missing",
            variable,
            str(path),
            "does not exist; point the variable at a directory of skills "
            f"(each with a {MANIFEST_FILENAME} inside)",
        )
    if not path.is_dir():
        raise SkillsConfigError("skills_directory_not_a_directory", variable, str(path), "is not a directory")
    if (path / MANIFEST_FILENAME).is_file():
        raise SkillsConfigError(
            "skills_directory_is_a_skill",
            variable,
            str(path),
            f"is itself a skill; declare its parent so {MANIFEST_FILENAME} is found one level down",
        )
    if not any((child / MANIFEST_FILENAME).is_file() for child in path.iterdir() if child.is_dir()):
        raise SkillsConfigError(
            "skills_directory_empty",
            variable,
            str(path),
            f"holds no child directory with a {MANIFEST_FILENAME}",
        )
    return path


def load_skills(environ: dict[str, str] | None = None) -> SkillsConfig:
    """Resolve the skills directories; empty when nothing is declared.

    Raises `SkillsConfigError` for a declared-but-unusable directory. Never
    raises for an unset variable: no skills is a valid worker.
    """
    env = os.environ if environ is None else environ
    directories: list[Path] = []
    sources: list[tuple[str, Path]] = []
    for variable in (SHIPPED_VARIABLE, LOCAL_VARIABLE):
        for raw in _split((env.get(variable) or "").strip()):
            path = _checked(variable, Path(raw).expanduser())
            if path in directories:
                # Declaring the same directory twice would load every skill
                # twice; fast-agent merges by name and warns, but the manifest
                # is the place to fix it.
                continue
            directories.append(path)
            sources.append((variable, path))
    return SkillsConfig(tuple(directories), tuple(sources))


__all__ = [
    "MANIFEST_FILENAME",
    "LOCAL_VARIABLE",
    "SHIPPED_VARIABLE",
    "SkillsConfig",
    "SkillsConfigError",
    "load_skills",
]
